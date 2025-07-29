import tkinter
from tkinter import ttk
import struct


class CANDashboard(tkinter.Frame):
    def __init__(self, master, name, can_db, *args, **kwargs):
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
        
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.dash.yview)
        vsb.grid(row=0, column=1, sticky="news")
        self.dash.config(yscrollcommand=vsb.set)

        self.dash_elements = []
        self.dash_data = {}
        self.dash_changes = {}
        self.can_decode = can_db
        
        try:
            self.pcapfile = open("/tmp/log{}.pcap".format(name), "wb")
            self.pcapfile.write(b"\xd4\xc3\xb2\xa1\x02\x00\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff\x00\x00\xe3\x00\x00\x00")
        except:
            self.pcapfile = None

    def apply_packet(self, packet, dec, tree, el):
        if not el["signals"]:
            for sig in tree:
                mux = not isinstance(sig, str)
                name = list(sig.keys())[0] if mux else sig
                l = {
                    "iid": el["iid"] + (name,),
                    "mux": mux,
                    "name": name,
                }
                el["signals"].append(l)
                if mux: l["value"] = {}
                else: l["value"] = dec[l["name"]]
                self.dash.insert(parent=el["iid"], index="end", text="", values=("", "", l["name"], l["value"], "", ""), iid=l["iid"])
        for t, l in zip(tree, el["signals"]):
            v = dec[l["name"]]
            if l["mux"]:
                if v not in l["value"]:
                    l["value"][v] = {
                        "iid": l["iid"] + (v,),
                        "name": "",
                        "raw": (v,),
                        "signals": [],
                        "count": 0,
                        "cycle": 0,
                        "last_ts": packet["ts"]
                    }
                    self.dash.insert(parent=l["iid"], index="end", iid=l["iid"]+(v,), text="", 
                        values=("", "", l["value"][v]["name"], v , "", 0))
                l["value"][v]["count"] += 1
                l["value"][v]["cycle"] = packet["ts"] - l["value"][v]["last_ts"]
                l["value"][v]["last_ts"] = packet["ts"]
                self.apply_packet(packet, dec, t[l["name"]][v], l["value"][v])
            else:
                l["value"] = dec[l["name"]]


    def dash_update(self, packet):
        if self.pcapfile is not None:
            length = len(packet["data"]) + 8
            can_head = struct.pack(">I", packet["id"])
            can_head += struct.pack("<4B", len(packet["data"]), 0x04 if packet["fd"] else 0x00, 0, 0)
            self.pcapfile.write(struct.pack("<4I", int(packet["ts"]//1000000), int(packet["ts"]%1000000), length, length)+can_head+packet["data"])

        index = 0
        iid = (packet["bus"], packet["id"])
        msg, dec = self.can_decode(packet)
        # Determine where the new packet should be inserted so the IDs are in order
        for i in range(len(self.dash_elements)):
            if iid > self.dash_elements[i]["iid"]:
                index += 1
            if self.dash_elements[i]["iid"] == iid:
                index = i
                break
        else:
            el = {
                "iid": iid,
                "name": msg.name if msg is not None else "",
                "raw": packet["data"],
                "signals": [],
                "count": 0,
                "cycle": 0,
                "last_ts": packet["ts"]
            }
            self.dash_elements.insert(index, el)
            self.dash.insert(parent="", index=(index if index >= 0 else "end"), iid=iid, text="", 
                values=(packet["bus"], packet["id"], el["name"], " ".join(hex(x)[2:].rjust(2, "0") for x in packet["data"]), "", 0))
            if msg is not None:
                self.apply_packet(packet, dec, msg.signal_tree, el)
            #print("inserting", iid, index, self.dash_elements[index])
            return
        
        el = self.dash_elements[index]
        el["count"] += 1
        el["cycle"] = packet["ts"] - el["last_ts"]
        el["last_ts"] = packet["ts"]
        el["raw"] = packet["data"]
        if msg is not None:
            self.apply_packet(packet, dec, msg.signal_tree, el)
    
    def update_element(self, el):
        if "signals" in el:
            self.dash.item(el["iid"], values=(el["iid"][0], el["iid"][1], el["name"], " ".join(hex(x)[2:].rjust(2, "0") for x in el["raw"]), el["cycle"], el["count"]))
            for l in el["signals"]:
                self.update_element(l)
        else:
            if el["mux"]:
                self.dash.item(el["iid"], values=("", "", el["name"], "", "", ""))
                for m in el["value"]:
                    self.update_element(el["value"][m])
            else:
                self.dash.item(el["iid"], values=("", "", el["name"], el["value"], "", ""))

    def update_elements(self):
        for el in self.dash_elements:
            self.update_element(el)

    def close(self):
        if self.pcapfile is not None:
            self.pcapfile.close()
            self.pcapfile = None
