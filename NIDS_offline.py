# Author: Laurin Koch
# Date: 2021
"""
Script to train the feature mapping (architecture of the anomaly detector) and the autoencoders (anomaly detector).
After training on a specific amount of packets the model gets executed on the rest of the data.
"""
from Kitsune import Kitsune
import numpy as np
import time
import os
from colorama import init, deinit, Fore
import pickle

# definition of some configuration variables and paths 
data_dir = 'data_sdc11073/results'
data_path = os.path.join(data_dir, 'capture_OPtable_traintest.pcapng')
packet_limit = np.Inf # number of packets to process
maxAE = 10 # maximum size for any autoencoder in the ensemble layer (decrease: better detection but trade off in processing speed)
FMgrace = 5000 # number of packets used to train the feature mapping
ADgrace = 60000 # number of packets used to train the anomaly detector (ensemble of autoencoders)
learning_rate = 0.1 # stochastic gradient descent learning rate 
hidden_ratio = 0.75 # ratio of hidden neurons to visible neurons
sensitivity = 1 # sensitivity parameter to fine tune the anomaly threshold phi

init(autoreset=True)

NIDS = Kitsune(data_path, packet_limit, maxAE, FMgrace, ADgrace, learning_rate, hidden_ratio, sensitivity)

print(Fore.BLUE + 'starting model...')

RMSEs = []
i = 0
start = time.time()

while True:
    i+=1
    if i % 1000 == 0:
        print(Fore.BLUE + f'processing no. {i}')
    rmse = NIDS.proc_next_packet()
    if rmse == -1:
        break
    RMSEs.append(rmse)
end = time.time()

print(Fore.BLUE + f'finished within {end - start} seconds')

threshold_phi = NIDS.phi * sensitivity
model = NIDS.AnomDetector
net_state = NIDS.FE.nstat

with open('models/model.pkl', 'wb') as f:
    pickle.dump([model, RMSEs, threshold_phi], f)

# with open('model.pkl', 'rb') as f:
#     model, RMSEs, threshold_phi = pickle.load(f)

# fitting RMSE scores to the log-normal distribution
from scipy.stats import norm
benignSample = np.log(RMSEs[FMgrace+ADgrace+1:100000])
logProbs = norm.logsf(np.log(RMSEs), np.mean(benignSample), np.std(benignSample))

# plot the RMSE anomaly scores
print(Fore.BLUE + 'plotting results...')
import matplotlib.pyplot as plt
plt.figure(figsize=(10,5))
fig = plt.scatter(range(FMgrace+ADgrace+1,len(RMSEs)),RMSEs[FMgrace+ADgrace+1:],s=0.1,c=logProbs[FMgrace+ADgrace+1:],cmap='RdYlGn')
plt.axhline(y=threshold_phi, color='r', linestyle='-')
plt.yscale('log')
plt.title("Anomaly Scores from Network IDS Execution Phase")
plt.ylabel('RMSE (log scaled)')
plt.xlabel('Network packet number')
figbar=plt.colorbar()
figbar.ax.invert_yaxis()
figbar.ax.set_ylabel('Log Probability\n ', rotation=270)
plt.show()

deinit()