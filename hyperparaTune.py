# Author: Laurin Koch
# Date: 2021
"""
Script to tune hyperparameter such as learning rate, hidden ratio, etc.
"""
from Kitsune import Kitsune
import numpy as np
import os
import pandas as pd
import pickle
import csv
from sklearn.metrics import f1_score
from hyperopt import hp, fmin, tpe, STATUS_OK, Trials

data_dir = 'data_sdc11073/results'
pcapng_traintestData_path = os.path.join(data_dir, 'capture_OPtable_traintest2.pcapng')
csv_traintestData_gt_path = os.path.join(data_dir, 'capture_OPtable_traintest2_gt.csv')
csv_outfile = os.path.join(data_dir, 'hyperpara_optimization_infos.csv')
packet_limit = np.Inf
FMgrace = 5000 
ADgrace = 60000
ITERATION = 0

def objective(space):
    global ITERATION
    ITERATION += 1

    NIDS = Kitsune(pcapng_traintestData_path, 
                  packet_limit,
                  max_autoencoder_size = space['max_AE'],
                  FM_grace_period = FMgrace, 
                  AD_grace_period = ADgrace, 
                  learning_rate = space['learning_rate'], 
                  hidden_ratio = space['hidden_ratio'], 
                  sensitivity = space['sensitivity'])
    
    packet_count = NIDS.packet_count

    for _ in range(packet_count):
        rmse = NIDS.proc_next_packet()
        if rmse == -1:
            break
        
    logs = NIDS.logs
    preds = [item[1] for item in logs]
    gt_data = pd.read_csv(csv_traintestData_gt_path, usecols=['anomaly'])
    gt = gt_data.anomaly.tolist()
    exec_start_idx = FMgrace + ADgrace
    gt_exec = gt[exec_start_idx:]
    f1 = f1_score(gt_exec, preds)
    loss = 1-f1

    # store optimization information in csv file 
    with open(csv_outfile, 'a', newline='') as f:
        writer = csv.writer(f, delimiter=',')
        writer.writerow([loss, space, ITERATION])

    return {'loss': loss, 'params': space, 'iteration': ITERATION, 'status': STATUS_OK}

# hyperparameter space, where each hyperparameter has its own probability distribution
space = {
    'max_AE': hp.quniform('max_AE', 1, 20, 1), # discrete uniform distribution
    'learning_rate': hp.loguniform('learning_rate', np.log(0.001), np.log(0.2)), # logarithmic uniform distribution
    'hidden_ratio': hp.uniform('hidden_ratio', 0.0, 1.0),
    'sensitivity': hp.uniform('sensitivity', 0.0, 1.0)
}

# write headers to csv file 
with open(csv_outfile, 'w', newline='') as fout:
    writer = csv.writer(fout, delimiter=',')
    writer.writerow(['loss', 'params', 'iteration'])

# result history with dictionary returned from the object function
trials = Trials()
# algorithm used for optimization: Tree Parzen Estimator
best_hyperpara = fmin(fn=objective, space=space, algo=tpe.suggest, max_evals=5, trials=trials)
print(best_hyperpara)

# store results to evaluate them in jupyter notebook
with open('models/hyperpara_24092021.pkl', 'wb') as f:
    pickle.dump([best_hyperpara, trials], f)