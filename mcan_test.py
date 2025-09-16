import sys
import mcan

m = mcan.MCan()
m.load_file(1, "../Formula-DBC/sensor_dbc.dbc")
m.load_file(2, "../Formula-DBC/main_dbc.dbc")
m.load_file(3, "../Formula-DBC/inverter_dbc.dbc")
#m.load_file(5, "../Formula-DBC/control_dbc.dbc")
win = mcan.MainWindow(m)

ethernet = mcan.sources.MCAN_Ethernet(m, "192.168.72.100", 5001)
#ethernet = mcan.sources.MCAN_Ethernet(m, "datalogger.local", 5001, tcp=True)
#ethernet = mcan.sources.MCAN_Ethernet(m, "192.168.73.1", 5001, tcp=True)
m.source(ethernet)

#m.source(mcan.sources.Replay(m, "inputs/loginverter.pcap", 3, 1))
#m.source(mcan.sources.Replay(m, "inputs/logsensor.pcap", 1, 1))
#m.source(mcan.sources.Replay(m, "inputs/logmain.pcap", 2, 1))

#mcan.source(sources.LoRATelemetry("/dev/ttyUSB0"))

m.rxrootstream.filter_range(busses={1,2,3,5}).exec(win.dash_func({1: "sensor", 2: "main", 3: "inverter", 5: "control"}))
m.rxrootstream.filter_range(min_id=501, max_id=501, busses={1}).exec(win.dash_func("SSDB"))
m.txrootstream.exec(ethernet.transmit)
#m.rxrootstream.filter_range(busses={1}).exec(ethernet.transmit)

win.mainloop()
