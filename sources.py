import cantools
import time
import math
import threading
import random
import socket
import struct

class RandomFrames:
    def __init__(self):
        self.q = None
        self.running = True
        self.db = cantools.database.load_file("/home/matthias/racing/Formula-DBC/main_dbc.dbc")

    def set_queue(self, q):
        self.q = q

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
                for s in "ABCD":
                    for n in range(1, 20):
                        packet["BMS_Voltages_"+s+str(n)] = 3.7
                        i += 1
                        if (i % 6) == 0:
                            packet["BMS_Voltages_mux"] = (i//6)-1
                            self.q.put({"bus": 1, "id": 702, "data": self.db.encode_message(702, packet), "ts": time.time()})
                            packet = {}
            unpacked = {"TireTemp_FL_Max": tv, "TireTemp_FR_Max": tv, "TireTemp_RL_Max": tv, "TireTemp_RR_Max": tv}
            data = self.db.encode_message(1874, unpacked)
            self.q.put({"bus": 1, "id": 1874, "data": data, "ts": time.time()})
            time.sleep(0.02)
            data = self.db.encode_message(1875, {"RotorTemp_FL_Max": tv, "RotorTemp_FR_Max": tv, "RotorTemp_RL_Max": tv, "RotorTemp_RR_Max": tv})
            self.q.put({"bus": 1, "id": 1875, "data": data, "ts": time.time()})
            time.sleep(random.random()*0.03 + 0.085)

    def run_fast(self):
        t0 = time.time()
        n = 0
        while self.running:
            t = time.time() - t0
            self.q.put({"bus": 1, "id": 505, "data": self.db.encode_message(505, {
                "VectorNav_VelNedN": 100*math.cos(t),
                "VectorNav_VelNedE": -100*math.sin(t),
            }), "ts": time.time()})
            time.sleep(0.005)

class MCAN_Ethernet:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.q = None
        self.socket = None
        self.running = True

    def set_queue(self, q):
        self.q = q
    
    def start(self):
        self.running = True
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('0.0.0.0', 40000))
        threading.Thread(target=self.run).start()

    def stop(self):
        self.running = False
        self.socket.close()

    def run(self):
        msb = 0
        offset = 0
        msb_loaded = False
        while self.running:
            frame = self.socket.recv(1500)
            i = 0
            while i < len(frame):
                bus, length, ts, id = struct.unpack("<BBHI", frame[i:i+8])
                if bus == 4:
                    msb = struct.unpack("<I", frame[i+8:i+12])[0]<<16
                    if not msb_loaded:
                        msb_loaded = True
                        offset = msb
                else:
                    packet = {"bus": bus, "id": id, "data": frame[i+8:i+8+(length&0x7f)], "ts": ts+msb-offset, "fd": length>>7}
                    self.q.put(packet)
                i += (length & 0x7f)+8

    def transmit(self, packet):
        frame = struct.pack("<BBHI", packet["bus"], (0x80 if packet["fd"] else 0) | (len(packet["data"])), 0, packet["id"])+packet["data"]
        self.socket.sendto(frame, (self.ip, self.port))


