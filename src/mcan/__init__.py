__version__ = "1.1.0"

from .mcan_main import *
import sys
import os.path

def _main():
    print(sys.argv)

    m = MCan()
    if len(sys.argv) > 1:
        m.load_setup(sys.argv[1])
    else:
        try:
            m.load_setup(os.path.join(m.config_dir, "setup.json"))
        except FileNotFoundError:
            os.mkdir(m.config_dir)
            m.setup = {}
            with open(os.path.join(m.config_dir, "setup.json"), "w") as f:
                f.write(json.dumps(m.setup))

    win = MainWindow(m)
    win.mainloop()
