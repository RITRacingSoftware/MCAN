import sys
import mcan
import sources

ethernet = sources.RandomFrames()
#ethernet = sources.MCAN_Ethernet("192.168.72.100", 5001)

mcan.source(ethernet)
#mcan.filter(lambda p: p["bus"] == 1 and p["id"] == 1874).exec(mcan.log)
mcan.rxrootstream.filter(lambda p: not (p["id"] & (1<<30))).exec(mcan.dash)
#mcan.txrootstream.filter(lambda p: 1 <= p["bus"] <= 3).exec(ethernet.transmit)

mcan.mainloop()
