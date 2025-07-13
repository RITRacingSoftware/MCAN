import struct
import json
import os.path
import collections
import threading
import time
import os
import select

from mcan import mcan_utils

BOOT_STATE_KEY =          0xABCDEF00
BOOT_STATE_NORMAL =             0x00
BOOT_STATE_VERIFY =             0x01
BOOT_STATE_VERIFY_SOFT_SWITCH = 0x02
BOOT_STATE_SOFT_SWITCHED =      0x04
BOOT_STATE_VERIFIED =           0x08
BOOT_STATE_ENTER =              0x10
BOOT_STATE_ERROR =              0x80
BOOT_STATE_NB_ERROR =           0x40


BOOT_STATUS_OK =                0x00
BOOT_STATUS_INVALID_ADDRESS =   0x01
BOOT_STATUS_ERASE_ERROR =       0x02
BOOT_STATUS_PROG_ERROR =        0x03
BOOT_STATUS_STATE_ERROR =       0x04
BOOT_STATUS_NB_ERROR =          0x05
BOOT_STATUS_ALREADY_BOOTED =    0x06
BOOT_STATUS_NO_BSM =            0x07
BOOT_STATUS_SOFTSWAP_SUCCESS =  0x08
BOOT_STATUS_MAINBANK =          0x09

class BootloaderError(Exception):
    pass

class BootManager:
    def __init__(self, txfunc):
        self.txfunc = txfunc
        self.boards = {}

        self.on_board_state_change = lambda *args: None
        self.on_board_added = lambda *args: None
        self.on_error = lambda *args: None

        with open("config.json") as f:
            self.config = {int(x) : y for x, y in json.load(f).items()}
        for board in self.config:
            self.boards[board] = {
                "index": len(self.boards),
                "bus": 0,
                "bankstatus": 0,
                "bootstate": 0,
                "offset": 0,
                "lastwrite": b"",
                "booted": True,
                "op_generator": None
            }

        self.c70_state = False

        self.timeouts = {}

        self.abortpipe_r, self.abortpipe_w = os.pipe()
        self.timeout_thread = threading.Thread(target=self.check_timeouts)
        self.timeout_thread.start()

    def check_timeouts(self):
        while True:
            t = time.time()
            tv = list(self.timeouts.keys())
            for x in tv:
                if t >= self.timeouts[x][0]:
                    func = self.timeouts[x][1]
                    del self.timeouts[x]
                    func(x)
            rlist, wlist, xlist = select.select([self.abortpipe_r], [], [], 0.1)
            if rlist: break
        os.close(self.abortpipe_r)

    def txctl(self, enabled):
        print("txctl", enabled)
        self.txfunc({"bus": 5, "data": b"\x01" if enabled else b"\x00", "id": 0, "fd": False})
        self.timeouts["txctl"] = (time.time() + 0.5, lambda *args: self.txctl(enabled))

    def c70ctl(self, enabled):
        if enabled:
            self.txfunc({"bus": 2, "data": b"\x00"*8, "id": 1793, "fd": False})
        else:
            self.txfunc({"bus": 2, "data": b"\xff"*8, "id": 1793, "fd": False})

    def simulate_state(self):
        self.onrecv({'bus': 2, 'id': 1108475904, 'data': b'\x00\x01\x00\x00\xC0\xef\xcd\xab', 'ts': 63604, 'fd': 1})

    def send_command(self, bus, id, data):
        self.txfunc({"bus": bus, "data": data, "id": (id<<18) | (1<<30), "fd": True})

    def make_command(self, bus, id, data):
        return {"bus": bus, "data": data, "id": (id<<18) | (1<<30), "fd": True}

    def make_read(self, bus, id, address, length, bankmode):
        return {"bus": bus, "data": struct.pack("<BB", length, bankmode), "id": (1<<30) | (id<<18) | address | (1<<17) | (1<<16), "fd": True}
    
    def make_write(self, bus, id, address, data):
        return {"bus": bus, "data": data, "id": (1<<30) | (id<<18) | address | (1<<17), "fd": True}

    def start_operation(self, board, gen):
        self.boards[board]["op_generator"] = gen
        self.txfunc(next(gen))

    #######################################################
    # Generator functions for operations
    #######################################################
    
    def boot_gen(self, board):
        bus = self.boards[board]["bus"]
        yield self.make_command(bus, board, b"\x55"*8)
        status = self.boards[board]["last_packet"]["status"]
        if status == BOOT_STATUS_MAINBANK or status == BOOT_STATUS_SOFTSWAP_SUCCESS:
            # Wait for BOOT_STATUS_OK message
            yield None
        elif status == BOOT_STATUS_ALREADY_BOOTED:
            print("Already booted")
            return
        else:
            print("Invalid response received", self.boards[board]["last_packet"])
            raise BootloaderError
        if self.boards[board]["last_packet"]["status"] == BOOT_STATUS_OK:
            print("Booted successfully")

    def read_bank_identifiers_gen(self, board):
        bus = self.boards[board]["bus"]
        yield self.make_read(bus, board, 0x3ffe0>>3, 32, (self.boards[board]["bankstatus"]&1))
        name = self.boards[board]["last_packet"]["data"].strip(b"\x00").decode()
        print("First bank", name)
        self.boards[board]["bank1"] = name
        self.on_board_state_change(board)
        yield self.make_read(bus, board, 0x3ffe0>>3, 32, (self.boards[board]["bankstatus"]&1)^1)
        name = self.boards[board]["last_packet"]["data"].strip(b"\x00").decode()
        print("Second bank", name)
        self.boards[board]["bank2"] = name
        self.on_board_state_change(board)
        yield self.make_command(bus, board, b"\x00")

    def soft_bank_swap_gen(self, board):
        bus = self.boards[board]["bus"]
        yield from self.boot_gen(board)
        yield self.make_command(bus, board, b"\x01")
        packet = self.boards[board]["last_packet"]
        if packet["status"] == BOOT_STATUS_MAINBANK and packet["bootstate"] == BOOT_STATE_KEY | BOOT_STATE_NB_ERROR | BOOT_STATE_VERIFY_SOFT_SWITCH:
            raise BootloaderError("BSM in non-booting bank did not run")
        if not (packet["status"] == BOOT_STATUS_SOFTSWAP_SUCCESS and packet["bootstate"] == BOOT_STATE_KEY | BOOT_STATE_SOFT_SWITCHED):
            raise BootloaderError("Unknown error while soft switching (status {}, state {:08x})".format(packet["status"], packet["bootstate"]))
        print("After soft swap", self.boards[board]["last_packet"])

    def hard_bank_swap_gen(self, board):
        bus = self.boards[board]["bus"]
        yield from self.soft_bank_swap_gen(board)
        yield from self.boot_gen(board)
        yield self.make_command(bus, board, b"\x02")
        packet = self.boards[board]["last_packet"]
        if packet["status"] != BOOT_STATUS_OK:
            raise BootloaderError("Board returned status {}".format(packet["status"]))
        if packet["bootstate"] != BOOT_STATE_KEY | BOOT_STATE_VERIFIED:
            raise BootloaderError("Board in invalid state after verify: {:08x}".format(packet["bootstate"]))
        yield self.make_command(bus, board, b"\x03")

    def reset_gen(self, board):
        bus = self.boards[board]["bus"]
        yield self.make_command(bus, board, b"\x00")
        print("Reset completed")

    def write_and_verify_gen(self, board, address, data):
        l = len(data)
        if l >= 32 and l&8:
            data += b"\xff"*8
            address |= (1<<15)
        packet = self.make_write(self.boards[board]["bus"], board, address, data)
        yield packet
        packet = self.boards[board]["last_packet"]
        if packet["type"] != "data":
            raise BootloaderError("Failed to verify write: no data packet received")
        recv = packet["data"]
        if recv[:l] != data[:l]:
            print("ERROR")
            print("    "+"".join(hex(x)[2:].rjust(2, "0") for x in data[:l]))
            print("    "+"".join(hex(x)[2:].rjust(2, "0") for x in recv[:l]))
            raise BootloaderError("Failed to verify write: incorrect data")


    def write_and_verify_from_file_gen(self, board, fname):
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
                    yield from self.write_and_verify_gen(board, (start_address - 0x08000000)>>3, buf)
                    start_address = a
                    buf = dwords[a]

                if len(buf) == 64:
                    yield from self.write_and_verify_gen(board, (start_address - 0x08000000)>>3, buf)
                    buf = bytearray([])
                print("\rWritten {}/{} doublewords".format(i+1, len(dword_addresses)), end="")
            if buf:
                yield from self.write_and_verify_gen(board, (start_address - 0x08000000)>>3, buf)
        print()
    
    def program_gen(self, board):
        print("program_gen", board)
        yield from self.boot_gen(board)
        yield from self.write_and_verify_from_file_gen(board, self.config[board]["program"])
        yield from self.hard_bank_swap_gen(board)


    #######################################################
    # Operations
    #######################################################

    def boot(self, board):
        self.start_operation(board, self.boot_gen(board))

    def boot_all(self):
        self.send_command(1, 0x7ff, b"\x55"*8)
        self.timeouts["boot_all"] = (time.time() + 0.5, lambda *args: self.read_bank_identifiers())

    def read_bank_identifiers(self):
        for board in self.boards:
            print("Reading bank identifiers", board)
            self.start_operation(board, self.read_bank_identifiers_gen(board))

    def soft_bank_swap(self, board):
        print("Soft bank swap", board)
        self.start_operation(board, self.soft_bank_swap_gen(board))

    def hard_bank_swap(self, board):
        print("Hard bank swap", board)
        self.start_operation(board, self.hard_bank_swap_gen(board))

    def reset(self, board):
        print("Resetting", board)
        self.start_operation(board, self.reset_gen(board))

    def program(self, board):
        print("Programming", board)
        self.start_operation(board, self.program_gen(board))


    #######################################################
    # Internal functions
    #######################################################

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
            self.boards[board] = {
                "index": len(self.boards),
                "bus": packet["bus"],
                "bankstatus": packet["bankstatus"],
                "bootstate": packet["bootstate"],
                "offset": 0,
                "lastwrite": b"",
                "booted": True,
                "op_generator": None
            }
            self.on_board_added(board)
        self.boards[board]["last_packet"] = packet
        if self.boards[board]["op_generator"] is not None:
            try:
                v = next(self.boards[board]["op_generator"])
                if v is not None: self.txfunc(v)
            except StopIteration:
                print("Operation done")
                self.boards[board]["op_generator"] = None
            except BootloaderError as e:
                self.boards[board]["op_generator"] = None
                self.on_error(e)
                print("Operation terminated due to error:", e)

        if packet["bus"] == 5 and packet["id"] == 0 and "txctl" in self.timeouts:
            del self.timeouts["txctl"]
                
        elif packet["type"] == "status":
            self.boards[board]["booted"] = True
            self.boards[board]["bootstate"] = packet["bootstate"]
            self.boards[board]["bankstatus"] = packet["bankstatus"]
            self.on_board_state_change(board)

    def close(self):
        os.write(self.abortpipe_w, b"x")
        os.close(self.abortpipe_w)

