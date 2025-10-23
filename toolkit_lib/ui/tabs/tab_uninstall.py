# --- START OF FILE toolkit_lib/ui/tabs/tab_uninstall.py ---

import tkinter as tk
from tkinter import ttk
from ..helpers import ScrollableFrame

def create_uninstall_tab(notebook, app):
    tab = ttk.Frame(notebook, padding="10"); notebook.add(tab, text='Desinstalar 🗑️')
    
    controls = ttk.Frame(tab); controls.pack(fill='x', pady=(0, 10))
    search_var = tk.StringVar(); search_var.trace_add("write", lambda *a: app._filter_uninstall_list(search_var))
    ttk.Label(controls, text="🔍 Buscar:").pack(side=tk.LEFT); ttk.Entry(controls, textvariable=search_var).pack(side=tk.LEFT, fill='x', expand=True)

    scroll = ScrollableFrame(tab); scroll.pack(fill='both', expand=True)
    app.uninstall_frame = ttk.Frame(scroll.scrollable_frame, padding=10); app.uninstall_frame.pack(fill='both', expand=True)
    
    return tab