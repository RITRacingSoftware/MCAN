import tkinter
from tkinter import ttk

def expand_wsbool(name):
    return lambda x: name + ": "+("Set" if x else "Not set")


class BitFieldLabel(ttk.Label):
    def __init__(self, master, name, value, fmt, **kwargs):
        self.value = value
        self.name = name
        self.fmt = fmt
        self.nbits = sum(x[0] for x in fmt)
        self.nbytes = ((self.nbits >> 3) + 1 if (self.nbits & 0x7) else (self.nbits >> 3))
        kwargs["text"] = hex(value)[2:].rjust(self.nbytes, "0").upper()
        if "font" not in kwargs:
            kwargs["font"] = ("Ubuntu Mono", 0)
        super().__init__(master, **kwargs)
        self.bind("<Double-Button-1>", self.onclick)
        self.expanded = None

    def set_value(self, value):
        self.config(text=hex(value)[2:].rjust(self.nbytes, "0").upper())
        self.value = value
        if self.expanded is not None and not self.expanded.closed:
            self.expanded.set_value(self.value)

    def onclick(self, event):
        if self.expanded is None or self.expanded.closed:
            self.expanded = BitFieldExpansion(self.name, self.value, self.fmt)
        else:
            self.expanded.lift()


class BitFieldExpansion(tkinter.Toplevel):
    def __init__(self, name, value, fmt):
        super().__init__()
        self.value = value
        self.fmt = fmt
        self.closed = False
        self.nbits = sum(x[0] for x in fmt)
        self.nbytes = ((self.nbits >> 3) + 1 if (self.nbits & 0x7) else (self.nbits >> 3))
        self.text = tkinter.Label(self, font=("Ubuntu Mono", 0), text=self.gentext(), justify="l")
        self.text.grid(row=0, column=0)
        self.protocol("WM_DELETE_WINDOW", self.on_quit)

    def on_quit(self):
        self.closed = True
        self.destroy()

    def gentext(self):
        text = ""
        cs = 0
        for bits, func in self.fmt:
            if func is None:
                cs += bits
                continue
            if text: text += "\n"
            for i in range(self.nbits):
                if i < cs:
                    text += "."
                elif i < cs+bits:
                    text += str((self.value >> (self.nbits - i - 1)) & 1)
                else:
                    text += "."
                if (i%4 == 3): text += " "
            text += " = " + func((self.value >> (self.nbits - cs - bits)) & ((1<<bits)-1))
            cs += bits
        return text
    
    def set_value(self, value):
        self.value = value
        self.text.config(text=self.gentext())
