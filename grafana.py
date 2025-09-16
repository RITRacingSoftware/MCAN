import requests
import time
import math
import mcan
import threading

m = mcan.MCan()
m.load_file(1, "../Formula-DBC/sensor_dbc.dbc")
m.load_file(2, "../Formula-DBC/main_dbc.dbc")
m.load_file(3, "../Formula-DBC/inverter_dbc.dbc")
m.load_file(5, "../Formula-DBC/control_dbc.dbc")
win = mcan.MainWindow(m)

ethernet = mcan.sources.MCAN_Ethernet(m, "192.168.72.100", 5001)
#ethernet = mcan.sources.MCAN_Ethernet(m, "datalogger.local", 5001, tcp=True)
m.source(ethernet)

#m.source(sources.Replay(m, "inputs/loginverter.pcap", 3, 1))
#m.source(sources.Replay(m, "inputs/logsensor.pcap", 1, 1))
#m.source(sources.Replay(m, "inputs/logmain.pcap", 2, 1))

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

