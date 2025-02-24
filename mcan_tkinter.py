import tkinter
from tkinter import ttk
import tkinter.font
import queue
from mcan import source, rootstream, rxqueue, start_sources, stop_sources, can_decode

root = None
dash = None
dash_elements = []
dash_data = {}

def dash(packet):
    global dash_elements, dash_data
    index = 0
    iid = (packet["bus"], packet["id"])
    for i in range(len(dash_elements)):
        if iid > dash_elements[i]:
            index += 1
        if dash_elements[i] == iid:
            index = i
            break
    else:
        dash_elements.insert(index, iid)
        print("inserting", iid, index, dash_elements)
    if (packet["bus"], packet["id"]) in dash_data:
        pass
        dash_data[packet["bus"], packet["id"]]["raw"] = packet["data"]
        decoded = can_decode(packet)
        for d in decoded:
            if d not in dash_data[packet["bus"], packet["id"]]["data"]:
                dash.insert(parent=iid, index="end", text="", values=("", "", d+": "+str(decoded[d])), iid=(iid[0], iid[1], d))
            else:
                dash.item((iid[0], iid[1], d), values=("", "", d+": "+str(decoded[d])))
            dash_data[packet["bus"], packet["id"]]["data"][d] = decoded[d]
        dash.item(iid, values=(packet["bus"], packet["id"], " ".join(hex(x)[2:].rjust(2, "0") for x in packet["data"])))
    else:
        decoded = can_decode(packet)
        dash_data[packet["bus"], packet["id"]] = {
            "expanded": True,
            "raw": packet["data"],
            "data": decoded
        }
        dash.insert(parent="", index=(index if index >= 0 else "end"), iid=iid, text="", 
            values=(packet["bus"], packet["id"], " ".join(hex(x)[2:].rjust(2, "0") for x in packet["data"])))
        for k in decoded:
            dash.insert(parent=iid, index="end", text="", values=("", "", k+": "+str(decoded[k])), iid=(iid[0], iid[1], k))

def update():
    try:
        while True:
            packet = rxqueue.get_nowait()
            rootstream.apply(packet)
    except queue.Empty: pass
    root.after(10, update)

def mainloop():
    global root, dash
    root = tkinter.Tk()
    root.title("MCAN v0.1")
    root.rowconfigure(0, weight=1)
    root.columnconfigure(0, weight=1)
    default_font = tkinter.font.nametofont("TkDefaultFont")
    print(default_font, default_font.actual("family"), default_font.actual("size"))
    style = ttk.Style(root)
    style.configure("Treeview", font=("Ubuntu Mono", 10))
    dash = ttk.Treeview(root)
    dash["columns"] = ["bus", "id", "data"]
    dash.column("#0", width=30, stretch=tkinter.NO)
    dash.column("bus", width=50, stretch=tkinter.NO)
    dash.column("id", width=50, stretch=tkinter.NO)
    dash.column("data", width=300, stretch=tkinter.YES)
    dash.heading("bus", text="Bus", anchor=tkinter.CENTER)
    dash.heading("id", text="ID", anchor=tkinter.CENTER)
    dash.heading("data", text="Data", anchor=tkinter.CENTER)
    dash.grid(row=0, column=0, sticky="news")
    start_sources()
    update()
    try:
        tkinter.mainloop()
    finally:
        stop_sources()
