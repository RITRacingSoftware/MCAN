import sys
import threading
import os
import cantools
import queue

import tkinter
from tkinter import ttk
import tkinter.font

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

def can_decode(packet):
    if packet["bus"] not in can_db: return {}
    db = can_db[packet["bus"]]
    if packet["id"] not in db._frame_id_to_message: return {}
    return db.get_message_by_frame_id(packet["id"]), db.decode_message(packet["id"], packet["data"])


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


def dash(packet):
    if window is not None: window.dash_update(packet)

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

        self.dash = ttk.Treeview(self)
        self.dash["columns"] = ["bus", "id", "signame", "data", "cycle", "count"]
        self.dash.column("#0", width=30, stretch=tkinter.NO)
        self.dash.column("bus", width=50, stretch=tkinter.NO)
        self.dash.column("id", width=50, stretch=tkinter.NO)
        self.dash.column("signame", width=300, stretch=tkinter.YES)
        self.dash.column("data", width=300, stretch=tkinter.YES)
        self.dash.column("cycle", width=50, stretch=tkinter.NO, anchor=tkinter.E)
        self.dash.column("count", width=50, stretch=tkinter.NO)
        self.dash.heading("bus", text="Bus", anchor=tkinter.CENTER)
        self.dash.heading("id", text="ID", anchor=tkinter.CENTER)
        self.dash.heading("signame", text="Signal name", anchor=tkinter.CENTER)
        self.dash.heading("data", text="Data", anchor=tkinter.CENTER)
        self.dash.heading("cycle", text="Cycle", anchor=tkinter.CENTER)
        self.dash.heading("count", text="Count", anchor=tkinter.CENTER)
        self.dash.grid(row=0, column=0, sticky="news")

        self.config(menu=self.menubar)

        self.dash_elements = []
        self.dash_data = {}
        self.boot = None
        
        rxrootstream.filter(lambda packet: packet["id"]&(1<<30)).exec(self.forward_boot)

    def forward_boot(self, packet):
        if self.boot is not None and not self.boot.closed:
            self.boot.onrecv(packet)

    def open_bootloader(self):
        self.boot = bootloader.Bootloader(transmit)

    def dash_update(self, packet):
        index = 0
        iid = (packet["bus"], packet["id"])
        for i in range(len(self.dash_elements)):
            if iid > self.dash_elements[i]:
                index += 1
            if self.dash_elements[i] == iid:
                index = i
                break
        else:
            self.dash_elements.insert(index, iid)
            print("inserting", iid, index, self.dash_elements)
        if iid in self.dash_data:
            self.dash_data[iid]["raw"] = packet["data"]
            self.dash_data[iid]["count"] += 1
            message, decoded = can_decode(packet)
            for d in decoded:
                if d not in self.dash_data[packet["bus"], packet["id"]]["data"]:
                    self.dash.insert(parent=iid, index="end", text="", values=("", "", d+": "+str(decoded[d])), iid=(iid[0], iid[1], d))
                else:
                    self.dash.item((iid[0], iid[1], d), values=("", "", d, str(decoded[d])))
                self.dash_data[packet["bus"], packet["id"]]["data"][d] = decoded[d]
            self.dash.item(iid, values=(packet["bus"], packet["id"], message.name, " ".join(hex(x)[2:].rjust(2, "0") for x in packet["data"]), packet["ts"]-self.dash_data[iid]["last_ts"], self.dash_data[iid]["count"]))
            self.dash_data[packet["bus"], packet["id"]]["last_ts"] = packet["ts"]
        else:
            message, decoded = can_decode(packet)
            self.dash_data[iid] = {
                "expanded": True,
                "raw": packet["data"],
                "data": decoded,
                "last_ts": packet["ts"],
                "count": 1
            }
            self.dash.insert(parent="", index=(index if index >= 0 else "end"), iid=iid, text="", 
                values=(packet["bus"], packet["id"], message.name, " ".join(hex(x)[2:].rjust(2, "0") for x in packet["data"]), "", self.dash_data[iid]["count"]))
            for k in decoded:
                self.dash.insert(parent=iid, index="end", text="", values=("", "", k, str(decoded[k])), iid=(iid[0], iid[1], k))

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
