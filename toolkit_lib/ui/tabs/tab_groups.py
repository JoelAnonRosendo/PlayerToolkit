# --- START OF FILE toolkit_lib/ui/tabs/tab_groups.py ---

import tkinter as tk
from tkinter import ttk, messagebox
from ..dialogs import open_group_manager

def create_groups_tab(notebook, app):
    tab = ttk.Frame(notebook, padding="10"); notebook.add(tab, text='Grupos 🗂️')
    tab.rowconfigure(1, weight=1); tab.columnconfigure(0, weight=1)

    controls = ttk.Frame(tab); controls.grid(row=0, column=0, sticky='ew', pady=(0, 10))
    ttk.Label(controls, text="Grupo:").pack(side=tk.LEFT); combo = ttk.Combobox(controls, state="readonly"); combo.pack(side=tk.LEFT, fill='x', expand=True, padx=5)
    
    contents = tk.Listbox(tab); contents.grid(row=1, column=0, sticky='nsew')
    
    def refresh_combo(): groups=app._load_groups(); combo['values']=sorted(groups.keys()); combo.set(''); contents.delete(0,tk.END)
    def on_select(e): contents.delete(0,tk.END); [contents.insert(tk.END, n) for n in sorted(app._load_groups().get(combo.get(),[]))]
    def apply():
        if not combo.get(): return
        app.apply_group_from_dashboard(combo.get())

    combo.bind('<<ComboboxSelected>>', on_select)
    buttons = ttk.Frame(tab); buttons.grid(row=2, column=0, sticky='ew', pady=(10, 0))
    ttk.Button(buttons, text="Aplicar Grupo", command=apply).pack(side=tk.LEFT, expand=True, fill='x', padx=(0,5))
    ttk.Button(buttons, text="Gestionar Grupos...", command=lambda: open_group_manager(app.root, refresh_combo, app.app_configs)).pack(side=tk.LEFT, expand=True, fill='x')
    
    refresh_combo()
    return tab