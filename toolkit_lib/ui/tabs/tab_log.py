# --- START OF FILE toolkit_lib/ui/tabs/tab_log.py ---

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

def create_log_tab(notebook, app):
    tab = ttk.Frame(notebook, padding="10"); notebook.add(tab, text='Log 📜')
    
    # Controles de Filtro y Exportación
    controls = ttk.Frame(tab); controls.pack(fill='x', pady=(0, 10))
    
    # Filtro por Nivel
    ttk.Label(controls, text="Nivel:").pack(side=tk.LEFT, padx=(0,5))
    app.log_level_filter = ttk.Combobox(controls, values=["TODOS", "INFO", "SUCCESS", "WARNING", "ERROR"], state="readonly", width=10)
    app.log_level_filter.set("TODOS")
    app.log_level_filter.pack(side=tk.LEFT)
    app.log_level_filter.bind("<<ComboboxSelected>>", lambda e: filter_log(app))
    
    # Filtro por Texto
    ttk.Label(controls, text="Buscar:", ).pack(side=tk.LEFT, padx=(10,5))
    app.log_text_filter_var = tk.StringVar()
    app.log_text_filter_var.trace_add("write", lambda *a: filter_log(app))
    ttk.Entry(controls, textvariable=app.log_text_filter_var).pack(side=tk.LEFT, fill='x', expand=True)
    
    ttk.Button(controls, text="Exportar...", command=lambda: export_log(app)).pack(side=tk.RIGHT, padx=(10,0))
    
    app.log_tree = ttk.Treeview(tab, columns=('time', 'level', 'message'), show='headings')
    app.log_tree.heading('time', text='Hora'); app.log_tree.heading('level', text='Nivel'); app.log_tree.heading('message', text='Mensaje')
    app.log_tree.column('time', width=100, stretch=tk.NO); app.log_tree.column('level', width=80, anchor='center', stretch=tk.NO)
    
    s = ttk.Style()
    for level, color in [("INFO", "white"), ("SUCCESS", "#40c840"), ("WARNING", "orange"), ("ERROR", "#ff5353")]:
        app.log_tree.tag_configure(level, foreground=color)
        s.configure(f"{level}.Treeview", background=s.lookup('TFrame', 'background')) # Color base
        # s.map(f"{level}.Treeview", background=[('selected', 'blue')]) # Si quieres cambiar el color de selección

    scroll = ttk.Scrollbar(tab, orient="vertical", command=app.log_tree.yview); app.log_tree.config(yscrollcommand=scroll.set)
    app.log_tree.pack(side=tk.LEFT, fill='both', expand=True); scroll.pack(side=tk.RIGHT, fill='y')

    app.original_log_data = [] # Para guardar todos los logs y poder filtrar

    return tab

def filter_log(app):
    level_filter = app.log_level_filter.get()
    text_filter = app.log_text_filter_var.get().lower()

    # Limpiar treeview
    [app.log_tree.delete(i) for i in app.log_tree.get_children()]

    # Repoblar con datos filtrados
    for time, level, msg in app.original_log_data:
        level_match = (level_filter == "TODOS" or level == level_filter)
        text_match = (text_filter in msg.lower())
        
        if level_match and text_match:
            app.log_tree.insert("", 0, values=(time, level, msg), tags=(level,))

def export_log(app):
    filepath = filedialog.asksaveasfilename(defaultextension=".log", filetypes=[("Log Files", "*.log")], title="Exportar Log", initialfile=f"PlayerToolkit_Log_{datetime.now():%Y-%m-%d_%H-%M}.log")
    if not filepath: return
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            for time, level, msg in reversed(app.original_log_data):
                f.write(f"[{time}] [{level}] {msg}\n")
        messagebox.showinfo("Éxito", "Log exportado correctamente.")
    except IOError as e:
        messagebox.showerror("Error", f"No se pudo guardar el archivo:\n{e}")