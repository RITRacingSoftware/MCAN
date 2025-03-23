import tkinter
from tkinter import ttk
from tkinter import filedialog
import struct
import mcan_utils
import json
import os.path

class Bootloader(tkinter.Toplevel):
    def __init__(self, txfunc):
        super().__init__()
        self.txfunc = txfunc
        self.boards = {}
        self.closed = False
        self.context_target = None
        self.title("Bootloader")
        self.geometry("600x200")

        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        
        tkinter.Button(self, text="Boot all", command=self.boot_all).grid(row=0, column=0, sticky="w")
        tkinter.Button(self, text="test", command=self.test_can).grid(row=0, column=1, sticky="w")
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
        self.contextmenu.add_command(label="Boot", command=self.boot)
        self.contextmenu.add_command(label="Soft bank swap", command=self.soft_bank_swap)
        self.contextmenu.add_command(label="Toggle booting bank", command=self.hard_bank_swap)
        self.contextmenu.bind("<FocusOut>", self.focusout)

        self.bind("<ButtonRelease-1>", self.click)

        with open("config.json") as f:
            self.config = {int(x) : y for x, y in json.load(f).items()}

        self.protocol("WM_DELETE_WINDOW", self.on_quit)

        #self.onrecv({'bus': 2, 'id': 1108475904, 'data': b'\x00\x00\x00\x00\x00\xef\xcd\xab', 'ts': 63604, 'fd': 1})
        #self.after(3000, self.simulate_state)

    def test_can(self):
        self.send_command(2, 0, b"\x00"*64)

    def simulate_state(self):
        self.onrecv({'bus': 2, 'id': 1108475904, 'data': b'\x00\x01\x00\x00\xC0\xef\xcd\xab', 'ts': 63604, 'fd': 1})

    def send_command(self, bus, id, data):
        self.txfunc({"bus": bus, "data": data, "id": (id<<18) | (1<<30), "fd": True})

    def start_read(self, bus, id, address, length, bankmode):
        self.txfunc({"bus": bus, "data": struct.pack("<BB", length, bankmode), "id": (1<<30) | (id<<18) | address | (1<<17) | (1<<16), "fd": True})

    def boot_all(self):
        for r in self.boards:
            self.boards[r]["operation"] = ""
        self.send_command(1, 0x7ff, b"\x55"*8)
        self.after(500, self.read_bank_identifiers)

    def boot(self, board=None):
        if board is None: board = self.context_target
        self.boards[board]["booted"] = True
        self.send_command(self.boards[board]["bus"], board, b"\x55"*8)

    def read_bank_identifiers(self):
        for board in self.boards:
            print("Reading bank identifiers", board)
            self.boards[board]["operation"] = "readname1"
            self.start_read(self.boards[board]["bus"], board, 0x3ffe0>>3, 32, (self.boards[board]["bankstatus"]&1))

    def start_write_from_generator(self, board):
        try:
            address, data = next(self.boards[board]["generator"])
        except StopIteration:
            self.hard_bank_swap(board)
            return
        self.boards[board]["offset"] = address
        self.boards[board]["lastwrite"] = data
        l = len(data)
        if l >= 32 and l&8:
            address |= (1<<15)
            l += 8
        self.txfunc({"bus": self.boards[board]["bus"], "data": data, "id": (1<<30) | (board<<18) | address | (1<<17), "fd": True})

    def generate_frames(self, fname):
        """Generate FDCAN frames from an IHEX file"""
        base_address = 0
        dwords = {}
        buf = bytearray([])
        with open(fname) as f:
            nrec = 0
            for record in f:
                nrec += 1
                length = int(record[1:3], 16)
                if record[7:9] == "02":
                    base_address = 16*int(record[9:13], 16)
                elif record[7:9] == "04":
                    base_address = int(record[9:13], 16)<<16
                elif record[7:9] == "00":
                    address = base_address + int(record[3:7], 16)
                    for i in range(length):
                        if (address & 0xfffffff8) not in dwords:
                            dwords[(address & 0xfffffff8)] = bytearray([255]*8)
                        dwords[(address & 0xfffffff8)][address & 0x07] = int(record[9+2*i:11+2*i], 16)
                        address += 1
            dword_addresses = [x for x in sorted(dwords.keys())]
            base_address = 0
            start_address = 0
            for i, a in enumerate(dword_addresses):
                if len(buf) == 0:
                    start_address = a
                    buf = dwords[a]
                elif a + 8 - start_address <= 64:
                    buf += bytearray([255]*(a - start_address - len(buf)))
                    buf += dwords[a]
                else:
                    yield (start_address - 0x08000000)>>3, buf
                    start_address = a
                    buf = dwords[a]

                if len(buf) == 64:
                    yield (start_address - 0x08000000)>>3, buf
                    buf = bytearray([])
                print("\rWritten {}/{} doublewords".format(i+1, len(dword_addresses)), end="")
            if buf:
                yield (start_address - 0x08000000)>>3, buf

    def program(self):
        print("Programming", self.context_target)
        self.boards[self.context_target]["operation"] = "program1"
        self.boards[self.context_target]["generator"] = self.generate_frames(self.config[self.context_target]["program"])
        self.send_command(self.boards[self.context_target]["bus"], self.context_target, b"\x55"*8)

    def soft_bank_swap(self, board=None):
        if board is None: board = self.context_target
        print("Soft bank swap", board)
        if not self.boards[board]["booted"]:
            print("Board is not booted")
            self.boards[board]["operation"] = "softswap"
            self.send_command(self.boards[board]["bus"], board, b"\x55"*8)
        else:
            self.boards[board]["operation"] = ""
            self.send_command(self.boards[board]["bus"], board, b"\x01")

    def hard_bank_swap(self, board=None):
        if board is None: board = self.context_target
        print("Full swap", board)
        if self.boards[board]["operation"] == "hardswap1":
            self.boards[board]["operation"] = "hardswap2"
            print("Hard swap: switching to NB bank")
            self.send_command(self.boards[board]["bus"], board, b"\x01")
        elif self.boards[board]["operation"] == "hardswap2":
            print("Hard swap: Entering NB bootloader")
            self.boards[board]["operation"] = "hardswap3"
            self.send_command(self.boards[board]["bus"], board, b"\x55"*8)
        elif self.boards[board]["operation"] == "hardswap3":
            print("Hard swap: NB boot reset")
            self.boards[board]["operation"] = "hardswap4"
        elif self.boards[board]["operation"] == "hardswap4":
            print("Hard swap: Verifying")
            self.boards[board]["operation"] = "hardswap5"
            self.send_command(self.boards[board]["bus"], board, b"\x02")
        elif self.boards[board]["operation"] == "hardswap5":
            print("Hard swap: finalizing")
            self.boards[board]["operation"] = ""
            self.send_command(self.boards[board]["bus"], board, b"\x03")
        else:
            self.boards[board]["operation"] = "hardswap1"
            self.send_command(self.boards[board]["bus"], board, b"\x55"*8)

    def parse_response(self, packet, print_response=False):
        packet["board"] = (packet["id"]>>18) & 0x7f
        if (packet["id"] & (1<<30)):
            if (packet["id"] & (1<<16)):
                packet["type"] = "data"
                #if print_response: print("    Data", packet["data"])
            else:
                if print_response: print("bus {:02x}, id {}/{:08x} (device {})".format(packet["bus"], "EXT" if (packet["id"] & (1<<30)) else "STD", packet["id"] & 0x1fffffff, packet["board"]))
                stat = struct.unpack("<BBHI", packet["data"])
                packet["type"] = "status"
                packet["status"], packet["bankstatus"], packet["flashstatus"], packet["bootstate"] = stat
                if print_response: print("    Status {:02x}, bank status {:02x}, FLASH status {:04x}, boot state {:08x}".format(*stat))

    def onrecv(self, packet):
        #print("Bootloader received", packet, hex(packet["id"]))
        self.parse_response(packet, True)
        board = packet["board"]
        if board not in self.boards:
            row = len(self.boards)+1
            if board not in self.config:
                self.config[board] = {
                    "program": ""
                }
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
            fnlabel = ttk.Label(self.table, text=os.path.basename(self.config[board]["program"]), anchor="center")
            fnlabel.grid(row=row, column=6, sticky="news")
            fnlabel.bind("<Double-Button-1>", lambda evt: self.set_filename(board))
            self.boards[board] = {
                "index": len(self.boards),
                "bus": packet["bus"],
                "elements": [
                    b1label, b2label, statelabel, bblabel, rblabel, fnlabel
                ],
                "bankstatus": packet["bankstatus"],
                "bootstate": packet["bootstate"],
                "operation": "",
                "offset": 0,
                "lastwrite": b"",
                "generator": None,
                "booted": True
            }
        elif packet["type"] == "status":
            self.boards[board]["booted"] = True
            self.boards[board]["elements"][2].set_value(packet["bootstate"])
            self.boards[board]["elements"][3].config(text=("2" if packet["bankstatus"] & 0x02 else "1"))
            self.boards[board]["elements"][4].config(text=("2" if packet["bankstatus"] & 0x01 else "1"))
            # Status message after reset
            if self.boards[board]["operation"] == "program1":
                self.boards[board]["operation"] = "program2"
            # Board has entered bootloader and is ready to receive data
            elif self.boards[board]["operation"] == "program2":
                self.boards[board]["operation"] = "write"
                self.start_write_from_generator(board)
            elif self.boards[board]["operation"] == "softswap":
                print("Continuing with soft swap")
                self.soft_bank_swap(board)
            elif self.boards[board]["operation"].startswith("hardswap"):
                print("Continuing with hard swap")
                self.hard_bank_swap(board)

        elif packet["type"] == "data":
            if self.boards[board]["operation"] == "readname1":
                name = packet["data"].strip(b"\x00").decode()
                self.boards[board]["bank1"] = name
                self.boards[board]["elements"][0].config(text=name)
                self.boards[board]["operation"] = "readname2"
                self.start_read(self.boards[board]["bus"], board, 0x3ffe0>>3, 32, (self.boards[board]["bankstatus"]&1)^1)
            elif self.boards[board]["operation"] == "readname2":
                name = packet["data"].strip(b"\x00").decode()
                self.boards[board]["bank2"] = name
                self.boards[board]["elements"][1].config(text=name)
                self.boards[board]["booted"] = False
                self.send_command(self.boards[board]["bus"], board, b"\x00")
            elif self.boards[board]["operation"] == "write":
                readback = packet["data"]
                if packet["id"] & (1<<15): readback = readback[:-8]
                if self.boards[board]["offset"] != packet["id"]&0x7fff:
                    print("ERROR: Incorrect address received ({}, should be {})".format(packet["id"]&0x7fff, self.boards[board]["offset"]))
                    self.boards[board]["operation"] = ""
                elif self.boards[board]["lastwrite"] != readback:
                    print("ERROR: Incorrect data read back")
                    self.boards[board]["operation"] = ""
                else:
                    self.start_write_from_generator(board)

    
    #######################################################
    # TKinter callback functions
    #######################################################

    def on_quit(self):
        self.closed = True
        self.destroy()

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

    def set_filename(self, board):
        self.config[board]["program"] = filedialog.askopenfilename(filetypes=[("HEX file", "*.ihex")])
        self.boards[board]["elements"][5].config(text=os.path.basename(self.config[board]["program"]))

