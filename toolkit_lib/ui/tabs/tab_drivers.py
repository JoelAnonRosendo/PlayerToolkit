# --- START OF FILE toolkit_lib/ui/tabs/tab_drivers.py ---

import tkinter as tk
from tkinter import ttk

def create_drivers_tab(notebook, app):
    tab = ttk.Frame(notebook, padding="10")
    notebook.add(tab, text='Drivers 🔩')
    
    top_frame = ttk.Frame(tab); top_frame.pack(fill='x', pady=(0,10))
    ttk.Label(top_frame, text="Instalación de Drivers", font=("Segoe UI", 12, "bold")).pack(side="left")
    ttk.Button(top_frame, text="Refrescar Lista 🔄", command=app.scan_and_populate_drivers).pack(side="right")
    
    tree_frame = ttk.Frame(tab); tree_frame.pack(fill='both', expand=True)
    app.drivers_tree = ttk.Treeview(tree_frame, columns=('status'), show='tree headings', selectmode='extended')
    app.drivers_tree.heading('#0', text='Paquete de Driver'); app.drivers_tree.heading('status', text='Estado');
    app.drivers_tree.column('#0', width=300)
    
    scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=app.drivers_tree.yview)
    app.drivers_tree.configure(yscrollcommand=scrollbar.set)
    app.drivers_tree.pack(side=tk.LEFT, fill='both', expand=True); scrollbar.pack(side=tk.RIGHT, fill='y')
    
    return tab