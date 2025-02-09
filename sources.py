import cantools
import time
import math
import threading
import random

class RandomFrames:
    def __init__(self, q, *args):
        self.q = q
        self.running = True

    def start(self):
        self.running = True
        threading.Thread(target=self.run).start()

    def stop(self):
        self.running = False

    def run(self):
        db = cantools.database.load_file("/home/matthias/racing/Formula-DBC/formula_main_dbc.dbc")
        t0 = time.time()
        while self.running:
            t = time.time() - t0
            tv = int(round(math.sin(t)*200+200))
            unpacked = {"TireTemp_FL_Max": tv, "TireTemp_FR_Max": tv, "TireTemp_RL_Max": tv, "TireTemp_RR_Max": tv}
            data = db.encode_message(1874, unpacked)
            self.q.put({"bus": 1, "id": 1874, "data": data})
            time.sleep(0.02)
            data = db.encode_message(1875, {"RotorTemp_FL_Max": tv, "RotorTemp_FR_Max": tv, "RotorTemp_RL_Max": tv, "RotorTemp_RR_Max": tv})
            self.q.put({"bus": 1, "id": 1875, "data": data})
            time.sleep(random.random()*0.03 + 0.085)
