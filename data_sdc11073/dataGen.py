# Author: Laurin Koch 
# Date: 2021
"""
Script to capture data transmitted between the devices and clients specified in fictEnvironments.py.
"""
from fictEnvironments import Med_Environments
import pyshark
import time, sys
import progressbar
import threading
from colorama import init, deinit, Fore, Back
import os
import csv


def live_packet_capture(interface=None,     
                    bpf_filter=None, 
                    display_filter=None,
                    timeout=30, 
                    tshark_path=None, 
                    output_file=None):
    """
    @param interface: string, name of interface to sniff on (e.g. eth0)
    @param bpf_filter: string, filter used to reduce size of raw packet capture
    @param display_filter: string, filter used to hide packets from packet list
    @param timeout: integer, sniffing on interface until given timeout
    @param tshark_path: path to binaries of tshark 
    @param output_file: path to results 
    @return: None
    """

    if interface is None: 
        print(Fore.RED + 'Please provide the used interface.')
        sys.exit(0)
    else:
        try:
            print(Fore.GREEN + 'start capturing data from interface: ', interface)
            capture = pyshark.LiveCapture(interface=interface, bpf_filter=bpf_filter, display_filter=display_filter, 
                                            tshark_path=tshark_path, output_file=output_file)
            t = threading.Thread(target=capture.sniff, kwargs={'timeout': timeout}, daemon=True)
            t.start()
            env = Med_Environments()
            env.setUp()
            env.start_OPtable_env()
            #env.start_OPtable_env(testdata=True)
            env.tearDown()
            t.join()
            if output_file is not None:
                print(Fore.GREEN + 'storing result in directory: ', output_file)
        except Exception as e: 
            print(Fore.RED + 'Error: ' + str(e))
            sys.exit(0)
        capture.clear()
        capture.close()
    return None


# FIXME: not useable to capture all packets
def vis_live_packet_capture(interface=None,     
                    bpf_filter=None, 
                    display_filter=None, 
                    timeout=30, 
                    tshark_path=None, 
                    output_file=None,
                    display=False):
    """
    @param interface: string, name of interface to sniff on (e.g. eth0)
    @param bpf_filter: string, filter used to reduce size of raw packet capture
    @param display_filter: string, filter used to hide packets from packet list
    @param timeout: integer, sniffing on interface until given timeout
    @param tshark_path: path to binaries of tshark 
    @param output_file: path to results
    @param display: boolean, True to print captured packets 
    @return: None
    """

    widgets = [
        progressbar.Bar(marker=progressbar.AnimatedMarker()),
        ' ',
        progressbar.FormatLabel('Packets captured: %(value)d'),
        ' ',
        progressbar.Timer()
    ]

    if interface is None: 
        print(Fore.RED + 'Please provide the used interface.')
        sys.exit(0)
    else:
        start = time.time()
        progress = progressbar.ProgressBar(widgets=widgets)
        try:
            print(Fore.GREEN + 'start capturing data from interface: ', interface)
            capture = pyshark.LiveCapture(interface=interface, bpf_filter=bpf_filter, display_filter=display_filter, 
                                            tshark_path=tshark_path, output_file=output_file)
            for i, packet in enumerate(capture.sniff_continuously()):
                progress.update(i)
                if display==True:
                    print(packet) 
                if time.time() - start > timeout:
                    capture.clear()
                    capture.close()
                    break
            if output_file is not None:
                print(Fore.GREEN + ' storing result in directory: ', output_file)
        except Exception as e: 
            print(Fore.RED + 'Error: ' + str(e))
            sys.exit(0)
    return None


def main():
    init(autoreset=True)
    live_packet_capture(interface='Adapter for loopback traffic capture', output_file='results/capture_OPtable_traintest2.pcapng', 
                        tshark_path='C:\\Program Files\\Wireshark\\tshark.exe', timeout=950)
    # live_packet_capture(interface='Adapter for loopback traffic capture', output_file='results/capture_OPtable_test.pcapng', 
    #                     tshark_path='C:\\Program Files\\Wireshark\\tshark.exe', timeout=75)

    # export pcapng capture file to csv file 
    # note: you need to add wireshark to the environment variables
    os.system('tshark -r results/capture_OPtable_traintest2.pcapng -T fields -e frame.number -e frame.time -e frame.time_delta -e ip.src -e ip.dst -e frame.len -E header=y -E separator=, > results/capture_OPtable_traintest2.csv')
    # write ground truth data 
    csv_file = 'results/capture_OPtable_traintest2.csv'
    csv_file_gt = 'results/capture_OPtable_traintest2_gt.csv'
    with open(csv_file, 'r') as fin, open(csv_file_gt, 'w', newline='') as fout:
        reader = csv.reader(fin)
        writer = csv.writer(fout, delimiter=',')
        headers = next(reader)
        headers.append('anomaly')
        writer.writerow(headers)
        for no, row in enumerate(reader):
            if no < 97790: # anomaly free
                row.append(0)
                writer.writerow(row)
            else: # anomaly
                row.append(1)
                writer.writerow(row)
    os.remove(csv_file)
    deinit()


if __name__ == '__main__':
    main()