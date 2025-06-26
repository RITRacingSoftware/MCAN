import sys
import threading
import os
import cantools
import queue
import time

import tkinter
from tkinter import ttk
import tkinter.font

import mcan_dash
import sources
import bootloader
import mcan_bootloader


source_list = []
rxqueue = queue.Queue()
filter_list = []

can_db = {
    1: cantools.database.load_file("../Formula-DBC/sensor_dbc.dbc"),
    2: cantools.database.load_file("../Formula-DBC/main_dbc.dbc"),
    3: cantools.database.load_file("../Formula-DBC/inverter_dbc.dbc")
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
        self.bootmenu = tkinter.Menu(self.menubar, tearoff=0)
        self.bootmenu.add_command(label="Bootloader", command=self.open_bootloader)
        self.menubar.add_cascade(label="Bootloader", menu=self.bootmenu)
        self.config(menu=self.menubar)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="news")

        self.stats_table = tkinter.Frame(self)
        self.stats_table.grid(row=1, column=0, sticky="news")

        self.stats = {
            "total_packets": 0,
            "last_packets": 0, 
            "total_bytes": 0,
            "last_bytes": 0,
            "last_time": 0
        }
        tkinter.Label(self.stats_table, text="Total packets", font=(None, 10)).grid(row=0, column=0, sticky="w")
        tkinter.Label(self.stats_table, text="Packet rate", font=(None, 10)).grid(row=0, column=2, sticky="w")
        tkinter.Label(self.stats_table, text="Total bytes", font=(None, 10)).grid(row=1, column=0, sticky="w")
        tkinter.Label(self.stats_table, text="Byte rate", font=(None, 10)).grid(row=1, column=2, sticky="w")
        tkinter.Label(self.stats_table, text="Total time", font=(None, 10)).grid(row=2, column=0, sticky="w")
        tkinter.Label(self.stats_table, text="Backlog", font=(None, 10)).grid(row=2, column=2, sticky="w")
        self.stats_elements = [tkinter.Label(self.stats_table, font=(None, 10)) for x in range(6)]
        for l, (r, c) in zip(self.stats_elements, [(0, 1), (0, 3), (1, 1), (1, 3), (2, 1), (2, 3)]):
            l.grid(row=r, column=c, sticky="w")
        self.stats_table.grid_columnconfigure(1, weight=1, minsize=100)
        self.stats_table.grid_columnconfigure(3, weight=1, minsize=100)

        self.grid_rowconfigure(0, weight=1)

        self.boot = None

        self.dash_targets = {}
        
        self.boot_manager = bootloader.BootManager(transmit)
        rxrootstream.filter(lambda packet: packet["id"]&(1<<30)).exec(self.boot_manager.onrecv)
        self.protocol("WM_DELETE_WINDOW", self.on_quit)

        self.ts = time.time()
        self.update_stats()

    def on_quit(self):
        for d in self.dash_targets:
            self.dash_targets[d].close()
        stop_sources()
        self.destroy()

    def can_decode(self, packet):
        if packet["bus"] not in can_db: return None, {}
        db = can_db[packet["bus"]]
        if packet["id"] not in db._frame_id_to_message: return None, {}
        return db.get_message_by_frame_id(packet["id"]), db.decode_message(packet["id"], packet["data"])

    def open_bootloader(self):
        self.boot = mcan_bootloader.BootloaderMenu(self.boot_manager)

    def dash_update(self, packet, target):
        if target not in self.dash_targets:
            self.dash_targets[target] = mcan_dash.CANDashboard(self, target, self.can_decode)
            self.notebook.add(self.dash_targets[target], text=target)
        self.dash_targets[target].dash_update(packet)

    def update_elements(self):
        t0 = time.time()
        try:
            while True:
                packet = rxqueue.get_nowait()
                self.stats["total_packets"] += 1
                self.stats["total_bytes"] += len(packet["data"])
                rxrootstream.apply(packet)
        except queue.Empty: pass
        for d in self.dash_targets:
            self.dash_targets[d].update_elements()
        self.after(10, self.update_elements)

    def update_stats(self):
        t = time.time()
        diff = t - self.stats["last_time"]
        self.stats["last_time"] = t
        self.stats_elements[0]["text"] = "{} packets".format(self.stats["total_packets"])
        self.stats_elements[1]["text"] = "{:.4f} packets/s".format((self.stats["total_packets"] - self.stats["last_packets"])/diff)
        self.stats_elements[2]["text"] = "{} B".format(self.stats["total_bytes"])
        self.stats_elements[3]["text"] = "{:.4f} B/s".format((self.stats["total_bytes"] - self.stats["last_bytes"])/diff)
        self.stats_elements[4]["text"] = "{:.4f}".format(t - self.ts)
        self.stats_elements[5]["text"] = "{} packets".format(rxqueue.qsize())
        self.stats["last_packets"] = self.stats["total_packets"]
        self.stats["last_bytes"] = self.stats["total_bytes"]
        self.after(500, self.update_stats)


def mainloop():
    global window
    window = MainWindow()
    start_sources()
    window.update_elements()
    try:
        tkinter.mainloop()
    finally:
        stop_sources()
