import tkinter
from tkinter import ttk
import struct
import mcan_utils

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

        self.onrecv({'bus': 2, 'id': 1108475904, 'data': b'\x00\x00\x00\x00\x00\xef\xcd\xab', 'ts': 63604, 'fd': 1})
        self.after(3000, self.simulate_state)


    def simulate_state(self):
        self.onrecv({'bus': 2, 'id': 1108475904, 'data': b'\x00\x01\x00\x00\xC0\xef\xcd\xab', 'ts': 63604, 'fd': 1})

    def send_command(self, bus, id, data):
        self.txfunc({"bus": bus, "data": data, "id": (id<<18) | (1<<30), "fd": True})

    def boot_all(self):
        self.send_command(1, 0x7ff, b"\x55"*8)

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
        if packet["board"] not in self.boards:
            row = len(self.boards)+1
            ttk.Label(self.table, text=str(packet["board"])).grid(row=row, column=0)
            #statelabel = ttk.Label(self.table, text=hex(packet["bootstate"])[2:].rjust(8, "0").upper(), font=("Ubuntu Mono", 0))
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
            self.boards[packet["board"]] = {
                "index": len(self.boards),
                "elements": [
                    None, None, statelabel, bblabel, rblabel
                ],
                "bankstatus": packet["bankstatus"],
                "bootstate": packet["bootstate"]
            }
        else:
            self.boards[packet["board"]]["elements"][2].set_value(packet["bootstate"])
            self.boards[packet["board"]]["elements"][3].config(text=("2" if packet["bankstatus"] & 0x02 else "1"))
            self.boards[packet["board"]]["elements"][4].config(text=("2" if packet["bankstatus"] & 0x01 else "1"))
        

