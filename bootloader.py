import tkinter
from tkinter import ttk
import struct
import mcan_utils
import json

class Bootloader(tkinter.Toplevel):
    def __init__(self, txfunc):
        super().__init__()
        self.txfunc = txfunc
        self.requests = {}
        self.boards = {}
        self.closed = False
        self.context_target = None
        self.title("Bootloader")
        self.geometry("600x200")

        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        
        tkinter.Button(self, text="Boot all", command=self.boot_all).grid(row=0, column=0, sticky="w")
        tkinter.Button(self, text="List boards", command=self.boot_all).grid(row=0, column=1, sticky="w")
        self.table = ttk.LabelFrame(self, text="Boards")
        self.table.grid(row=1, column=0, columnspan=2, sticky="news")
        self.table.columnconfigure(0, minsize=30)
        self.table.columnconfigure(1, minsize=50, weight=1)
        self.table.columnconfigure(2, minsize=50, weight=1)
        self.table.columnconfigure(3, minsize=30)
        self.table.columnconfigure(4, minsize=30)
        self.table.columnconfigure(5, minsize=30)
        self.table.bind_all("<Button-3>", self.open_context_menu)
        ttk.Label(self.table, text="ID").grid(row=0, column=0)
        ttk.Label(self.table, text="Bank 1").grid(row=0, column=1)
        ttk.Label(self.table, text="Bank 2").grid(row=0, column=2)
        ttk.Label(self.table, text="State").grid(row=0, column=3)
        ttk.Label(self.table, text="BB").grid(row=0, column=4)
        ttk.Label(self.table, text="RB").grid(row=0, column=5)
        ttk.Label(self.table, text="Filename").grid(row=0, column=6)

        self.contextmenu = tkinter.Menu(self, tearoff=0)
        self.contextmenu.add_command(label="Program", command=self.program)
        self.contextmenu.add_command(label="Soft bank swap", command=self.soft_bank_swap)
        self.contextmenu.add_command(label="Toggle booting bank", command=self.full_bank_swap)
        self.contextmenu.bind("<FocusOut>", self.focusout)

        self.bind_all("<ButtonRelease-1>", self.click)

        with open("config.json") as f:
            self.config = json.load(f)

        #self.onrecv({'bus': 2, 'id': 1108475904, 'data': b'\x00\x00\x00\x00\x00\xef\xcd\xab', 'ts': 63604, 'fd': 1})
        #self.after(3000, self.simulate_state)


    def simulate_state(self):
        self.onrecv({'bus': 2, 'id': 1108475904, 'data': b'\x00\x01\x00\x00\xC0\xef\xcd\xab', 'ts': 63604, 'fd': 1})

    def send_command(self, bus, id, data):
        self.txfunc({"bus": bus, "data": data, "id": (id<<18) | (1<<30), "fd": True})

    def start_read(self, bus, id, address, length, bankmode):
        self.txfunc({"bus": bus, "data": struct.pack("<BB", length, bankmode), "id": (1<<30) | (id<<18) | address | (1<<17) | (1<<16), "fd": True})

    def boot_all(self):
        self.send_command(1, 0x7ff, b"\x55"*8)
        self.after(500, self.read_bank_identifiers)

    def read_bank_identifiers(self):
        for board in self.boards:
            self.requests[board] = "readname"
            self.start_read(1, board, 0x3ffe0>>3, 32, (self.boards[board]["bankstatus"]&1))

    def open_context_menu(self, event):
        tablepos = event.y_root - self.table.winfo_rooty()
        for board in self.boards:
            x, y, width, height = self.table.grid_bbox(0, self.boards[board]["index"]+1)
            if y <= tablepos < y + height:
                self.context_target = board
                try:
                    self.contextmenu.tk_popup(event.x_root, event.y_root)
                finally:
                    self.contextmenu.grab_release()
                break

    def focusout(self, event):
        if self.focus_get() != self.contextmenu:
            self.contextmenu.unpost()

    def click(self, event):
        if event.widget != self.focus_get():
            self.contextmenu.unpost()

    def program(self):
        print("Programming", self.context_target)

    def soft_bank_swap(self):
        print("Soft bank swap", self.context_target)

    def full_bank_swap(self):
        print("Full swap", self.context_target)

    def parse_response(self, packet, print_response=False):
        packet["board"] = (packet["id"]>>18) & 0x7f
        if print_response: print("bus {:02x}, id {}/{:08x} (device {})".format(packet["bus"], "EXT" if (packet["id"] & (1<<30)) else "STD", packet["id"] & 0x1fffffff, packet["board"]))
        if (packet["id"] & (1<<30)):
            if (packet["id"] & (1<<16)):
                packet["type"] = "data"
                if print_response: print("    Data", packet["data"])
            else:
                stat = struct.unpack("<BBHI", packet["data"])
                packet["type"] = "status"
                packet["status"], packet["bankstatus"], packet["flashstatus"], packet["bootstate"] = stat
                if print_response: print("    Status {:02x}, bank status {:02x}, FLASH status {:04x}, boot state {:08x}".format(*stat))

    def onrecv(self, packet):
        print("Bootloader received", packet, hex(packet["id"]))
        self.parse_response(packet, True)
        board = packet["board"]
        if board not in self.boards:
            row = len(self.boards)+1
            ttk.Label(self.table, text=str(board)).grid(row=row, column=0)
            b1label = ttk.Label(self.table, text="")
            b1label.grid(row=row, column=1)
            b2label = ttk.Label(self.table, text="")
            b2label.grid(row=row, column=2)
            statelabel = mcan_utils.BitFieldLabel(self.table, "Boot state", packet["bootstate"], [
                (24, lambda v: "State key "+("(correct)" if v == 0xABCDEF else "(invalid)")), 
                (1, mcan_utils.expand_wsbool("ERROR")),
                (1, mcan_utils.expand_wsbool("NB_ERROR")),
                (1, None),
                (1, mcan_utils.expand_wsbool("ENTER")),
                (1, mcan_utils.expand_wsbool("VERIFIED")),
                (1, mcan_utils.expand_wsbool("SOFT_SWITCHED")),
                (1, mcan_utils.expand_wsbool("VERIFY_SOFT_SWITCH")),
                (1, mcan_utils.expand_wsbool("VERIFY"))
            ], anchor="center")
            statelabel.grid(row=row, column=3)
            bblabel = ttk.Label(self.table, text=("2" if packet["bankstatus"] & 0x02 else "1"))
            bblabel.grid(row=row, column=4)
            rblabel = ttk.Label(self.table, text=("2" if packet["bankstatus"] & 0x01 else "1"))
            rblabel.grid(row=row, column=5)
            self.boards[board] = {
                "index": len(self.boards),
                "elements": [
                    b1label, b2label, statelabel, bblabel, rblabel
                ],
                "bankstatus": packet["bankstatus"],
                "bootstate": packet["bootstate"]
            }
        elif packet["type"] == "status":
            self.boards[board]["elements"][2].set_value(packet["bootstate"])
            self.boards[board]["elements"][3].config(text=("2" if packet["bankstatus"] & 0x02 else "1"))
            self.boards[board]["elements"][4].config(text=("2" if packet["bankstatus"] & 0x01 else "1"))
        elif packet["type"] == "data":
            if self.requests[board] == "readname":
                name = packet["data"].strip(b"\x00").decode()
                self.boards[board]["bank1"] = name
                self.boards[board]["elements"][0].config(text=name)
                self.requests[packet["board"]] = "readname2"
                self.start_read(1, board, 0x3ffe0>>3, 32, (self.boards[board]["bankstatus"]&1)^1)
            elif self.requests[board] == "readname2":
                name = packet["data"].strip(b"\x00").decode()
                self.boards[board]["bank2"] = name
                self.boards[board]["elements"][1].config(text=name)
                
        

