import sys
import mcan

m = mcan.MCan()
m.load_file(1, "../Formula-DBC/sensor_dbc.dbc")
m.load_file(2, "../Formula-DBC/main_dbc.dbc")
m.load_file(3, "../Formula-DBC/inverter_dbc.dbc")
win = mcan.MainWindow(m)

#ethernet = mcan.sources.MCAN_Ethernet(m, "192.168.72.100", 5001)
ethernet = mcan.sources.MCAN_Ethernet(m, "192.168.73.1", 5001, tcp=True)
m.source(ethernet)

def convert_to_sensor(packet):
    packet["bus"] = 1
    ethernet.transmit(packet)

#m.source(mcan.sources.Replay(m, "inputs/loginverter.pcap", 3, 1))
#m.source(mcan.sources.Replay(m, "inputs/logsensor.pcap", 1, 1))
#m.source(mcan.sources.Replay(m, "inputs/logmain.pcap", 2, 1))

#mcan.source(sources.LoRATelemetry("/dev/ttyUSB0"))

#mcan.filter(lambda p: p["bus"] == 1 and p["id"] == 1874).exec(mcan.log)
#mcan.rxrootstream.filter(lambda p: not (p["id"] & (1<<30))).exec(lambda p: mcan.dash(p, "all"))
m.rxrootstream.filter(lambda p: not (p["id"] & (1<<30) & 0) and p["bus"] in [1, 2, 3, 5]).exec(lambda p: win.dash_update(p, ["all", "sensor", "main", "inverter", "", "control"][p["bus"]]))
m.rxrootstream.filter(lambda p: p["id"] == 501).exec(lambda p: win.dash_update(p, "SSDB"))
#m.rxrootstream.filter(lambda p: 1 <= p["bus"] <= 3).exec(convert_to_sensor)

win.mainloop()
