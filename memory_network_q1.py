'''Trains a memory network on the bAbI dataset.
References:
- Jason Weston, Antoine Bordes, Sumit Chopra, Tomas Mikolov, Alexander M. Rush,
  "Towards AI-Complete Question Answering: A Set of Prerequisite Toy Tasks",
  http://arxiv.org/abs/1502.05698
- Sainbayar Sukhbaatar, Arthur Szlam, Jason Weston, Rob Fergus,
  "End-To-End Memory Networks",
  http://arxiv.org/abs/1503.08895
Reaches 98.6% accuracy on task 'single_supporting_fact_10k' after 120 epochs.
Time per epoch: 3s on CPU (core i7).
'''
from __future__ import print_function

from keras.models import Sequential, Model
from keras.layers.embeddings import Embedding
from keras.layers import Input, Activation, Dense, Permute, Dropout
from keras.layers import add, dot, concatenate
from keras.layers import LSTM
from keras.utils.data_utils import get_file
from keras.preprocessing.sequence import pad_sequences
from functools import reduce
import tarfile
import numpy as np
import re
from keras.models import load_model
import os

# avoid tensorflow debugging messages
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

from pprint import pprint


def tokenize(sent):
    '''Return the tokens of a sentence including punctuation.
    >>> tokenize('Bob dropped the apple. Where is the apple?')
    ['Bob', 'dropped', 'the', 'apple', '.', 'Where', 'is', 'the', 'apple', '?']
    '''
    return [x.strip() for x in re.split('(\W+)?', sent) if x.strip()]


def parse_stories(lines, only_supporting=False):
    '''Parse stories provided in the bAbi tasks format
    If only_supporting is true, only the sentences
    that support the answer are kept.
    '''
    data = []
    story = []
    for line in lines:
        line = line.decode('utf-8').strip()
        nid, line = line.split(' ', 1)
        nid = int(nid)
        if nid == 1:
            story = []
        if '\t' in line:
            q, a, supporting = line.split('\t')
            q = tokenize(q)
            substory = None
            if only_supporting:
                # Only select the related substory
                supporting = map(int, supporting.split())
                substory = [story[i - 1] for i in supporting]
            else:
                # Provide all the substories
                substory = [x for x in story if x]
            data.append((substory, q, a))
            story.append('')
        else:
            sent = tokenize(line)
            story.append(sent)

    return data


def get_stories(f, only_supporting=False, max_length=None):
    '''Given a file name, read the file,
    retrieve the stories,
    and then convert the sentences into a single story.
    If max_length is supplied,
    any stories longer than max_length tokens will be discarded.
    '''
    data = parse_stories(f.readlines(), only_supporting=only_supporting)
    flatten = lambda data: reduce(lambda x, y: x + y, data)
    data = [(flatten(story), q, answer) for story, q, answer in data if not max_length or len(flatten(story)) < max_length]
    return data


def vectorize_stories(data, word_idx, story_maxlen, query_maxlen):
    X = []
    Xq = []
    Y = []
    for story, query, answer in data:

        x = [word_idx[w] for w in story]
        xq = [word_idx[w] for w in query]
        # let's not forget that index 0 is reserved
        y = np.zeros(len(word_idx) + 1)
        y[word_idx[answer]] = 1
        X.append(x)
        Xq.append(xq)
        Y.append(y)
    return (pad_sequences(X, maxlen=story_maxlen),
            pad_sequences(Xq, maxlen=query_maxlen), np.array(Y))


def vectorize_query(data, word_idx, query_maxlen):
    Xq = []
    tokens = tokenize(data)
    xq = [word_idx[w] for w in tokens]
    Xq.append(xq)

    return pad_sequences(Xq, maxlen=query_maxlen)

def vectorize_story(data, word_idx, story_maxlen):
    X = []
    #Xq = []
    #Y = []
    print (data)
    for storyy in data:
        tokens = tokenize(storyy)
        x = [word_idx[w] for w in tokens]
        #xq = [word_idx[w] for w in query]
        # let's not forget that index 0 is reserved
        #y = np.zeros(len(word_idx) + 1)
        #y[word_idx[answer]] = 1
        X.append(x)
        #Xq.append(xq)
        #Y.append(y)
    return pad_sequences(X, maxlen=story_maxlen)




try:
    path = get_file('babi-tasks-v1-2.tar.gz', origin='https://s3.amazonaws.com/text-datasets/babi_tasks_1-20_v1-2.tar.gz')
except:
    print('Error downloading dataset, please download it manually:\n'
          '$ wget http://www.thespermwhale.com/jaseweston/babi/tasks_1-20_v1-2.tar.gz\n'
          '$ mv tasks_1-20_v1-2.tar.gz ~/.keras/datasets/babi-tasks-v1-2.tar.gz')
    raise
tar = tarfile.open(path)

challenges = {
    # QA1 with 10,000 samples
    'single_supporting_fact_10k': 'tasks_1-20_v1-2/en-10k/qa1_single-supporting-fact_{}.txt',
    # QA2 with 10,000 samples
    'two_supporting_facts_10k': 'tasks_1-20_v1-2/en-10k/qa2_two-supporting-facts_{}.txt',
}
challenge_type = 'single_supporting_fact_10k'
challenge = challenges[challenge_type]



print ("\t --------------------- Refbot --------------------- \t")

print('Extracting stories for the challenge:', challenge_type)
train_stories = get_stories(tar.extractfile(challenge.format('train')))
test_stories = get_stories(tar.extractfile(challenge.format('test')))

vocab = set()
for story, q, answer in train_stories + test_stories:
    vocab |= set(story + q + [answer])
vocab = sorted(vocab)

# Reserve 0 for masking via pad_sequences
vocab_size = len(vocab) + 1
story_maxlen = max(map(len, (x for x, _, _ in train_stories + test_stories)))
query_maxlen = max(map(len, (x for _, x, _ in train_stories + test_stories)))


# values to test the data
# print('-')
# print('Vocab size:', vocab_size, 'unique words')
# print('Story max length:', story_maxlen, 'words')
# print('Query max length:', query_maxlen, 'words')
# print('Number of training stories:', len(train_stories))
# print('Number of test stories:', len(test_stories))
# print('Vectorizing the word sequences...')

word_idx = dict((c, i + 1) for i, c in enumerate(vocab))
inputs_train, queries_train, answers_train = vectorize_stories(train_stories,
                                                               word_idx,
                                                               story_maxlen,
                                                               query_maxlen)
inputs_test, queries_test, answers_test = vectorize_stories(test_stories,
                                                            word_idx,
                                                            story_maxlen,
                                                            query_maxlen)

# print('-')
# print('inputs: integer tensor of shape (samples, max_length)')
# print('inputs_train shape:', inputs_train.shape)
# print('inputs_test shape:', inputs_test.shape)
# print('-')
# print('queries: integer tensor of shape (samples, max_length)')
# print('queries_train shape:', queries_train.shape)
# print('queries_test shape:', queries_test.shape)
# print('-')
# print('answers: binary (1 or 0) tensor of shape (samples, vocab_size)')
# print('answers_train shape:', answers_train.shape)
# print('answers_test shape:', answers_test.shape)
# print('-')
# print('Compiling...')

# placeholders
input_sequence = Input((story_maxlen,))
question = Input((query_maxlen,))

# encoders
# embed the input sequence into a sequence of vectors
input_encoder_m = Sequential()
input_encoder_m.add(Embedding(input_dim=vocab_size,
                              output_dim=64))
input_encoder_m.add(Dropout(0.3))
# output: (samples, story_maxlen, embedding_dim)

# embed the input into a sequence of vectors of size query_maxlen
input_encoder_c = Sequential()
input_encoder_c.add(Embedding(input_dim=vocab_size,
                              output_dim=query_maxlen))
input_encoder_c.add(Dropout(0.3))
# output: (samples, story_maxlen, query_maxlen)

# embed the question into a sequence of vectors
question_encoder = Sequential()
question_encoder.add(Embedding(input_dim=vocab_size,
                               output_dim=64,
                               input_length=query_maxlen))
question_encoder.add(Dropout(0.3))
# output: (samples, query_maxlen, embedding_dim)

# encode input sequence and questions (which are indices)
# to sequences of dense vectors
input_encoded_m = input_encoder_m(input_sequence)
input_encoded_c = input_encoder_c(input_sequence)
question_encoded = question_encoder(question)

# compute a 'match' between the first input vector sequence
# and the question vector sequence
# shape: `(samples, story_maxlen, query_maxlen)`
match = dot([input_encoded_m, question_encoded], axes=(2, 2))
match = Activation('softmax')(match)

# add the match matrix with the second input vector sequence
response = add([match, input_encoded_c])  # (samples, story_maxlen, query_maxlen)
response = Permute((2, 1))(response)  # (samples, query_maxlen, story_maxlen)

# concatenate the match matrix with the question vector sequence
answer = concatenate([response, question_encoded])

# the original paper uses a matrix multiplication for this reduction step.
# we choose to use a RNN instead.
answer = LSTM(32)(answer)  # (samples, 32)

# one regularization layer -- more would probably be needed.
answer = Dropout(0.3)(answer)
answer = Dense(vocab_size)(answer)  # (samples, vocab_size)
# we output a probability distribution over the vocabulary
answer = Activation('softmax')(answer)

# build the final model
model = Model([input_sequence, question], answer)
model.compile(optimizer='rmsprop', loss='categorical_crossentropy',
              metrics=['accuracy'])


model_path1 = '/Users/Chat/8451hack/demo/Deep-Learning/qa_chat_bot/model1.h5'
model_name = 'model1.h5'

try:
    #model.load_weights(model_path1)
    model = load_model(model_name)
except Exception:
    # train
    model.fit([inputs_train, queries_train], answers_train,
            batch_size=32,
            epochs=120,
            validation_data=([inputs_test, queries_test], answers_test))


    #model_path1 = r'C:\Users\priya\Documents\my_dl\qachatbot\model1.h5'
    #model.save(model_path1)
    model.save(model_name)
#model save as pickle file
# model load again
# write story answer question in the format in a text file

#model.load_weights(model_path1)


# Display a selected test story
def run_demo(test_stories, model):
    n = 10
    story_list = test_stories[n][0]
    story = ' '.join(word for word in story_list)

    print("\n\n \t\t ------------- Text ------------ \t\t \n {0}"
             "\n\t\t----------------------------------".format(story))

    while True:
        print ("Press 'q' to exit Refbot.")
        qu = raw_input("Ask question: ")

        if qu == 'q':
            print ("\t \t ---- Refbot exited ---- \t\t")
            break

        q = vectorize_query(qu, word_idx, query_maxlen)
        ans = test_stories[n][2]
        #print("Actual answer is: ", ans)
        input_story = np.reshape(inputs_test[n], (1, story_maxlen))

        final_answer, confidence = get_answer(input_story,q, model)

        print ("\n---------------------\t")
        print("Answer: ", final_answer)
        print("Confidence: ",confidence)
        print ("---------------------\t")


def get_answer(input_story, q, model):
    pred_results3 = model.predict(([input_story, q]))
    val_max2 = np.argmax(pred_results3[0])
    k = "answer not found"
    # Generate prediction from model
    for key, val in word_idx.items():
        if val == val_max2:
            k = key

    return k,pred_results3[0][val_max2]


def load_story(file_path=None, text=None):

    # text = "John and Sandra went to the bedroom.\n" \
    #        "Sandra and John moved to the garden.\n" \
    #        "John and Daniel moved to the kitchen.\n" \
    #        "Mary and Sandra journeyed to the office.\n" \
    #        "Sandra and John travelled to the bedroom.\n" \
    #        "Mary and John moved to the kitchen.\n" \
    #        "John and Sandra went back to the bathroom.\n" \
    #        "Daniel and Mary moved to the garden.\n"

    data = None

    file_path = 'text1.txt'
    if text:
        data = parse_stories(text.splitlines)

    elif file_path:
        f = open(file_path)
        lines = f.readlines()

        #data = parse_stories(lines, only_supporting=False)
        data = vectorize_story(lines,word_idx,story_maxlen)
        print (data)

    else:
        print ("Error: No data loaded. Refbot Exited")
        return


    print("\n\n \t\t ------------- Text ------------ \t\t \n {0}"
             "\n\t\t----------------------------------".format(data))

    stories = get_stories(text, only_supporting=False,max_length=None)
    print (stories)

#n = np.random.randint(0,1000)
run_demo(test_stories, model)
#load_story()


## Read my own file

# f = open(r"C:\Users\priya\Documents\my_dl\qachatbot\my_test_q2.txt", "r")
# print(f.readlines())
# data = parse_stories(f.readlines(), only_supporting=False)
# print(data)
# extra_stories = get_stories(f, only_supporting=False, max_length=None)
#
# print(extra_stories)
