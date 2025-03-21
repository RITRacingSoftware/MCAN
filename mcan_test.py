import sys
import mcan
import sources

#mcan.source(sources.RandomFrames())
#mcan.source(sources.MCAN_Ethernet('192.168.72.100', 5001))
#mcan.filter(lambda p: p["bus"] == 1 and p["id"] == 1874).exec(mcan.log)
mcan.rootstream.exec(mcan.dash)
#mcan.filter(lambda p: p["bus"] == 1).exec(mcan_outputs.ethernet_tx)

mcan.mainloop()
