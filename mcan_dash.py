import tkinter
from tkinter import ttk
import struct

class CANDashboard(tkinter.Frame):
    def __init__(self, master, name, *args, **kwargs):
        super().__init__(master, *args, **kwargs)

        self.name = name

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
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        
        self.dash_elements = []
        self.dash_data = {}
        
        self.pcapfile = open("/tmp/log{}.pcap".format(name), "wb")
        self.pcapfile.write(b"\xd4\xc3\xb2\xa1\x02\x00\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff\x00\x00\xe3\x00\x00\x00")

    def dash_update(self, packet):
        if self.pcapfile is not None:
            length = len(packet["data"]) + 8
            can_head = struct.pack(">I", packet["id"])
            can_head += struct.pack("<4B", len(packet["data"]), 0x04 if packet["fd"] else 0x00, 0, 0)
            self.pcapfile.write(struct.pack("<4I", int(packet["ts"]//1000000), int(packet["ts"]%1000000), length, length)+can_head+packet["data"])

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
            message, decoded = self.master.can_decode(packet)
            for d in decoded:
                if d not in self.dash_data[packet["bus"], packet["id"]]["data"]:
                    self.dash.insert(parent=iid, index="end", text="", values=("", "", d+": "+str(decoded[d])), iid=(iid[0], iid[1], d))
                else:
                    self.dash.item((iid[0], iid[1], d), values=("", "", d, str(decoded[d])))
                self.dash_data[packet["bus"], packet["id"]]["data"][d] = decoded[d]
            self.dash.item(iid, values=(packet["bus"], packet["id"], message.name, " ".join(hex(x)[2:].rjust(2, "0") for x in packet["data"]), packet["ts"]-self.dash_data[iid]["last_ts"], self.dash_data[iid]["count"]))
            self.dash_data[packet["bus"], packet["id"]]["last_ts"] = packet["ts"]
        else:
            message, decoded = self.master.can_decode(packet)
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

    def close(self):
        self.pcapfile.close()
        self.pcapfile = None
