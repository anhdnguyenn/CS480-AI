"""Statistical Language Processing tools.  (Chapter 23)
We define Unigram and Ngram text models, use them to generate random text,
and show the Viterbi algorithm for segmentatioon of letters into words.
Then we show a very simple Information Retrieval system, and an example
working on a tiny sample of Unix manual pages."""

from utils import *
from math import log, exp
import re, probability, string, search

class CountingProbDist(probability.ProbDist):
    """A probability distribution formed by observing and counting examples. 
    If P is an instance of this class and o
    is an observed value, then there are 3 main operations:
    p.add(o) increments the count for observation o by 1.
    p.sample() returns a random element from the distribution.
    p[o] returns the probability for o (as in a regular ProbDist)."""

    def __init__(self, observations=[], default=0):
        """Create a distribution, and optionally add in some observations.
        By default this is an unsmoothed distribution, but saying default=1,
        for example, gives you add-one smoothing."""
        update(self, dictionary=DefaultDict(default), needs_recompute=False,
               table=[], n_obs=0)
        for o in observations:
            self.add(o)
        
    def add(self, o):
        """Add an observation o to the distribution."""
        self.dictionary[o] += 1
        self.n_obs += 1
        self.needs_recompute = True

    def sample(self):
        """Return a random sample from the distribution."""
        if self.needs_recompute: self._recompute()
        if self.n_obs == 0:
            return None
        i = bisect.bisect_left(self.table, (1 + random.randrange(self.n_obs),))
        (count, o) = self.table[i]
        return o

    def __getitem__(self, item):
        """Return an estimate of the probability of item."""
        if self.needs_recompute: self._recompute()
        return self.dictionary[item] / self.n_obs

    def __len__(self):
        if self.needs_recompute: self._recompute()
        return self.n_obs

    def top(self, n):
        "Return (count, obs) tuples for the n most frequent observations."
        items = [(v, k) for (k, v) in self.dictionary.items()]
        items.sort(); items.reverse()
        return items[0:n]

    def _recompute(self):
        """Recompute the total count n_obs and the table of entries."""
        n_obs = 0
        table = []
        for (o, count) in self.dictionary.items():
            n_obs += count
            table.append((n_obs, o))
        update(self, n_obs=float(n_obs), table=table, needs_recompute=False)

#______________________________________________________________________________

class UnigramTextModel(CountingProbDist):
    """This is a discrete probability distribution over words, so you
    can add, sample, or get P[word], just like with CountingProbDist.  You can
    also generate a random text n words long with P.samples(n)"""

    def samples(self, n):
        "Return a string of n words, random according to the model."
        return ' '.join([self.sample() for i in range(n)])

class NgramTextModel(CountingProbDist):
    """This is a discrete probability distribution over n-tuples of words.
    You can add, sample or get P[(word1, ..., wordn)]. The method P.samples(n)
    builds up an n-word sequence; P.add_text and P.add_sequence add data."""

    def __init__(self, n, observation_sequence=[]):
        ## In addition to the dictionary of n-tuples, cond_prob is a
        ## mapping from (w1, ..., wn-1) to P(wn | w1, ... wn-1)
        CountingProbDist.__init__(self)
        self.n = n
        self.cond_prob = DefaultDict(CountingProbDist()) 
        self.add_sequence(observation_sequence)

    ## sample, __len__, __getitem__ inherited from CountingProbDist
    ## Note they deal with tuples, not strings, as inputs

    def add(self, ngram):
        """Count 1 for P[(w1, ..., wn)] and for P(wn | (w1, ..., wn-1)"""
        CountingProbDist.add(self, ngram)        
        self.cond_prob[ngram[:-1]].add(ngram[-1])
        
    def add_sequence(self, words):
        """Add each of the tuple words[i:i+n], using a sliding window.
        Prefix some copies of the empty word, '', to make the start work."""
        n = self.n
        words = ['',] * (n-1) + words
        for i in range(len(words)-n):
            self.add(tuple(words[i:i+n]))

    def samples(self, nwords):
        """Build up a random sample of text n words long, using the"""
        n = self.n
        nminus1gram = ('',) * (n-1)
        output = []
        while len(output) < nwords:
            wn = self.cond_prob[nminus1gram].sample()
            if wn:
                output.append(wn)
                nminus1gram = nminus1gram[1:] + (wn,)
            else: ## Cannot continue, so restart.
                nminus1gram = ('',) * (n-1)
        return ' '.join(output)
    
#______________________________________________________________________________


def viterbi_segment(text, P):
    """Find the best segmentation of the string of characters, given the 
    UnigramTextModel P."""
    # best[i] = best probability for text[0:i]
    # words[i] = best word ending at position i
    n = len(text)
    words = [''] + list(text)
    best = [1.0] + [0.0] * n
    ## Fill in the vectors best, words via dynamic programming
    for i in range(n+1):
        for j in range(0, i):
            w = text[j:i]
            if P[w] * best[i - len(w)] >= best[i]:
                best[i] = P[w] * best[i - len(w)]
                words[i] = w
    ## Now recover the sequence of best words
    sequence = []; i = len(words)-1
    while i > 0:
        sequence[0:0] = [words[i]]
        i = i - len(words[i])
    ## Return sequence of best words and overall probability
    return sequence, best[-1]
    

#______________________________________________________________________________


class IRSystem:
    """A very simple Information Retrieval System, as discussed in Sect. 23.2.
    The constructor s = IRSystem('the a') builds an empty system with two 
    stopwords. Next, index several documents with s.index_document(text, url).
    Then ask queries with s.query('query words', n) to retrieve the top n 
    matching documents.  Queries are literal words from the document,
    except that stopwords are ignored, and there is one special syntax:
    The query "learn: man cat", for example, runs "man cat" and indexes it."""

    def __init__(self, stopwords='the a of'):
        """Create an IR System. Optionally specify stopwords."""
        ## index is a map of {word: {docid: count}}, where docid is an int,
        ## indicating the index into the documents list.
        update(self, index=DefaultDict(DefaultDict(0)), 
               stopwords=set(words(stopwords)), documents=[])

    def index_collection(self, filenames):
        "Index a whole collection of files."
        for filename in filenames:
            self.index_document(open(filename).read(), filename)

    def index_document(self, text, url):
        "Index the text of a document."
        ## For now, use first line for title
        title = text[:text.index('\n')].strip()
        docwords = words(text)
        docid = len(self.documents)
        self.documents.append(Document(title, url, len(docwords)))
        for word in docwords:
            if word not in self.stopwords:
                self.index[word][docid] += 1

    def query(self, query_text, n=10):
        """Return a list of n (score, docid) pairs for the best matches.
        Also handle the special syntax for 'learn: command'."""
        if query_text.startswith("learn:"):
            doctext = os.popen(query_text[len("learn:"):], 'r').read()
            self.index_document(doctext, query_text)
            return []
        qwords = [w for w in words(query_text) if w not in self.stopwords]
        shortest = argmin(qwords, lambda w: len(self.index[w]))
        docs = self.index[shortest]
        results = [(sum([self.score(w, d) for w in qwords]), d) for d in docs]
        results.sort(); results.reverse()
        return results[:n]

    def score(self, word, docid):
        "Compute a score for this word on this docid."
        ## There are many options; here we take a very simple approach
        return (math.log(1 + self.index[word][docid])
                / math.log(1 + self.documents[docid].nwords))

    def present(self, results):
        "Present the results as a list."
        for (score, d) in results:
            doc = self.documents[d]
            print "%5.2f|%25s | %s" % (100 * score, doc.url, doc.title[:45])

    def present_results(self, query_text, n=10):
        "Get results for the query and present them."
        self.present(self.query(query_text, n))

class UnixConsultant(IRSystem):
    """A trivial IR system over a small collection of Unix man pages."""
    def __init__(self):
        IRSystem.__init__(self, stopwords="how do i the a of")
        import os
        mandir = '../data/MAN/'
        man_files = [mandir + f for f in os.listdir(mandir)
		     if f.endswith('.txt')]
        self.index_collection(man_files)

class Document:
    """Metadata for a document: title and url; maybe add others later."""
    def __init__(self, title, url, nwords):
        update(self, title=title, url=url, nwords=nwords)

def words(text, reg=re.compile('[a-z0-9]+')):
    """Return a list of the words in text, ignoring punctuation and
    converting everything to lowercase (to canonicalize).
    >>> words("``EGAD!'' Edgar cried.")
    ['egad', 'edgar', 'cried']
    """
    return reg.findall(text.lower())

def canonicalize(text):
    """Return a canonical text: only lowercase letters and blanks.
    >>> canonicalize("``EGAD!'' Edgar cried.")
    'egad edgar cried'
    """
    return ' '.join(words(text))


#______________________________________________________________________________

## Example application (not in book): decode a cipher.  
## A cipher is a code that substitutes one character for another.
## A shift cipher is a rotation of the letters in the alphabet,
## such as the famous rot13, which maps A to N, B to M, etc.

#### Encoding 

def shift_encode(plaintext, n):
    """Encode text with a shift cipher that moves each letter up by n letters.
    >>> shift_encode('abc z', 1)
    'bcd a'
    """
    return encode(plaintext, alphabet[n:] + alphabet[:n])
    
def rot13(plaintext):
    """Encode text by rotating letters by 13 spaces in the alphabet.
    >>> rot13('hello')
    'uryyb'
    >>> rot13(rot13('hello'))
    'hello'
    """
    return shift_encode(plaintext, 13)

def encode(plaintext, code):
    "Encodes text, using a code which is a permutation of the alphabet."
    from string import maketrans
    trans = maketrans(alphabet + alphabet.upper(), code + code.upper())
    return plaintext.translate(trans)

alphabet = 'abcdefghijklmnopqrstuvwxyz'  
    
def bigrams(text):
    """Return a list of pairs in text (a sequence of letters or words).
    >>> bigrams('this')
    ['th', 'hi', 'is']
    >>> bigrams(['this', 'is', 'a', 'test'])
    [['this', 'is'], ['is', 'a'], ['a', 'test']]
    """
    return [text[i:i+2] for i in range(len(text) - 1)]

#### Decoding a Shift (or Caesar) Cipher

class ShiftDecoder:
    """There are only 26 possible encodings, so we can try all of them,
    and return the one with the highest probability, according to a 
    bigram probability distribution."""
    def __init__(self, training_text):
        training_text = canonicalize(training_text)
        self.P2 = CountingProbDist(bigrams(training_text), default=1)

    def score(self, plaintext):
        "Return a score for text based on how common letters pairs are."
        s = 1.0
        for bi in bigrams(plaintext):
            s = s * self.P2[bi]
        return s
    
    def decode(self, ciphertext):
        "Return the shift decoding of text with the best score."
        return argmax(all_shifts(ciphertext), self.score)

def all_shifts(text):
    "Return a list of all 26 possible encodings of text by a shift cipher."
    return [shift_encode(text, n) for n in range(len(alphabet))]

#### Decoding a General Permutation Cipher

class PermutationDecoder:
    """This is a much harder problem than the shift decoder.  There are 26!
    permutations, so we can't try them all.  Instead we have to search.
    We want to search well, but there are many things to consider:
    Unigram probabilities (E is the most common letter); Bigram probabilities
    (TH is the most common bigram); word probabilities (I and A are the most
    common one-letter words, etc.); etc.
      We could represent a search state as a permutation of the 26 letters,
    and alter the solution through hill climbing.  With an initial guess
    based on unigram probabilities, this would probably fair well. However,
    I chose instead to have an incremental representation. A state is 
    represented as a letter-to-letter map; for example {'z': 'e'} to
    represent that 'z' will be translated to 'e'
    """
    def __init__(self, training_text, ciphertext=None):
        self.Pwords = UnigramTextModel(words(training_text))
        self.P1 = UnigramTextModel(training_text) # By letter
        self.P2 = NgramTextModel(2, training_text) # By letter pair
        if ciphertext:
            return self.decode(ciphertext)

    def decode(self, ciphertext):
        "Search for a decoding of the ciphertext."
        self.ciphertext = ciphertext
        problem = PermutationDecoderProblem(decoder=self)
        return search.best_first_tree_search(problem, self.score)

    def score(self, ciphertext, code):
        """Score is product of word scores, unigram scores, and bigram scores.
        This can get very small, so we use logs and exp."""
        text = decode(ciphertext, code)
        logP = (sum([log(self.Pwords[word]) for word in words(text)]) +
                sum([log(self.P1[c]) for c in text]) +
                sum([log(self.P2[b]) for b in bigrams(text)]))
        return exp(logP)

class PermutationDecoderProblem(search.Problem):
    def __init__(self, initial=None, goal=None, decoder=None):
        self.initial = initial or {}
        self.decoder = decoder

    def successors(self, state):
        ## Find the best 
        p, plainchar = max([(self.decoder.P1[c], c) 
                            for c in alphabet if c not in state])
        succs = [extend(state, plainchar, cipherchar)] #????
        
    def goal_test(self, state):
        "We're done when we get all 26 letters assigned."
        return len(state) >= 26


#______________________________________________________________________________

def simscore(list1, list2):
    matchcount = 0
    totaldiff = 0
    for item in list2:
        if item in list1:
            matchcount +=1
            #  not very efficient, but who cares?
            diff = abs(list1.index(item)-list2.index(item))
            totaldiff += diff
    score = ((1/float(1+(0.1*totaldiff)))*matchcount)/len(list1)
    return (score, matchcount, totaldiff)
TEXT_IN = ''
TEXT_OUT = ''
def mycode():
    # Read in the entire text of bleakhouse
    bleakhouse = open("bleakhouse.txt").read()
    # Make a list of all the words that appear in order.
    wordseqBleak = words(bleakhouse)
    # Create a dictionary with a count for each word.
    P1Bleak = UnigramTextModel(wordseqBleak)
    # Create a table with a count for each bigram (pair of words)
    # that can return all kinds of interesting information.
    P2Bleak = NgramTextModel(2, wordseqBleak)
    # Create a table with a count for each trigram (group of 3 words)
    # that can (again) return lots of interesting stuff.
    P3Bleak = NgramTextModel(3, wordseqBleak)

    # Now do the same for Jane Austen's moonstone and Sensibility
    moonstone = open("moonstone.txt").read()
    wordSeqMoonstone = words(moonstone)
    P1moonstone = UnigramTextModel(wordSeqMoonstone)
    P2moonstone = NgramTextModel(2, wordSeqMoonstone)
    P3moonstone = NgramTextModel(3, wordSeqMoonstone)

    # Now do the same for a third (mystery) text.  Hint:  This is
    # Jane Austen's secret and Prejudice
    secret = open("secret.txt").read()
    wordseqsecret = words(secret)
    P1secret = UnigramTextModel(wordseqsecret)
    P2secret = NgramTextModel(2, wordseqsecret)

    # This creates a list of the 10 most frequent individual
    # words in each document, then compares the lists using
    # a similarity metric.
    Bleak1top = map((lambda x: x[1:][0]), P1Bleak.top(10))
    moonstone1top = map((lambda x: x[1:][0]), P1moonstone.top(10))
    secret1top = map((lambda x: x[1:][0]), P1secret.top(10))
    F1vsP1 = simscore(Bleak1top, secret1top)
    print "for 10 Words"
    print "BlakevsSecrete simscore: "
    print "score: " + str(F1vsP1[0])
    print "matchCount: " +str(F1vsP1[1])
    print "total diff: " +str(F1vsP1[2])
    S1vsP1 = simscore(moonstone1top, secret1top)
    print "MoonvsSecrete simscore: "
    print "score: " + str(S1vsP1[0])
    print "matchCount: " +str(S1vsP1[1])
    print "total diff: " +str(S1vsP1[2])
    print ' '
    print "For 100 Words"
    # This does the same as the above for the top  100 words, rather
    # than the top 10 words.
    Bleak1top100 = map((lambda x: x[1:][0]), P1Bleak.top(100))
    moonstone1top100 = map((lambda x: x[1:][0]), P1moonstone.top(100))
    secret1top100 = map((lambda x: x[1:][0]), P1secret.top(100))
    F1100vsP1100 = simscore(Bleak1top100, secret1top100)
    print "BlakevsSecrete simscore: " 
    print "score: " + str(F1100vsP1100[0])
    print "matchCount: " +str(F1100vsP1100[1])
    print "total diff: " +str(F1100vsP1100[2])
    S1100vsP1100 = simscore(moonstone1top100, secret1top100)
    print "MoonvsSecrete simscore: " 
    print "score: " + str(S1100vsP1100[0])
    print "matchCount: " +str(S1100vsP1100[1])
    print "total diff: " +str(S1100vsP1100[2])
    print''
    print "for top 10 Bigrams word"
    # This does the same, for the top 10 bigrams in each text.
    Bleak2top = map((lambda x: x[1:][0]), P2Bleak.top(10))
    moonstone2top = map((lambda x: x[1:][0]), P2moonstone.top(10))
    secret2top = map((lambda x: x[1:][0]), P2secret.top(10))
    F2vsP2 = simscore(Bleak2top, secret2top)
    print "BlakevsSecrete simscore: "
    print "score: " + str(F2vsP2[0])
    print "matchCount: " +str(F2vsP2[1])
    print "total diff: " +str(F2vsP2[2])
    S2vsP2 = simscore(moonstone2top, secret2top)
    print "MoonvsSecrete simscore: "
    print "score: " + str(F2vsP2[0])
    print "matchCount: " +str(F2vsP2[1])
    print "total diff: " +str(F2vsP2[2])
    print ''
    print "for top 100 Bigrams word"
    # Same again for the top 100 bigrams.
    Bleak2top100 = map((lambda x: x[1:][0]), P2Bleak.top(100))
    moonstone2top100 = map((lambda x: x[1:][0]), P2moonstone.top(100))
    secret2top100 = map((lambda x: x[1:][0]), P2secret.top(100))
    F2100vsP2100 = simscore(Bleak2top100, secret2top100)
    print "BlakevsSecrete simscore: "
    print "score: " + str(F2100vsP2100[0])
    print "matchCount: " +str(F2100vsP2100[1])
    print "total diff: " +str(F2100vsP2100[2])
    S2100vsP2100 = simscore(moonstone2top100, secret2top100)
    print "MoonvsSecrete simscore: " 
    print "score: " + str(S2100vsP2100[0])
    print "matchCount: " +str(S2100vsP2100[1])
    print "total diff: " +str(S2100vsP2100[2])
    print ''
    # This prints a bunch of interesting statistical information
    # out to the screen.
    Bleakprob = 0
    moonstoneprob = 0
    Bleakcount = 0
    moonstonecount = 0
    secrettotalwords = len(wordseqsecret)
    print "Bleak the prob: " + str(P1Bleak['the'])
    print "moonstone the prob: " + str(P1moonstone['the'])
    print "secret the prob: " + str(P1secret['the'])
    print "Bleak word count: " + str(len(wordseqBleak))
    print "moonstone word count: " + str(len(wordSeqMoonstone))
    print "secret word count: " + str(len(wordseqsecret))
    print "Bleak top 10: " + str(P1Bleak.top(10))
    print "moonstone top 10: " + str(P1moonstone.top(10))
    print "secret top 10: " + str(P1secret.top(10))

    # This goes through each word in secret, notes how likely that word
    # is in one of the other texts and keeps a running total.
    # It also just counts the number of words in secret that appear in
    # the other texts.
    for word in wordseqsecret:
        p1wordBleak = P1Bleak[word]
        p1wordmoonstone = P1moonstone[word]
        if p1wordBleak > 0:
            Bleakcount += 1
        Bleakprob = Bleakprob + p1wordBleak
        if p1wordmoonstone > 0:
            moonstonecount += 1
        moonstoneprob = moonstoneprob + p1wordmoonstone
        # print "word: " + word + " wordprob: " + str(p1wordmoonstone) + " moonstoneprob: " + str(moonstoneprob)        
    print "Bleak probability is: " + str(Bleakprob)
    print "moonstone probability is: " + str(moonstoneprob)
    print "Bleak count and prob are: " + str(Bleakcount) + " " + str(Bleakcount/float(secrettotalwords))
    print "moonstone count and prob are: " + str(moonstonecount) + " " + str(moonstonecount/float(secrettotalwords))

    # This does the same kind of thing as above with bigrams.
    Bleak2prob = 0
    moonstone2prob = 0
    Bleak2count = 0
    moonstone2count = 0
    for index in xrange(1, len(wordseqsecret)):
        p2wordsBleak = P2Bleak[wordseqsecret[index-1],wordseqsecret[index]]
        p2wordsmoonstone = P2moonstone[wordseqsecret[index-1],wordseqsecret[index]]
        if p2wordsBleak > 0:
            Bleak2count +=1
        Bleak2prob = Bleak2prob + p2wordsBleak
        if p2wordsmoonstone > 0:
            moonstone2count +=1
        moonstone2prob = moonstone2prob + p2wordsmoonstone
    print "Bleak bigram prob is: " + str(Bleak2prob)
    print "moonstone bigram prob is: " + str(moonstone2prob)
    print "Bleak bigram count and prob are: " + str(Bleak2count) + " " + str(Bleak2count/float(secrettotalwords))
    print "moonstone bigram count and prob are: " + str(moonstone2count) + " " + str(moonstone2count/float(secrettotalwords))

    # The same thing yet again with trigrams.
    Bleak3prob = 0
    moonstone3prob = 0
    Bleak3count = 0
    moonstone3count = 0
    for index in xrange(2, len(wordseqsecret)):
        p3wordsBleak = P3Bleak[wordseqsecret[index-2],wordseqsecret[index-1],wordseqsecret[index]]
        p3wordsmoonstone = P3moonstone[wordseqsecret[index-2],wordseqsecret[index-1],wordseqsecret[index]]
        if p3wordsBleak > 0:
            Bleak3count +=1
        Bleak3prob = Bleak3prob + p3wordsBleak
        if p3wordsmoonstone > 0:
            moonstone3count +=1
        moonstone3prob = moonstone3prob + p3wordsmoonstone
    print "Bleak trigram prob is: " + str(Bleak3prob)
    print "moonstone trigram prob is: " + str(moonstone3prob)
    print "Bleak trigram count and prob are: " + str(Bleak3count) + " " + str(Bleak3count/float(secrettotalwords))
    print "moonstone trigram count and prob are: " + str(moonstone3count) + " " + str(moonstone3count/float(secrettotalwords))

mycode()
__doc__ += """
## Create a Unigram text model from the words in the book "bleakhouse".
>>> bleakhouse = DataFile("EN-text/bleakhouse.txt").read()
>>> wordseq = words(bleakhouse)
>>> P = UnigramTextModel(wordseq)

## Now do segmentation, using the text model as a prior.
>>> s, p = viterbi_segment('itiseasytoreadwordswithoutspaces', P) 
>>> s 
['it', 'is', 'easy', 'to', 'read', 'words', 'without', 'spaces']
>>> 1e-30 < p < 1e-20 
True
>>> s, p = viterbi_segment('wheninthecourseofhumaneventsitbecomesnecessary', P)
>>> s 
['when', 'in', 'the', 'course', 'of', 'human', 'events', 'it', 'becomes', 'necessary']

## Test the decoding system
>>> shift_encode("This is a secret message.", 17) 
'Kyzj zj r jvtivk dvjjrxv.'

>>> ring = ShiftDecoder(bleakhouse)
>>> ring.decode('Kyzj zj r jvtivk dvjjrxv.') 
'This is a secret message.'
>>> ring.decode(rot13('Hello, world!')) 
'Hello, world!'

## CountingProbDist
## Add a thousand samples of a roll of a die to D.
>>> D = CountingProbDist()
>>> for i in range(10000): 
...     D.add(random.choice('123456'))
>>> ps = [D[n] for n in '123456']
>>> 1./7. <= min(ps) <= max(ps) <= 1./5. 
True
"""

__doc__ += """
## Compare 1-, 2-, and 3-gram word models of the same text.
>>> bleakhouse = DataFile("EN-text/bleakhouse.txt").read()
>>> wordseq = words(bleakhouse)
>>> P1 = UnigramTextModel(wordseq)
>>> P2 = NgramTextModel(2, wordseq)
>>> P3 = NgramTextModel(3, wordseq)

## Generate random text from the N-gram models
>>> P1.samples(20)
'you thought known but were insides of see in depend by us dodecahedrons just but i words are instead degrees'

>>> P2.samples(20)
'bleakhouse well then can anything else more into the total destruction and circles teach others confine women must be added'

>>> P3.samples(20)
'bleakhouse by edwin a abbott 1884 to the wake of a certificate from nature herself proving the equal sided triangle'

## The most frequent entries in each model
>>> P1.top(10)
[(2081, 'the'), (1479, 'of'), (1021, 'and'), (1008, 'to'), (850, 'a'), (722, 'i'), (640, 'in'), (478, 'that'), (399, 'is'), (348, 'you')]

>>> P2.top(10)
[(368, ('of', 'the')), (152, ('to', 'the')), (152, ('in', 'the')), (86, ('of', 'a')), (80, ('it', 'is')), (71, ('by', 'the')), (68, ('for', 'the')), (68, ('and', 'the')), (62, ('on', 'the')), (60, ('to', 'be'))]

>>> P3.top(10)
[(30, ('a', 'straight', 'line')), (19, ('of', 'three', 'dimensions')), (16, ('the', 'moonstone', 'of')), (13, ('by', 'the', 'moonstone')), (13, ('as', 'well', 'as')), (12, ('of', 'the', 'circles')), (12, ('of', 'sight', 'recognition')), (11, ('the', 'number', 'of')), (11, ('that', 'i', 'had')), (11, ('so', 'as', 'to'))]

## Probabilities of some common n-grams
>>> P1['the']
0.061139348356200607

>>> P2[('of', 'the')]
0.010812081325655188

>>> P3[('', '', 'but')]
0.0

>>> P3[('so', 'as', 'to')]
0.00032318721353860618

## Distributions given the previous n-1 words
>>> P2.cond_prob['went',].dictionary
>>> P3.cond_prob['in', 'order'].dictionary
{'to': 6}

## Build and test an IR System
>>> uc = UnixConsultant()
>>> uc.present_results("how do I remove a file")
76.83|       ../data/man/rm.txt | RM(1)			       FSF			    RM(1)
67.83|      ../data/man/tar.txt | TAR(1)									TAR(1)
67.79|       ../data/man/cp.txt | CP(1)			       FSF			    CP(1)
66.58|      ../data/man/zip.txt | ZIP(1L)							  ZIP(1L)
64.58|     ../data/man/gzip.txt | GZIP(1)								       GZIP(1)
63.74|     ../data/man/pine.txt | pine(1)							  pine(1)
62.95|    ../data/man/shred.txt | SHRED(1)		       FSF			 SHRED(1)
57.46|     ../data/man/pico.txt | pico(1)							  pico(1)
43.38|    ../data/man/login.txt | LOGIN(1)		   Linux Programmer's Manual		     
41.93|       ../data/man/ln.txt | LN(1)			       FSF			    LN(1)

>>> uc.present_results("how do I delete a file")
75.47|     ../data/man/diff.txt | DIFF(1)				   GNU Tools			       DIFF(1)
69.12|     ../data/man/pine.txt | pine(1)							  pine(1)
63.56|      ../data/man/tar.txt | TAR(1)									TAR(1)
60.63|      ../data/man/zip.txt | ZIP(1L)							  ZIP(1L)
57.46|     ../data/man/pico.txt | pico(1)							  pico(1)
51.28|    ../data/man/shred.txt | SHRED(1)		       FSF			 SHRED(1)
26.72|       ../data/man/tr.txt | TR(1)			  User Commands			    TR(1)

>>> uc.present_results("email")
18.39|     ../data/man/pine.txt | pine(1)							  pine(1)
12.01|     ../data/man/info.txt | INFO(1)			       FSF			  INFO(1)
 9.89|     ../data/man/pico.txt | pico(1)							  pico(1)
 8.73|     ../data/man/grep.txt | GREP(1)								       GREP(1)
 8.07|      ../data/man/zip.txt | ZIP(1L)							  ZIP(1L)

>>> uc.present_results("word counts for files")
112.38|     ../data/man/grep.txt | GREP(1)								       GREP(1)
101.84|       ../data/man/wc.txt | WC(1)			  User Commands			    WC(1)
82.46|     ../data/man/find.txt | FIND(1L)							      FIND(1L)
74.64|       ../data/man/du.txt | DU(1)			       FSF			    DU(1)

>>> uc.present_results("learn: date")
>>> uc.present_results("2003")
14.58|     ../data/man/pine.txt | pine(1)							  pine(1)
11.62|      ../data/man/jar.txt | FASTJAR(1)			      GNU			    FASTJAR(1)
"""
