# Author: Laurin Koch
# Date: 2021
"""
Script to train the feature mapping (architecture of the anomaly detector) and the autoencoders (anomaly detector).
After training the model gets executed on live captured packets.
"""
from Kitsune import Kitsune
import numpy as np
import os
from colorama import init, deinit, Fore
import pickle

data_dir = 'data_sdc11073/results'
data_path = os.path.join(data_dir, 'capture_OPtable_2.pcapng')
packet_limit = np.Inf # number of packets to process
maxAE = 10 # maximum size for any autoencoder in the ensemble layer 
FMgrace = 5000 # number of packets used to train the feature mapping
ADgrace = 60000 # number of packets used to train the anomaly detector (ensemble of autoencoders)
learning_rate = 0.1 # stochastic gradient descent learning rate 
hidden_ratio = 0.75 # ratio of hidden neurons to visible neurons
sensitivity = 1 # sensitivity parameter to fine tune the anomaly threshold phi

init(autoreset=True)

NIDS = Kitsune(data_path, packet_limit, maxAE, FMgrace, ADgrace, learning_rate, hidden_ratio, sensitivity)

RMSEs_train = NIDS.proc_packets_train()
RMSEs_exec = NIDS.proc_packets_live(timeout=120, animate=False)

#threshold_phi = NIDS.phi * sensitivity
#model = NIDS.AnomDetector
#net_state = NIDS.FE.nstat

#with open('models/model_live.pkl', 'wb') as f:
#    pickle.dump([model, RMSEs_train, RMSEs_exec, threshold_phi], f)

deinit()