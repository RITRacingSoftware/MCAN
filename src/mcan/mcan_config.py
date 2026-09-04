import tkinter
from tkinter import ttk

class ConfigMenu(tkinter.Toplevel):
    def __init__(self, inst):
        super().__init__()
        self.inst = inst
        self.context_target = None

        self.sources_frame = tkinter.LabelFrame(self, text="Sources")
        self.sources_frame.grid(row=0, column=0)
        self.sources_frame.columnconfigure(0, weight=1)
        
        self.sources_tree = ttk.Treeview(self.sources_frame)
        self.sources_tree.bind("<Button-3>", self.open_context_menu)
        self.sources_tree["columns"] = ["type", "description"]
        self.sources_tree.column("#0", width=0, stretch=tkinter.NO)
        self.sources_tree.column("type", width=100, stretch=tkinter.NO)
        self.sources_tree.column("description", width=200, stretch=tkinter.YES)
        self.sources_tree.heading("type", text="Type", anchor=tkinter.CENTER)
        self.sources_tree.heading("description", text="Description", anchor=tkinter.CENTER)
        self.sources_tree.grid(row=0, column=0, sticky="news")
        
        vsb = ttk.Scrollbar(self.sources_frame, orient="vertical", command=self.sources_tree.yview)
        vsb.grid(row=0, column=1, sticky="news")
        self.sources_tree.config(yscrollcommand=vsb.set)

        self.rx_frame = tkinter.LabelFrame(self, text="RX filters")
        self.rx_frame.grid(row=1, column=0)

        self.contextmenu = tkinter.Menu(self, tearoff=0)
        self.contextmenu.add_command(label="Options", command=self.open_options)
        self.contextmenu.bind("<FocusOut>", self.focusout)

        self.bind("<ButtonRelease-1>", self.click)


        self.update_sources(self.inst.source_list)

    def update_sources(self, sources):
        self.sources_tree.delete(*self.sources_tree.get_children())
        for i, s in enumerate(sources):
            t, d = s.dump_string()
            self.sources_tree.insert("", "end", str(i), values=(t, d))
    
    def open_context_menu(self, event):
        print("opening menu")
        iid = self.sources_tree.identify_row(event.y)
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

    def open_options(self, event):
        pass

