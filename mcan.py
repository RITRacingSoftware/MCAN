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

class MCan:
    def __init__(self):
        self.rxrootstream = CANStream()
        self.txrootstream = CANStream()
        
        self.boot_manager = bootloader.BootManager(self.transmit)
        self.rxrootstream.filter(lambda packet: packet["id"]&(1<<30)).exec(self.boot_manager.onrecv)

        self.total_packets = 0
        self.last_packets = 0
        self.total_bytes = 0
        self.last_bytes = 0
        self.last_time = 0
        self.start_time = time.time()

        self.source_list = []

    def close(self):
        self.stop_sources()
        self.boot_manager.close()

    def source(self, s):
        s.rxrootstream = self.rxrootstream
        self.source_list.append(s)

    def start_sources(self):
        for s in self.source_list: 
            s.start()

    def stop_sources(self):
        for s in self.source_list:
            s.stop()

    def transmit(self, packet):
        self.txrootstream.apply(packet)
    
    def onrecv(self, packet):
        self.total_packets += 1
        self.total_bytes += len(packet["data"])
        self.rxrootstream.apply(packet)

    def dump_stats(self):
        t = time.time()
        diff = t - self.last_time
        stats = {
            "total_packets": self.total_packets,
            "total_bytes": self.total_bytes,
            "packet_rate": (self.total_packets - self.last_packets)/diff,
            "byte_rate": (self.total_bytes - self.last_bytes)/diff,
            "total_time": t - self.start_time
        }
        self.last_time = t
        self.last_packets = self.total_packets
        self.last_bytes = self.total_bytes
        for s in self.source_list:
            if hasattr(s, "dump_stats"):
                stats.update(**s.dump_stats())
        return stats

class MainWindow(tkinter.Tk):
    def __init__(self, inst):
        super().__init__()
        self.title("MCAN v0.1")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.inst = inst
        style = ttk.Style(self)
        style.configure("Treeview", font=("Ubuntu Mono", 10))

        self.menubar = tkinter.Menu(self)
        self.bootmenu = tkinter.Menu(self.menubar, tearoff=0)
        self.bootmenu.add_command(label="Bootloader", command=self.open_bootloader)
        self.menubar.add_cascade(label="Bootloader", menu=self.bootmenu)
        self.config(menu=self.menubar)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="news")

        self.stats_table = ttk.LabelFrame(self, text="Statistics")
        self.stats_table.grid(row=1, column=0, sticky="news")

        self.stats_layout = [
            [["total_packets", "Total packets", "{} packets"], ["packet_rate", "Packet rate", "{:.4f} packets/s"]],
            [["total_bytes", "Total bytes", "{} B"], ["byte_rate", "Byte rate", "{:.4f} B/s"]],
            [["total_time", "Total time", "{:.4f} s"], ["dash_backlog", "Backlog", "{} packets"]],
            [["replay_backlog", "Replay backlog", "{:.4f}"]]
        ]
        self.stats_elements = []
        self.stats_table.grid_columnconfigure(1, weight=1, minsize=100)
        self.stats_table.grid_columnconfigure(3, weight=1, minsize=100)

        self.grid_rowconfigure(0, weight=1)

        self.boot = None

        self.dash_targets = {}
        self.dash_queue = queue.Queue()
        
        self.ts = time.time()

    def close(self):
        self.inst.close()
        for d in self.dash_targets:
            self.dash_targets[d].close()

    def can_decode(self, packet):
        if packet["bus"] not in can_db: return None, {}
        db = can_db[packet["bus"]]
        if packet["id"] not in db._frame_id_to_message: return None, {}
        return db.get_message_by_frame_id(packet["id"]), db.decode_message(packet["id"], packet["data"])

    def open_bootloader(self):
        self.boot = mcan_bootloader.BootloaderMenu(self.inst.boot_manager)

    def dash_update(self, packet, target):
        self.dash_queue.put((packet, target))

    def update_elements(self):
        t0 = time.time()
        try:
            while True:
                packet, target = self.dash_queue.get_nowait()
                if target not in self.dash_targets:
                    self.dash_targets[target] = mcan_dash.CANDashboard(self, target, self.can_decode)
                    self.notebook.add(self.dash_targets[target], text=target)
                self.dash_targets[target].dash_update(packet)
        except queue.Empty: pass
        for d in self.dash_targets:
            self.dash_targets[d].update_elements()
        self.after(10, self.update_elements)

    def update_stats(self):
        stat = self.inst.dump_stats()
        stat["dash_backlog"] = self.dash_queue.qsize()
        self.after(500, self.update_stats)
        if self.stats_elements == []:
            for rn, r in enumerate(self.stats_layout):
                row = []
                if [x for x in r if x[0] in stat]:
                    for cn, c in enumerate(r):
                        row.append(tkinter.Label(self.stats_table, text="", font=(None, 10)))
                        row[-1].grid(row=rn, column=2*cn+1, sticky="w")
                        tkinter.Label(self.stats_table, text=self.stats_layout[rn][cn][1], font=(None, 10)).grid(row=rn, column=2*cn, sticky="w")
                self.stats_elements.append(row)

        for rn, r in enumerate(self.stats_layout):
            if [x for x in r if x[0] in stat] == []: continue
            for cn, c in enumerate(r):
                self.stats_elements[rn][cn]["text"] = self.stats_layout[rn][cn][2].format(stat[self.stats_layout[rn][cn][0]])

    def mainloop(self):
        self.inst.start_sources()
        self.update_stats()
        self.update_elements()
        try:
            tkinter.mainloop()
        finally:
            print("closing")
            self.close()
