import cantools
import time
import math
import threading
import random

class RandomFrames:
    def __init__(self, q, *args):
        self.q = q
        self.running = True
        self.db = cantools.database.load_file("/home/matthias/racing/Formula-DBC/main_dbc.dbc")

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
                            self.q.put({"bus": 1, "id": 702, "data": self.db.encode_message(702, packet)})
                            packet = {}
            unpacked = {"TireTemp_FL_Max": tv, "TireTemp_FR_Max": tv, "TireTemp_RL_Max": tv, "TireTemp_RR_Max": tv}
            data = self.db.encode_message(1874, unpacked)
            self.q.put({"bus": 1, "id": 1874, "data": data})
            time.sleep(0.02)
            data = self.db.encode_message(1875, {"RotorTemp_FL_Max": tv, "RotorTemp_FR_Max": tv, "RotorTemp_RL_Max": tv, "RotorTemp_RR_Max": tv})
            self.q.put({"bus": 1, "id": 1875, "data": data})
            time.sleep(random.random()*0.03 + 0.085)

    def run_fast(self):
        t0 = time.time()
        while self.running:
            t = time.time() - t0
            self.q.put({"bus": 1, "id": 505, "data": self.db.encode_message(505, {
                "VectorNav_VelNedN": 100*math.cos(t),
                "VectorNav_VelNedE": -100*math.sin(t)
            })})
            time.sleep(0.01)
            
