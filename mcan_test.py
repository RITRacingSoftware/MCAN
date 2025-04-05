import sys
import mcan
import sources

#ethernet = sources.RandomFrames()
ethernet = sources.MCAN_Ethernet("192.168.72.100", 5001)

mcan.source(ethernet)
#mcan.filter(lambda p: p["bus"] == 1 and p["id"] == 1874).exec(mcan.log)
#mcan.rxrootstream.filter(lambda p: not (p["id"] & (1<<30))).exec(lambda p: mcan.dash(p, "all"))
mcan.rxrootstream.filter(lambda p: not (p["id"] & (1<<30)) and p["bus"] <= 3).exec(lambda p: mcan.dash(p, ["all", "sensor", "main", "inverter"][p["bus"]]))
#mcan.rxrootstream.filter(lambda p: not (p["id"] & (1<<30)) and p["id"] == 702).exec(lambda p: mcan.dash(p, "BMS"))
mcan.txrootstream.filter(lambda p: 1 <= p["bus"] <= 3).exec(ethernet.transmit)

mcan.mainloop()
