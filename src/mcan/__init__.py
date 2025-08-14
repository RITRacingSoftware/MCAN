__version__ = "1.0.0"

from .mcan_main import *
import sys

def _main():
    print(sys.argv)
    m = MCan()
    win = MainWindow(m)
    if len(sys.argv) > 1:
        m.load_setup(sys.argv[1])
    win.mainloop()
