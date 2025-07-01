import cantools
import time
import math
import threading
import random
import socket
import struct
import serial
import zlib
import select
import os

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
    def __init__(self, inst, fname, bus, scale=1):
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
    
    def dump_stats(self):
        return {"replay_backlog": self.backlog}

class MCAN_Ethernet:
    def __init__(self, inst, ip, port):
        self.ip = ip
        self.port = port
        self.inst = inst
        self.socket = None
        self.running = True
        self.abortpipe_r = None
        self.abortpipe_w = None
    
    def start(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('0.0.0.0', 40000))
        self.socket.setblocking(0)
        self.abortpipe_r, self.abortpipe_w = os.pipe()
        threading.Thread(target=self.run).start()

    def stop(self):
        self.running = False
        os.write(self.abortpipe_w, b"x")
        os.close(self.abortpipe_w)
        self.socket.close()

    def run(self):
        msb = 0
        offset = 0
        msb_loaded = False
        while self.running:
            rlist, wlist, xlist = select.select([self.socket, self.abortpipe_r], [], [])
            if self.abortpipe_r in rlist: break
            frame = self.socket.recv(1500)
            i = 0
            while i < len(frame):
                bus, length, ts, id = struct.unpack("<BBHI", frame[i:i+8])
                if bus == 4:
                    newmsb = struct.unpack("<I", frame[i+8:i+12])[0]<<16
                    if newmsb < msb:
                        print("Warning: backwards jump in timestamp packet ({} to {})".format(msb>>16, newmsb>>16))
                        offset = newmsb - (msb - offset)
                    elif not msb_loaded:
                        msb_loaded = True
                        offset = newmsb
                    msb = newmsb
                else:
                    packet = {"bus": bus, "id": id, "data": frame[i+8:i+8+(length&0x7f)], "ts": ts+msb-offset, "fd": length>>7}
                    self.inst.onrecv(packet)
                i += (length & 0x7f)+8
        os.close(self.abortpipe_r)

    def transmit(self, packet):
        #print("transmit", packet)
        frame = struct.pack("<BBHI", packet["bus"], (0x80 if packet["fd"] else 0) | (len(packet["data"])), 0, packet["id"])+packet["data"]
        self.socket.sendto(frame, (self.ip, self.port))


