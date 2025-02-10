import curses
import sys
import threading
import queue
import sources
import os
import cantools

source_list = []
rxqueue = queue.Queue()
filter_list = []
stdscr = None
options = {
    "interactive": False,
    "dasboardheight": 0.75
}

lines = cols = 0

log_window = None
log_window_pos = None
log_history = []
log_cursorpos = -1
log_scrolloffset = 0

dash_window = None
dash_window_pos = None
dash_data = {}
dash_cursorpos = 0
dash_scrolloffset = 0

cursor_window = "dash"

command_buf = ""

changed = False

debug = open("/tmp/debug", "w")
can_db = {
    1: cantools.database.load_file("/home/matthias/racing/Formula-DBC/formula_main_dbc.dbc")
}


class Filter:
    def __init__(self, func):
        self.chain = [lambda x: x if func(x) else None]

    def filter(self, func):
        self.chain.append(lambda x: x if func(x) else None)
        return self

    def exec(self, func):
        self.chain.append(func)
        return self

def source(s, *args, **kwargs):
    source_list.append(s(rxqueue, *args, **kwargs))

def filter(func):
    f = Filter(func)
    filter_list.append(f)
    return f


def update():
    global log_window, log_history, log_cursorpos, log_scrolloffset, dash_cursorpos, dash_scrolloffset
    #debug.write("redrawing\n")
    debug.flush()
    stdscr.addstr(0, 0, "MCAN v0.0")
    log_cursor = 0
    dash_cursor = 0

    log_window.erase()
    lh, lw = log_window.getmaxyx()
    log_window.addstr(0, 0, "Log ")
    log_window.hline(curses.ACS_HLINE, cols-4)
    if log_history:
        log_cursor = log_cursorpos % len(log_history)
        if log_cursor - log_scrolloffset >= lh - 1:
            log_scrolloffset = log_cursor - lh + 2
        if log_cursor < log_scrolloffset:
            log_scrolloffset = log_cursor
        for i in range(1, lh):
            if log_scrolloffset + i - 1 >= len(log_history): break
            log_window.addstr(i, 0, log_history[log_scrolloffset + i - 1][:cols-1])
    log_window.refresh()

    dash_window.erase()
    dash_window.addstr(0, 0, "Dashboard ")
    dash_window.hline(curses.ACS_HLINE, cols-10)
    dash_window.addstr(1, 0, "Bus")
    dash_window.addstr(1, 11, "ID")
    dash_window.addstr(1, 14, "Data")
    dh, dw = dash_window.getmaxyx()
    if dash_data:
        order = sorted(dash_data.keys())
        i = 0
        for k in order:
            dash_data[k]["line"] = i
            i += (1 + len(dash_data[k]["data"])) if dash_data[k]["expanded"] else 1
        if dash_cursorpos < 0: dash_cursorpos = 0
        if dash_cursorpos >= i: dash_cursorpos = i-1
        if dash_cursor - dash_scrolloffset >= dh - 1:
            dash_scrolloffset = dash_cursor - dh + 2
        if dash_cursor < dash_scrolloffset:
            dash_scrolloffset = dash_cursor
        for k in order:
            l = (1 + len(dash_data[k]["data"])) if dash_data[k]["expanded"] else 1
            pos = dash_data[k]["line"]
            if pos >= dash_scrolloffset + dh - 2: break
            if pos + l >= dash_scrolloffset:
                if pos >= dash_scrolloffset:
                    dash_window.addstr(pos-dash_scrolloffset+2, 0, str(k[0]).rjust(3))
                    dash_window.addstr(pos-dash_scrolloffset+2, 4, str(k[1]).rjust(9))
                    dash_window.addstr(pos-dash_scrolloffset+2, 14, " ".join(hex(x)[2:].rjust(2, "0") for x in dash_data[k]["raw"]))
                if dash_data[k]["expanded"]:
                    for j, d in enumerate(dash_data[k]["data"]):
                        if pos+j >= dh - 3: break
                        if pos+j+1 >= dash_scrolloffset:
                            dash_window.addstr(pos+j-dash_scrolloffset+3, 14, d+": "+str(dash_data[k]["data"][d]))
    dash_window.refresh()

    stdscr.move(lines-1, 0)
    stdscr.clrtoeol()
    stdscr.addstr(lines-1, 0, command_buf)

    if cursor_window == "dash":
        y, x = dash_window_pos
        stdscr.move(2+dash_cursorpos - dash_scrolloffset + y, x)
    if cursor_window == "log":
        y, x = log_window_pos
        stdscr.move(1+log_cursorpos - log_scrolloffset + y, x)

    stdscr.refresh()

def log(data):
    global changed
    s = str(data)
    log_history.append(s)
    changed = True
    if not stdscr:
        print(s)

def dash(packet):
    global dash_data, changed
    changed = True
    dash_data[packet["bus"], packet["id"]] = {
        "expanded": False,
        "raw": packet["data"],
        "data": can_db[packet["bus"]].decode_message(packet["id"], packet["data"])
    }


def update_sizes():
    global lines, cols, log_window, log_window_pos, dash_window, dash_window_pos
    lines, cols = stdscr.getmaxyx()
    log_startline = int(round(lines * options["dasboardheight"]))
    debug.write("size: {}x{}, log_startline: {}\n".format(lines, cols, log_startline))
    debug.flush()

    if log_window is not None:
        del log_window
    log_window = curses.newwin(lines - log_startline-1, cols, log_startline, 0)
    log_window_pos = (log_startline, 0)

    if dash_window is not None:
        del dash_window
    dash_window = curses.newwin(log_startline - 1, cols, 1, 0)
    dash_window_pos = (1, 0)


    
def mainloop_internal(stdscr_l):
    global stdscr, lines, cols, changed, dash_cursorpos, command_buf
    stdscr = stdscr_l
    if stdscr is not None:
        stdscr.timeout(10)
        update_sizes()
        update()

    for s in source_list:
        s.start()
    filter_list_compiled = [f.chain for f in filter_list]
    try:
        while True:
            c = stdscr.getch()
            if c == -1:
                pass
            elif c == curses.KEY_RESIZE:
                update_sizes()
                update()
            elif c == curses.KEY_UP:
                if cursor_window == "dash":
                    dash_cursorpos -= 1
                update()
            elif c == curses.KEY_DOWN:
                if cursor_window == "dash":
                    dash_cursorpos += 1
                update()
            elif command_buf:
                if c == ord("\n"):
                    debug.write("Command: "+command_buf+"\n")
                    debug.flush()
                    if command_buf == ":q": break
                    elif command_buf[:4] == ">>> ": exec(command_buf[4:])
                    command_buf = ""
                elif c == 127 or c == curses.KEY_BACKSPACE:
                    command_buf = command_buf[:-1]
                else: 
                    command_buf += chr(c)
                update()
            elif c == ord(":") or c == ord(">"):
                command_buf = chr(c)
                if c == ord(">"): command_buf += ">> "
                update()
            changed = False
            try:
                while True:
                    packet = rxqueue.get_nowait()
                    for f in filter_list_compiled:
                        p = packet
                        for part in f:
                            p = part(p)
                            if p is None: break
            except queue.Empty: pass
            if changed:
                update()
    finally:
        for s in source_list:
            s.stop()
        debug.close()


def mainloop():
    if options["interactive"]:
        os.environ.setdefault('ESCDELAY', '25')
        curses.wrapper(mainloop_internal)
    else:
        mainloop_internal(None)

