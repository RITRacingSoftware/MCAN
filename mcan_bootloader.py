import tkinter
from tkinter import ttk
from tkinter import filedialog
import struct
import json
import os.path
import collections
import threading

import mcan_utils
import bootloader

class BootloaderMenu(tkinter.Toplevel):
    def __init__(self, boot_manager):
        super().__init__()
        self.boot_manager = boot_manager
        self.closed = False
        self.context_target = None
        self.title("Bootloader")

        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        
        self.menubar = tkinter.Menu(self)
        self.cmdmenu = tkinter.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Commands", menu=self.cmdmenu)
        self.cmdmenu.add_command(label="Boot all", command=self.boot_manager.boot_all)
        self.cmdmenu.add_command(label="Disable non-boot messages", command=lambda: self.boot_manager.txctl(0))
        self.cmdmenu.add_command(label="Enable non-boot messages", command=lambda: self.boot_manager.txctl(1))
        self.cmdmenu.add_command(label="Disable C70", command=lambda: self.boot_manager.c70ctl(0))
        self.cmdmenu.add_command(label="Enable C70", command=lambda: self.boot_manager.c70ctl(1))
        self.config(menu=self.menubar)
        
        self.table = ttk.LabelFrame(self, text="Boards")
        self.table.grid(row=1, column=0, columnspan=3, sticky="news")
        self.table.rowconfigure(0, weight=1)
        self.table.columnconfigure(0, weight=1)

        self.treeview = ttk.Treeview(self.table)
        self.treeview.bind("<Button-3>", self.open_context_menu)
        self.treeview["columns"] = ["id", "bank1", "bank2", "state", "bb", "rb", "fname"]
        self.treeview.column("#0", width=0, stretch=tkinter.NO)
        self.treeview.column("id", width=30, stretch=tkinter.NO)
        self.treeview.column("bank1", width=200, stretch=tkinter.YES)
        self.treeview.column("bank2", width=200, stretch=tkinter.YES)
        self.treeview.column("state", width=70, stretch=tkinter.NO)
        self.treeview.column("bb", width=30, stretch=tkinter.NO, anchor=tkinter.E)
        self.treeview.column("rb", width=30, stretch=tkinter.NO)
        self.treeview.column("fname", width=100, stretch=tkinter.NO)
        self.treeview.heading("id", text="ID", anchor=tkinter.CENTER)
        self.treeview.heading("bank1", text="Bank 1", anchor=tkinter.CENTER)
        self.treeview.heading("bank2", text="Bank 2", anchor=tkinter.CENTER)
        self.treeview.heading("state", text="State", anchor=tkinter.CENTER)
        self.treeview.heading("bb", text="BB", anchor=tkinter.CENTER)
        self.treeview.heading("rb", text="RB", anchor=tkinter.CENTER)
        self.treeview.heading("fname", text="Filename", anchor=tkinter.CENTER)
        self.treeview.grid(row=0, column=0, sticky="news")
        
        vsb = ttk.Scrollbar(self.table, orient="vertical", command=self.treeview.yview)
        vsb.grid(row=0, column=1, sticky="news")
        self.treeview.config(yscrollcommand=vsb.set)

        self.contextmenu = tkinter.Menu(self, tearoff=0)
        self.contextmenu.add_command(label="Program", command=self.program)
        self.contextmenu.add_command(label="Boot", command=self.boot)
        self.contextmenu.add_command(label="Soft bank swap", command=self.soft_bank_swap)
        self.contextmenu.add_command(label="Toggle booting bank", command=self.hard_bank_swap)
        self.contextmenu.add_command(label="Reset", command=self.reset)
        self.contextmenu.bind("<FocusOut>", self.focusout)

        self.bind("<ButtonRelease-1>", self.click)

        self.boot_manager.on_board_state_change = self.update_board_item
        self.boot_manager.on_board_added = self.insert_board_item
        self.boot_manager.on_error = self.on_error

        for b in self.boot_manager.boards:
            self.insert_board_item(b)

        self.protocol("WM_DELETE_WINDOW", self.on_quit)


    #######################################################
    # Operations
    #######################################################

    def boot(self, board=None):
        if board is None: board = self.context_target
        self.boot_manager.boot(board)
    
    def soft_bank_swap(self, board=None):
        if board is None: board = self.context_target
        self.boot_manager.soft_bank_swap(board)
    
    def hard_bank_swap(self, board=None):
        if board is None: board = self.context_target
        self.boot_manager.hard_bank_swap(board)
    
    def reset(self, board=None):
        if board is None: board = self.context_target
        self.boot_manager.reset(board)
    
    def program(self, board=None):
        if board is None: board = self.context_target
        self.boot_manager.program(board)

    def update_board_item(self, board):
        b = self.boot_manager.boards[board]
        self.treeview.item(board, values=(board, b.get("bank1", ""), b.get("bank2", ""), hex(b["bootstate"])[2:].rjust(8, "0"), ("2" if b["bankstatus"] & 0x02 else "1"), 
                           ("2" if b["bankstatus"] & 0x01 else "1"), os.path.basename(self.boot_manager.config[board]["program"])))

    def insert_board_item(self, board):
        b = self.boot_manager.boards[board]
        self.treeview.insert(iid=board, parent="", text="", index="end", values=(board, b.get("bank1", ""), b.get("bank2", ""), hex(b["bootstate"])[2:].rjust(8, "0"), ("2" if b["bankstatus"] & 0x02 else "1"), 
                             ("2" if b["bankstatus"] & 0x01 else "1"), os.path.basename(self.boot_manager.config[board]["program"])))

    def on_error(self, e):
        threading.Thread(target=tkinter.messagebox.showerror, args=("Bootloader error", str(e))).start()

    
    #######################################################
    # TKinter callback functions
    #######################################################

    def on_quit(self):
        self.closed = True
        self.boot_manager.on_board_state_change = lambda *args: None
        self.boot_manager.on_board_added = lambda *args: None
        self.boot_manager.on_error = lambda *args: None
        self.destroy()

    def open_context_menu(self, event):
        print("opening menu")
        iid = self.treeview.identify_row(event.y)
        if iid:
            self.context_target = int(iid)
            try:
                self.contextmenu.tk_popup(event.x_root, event.y_root)
            finally:
                self.contextmenu.grab_release()

    def focusout(self, event):
        if self.focus_get() != self.contextmenu:
            self.contextmenu.unpost()

    def click(self, event):
        if event.widget != self.focus_get():
            self.contextmenu.unpost()

    def set_filename(self, board):
        self.config[board]["program"] = filedialog.askopenfilename(filetypes=[("HEX file", "*.ihex")])
        self.boards[board]["elements"][5].config(text=os.path.basename(self.config[board]["program"]))

