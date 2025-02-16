import mcan
import sources
import mcan_outputs

#mcan_outputs.ethernet_start()

mcan.source(sources.RandomFrames)
#mcan.filter(lambda p: p["bus"] == 1 and p["id"] == 1874).exec(mcan.log)
mcan.rootstream.filter(lambda p: p["bus"] == 1).exec(mcan.dash)
#mcan.filter(lambda p: p["bus"] == 1).exec(mcan_outputs.ethernet_tx)

mcan.options["interactive"] = True
mcan.options["dashboardheight"] = 0.75
mcan.mainloop()
