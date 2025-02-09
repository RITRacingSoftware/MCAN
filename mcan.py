#import curses
import sys
import threading
import queue
import sources

source_list = []
rxqueue = queue.Queue()
filter_list = []
options = {
    "interactive": False
}

class Filter:
    def __init__(self, func):
        self.chain = [lambda x: x if func(x) else None]

    def filter(self, func):
        self.chain.append(lambda x: x if func(x) else None)
        return self

    def exec(self, func):
        self.chain.append(func)
        return self

def source(s, *args, **kwargs):
    source_list.append(s(rxqueue, *args, **kwargs))

def filter(func):
    f = Filter(func)
    filter_list.append(f)
    return f

def log_can(packet):
    print(packet)


def mainloop():
    for s in source_list:
        s.start()
    filter_list_compiled = [f.chain for f in filter_list]
    while True:
        packet = rxqueue.get()
        for f in filter_list_compiled:
            p = packet
            for part in f:
                p = part(p)
                if p is None: break


