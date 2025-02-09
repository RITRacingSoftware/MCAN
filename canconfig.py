import mcan
import sources

mcan.source(sources.RandomFrames)
mcan.filter(lambda p: p["bus"] == 1 and p["id"] == 1874).exec(mcan.log_can)

mcan.options["interactive"] = True
mcan.mainloop()
