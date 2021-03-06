
import os
import tqdm
import nltk
import multiprocessing
import pickle
import numpy as np
import collections
from utils import parameters
from utils.fasttext import FastVector

params = parameters.Parameters()


def ptb_data_read(corpus_file, sent_file):
    if os.path.exists(sent_file):
        print("Loading sentences file")
        with open(sent_file, 'rb') as rf:
            sentences = pickle.load(file=rf)
        return sentences

    if not os.path.exists("./trained_embeddings_"+params.name):
        os.makedirs("./trained_embeddings_"+params.name)
    sentences = []
    with open(corpus_file) as rf:
        for line in rf:
            sentences.append(['<BOS>'] + line.strip().split(' ') + ['<EOS>'])
    with open(sent_file, 'wb') as wf:
        pickle.dump(sentences, file=wf)
    return sentences

def ptb_read(data_path):

    sentences_data = ptb_data_read(os.path.join(data_path, 'data.txt'),
                               sent_file="./trained_embeddings_"+params.name+"/sentences.pickle")

    label_data = ptb_data_read(os.path.join(data_path, 'labels.txt'),
                               sent_file="./trained_embeddings_"+params.name+"/labels.pickle")

    return sentences_data, label_data

class Dictionary(object):
    def __init__(self, sentences,labels, vocab_drop):
        # sentences - array of sentences
        self._vocab_drop = vocab_drop
        if vocab_drop < 0:
            raise ValueError
        self._sentences = sentences
        self._labels = labels
        self._word2idx = {}
        self._idx2word = {}
        self._words = []
        self._hindi_words=[]
        self._english_words=[]
        self._vocab=[]
        self._sizes=[]
        self.get_words()
        # print(self._words,len(self._words))
        # print(self._hindi_words,len(self._hindi_words))
        # print(self._english_words,len(self._english_words))
        self._words.append('<unk>')
        self.build_vocabulary()
        self._mod_sentences()

    @property
    def vocab_size(self):
        return len(self._idx2word)

    @property
    def sizes(self):
        return self._sizes

    @property
    def vocab(self):
        return self._vocab

    @property
    def sentences(self):
        return self._sentences

    @property
    def labels(self):
        return self._labels

    @property
    def word2idx(self):
        return self._word2idx

    @property
    def idx2word(self):
        return self._idx2word

    def seq2dx(self, sentence):
        return [self.word2idx[wd] for wd in sentence]

    def get_words(self):
        for i in range(len(self.sentences)):
            sent=self.sentences[i]
            for j in range(len(sent)):
                word=sent[j]
                if word in ["<EOS>","<BOS>","<PAD>", "<UNK>"]:
                    self._words.append(word)
                elif (self._labels[i][j] == '0'):
                    self._english_words.append(word.lower())
                elif (self._labels[i][j] == '1'):
                    self._hindi_words.append(word.lower())
                elif (self._labels[i][j] == '2'):
                    self._words.append(word.lower())
                    
    def _mod_sentences(self):
        # for every sentence, if word not in vocab set to <unk>
        for i in range(len(self._sentences)):
            sent = self._sentences[i]
            lab=self._labels[i]
            for j in range(len(sent)):
                sent[j] = sent[j] if sent[j] in ["<EOS>",
                                        "<BOS>",
                                        "<PAD>", "<UNK>",
                                        "N"] else sent[j].lower()
                try:
                    self.word2idx[sent[j]]
                except:
                    sent[j] = '<unk>'
                    lab[j]='2'
            self._sentences[i] = sent
            self._labels[i] = lab

    def build_vocabulary(self):
        counter_words = collections.Counter(self._words)
        # words, that occur less than 5 times dont include
        sorted_dict_words = sorted(counter_words.items(), key= lambda x: (-x[1], x[0]))
        # keep n words to be included in vocabulary
        sorted_dict_words = [(wd, count) for wd, count in sorted_dict_words
                       if count >= self._vocab_drop or wd in ['<unk>',
                                                              '<BOS>',
                                                              '<EOS>']]
        counter_h_words = collections.Counter(self._hindi_words)
        # words, that occur less than 5 times dont include
        sorted_dict_h_words = sorted(counter_h_words.items(), key= lambda x: (-x[1], x[0]))
        # keep n words to be included in vocabulary
        sorted_dict_h_words = [(wd, count) for wd, count in sorted_dict_h_words
                       if count >= self._vocab_drop or wd in ['<unk>',
                                                              '<BOS>',
                                                              '<EOS>']]
        counter_e_words = collections.Counter(self._english_words)
        # words, that occur less than 5 times dont include
        sorted_dict_e_words = sorted(counter_e_words.items(), key= lambda x: (-x[1], x[0]))
        # keep n words to be included in vocabulary
        sorted_dict_e_words = [(wd, count) for wd, count in sorted_dict_e_words
                       if count >= self._vocab_drop or wd in ['<unk>',
                                                              '<BOS>',
                                                              '<EOS>']]
        

        # print(sorted_dict_words)
        # print(sorted_dict_e_words)
        # print(sorted_dict_h_words)
        # after sorting the dictionary, get ordered words
        all_words=[]
        words, _ = list(zip(*sorted_dict_words))
        e_words, _ = list(zip(*sorted_dict_e_words))
        h_words, _ = list(zip(*sorted_dict_h_words))
        
        all_words.extend(words)
        all_words.extend(e_words)
        all_words.extend(h_words)
        sizes=[len(words)+1,len(e_words),len(h_words)]
        print(sizes)
        # print(all_words)
        # print(sizes)
        # print(len(all_words))
        self._word2idx = dict(zip(all_words, range(1, len(all_words) + 1)))
        self._idx2word = dict(zip(range(1, len(all_words) + 1), all_words))
        # add <PAD> as zero
        # print(words)
        self._idx2word[0] = '<PAD>'
        self._word2idx['<PAD>'] = 0
        # print(self._idx2word)
        all_words=['<PAD>']+all_words
        self._vocab=all_words
        self._sizes=sizes

    def __len__(self):
        return len(self.idx2word)

def train_w2vec(embed_fn, embed_size, w2vec_it=5, tokenize=True,
                sentences=None, model_path="./trained_embeddings_"+params.name):
    from gensim.models import KeyedVectors, Word2Vec
    embed_fn += '.embed'
    print(os.path.join(model_path, embed_fn))
    print("Corpus contains {0:,} tokens".format(
        sum(len(sent) for sent in sentences)))
    if os.path.exists(os.path.join(model_path, embed_fn)):
        print("Loading existing embeddings file")
        return KeyedVectors.load_word2vec_format(
            os.path.join(model_path, embed_fn))
    # sample parameter-downsampling for frequent words
    w2vec = Word2Vec(sg=0,
                     workers=multiprocessing.cpu_count(),
                     size=embed_size, min_count=0, window=5, iter=w2vec_it) #CBOW MODEL IS USED AND Embed_size default
    w2vec.build_vocab(sentences=sentences)
    print("Training w2vec")
    w2vec.train(sentences=sentences,
                total_examples=w2vec.corpus_count, epochs=w2vec.iter)
    # Save it to model_path
    if not os.path.exists(model_path):
        os.makedirs(model_path)
    w2vec.wv.save_word2vec_format(os.path.join(model_path, embed_fn))
    return KeyedVectors.load_word2vec_format(os.path.join(model_path, embed_fn))

def save_data(sentences, pkl_file,text_file):
    
    with open(pkl_file, 'wb') as wf:
        pickle.dump(sentences, file=wf)

    with open(text_file, 'w') as wf:
        for sent in sentences:
            line=' '.join([word for word in sent if word not in ['<BOS>',
                                                                  '<EOS>']])
            wf.write(line)
            wf.write("\n")
def prepare_data(data_raw,labels_raw, params,data_path):
    # get embeddings, prepare data
    print("building dictionary")
    data_dict = Dictionary(data_raw,labels_raw, params.vocab_drop)
    save_data(data_dict.sentences,"./trained_embeddings_"+params.name+"/sentences_mod.pickle",os.path.join(data_path, 'data_mod.txt'))
    save_data(data_dict.labels,"./trained_embeddings_"+params.name+"/labels_mod.pickle",os.path.join(data_path, 'labels_mod.txt'))

    sizes=data_dict.sizes
    b1=sizes[0]
    b2=sizes[0]+sizes[1]
    b3=sizes[0]+sizes[1]+sizes[2]
    
    model_path="./trained_embeddings_"+params.name
    filename=os.path.join(model_path, "embedding_file.pkl")
    
    if os.path.exists(filename):
        with open(filename,'rb') as rf:
            embed_arr=pickle.load(rf)

    else:
        dirname = os.path.dirname(__file__)
        hi_align_vec_path = os.path.join(dirname, './../wiki.hi.align.vec')
        en_align_vec_path = os.path.join(dirname, './../wiki.en.align.vec')

        hi_align_dictionary = FastVector(vector_file=hi_align_vec_path)
        en_align_dictionary = FastVector(vector_file=en_align_vec_path)
        print("loaded the files..")

        embed_arr = embed_arr = np.zeros([data_dict.vocab_size, params.embed_size])
        for i in range(embed_arr.shape[0]):
            print(i)
            if i == 0:
                continue
            elif (i>0 and i<b1):
                try:
                    embed_arr[i]=en_align_dictionary[data_dict.idx2word[i]]
                    print(str(i), "english")
                except:
                    pass
                try:
                    embed_arr[i]=hi_align_dictionary[data_dict.idx2word[i]]    
                    print(str(i), "hindi")
                except:
                    embed_arr[i]=hi_align_dictionary["unk"]
                    print(str(i), "unk")

            elif(i>=b1 and i<b2):
                try:
                    embed_arr[i]=en_align_dictionary[data_dict.idx2word[i]]
                    print(str(i), "english")
                except:
                    embed_arr[i]=hi_align_dictionary["unk"]
                    print(str(i),"unk")
                    

            elif(i>=b2 and i<b3):
                try:
                    embed_arr[i]=hi_align_dictionary[data_dict.idx2word[i]]
                    print(str(i), "hindi")
                except:
                    embed_arr[i]=hi_align_dictionary["unk"]
                    print(str(i),"unk")
                    

        print("Embedding created")
        if not os.path.exists(model_path):
            os.makedirs(model_path)

        with open(filename,'wb') as wf:
            pickle.dump(embed_arr,wf)


    # if params.pre_trained_embed:
    #     w2_vec = train_w2vec(params.input, params.embed_size,
    #                         w2vec_it=5,
    #                         sentences=data_dict.sentences,
    #                         model_path="./trained_embeddings_"+params.name)
    #     embed_arr = np.zeros([data_dict.vocab_size, params.embed_size])
    #     for i in range(embed_arr.shape[0]):
    #         if i == 0:
    #             continue
    #         try:
    #             embed_arr[i] = w2_vec.word_vec(unicode(data_dict.idx2word[i], "utf-8"))
    #             # print(data_dict.idx2word[i])

    #         except:
    #             ax=2                
    #             # embed_arr[i] = w2_vec.word_vec('<unk>')
    data = [[data_dict.word2idx[word] \
             for word in sent[:-1]] for sent in data_dict.sentences \
            if len(sent) < params.sent_max_size - 2]
    
    encoder_data = [[data_dict.word2idx[word] \
                   for word in sent[1:]] for sent in data_dict.sentences \
                  if len(sent) < params.sent_max_size - 2]


    decoder_labels=[]
    for sent in data_dict.sentences:
        a=[]
        for word in sent[1:]:
            index=data_dict.word2idx[word]
            if(index>=b1 and index<b2):
                a.append(index-b1)
            elif(index>=b2):
                a.append(index-b2)
            else:
                a.append(index)

        decoder_labels.append(a)

    # for i in range(5):
    #     print(encoder_data[i])
    #     print(decoder_labels[i])
    #     print("------------------")

    # exit()
    filename=os.path.join(model_path, "data_dict.pkl")
    with open(filename,'wb') as wf:
            pickle.dump(data_dict,wf)
    
    print("----Corpus_Information--- \n "
          "Raw data size: {} sentences \n Vocabulary size {}"
          "\n Limited data size {} sentences \n".format(
              len(data_raw), data_dict.vocab_size, len(data)))
    return data, encoder_data,decoder_labels, embed_arr, data_dict
