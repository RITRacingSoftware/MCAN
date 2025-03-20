import sys
if len(sys.argv) > 1 and sys.argv[1] == "curses":
    import mcan_curses as mcan
else:
    import mcan_tkinter as mcan
import sources
import mcan_outputs

#mcan_outputs.ethernet_start()

#mcan.source(sources.RandomFrames())
mcan.source(sources.MCAN_Ethernet('192.168.72.1', 5001))
#mcan.filter(lambda p: p["bus"] == 1 and p["id"] == 1874).exec(mcan.log)
mcan.rootstream.exec(mcan.dash)
#mcan.filter(lambda p: p["bus"] == 1).exec(mcan_outputs.ethernet_tx)

mcan.mainloop()
