# Author: Laurin Koch 
# Date: 2021
"""
Script to manually label the data after generation and apposition of synthetical anomalies with ID2T program from GitHub.
Note: ID2T currently only supports Linux Systems and MacOS (or WSL2 with Ubuntu 20.04)
"""
import os
import csv

# export pcapng capture file to csv file 
# note: you need to add wireshark to the environment variables
os.system('tshark -r ID2T_synth_attack/OPtable_merged_and_gt/capture_OPtable_SMBScanAttack.pcapng -T fields -e frame.number -e frame.time -e frame.time_delta -e ip.src -e ip.dst -e frame.len -E header=y -E separator=, > ID2T_synth_attack/OPtable_merged_and_gt/capture_OPtable_SMBScanAttack.csv')
# write ground truth data 
csv_file = 'ID2T_synth_attack/OPtable_merged_and_gt/capture_OPtable_SMBScanAttack.csv'
csv_file_gt = 'ID2T_synth_attack/OPtable_merged_and_gt/capture_OPtable_SMBScanAttack_gt.csv'
with open(csv_file, 'r') as fin, open(csv_file_gt, 'w', newline='') as fout:
    reader = csv.reader(fin)
    writer = csv.writer(fout, delimiter=',')
    headers = next(reader)
    headers.append('anomaly')
    writer.writerow(headers)
    for no, row in enumerate(reader):
        if no < 69999: # anomaly free
            row.append(0)
            writer.writerow(row)
        else: # anomaly
            row.append(1)
            writer.writerow(row)
os.remove(csv_file)