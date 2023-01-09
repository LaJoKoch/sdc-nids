# Author: Laurin Koch
# Date: 2021
"""
Script to analyse the captured data.
"""
import pyshark


# TODO: get quick overview of captured packets 
def analyse_packets(input_file=None, display_filter=None):
    capture = pyshark.FileCapture(input_file=input_file, display_filter=display_filter)
    for packet in capture:
        pass


def main():
    analyse_packets(input_file='results/capture_1.pcapng')


if __name__ == '__main__':
    main()