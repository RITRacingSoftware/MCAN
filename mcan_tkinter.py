import tkinter
from tkinter import ttk
import tkinter.font
import queue
from mcan import source, rootstream, rxqueue, start_sources, stop_sources, can_decode


window = None

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
        self.bootmenu = tkinter.Menu(self.menubar, tearoff=0)
        self.bootmenu.add_command(label="Bootloader", command=print)
        self.menubar.add_cascade(label="Bootloader", menu=self.bootmenu)

        self.dash = ttk.Treeview(self)
        self.dash["columns"] = ["bus", "id", "data", "cycle", "count"]
        self.dash.column("#0", width=30, stretch=tkinter.NO)
        self.dash.column("bus", width=50, stretch=tkinter.NO)
        self.dash.column("id", width=50, stretch=tkinter.NO)
        self.dash.column("data", width=300, stretch=tkinter.YES)
        self.dash.column("cycle", width=50, stretch=tkinter.NO, anchor=tkinter.E)
        self.dash.column("count", width=50, stretch=tkinter.NO)
        self.dash.heading("bus", text="Bus", anchor=tkinter.CENTER)
        self.dash.heading("id", text="ID", anchor=tkinter.CENTER)
        self.dash.heading("data", text="Data", anchor=tkinter.CENTER)
        self.dash.heading("cycle", text="Cycle", anchor=tkinter.CENTER)
        self.dash.heading("count", text="Count", anchor=tkinter.CENTER)
        self.dash.grid(row=0, column=0, sticky="news")

        self.dash_elements = []
        self.dash_data = {}


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
        if (packet["bus"], packet["id"]) in self.dash_data:
            pass
            self.dash_data[packet["bus"], packet["id"]]["raw"] = packet["data"]
            decoded = can_decode(packet)
            for d in decoded:
                if d not in self.dash_data[packet["bus"], packet["id"]]["data"]:
                    self.dash.insert(parent=iid, index="end", text="", values=("", "", d+": "+str(decoded[d])), iid=(iid[0], iid[1], d))
                else:
                    self.dash.item((iid[0], iid[1], d), values=("", "", d+": "+str(decoded[d])))
                self.dash_data[packet["bus"], packet["id"]]["data"][d] = decoded[d]
            self.dash.item(iid, values=(packet["bus"], packet["id"], " ".join(hex(x)[2:].rjust(2, "0") for x in packet["data"]), packet["ts"]-self.dash_data[packet["bus"], packet["id"]]["last_ts"]))
            self.dash_data[packet["bus"], packet["id"]]["last_ts"] = packet["ts"]
        else:
            decoded = can_decode(packet)
            self.dash_data[packet["bus"], packet["id"]] = {
                "expanded": True,
                "raw": packet["data"],
                "data": decoded,
                "last_ts": packet["ts"]
            }
            self.dash.insert(parent="", index=(index if index >= 0 else "end"), iid=iid, text="", 
                values=(packet["bus"], packet["id"], " ".join(hex(x)[2:].rjust(2, "0") for x in packet["data"])))
            for k in decoded:
                self.dash.insert(parent=iid, index="end", text="", values=("", "", k+": "+str(decoded[k])), iid=(iid[0], iid[1], k))

    def update(self):
        try:
            while True:
                packet = rxqueue.get_nowait()
                rootstream.apply(packet)
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
