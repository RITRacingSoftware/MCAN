import sys
import mcan

m = mcan.MCan()
win = mcan.MainWindow(m)

ethernet = mcan.sources.MCAN_Ethernet(m, "192.168.72.100", 5001)
m.source(ethernet)

#m.source(mcan.sources.Replay(m, "inputs/loginverter.pcap", 3, 1))
#m.source(mcan.sources.Replay(m, "inputs/logsensor.pcap", 1, 1))
#m.source(mcan.sources.Replay(m, "inputs/logmain.pcap", 2, 1))

#mcan.source(sources.LoRATelemetry("/dev/ttyUSB0"))

#mcan.filter(lambda p: p["bus"] == 1 and p["id"] == 1874).exec(mcan.log)
#mcan.rxrootstream.filter(lambda p: not (p["id"] & (1<<30))).exec(lambda p: mcan.dash(p, "all"))
m.rxrootstream.filter(lambda p: not (p["id"] & (1<<30)) and p["bus"] in [1, 2, 3]).exec(lambda p: win.dash_update(p, ["all", "sensor", "main", "inverter"][p["bus"]]))
m.rxrootstream.filter(lambda p: p["id"] == 501).exec(lambda p: win.dash_update(p, "SSDB"))
m.txrootstream.filter(lambda p: 1 <= p["bus"] <= 3).exec(ethernet.transmit)

win.mainloop()
