from FeatureExtractor import *
from KitNET.KitNET import KitNET
from colorama import Fore
import pyshark
import progressbar
import time
import netStat as ns
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# MIT License
#
# Copyright (c) 2018 Yisroel mirsky
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

class Kitsune:
    def __init__(self,file_path,limit,max_autoencoder_size=10,FM_grace_period=None,AD_grace_period=10000,learning_rate=0.1,hidden_ratio=0.75,sensitivity=1):
        #init packet feature extractor (AfterImage)
        self.FE = FE(file_path,limit)
        self.packet_count = self.FE.num_lines
        # initial threshold phi value 
        self.phi = -1

        # store predictions, packet index, network state vector
        self.logs = []

        #init Kitnet
        self.AnomDetector = KitNET(self.FE.get_num_features(),max_autoencoder_size,FM_grace_period,AD_grace_period,learning_rate,hidden_ratio,sensitivity)
        self.feature_map = None 

    def proc_next_packet(self):
        # create feature vector
        netState_vec = self.FE.get_next_vector()
        curPacketIndex = self.FE.curPacketIndx
        if len(netState_vec) == 0:
            return -1 #Error or no packets left

        # process() will train during the grace periods, then execute on all the rest
        current_rmse = self.AnomDetector.process(netState_vec)

        # if training mode: set the anomaly threshold phi to maximum rmse
        if self.AnomDetector.n_trained < self.AnomDetector.FM_grace_period + self.AnomDetector.AD_grace_period:
            if current_rmse > self.phi:
                self.phi = current_rmse
            # end of training mode
            if self.AnomDetector.n_trained == self.AnomDetector.FM_grace_period+self.AnomDetector.AD_grace_period-1:
                print(f'anomaly threshold is set to {self.phi}')
                self.feature_map = self.AnomDetector.v

        # if execute mode: use anomaly threshold to raise alarms
        elif self.AnomDetector.n_trained > self.AnomDetector.FM_grace_period + self.AnomDetector.AD_grace_period:
            if current_rmse > self.phi*self.AnomDetector.sensitivity:
                self.logs.append([curPacketIndex, 1, netState_vec.copy()])
                #print(Fore.RED + 'ALERT: Anomaly found!')
            else:
                self.logs.append([curPacketIndex, 0, netState_vec.copy()])

        return current_rmse 

    def proc_packets_train(self):
        RMSEs_train = []
        for _ in range(self.packet_count):
            netState_vec = self.FE.get_next_vector()

            if len(netState_vec) == 0:
                print(Fore.GREEN + f'anomaly threshold is set to {self.phi}')
                break

            current_rmse = self.AnomDetector.train(netState_vec)

            if current_rmse > self.phi:
                self.phi = current_rmse
            RMSEs_train.append(current_rmse)
        return RMSEs_train
            
    def proc_packets_live(self, timeout=60, animate=False):

        # Prep Feature extractor (AfterImage)
        maxHost = 100000000000
        maxSess = 100000000000
        nstat = ns.netStat(np.nan, maxHost, maxSess)

        RMSEs_exec = []
        widgets = [
        progressbar.Bar(marker=progressbar.AnimatedMarker()),
        ' ',
        progressbar.FormatLabel('Packets captured: %(value)d'),
        ' ',
        progressbar.Timer()]

        # note: when capturing traffic from loopback adapter there are no IPv4, IPv6 headers
        # use_json argument improves parsing speed by factor 2
        capture = pyshark.LiveCapture(interface='Ethernet 2', tshark_path='C:\\Program Files\\Wireshark\\tshark.exe', use_json=True)
        progress = progressbar.ProgressBar(widgets=widgets)
        sniff_start = time.time()

        if animate == True:
            def data_gen():
                for i, packet in enumerate(capture.sniff_continuously()):
                    progress.update(i)
                    curPktIdx = i
                    timestamp = packet.sniff_timestamp
                    framelen = len(packet)
                    IPtype = np.nan
                    try:
                        if hasattr(packet, 'ipv4') and (hasattr(packet, 'tcp') or hasattr(packet, 'udp') or hasattr(packet, 'http')):
                            srcIP = packet.ip.src
                            dstIP = packet.ip.dst
                            IPtype = 0
                            srcproto = str(packet[packet.transport_layer].srcport)
                            dstproto = str(packet[packet.transport_layer].dstport)
                        elif hasattr(packet, 'ipv6') and (hasattr(packet, 'tcp') or hasattr(packet, 'udp') or hasattr(packet, 'http')):
                            srcIP = packet.ipv6.src
                            dstIP = packet.ipv6.dst
                            IPtype = 1
                            srcproto = str(packet[packet.transport_layer].srcport)
                            dstproto = str(packet[packet.transport_layer].dstport)
                        else:
                            srcIP = ''
                            dstIP = ''
                            srcproto = ''
                            dstproto = ''
                        srcMAC = packet.eth.src
                        dstMAC = packet.eth.dst
                    except AttributeError as e:
                        print(e)
                        pass
                    
                    netState_vec = nstat.updateGetStats(IPtype, srcMAC, dstMAC, srcIP, srcproto, dstIP, dstproto,
                                                        int(framelen),
                                                        float(timestamp))

                    current_rmse = self.AnomDetector.execute(netState_vec)
                    anomaly = False
                    if current_rmse > self.phi*self.AnomDetector.sensitivity:
                        #print(Fore.RED + 'ALERT: Anomaly found!')
                        anomaly = True
                    if time.time() - sniff_start > timeout:
                        capture.clear()
                        capture.close()
                        break
                    RMSEs_exec.append(current_rmse)
                    yield curPktIdx, current_rmse, anomaly
            
            def init():
                del xdata[:]
                del ydata[:]

            fig = plt.figure()
            ax = fig.add_subplot(1,1,1)
            xdata = []
            ydata = []
            ax.axhline(y=self.phi*self.AnomDetector.sensitivity, color='k', linestyle='--', linewidth=0.5)
            plt.yscale('log')
            plt.xlabel('Packet number')
            plt.ylabel('RMSE (log scaled)')
            plt.title('Anomaly Scores from Network IDS - live Execution Phase')

            def update(data):
                x_data, y_data, anomaly = data
                xdata.append(x_data)
                ydata.append(y_data)
                if anomaly == True:
                    ax.scatter(x_data, y_data, marker='.', color='r')
                    #ax.plot(xdata, ydata, '-', color='r')
                else:
                    ax.scatter(x_data, y_data, marker='.', color='g')
                    #ax.plot(xdata, ydata, '-', color='g')
            
            ani = animation.FuncAnimation(fig, update, data_gen, interval=1000, init_func=init)
            plt.show()

        else:
            for i, packet in enumerate(capture.sniff_continuously()):
                progress.update(i)
                timestamp = packet.sniff_timestamp
                framelen = len(packet)
                IPtype = np.nan
                try:
                    #if 'IPv4' in str(packet.layers[0]) and ('TCP' in str(packet.layers) or 'UDP' in str(packet.layers) or 'HTTP' in str(packet.layers)):
                    if hasattr(packet, 'ipv4') and (hasattr(packet, 'tcp') or hasattr(packet, 'udp') or hasattr(packet, 'http')):
                        srcIP = packet.ip.src
                        dstIP = packet.ip.dst
                        IPtype = 0
                        srcproto = str(packet[packet.transport_layer].srcport)
                        dstproto = str(packet[packet.transport_layer].dstport)
                    #elif 'IPv6' in str(packet.layers[0]) and ('TCP' in str(packet.layers) or 'UDP' in str(packet.layers) or 'HTTP' in str(packet.layers)):
                    elif hasattr(packet, 'ipv6') and (hasattr(packet, 'tcp') or hasattr(packet, 'udp') or hasattr(packet, 'http')):
                        srcIP = packet.ipv6.src
                        dstIP = packet.ipv6.dst
                        IPtype = 1
                        srcproto = str(packet[packet.transport_layer].srcport)
                        dstproto = str(packet[packet.transport_layer].dstport)
                    else:
                        srcIP = ''
                        dstIP = ''
                        srcproto = ''
                        dstproto = ''
                    srcMAC = packet.eth.src
                    dstMAC = packet.eth.dst
                except AttributeError as e:
                    print(e)
                    pass
                
                netState_vec = nstat.updateGetStats(IPtype, srcMAC, dstMAC, srcIP, srcproto, dstIP, dstproto,
                                                    int(framelen),
                                                    float(timestamp))

                current_rmse = self.AnomDetector.execute(netState_vec)
                if current_rmse > self.phi*self.AnomDetector.sensitivity:
                    #print(Fore.RED + 'ALERT: Anomaly found!')
                    pass
                if time.time() - sniff_start > timeout:
                    capture.clear()
                    capture.close()
                    break
                RMSEs_exec.append(current_rmse)
            #capture.apply_on_packets(packet_callback, timeout=60)
        return RMSEs_exec