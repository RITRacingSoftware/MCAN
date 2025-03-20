import sys
import threading
import queue
import sources
import os
import cantools

source_list = []
rxqueue = queue.Queue()
filter_list = []

can_db = {
    1: cantools.database.load_file("/home/matthias/racing/Formula-DBC/main_dbc.dbc")
#    2: cantools.database.load_file("/home/matthias/racing/Formula-DBC/sensor_dbc.dbc"),
#    3: cantools.database.load_file("/home/matthias/racing/Formula-DBC/inverter_dbc.dbc")
}

def can_decode(packet):
    if packet["bus"] not in can_db: return {}
    return can_db[packet["bus"]].decode_message(packet["id"], packet["data"])


class CANStream:
    def __init__(self):
        self.branches = []

    def filter(self, func, enabled=True):
        br = CANStream()
        self.branches.append([enabled, lambda x: x if func(x) else None, br])
        return br

    def exec(self, func, enabled=True):
        br = CANStream()
        self.branches.append([enabled, func, br])
        return br

    def apply(self, element):
        for b in self.branches:
            if b[0]:
                part = b[1](element)
                if part is not None: b[2].apply(part)

rootstream = CANStream()

def source(s):
    s.set_queue(rxqueue)
    source_list.append(s)

def start_sources():
    for s in source_list: 
        s.start()

def stop_sources():
    for s in source_list:
        s.stop()

