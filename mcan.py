import sys
import threading
import os
import cantools
import queue

import tkinter
from tkinter import ttk
import tkinter.font

import mcan_dash
import sources
import bootloader


source_list = []
rxqueue = queue.Queue()
filter_list = []

can_db = {
    1: cantools.database.load_file("/home/matthias/racing/Formula-DBC/sensor_dbc.dbc"),
    2: cantools.database.load_file("/home/matthias/racing/Formula-DBC/main_dbc.dbc"),
    3: cantools.database.load_file("/home/matthias/racing/Formula-DBC/inverter_dbc.dbc")
}


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

rxrootstream = CANStream()
txrootstream = CANStream()

def source(s):
    s.set_queue(rxqueue)
    source_list.append(s)

def start_sources():
    for s in source_list: 
        s.start()

def stop_sources():
    for s in source_list:
        s.stop()

def transmit(packet):
    txrootstream.apply(packet)


def dash(packet, target):
    if window is not None: window.dash_update(packet, target)

class MainWindow(tkinter.Tk):
    def __init__(self):
        super().__init__()
        self.title("MCAN v0.1")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        style = ttk.Style(self)
        style.configure("Treeview", font=("Ubuntu Mono", 10))

        self.menubar = tkinter.Menu(self)
        #self.bootmenu = tkinter.Menu(self.menubar, tearoff=0)
        self.menubar.add_command(label="Bootloader", command=self.open_bootloader)
        #self.menubar.add_cascade(label="Bootloader", menu=self.bootmenu)
        self.config(menu=self.menubar)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="news")

        self.boot = None

        self.dash_targets = {}
        
        rxrootstream.filter(lambda packet: packet["id"]&(1<<30)).exec(self.forward_boot)
        self.protocol("WM_DELETE_WINDOW", self.on_quit)

        #for target in ["all", "sensor", "main", "inverter"]:
        #    self.dash_targets[target] = mcan_dash.CANDashboard(self, target)
        #    self.notebook.add(self.dash_targets[target], text=target)

    def on_quit(self):
        for d in self.dash_targets:
            self.dash_targets[d].close()
        self.destroy()

    def can_decode(self, packet):
        if packet["bus"] not in can_db: return {}
        db = can_db[packet["bus"]]
        if packet["id"] not in db._frame_id_to_message: return {}
        return db.get_message_by_frame_id(packet["id"]), db.decode_message(packet["id"], packet["data"])

    def forward_boot(self, packet):
        if self.boot is not None and not self.boot.closed:
            self.boot.onrecv(packet)

    def open_bootloader(self):
        self.boot = bootloader.Bootloader(transmit)

    def dash_update(self, packet, target):
        if target not in self.dash_targets:
            self.dash_targets[target] = mcan_dash.CANDashboard(self, target)
            self.notebook.add(self.dash_targets[target], text=target)
        self.dash_targets[target].dash_update(packet)

    def update(self):
        try:
            while True:
                packet = rxqueue.get_nowait()
                rxrootstream.apply(packet)
        except queue.Empty: pass
        self.after(10, self.update)


def mainloop():
    global window
    window = MainWindow()
    start_sources()
    window.update()
    try:
        tkinter.mainloop()
    finally:
        stop_sources()
