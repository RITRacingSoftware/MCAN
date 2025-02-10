import mcan
import sources

mcan.source(sources.RandomFrames)
#mcan.filter(lambda p: p["bus"] == 1 and p["id"] == 1874).exec(mcan.log)
mcan.filter(lambda p: p["bus"] == 1).exec(mcan.dash)

mcan.options["interactive"] = True
mcan.options["dashboardheight"] = 0.75
mcan.mainloop()
