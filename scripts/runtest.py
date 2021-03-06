import sys
import time
import collections
import copy
import itertools
import os
import pickle
import random
import re
import shutil
import string

sys.path.append('scripts/glimpse_scripts')

import glimpse_scripts.create_model as create_model
import glimpse_scripts.run_model as run_model 

corpus = 'corpus'
test_set = 'test_set'
train_set = 'train_set'
data_folder = 'data'
classes = sorted([ os.path.join(corpus, f) for f in os.listdir(corpus) if os.path.isdir(os.path.join(corpus, f)) ])

def runtest(num_protos):

    # Begin the timers for debugging purposes

    start = time.clock()
    start_realtime = time.time()
    
    # Move into a work folder to minimize clutter and latency in main folder (i.e. for `ls`)
    
    print 'Moving into {0}... {1}'.format(data_folder, time.clock() - start)
    
    os.chdir(data_folder)
    
    # Use create_model.py to create an HMAX model from the training set 
    
    print 'Creating new model... {0}'.format(time.clock() - start)
    
    params = 'params.p'
    model = create_model.create_model(train_set, num_protos, suppress_gui=True, params=pickle.load(open('params.p', 'rb')))
    
    # Use run_model.py to get the C2 activations for each image in the corpus 
    # Split output from run_model.py into multiple .predictions files
    # Set the first column of each line to one to satisfy SVMLearn requirements
    
    print 'Calculating C2 activations... {0}'.format(time.clock() - start)
    
    for s in [test_set, train_set]:
        run_model.run_model(s, model)
        f = open('features', 'r').readlines()
        p = open('features-paths', 'r').readlines()
        
        features = [ [] for _ in range(int(f[-1].split(' ')[0]) + 1) ]
        paths = [ [] for _ in range(int(f[-1].split(' ')[0]) + 1) ]
    
        for line in range(len(f)):
            features[int(f[line].split(' ')[0])].append(f[line])
            paths[int(f[line].split(' ')[0])].append(p[line])
    
        for i in range(len(features)):
            number = int(features[i][0].split(' ')[0])
            base = os.path.basename(classes[number])
            set_name = 'test' if s is test_set else 'train'
            for line in range(len(features[i])):
                features[i][line] = '1' + features[i][line][1:]
            open('{0}.{1}'.format(base, set_name), 'w').writelines(features[i])
            open('{0}.names.{1}'.format(base, set_name), 'w').writelines(paths[i])
    
    # Make exhaustive pairwise data from individual classes.
    # Train an svm for each pairwise data set. Positive examples come first.
    
    pairs = list(itertools.combinations([ os.path.basename(c) for c in classes ], r=2)) 
    
    for pair in pairs:
        class_trains = [ '{0}.train'.format(c) for c in pair ] 
        class_lines = [ open(t, 'r').readlines() for t in class_trains ]
        pair_train = '{0}.train'.format('-'.join(pair))
    
        for line in range(len(class_lines[1])):
            class_lines[1][line] = '-1' + class_lines[1][line][1:]
        
        pair_train_lines = [] 
        for lines in class_lines:
            pair_train_lines.extend(lines)
        
        open(pair_train, 'w').write(''.join(pair_train_lines))
        print 'Training SVM using {0}... {1}'.format(pair_train, time.clock() - start)
        os.system('/stash/mm-group/svm_light/svm_learn -v 0 {0}.train {0}.svm'.format('-'.join(pair)))
    
    svms = [ f for f in os.listdir('.') if '.svm' in f ]
    
    # Use each svm to classify each class of images.
    
    print 'Classifying images...'
    
    for c in [ os.path.basename(k) for k in classes ]:
        for svm in svms:
            test = '{0}.test'.format(c)
            pairname = svm.split('.')[0]
            pred = '{0}-{1}.predictions'.format(c, pairname) 
            print 'Testing {0} using {1}... {2}'.format(c, svm, time.clock() - start)
            os.system('/stash/mm-group/svm_light/svm_classify -v 0 {0} {1} {2}'.format(test, svm, pred))
    
    # Accumulate predictions into a list.
    
    preds = [ f for f in os.listdir('.') if '.predictions' in f ]
    votes = []
    results = []
    
    for c in [ os.path.basename(k) for k in classes ]:
        class_preds = [ p for p in preds if p.split('-')[0] == c ]
        class_images = '{0}.names.test'.format(c)
        class_images_lines = open(class_images, 'r').read().splitlines()
        print 'Accumulating results for {0}... {1}'.format(c, time.clock() - start)
        predictions = [ collections.Counter() for _ in class_images_lines ]
        for n in range(len(class_preds)):
            pred = class_preds[n] 
            class_pred_lines = open(pred, 'r').read().splitlines()
            for line in range(len(class_pred_lines)):
                value = float(class_pred_lines[line])
                pred_classes = re.findall(r'.*-(.*)-(.*)\.predictions', pred)[0]
                if value > 0:
                    pred_class = pred_classes[0]
                else:
                    pred_class = pred_classes[1]
                    
                predictions[line].update([pred_class])
    
        for n in range(len(predictions)):
            counter = predictions[n]
            highest_freq = counter.most_common(1)[0][1]
            highest_classes = [ el for el in list(counter) if counter[el] == highest_freq ] 
            chosen_class = random.choice(list(set(highest_classes)))
            results.append([class_images_lines[n], c, chosen_class])
    
    # Calculate overall accuracy.
    
    print 'Calculating accuracy... {0}'.format(time.clock() - start)
    
    accuracy = len([ k for k in results if k[1] == k[2] ]) / float(len(results))
    
    # Format the output for results.txt.
    
    print 'Formatting output... {0}'.format(time.clock() - start)
    
    titles = ['IMAGE', 'ACTUAL CATEGORY', 'PREDICTED CATEGORY']
    format_results = [titles] + copy.deepcopy(results)
    maxlens = [0] * len(results[0])
    
    for row in results:
        for n in range(len(row)):
            maxlens[n] = max(maxlens[n], len(row[n]))
    
    for row in range(len(format_results)):
        for n in range(len(format_results[0])):
            format_results[row][n] = string.ljust(format_results[row][n], maxlens[n])
       
    with open('results.txt', 'w') as f:
        f.write('Accuracy: {0}\n'.format(accuracy))
        for line in format_results:
            f.write('\t\t'.join(line) + '\n')
    
    # Generate a confusion matrix in matrix.png.
    
    print 'Generating confusion matrix... {0}'.format(time.clock() - start)
    
    output_matrix = []
    
    for actual in [ os.path.basename(c) for c in classes ]:
        outputs = [ k for k in results if k[1] == actual ]
        row = []
        for predicted in [ os.path.basename(c) for c in classes ]:
            count = len([ k for k in outputs if k[2] == predicted ])
            row.append(count)
    
        output_matrix.append(row)
    
    # Normalize the output matrix.
    
    sums = [] 
    for col in range(len(output_matrix[0])):
        sums.append(sum([ output_matrix[n][col] for n in range(len(output_matrix)) ]))
    
    for row in range(len(output_matrix)):
        for col in range(len(output_matrix[0])):
           if sums[col] != 0:
               output_matrix[row][col] /= float(sums[col])
    
    # Pickle both the output matrix and the class list.
    
    pickle.dump(output_matrix, open('matrix.p', 'wb'))
    pickle.dump([ os.path.basename(c) for c in classes ], open('classes.p', 'wb'))
    
    print 'Done. Results in ./results.txt. Confusion matrix in ./matrix.p. Class names in ./classes.p. Runtime: {0}'.format(time.clock() - start)
    print 'Accuracy is {0:.3f}%.'.format(accuracy*100)
    print 'Overall time taken: {0}'.format(time.time() - start_realtime)
