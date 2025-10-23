# --- START OF FILE toolkit_lib/ui/tabs/tab_apps.py ---

import tkinter as tk
from tkinter import ttk
from ..helpers import ToolTip

def create_apps_tab(notebook, app):
    tab = ttk.Frame(notebook, padding="10")
    notebook.add(tab, text='Aplicaciones 📦')

    controls = ttk.Frame(tab); controls.pack(fill='x', pady=(0, 10))
    ttk.Button(controls, text="Refrescar 🔄", command=lambda: app._rescan_and_refresh_ui()).pack(side="left")
    app.search_var = tk.StringVar(); app.search_var.trace_add("write", lambda *a: app._filter_app_tree())
    ttk.Label(controls, text="🔍 Buscar:").pack(side="left", padx=(10,5)); ttk.Entry(controls, textvariable=app.search_var).pack(side="left", fill='x', expand=True)

    tree_frame = ttk.Frame(tab); tree_frame.pack(fill='both', expand=True)
    app.app_tree = ttk.Treeview(tree_frame, columns=('status_icon', 'status_text', 'progress', 'selector'), show='tree headings')
    app.app_tree.heading('#0', text='Aplicación'); app.app_tree.heading('status_icon', text='Estado'); app.app_tree.heading('status_text', text=''); app.app_tree.heading('progress', text='Progreso'); app.app_tree.heading('selector', text='Versión/Archivo')
    app.app_tree.column('#0', width=250, stretch=tk.YES); app.app_tree.column('status_icon', width=40, anchor='center'); app.app_tree.column('status_text', width=120); app.app_tree.column('progress', width=120); app.app_tree.column('selector', width=180, stretch=tk.YES)
    app.app_tree.tag_configure('disabled', foreground='gray'); app.app_tree.tag_configure('category', font=("Segoe UI", 10, "bold")); app.app_tree.bind('<Button-1>', app._on_tree_click)
    
    scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=app.app_tree.yview); app.app_tree.configure(yscrollcommand=scroll.set)
    app.app_tree.pack(side=tk.LEFT, fill='both', expand=True); scroll.pack(side=tk.RIGHT, fill='y')
    
    return tab