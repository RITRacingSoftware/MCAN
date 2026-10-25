import cantools
import time
import math
import threading
import random
import socket
import selectors
import struct
import serial
import zlib
import select
import os
import sys

def read_cf(data):
    msb = 0
    offset = 0
    msb_loaded = False
    i = 0
    while i < len(data):
        bus, length, ts, id = struct.unpack("<BBHI", data[i:i+8])
        if bus == 4:
            msb = struct.unpack("<I", data[i+8:i+12])[0]<<16
            if not msb_loaded:
                msb_loaded = True
                offset = msb
        else:
            yield i + (length & 0x7f) + 8, {"bus": bus, "id": id, "data": data[i+8:i+8+(length&0x7f)], "ts": ts+msb-offset, "fd": length>>7}
        i += (length & 0x7f)+8

class RandomFrames:
    def __init__(self, inst):
        self.inst = inst
        self.running = True
        self.db = cantools.database.load_file("../Formula-DBC/main_dbc.dbc")

    def start(self):
        self.running = True
        threading.Thread(target=self.run).start()
        threading.Thread(target=self.run_fast).start()

    def stop(self):
        self.running = False

    def run(self):
        t0 = time.time()
        tb = 0
        while self.running:
            t = time.time() - t0
            tv = math.sin(t)*200+200
            if t - tb >= 1:
                i = 0
                packet = {}
                for s in "ABCDEFGH":
                    for n in range(1, 18):
                        packet["BMS_Voltages_"+s+str(n)] = random.random()*2 + 2.5
                        i += 1
                        if (i % 6) == 0:
                            packet["BMS_Voltages_mux"] = (i//6)-1
                            self.inst.onrecv({"bus": 2, "id": 702, "data": self.db.encode_message(702, packet), "ts": time.time()*1000000, "fd": False})
                            packet = {}
                tb = t
            unpacked = {"TireTemp_FL_Max": tv, "TireTemp_FR_Max": tv, "TireTemp_RL_Max": tv, "TireTemp_RR_Max": tv}
            data = self.db.encode_message(1874, unpacked)
            self.inst.onrecv({"bus": 2, "id": 1874, "data": data, "ts": time.time()*1000000, "fd": False})
            time.sleep(0.02)
            data = self.db.encode_message(1875, {"RotorTemp_FL_Max": tv, "RotorTemp_FR_Max": tv, "RotorTemp_RL_Max": tv, "RotorTemp_RR_Max": tv})
            self.inst.onrecv({"bus": 2, "id": 1875, "data": data, "ts": time.time()*1000000, "fd": False})
            time.sleep(random.random()*0.03 + 0.085)

    def run_fast(self):
        t0 = time.time()
        n = 0
        while self.running:
            t = time.time() - t0
            self.inst.onrecv({"bus": 2, "id": 505, "data": self.db.encode_message(505, {
                "VectorNav_VelNedN": 100*math.cos(t),
                "VectorNav_VelNedE": -100*math.sin(t),
            }), "ts": time.time()*1000000, "fd": False})
            time.sleep(0.005)

class LoRATelemetry:
    def __init__(self, inst, port):
        self.port = port
        self.running = True
        self.inst = inst

    def start(self):
        self.s = serial.Serial(self.port, 115200)
        self.s.write(b"AT+BAND=915000000,M\r\n")
        print(self.s.readline())
        self.s.write(b"AT+PARAMETER=5,9,1,4\r\n")
        self.s.write(b"AT+NETWORKID=18\r\n")
        self.s.write(b"AT+ADDRESS=6\r\n")
        self.running = True
        threading.Thread(target=self.run).start()

    def stop(self):
        self.running = False
        self.s.close()

    def run(self):
        while self.running:
            l = self.s.readline()
            if l.startswith(b"+OK"):
                continue
            if l.startswith(b"+ERR"):
                pass
                print("Received error from LoRA", l.decode())
            if l.startswith(b"+RCV"):
                ch, length, data = l.split(b",", 2)
                length = int(length)
                # use <= here since the data may end in a \n, but the trailing info must still be read
                while len(data) <= length:
                    data += self.s.readline()
                data = data.rsplit(b",", 2)[0]
                if ch == b"+RCV=8":
                    try:
                        data = zlib.decompress(data)
                    except zlib.error:
                        data = b""
                i = 0
                while i < len(data):
                    bus, length, tsl, id, tsh = struct.unpack("<BBHHH", data[i:i+8])
                    packet = {"bus": bus, "id": id, "data": data[i+8:i+8+(length&0x7f)], "ts": tsl | (tsh << 16), "fd": length>>7}
                    self.inst.onrecv(packet)
                    i += (length & 0x7f)+8


class Replay:
    def __init__(self, inst, fname, bus=None, scale=1):
        self.fname = fname
        self.bus = bus
        self.scale = scale
        self.inst = inst
        self.backlog = 0
        self.running = True
    
    def start(self):
        self.running = True
        threading.Thread(target=self.run).start()

    def stop(self):
        self.running = False

    def run(self):
        t0 = 0
        ts0 = 0
        offset_ready = False
        msb = 0
        ext = os.path.splitext(self.fname)[1][1:]
        if ext == "pcap":
            with open(self.fname, "rb") as f:
                head = f.read(24)
                while self.running:
                    head = f.read(16)
                    if len(head) == 0:
                        offset_ready = False
                        f.seek(0)
                        f.read(24)
                        print("rolling over")
                        continue
                    sec, usec, length = struct.unpack("<3I", head[:12])
                    ts = sec + usec / 1000000.0
                    data = f.read(length)
                    if offset_ready:
                        t = (time.time() - t0)/self.scale + ts0
                        self.backlog = t - ts
                        if t < ts: time.sleep(self.scale*(ts - t))
                    else:
                        ts0 = ts
                        t0 = time.time()
                        offset_ready = True
                    packet = {
                        "id": struct.unpack(">I", data[:4])[0],
                        "fd": data[5] > 0,
                        "ts": ts*1000000,
                        "data": data[8:],
                        "bus": self.bus
                    }
                    self.inst.onrecv(packet)
        elif ext == "zcf":
            print("Replaying ZCF")
            with open(self.fname, "rb") as f:
                obj = zlib.decompressobj()
                cont = obj.decompress(f.read())
                zcf_iter = read_cf(cont)
                while self.running:
                    try:
                        n, packet = next(zcf_iter)
                    except StopIteration:
                        print("rollong over")
                        offset_ready = False
                        zcf_iter = read_cf(cont)
                        continue
                    ts = packet["ts"] / 1000000.0
                    if offset_ready:
                        t = (time.time() - t0)/self.scale + ts0
                        self.backlog = t - ts
                        if t < ts: time.sleep(self.scale*(ts - t))
                    else:
                        ts0 = ts
                        t0 = time.time()
                        offset_ready = True
                    self.inst.onrecv(packet)

    
    def dump_stats(self):
        return {"replay_backlog": self.backlog}

    def dump(self):
        return {
            "type": "replay",
            "fname": self.fname,
            "bus": self.bus,
            "scale": self.scale
        }

    def dump_string(self):
        return "Replay", f"{self.fname} -> bus {self.bus}"

class MCAN_Ethernet:
    def __init__(self, inst, ip, port, tcp=False):
        self.ip = ip
        self.port = port
        self.inst = inst
        self.socket = None
        self.running = True
        self.abortpipe_r = None
        self.abortpipe_w = None
        self.tcp = tcp
    
    def start(self):
        if self.tcp:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.ip, self.port))
        else:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.bind(('0.0.0.0', 40000))
        self.socket.setblocking(0)
        if sys.platform == "linux":
            self.abortpipe_r, self.abortpipe_w = os.pipe()
        threading.Thread(target=self.run).start()

    def stop(self):
        self.running = False
        if self.abortpipe_w is not None:
            os.write(self.abortpipe_w, b"x")
            os.close(self.abortpipe_w)
        self.socket.close()

    def run(self):
        msb = 0
        offset = 0
        msb_loaded = False
        frame = b""
        while self.running:
            if self.abortpipe_r is not None:
                rlist, wlist, xlist = select.select([self.socket, self.abortpipe_r], [], [])
            else:
                rlist, wlist, xlist = select.select([self.socket], [], [])
            if self.abortpipe_r in rlist: break
            frame += self.socket.recv(1500)
            if len(frame) == 0:
                self.socket.shutdown(socket.SHUT_RDWR)
                print("Socket closed!")
                return
            i = 0
            while i+1 < len(frame) and i+(frame[i+1]&0x7f)+8 <= len(frame):
                bus, length, ts, id = struct.unpack("<BBHI", frame[i:i+8])
                if bus == 4:
                    newmsb = struct.unpack("<I", frame[i+8:i+12])[0]<<16
                    if newmsb < msb:
                        #print("Warning: backwards jump in timestamp packet ({} to {})".format(msb>>16, newmsb>>16))
                        offset = newmsb - (msb - offset)
                    elif not msb_loaded:
                        msb_loaded = True
                        offset = newmsb
                    msb = newmsb
                else:
                    packet = {"bus": bus, "id": id, "data": frame[i+8:i+8+(length&0x7f)], "ts": ts+msb-offset, "fd": length>>7}
                    self.inst.onrecv(packet)
                i += (length & 0x7f)+8
            frame = frame[i:]
        if self.abortpipe_r is not None: os.close(self.abortpipe_r)

    def transmit(self, packet):
        frame = struct.pack("<BBHI", packet["bus"], (0x80 if packet["fd"] else 0) | (len(packet["data"])), 0, packet["id"])+packet["data"]
        self.socket.sendto(frame, (self.ip, self.port))

    def transmit_multiple(self, packets):
        frame = b""
        for packet in packets:
            frame += struct.pack("<BBHI", packet["bus"], (0x80 if packet["fd"] else 0) | (len(packet["data"])), 0, packet["id"])+packet["data"]
        self.socket.sendto(frame, (self.ip, self.port))

    def dump(self):
        return {
            "type": "ip",
            "tcp": self.tcp,
            "ip": self.ip,
            "port": self.port
        }

    def dump_string(self):
        return "IP", f"{'TCP' if self.tcp else 'UDP'} on {self.ip}:{self.port}"

class TCPServer:
    def __init__(self, inst, ip, port):
        self.ip = ip
        self.port = port
        self.inst = inst
        self.socket = None
        self.running = True
        self.abortpipe_r = None
        self.abortpipe_w = None
        self.last_ts = 0
        self.recv_ts = 0
        self.unread = {}
        self.sel = selectors.DefaultSelector()

    def start(self):
        self.socket = socket.socket()
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.socket.bind((self.ip, self.port))
        self.socket.listen(100)
        self.socket.setblocking(False)
        self.sel.register(self.socket, selectors.EVENT_READ, self.accept)

        threading.Thread(target=self.run).start()

    def stop(self):
        self.running = False
        self.socket.close()
        for obj, val in self.sel.get_map().items():
            if val.fileobj == self.socket: continue
            print("Closing open connection", obj, val)
            val.fileobj.shutdown(socket.SHUT_RDWR)

    def transmit(self, packet):
        ts_us = int(packet["ts"])
        bv = bytearray([])
        if (ts_us >> 16) != self.last_ts:
            self.last_ts = ts_us >> 16
            bv += struct.pack("<BBHII", 4, 4, ts_us & 0xffff, 0, self.last_ts)
        bv += struct.pack("<BBHI", packet["bus"], (0x80 if packet["fd"] else 0) | (len(packet["data"])), ts_us & 0xffff, packet["id"])+packet["data"]
        for obj, val in self.sel.get_map().items():
            if val.fileobj == self.socket: continue
            val.fileobj.send(bv)

    def accept(self, sock, mask):
        conn, addr = sock.accept()  # Should be ready
        print('accepted', conn, 'from', addr)
        conn.setblocking(False)
        self.unread[conn.fileno()] = bytearray([])
        self.sel.register(conn, selectors.EVENT_READ, self.read)

    def read(self, conn, mask):
        data = conn.recv(1500)  # Should be ready
        if data:
            frame = self.unread[conn.fileno()] + data
            i = 0
            while i+1 < len(frame) and i+(frame[i+1]&0x7f)+8 <= len(frame):
                bus, length, ts, id = struct.unpack("<BBHI", frame[i:i+8])
                if bus == 4:
                    self.recv_ts = struct.unpack("<I", frame[i+8:i+12])[0]<<16
                else:
                    packet = {"bus": bus, "id": id, "data": frame[i+8:i+8+(length&0x7f)], "ts": (self.recv_ts<<16) + ts, "fd": length>>7}
                    # Special behavior just for TCPServer
                    # TODO: unified behavior, maybe have independent RX/TX streams for each source?
                    self.inst.transmit(packet)
                i += (length & 0x7f)+8
            self.unread[conn.fileno()] = frame[i:]
        else:
            print('closing', conn)
            self.sel.unregister(conn)
            conn.close()

    def run(self):
        while self.running:
            events = self.sel.select(timeout=0.1)
            for key, mask in events:

                callback = key.data
                callback(key.fileobj, mask)
    
    def dump(self):
        return {
            "type": "tcp_server",
            "ip": self.ip,
            "port": self.port
        }



def construct(inst, type, **kwargs):
    cls = {"ip": MCAN_Ethernet, "replay": Replay}.get(type, None)
    if cls is None: return
    return cls(inst, **kwargs)


