import requests
import time
import math
import mcan
import sources
import threading

m = mcan.MCan()

m.source(sources.Replay(m, "inputs/loginverter.pcap", 3, 1))
m.source(sources.Replay(m, "inputs/logsensor.pcap", 1, 1))
m.source(sources.Replay(m, "inputs/logmain.pcap", 2, 1))

s = requests.Session()
with open("token.txt") as f:
    s.headers["Authorization"] = "Bearer " + f.read().strip()
s.headers["Content-Type"] = "text/plain; charset=utf-8"
t = time.time()

req = ""

t0 = time.time()
first_ts = False

lock = threading.Lock()

def onrecv(packet):
    global req, t0, first_ts
    if not first_ts:
        first_ts = False
        t0 = time.time()*1000000 - packet["ts"]
    m.can_decode(packet, decode_choices=False)
    if "decoded" in packet:
        line = packet["message"].name + " " + ",".join("{}={}".format(x, packet["decoded"][x]) for x in packet["decoded"]) + " {:d}".format(int((t0 + packet["ts"])*1000))
        with lock:
            req += line + "\n"

m.rxrootstream.exec(onrecv)

m.start_sources()
try:
    while True:
        with lock:
            output = req
            req = ""
        s.post("http://localhost:3000/api/live/push/telemetry", output)
        time.sleep(0.025)
finally:
    m.close()
    exit()

