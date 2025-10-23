# --- START OF FILE toolkit_lib/ui/tabs/tab_config.py ---

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from ..dialogs import ConfigWizardDialog, VariablesManagerDialog
from ..helpers import ToolTip
import shutil

def create_config_tab(notebook, app):
    tab = ttk.Frame(notebook, padding="10"); notebook.add(tab, text='Configuración ⚙️')
    
    cfg_frame = ttk.LabelFrame(tab, text="Editor de Comportamiento", padding=15); cfg_frame.pack(fill="both", expand=True)
    cfg_frame.rowconfigure(0, weight=1); cfg_frame.columnconfigure(0, weight=1)
    
    cols = ("Aplicación", "Categoría", "Tipo", "Args", "Dependencias"); 
    app.config_treeview = ttk.Treeview(cfg_frame, columns=cols, show='headings', selectmode='browse')
    for col in cols: app.config_treeview.heading(col, text=col)
    app.config_treeview.grid(row=0, column=0, sticky='nsew')
    app.config_treeview.bind("<Double-1>", lambda e: on_config_edit(app))
    
    scroll = ttk.Scrollbar(cfg_frame, orient="vertical", command=app.config_treeview.yview); app.config_treeview.config(yscrollcommand=scroll.set); scroll.grid(row=0, column=1, sticky='ns')

    buttons = ttk.Frame(tab, padding=(0,10,0,0)); buttons.pack(fill='x', side='bottom')
    
    # --- BOTÓN "ACERCA DE..." AÑADIDO DE VUELTA ---
    ttk.Button(buttons, text="Acerca de...", command=app._show_about_dialog).pack(side='left')
    ttk.Button(buttons, text="Gestionar Variables...", command=lambda: VariablesManagerDialog(app.root, "Variables", app)).pack(side='left', padx=5)
    
    ttk.Button(buttons, text="Guardar Cambios", command=lambda: save_config(app)).pack(side='right')
    ttk.Button(buttons, text="Importar", command=lambda: import_config(app)).pack(side='right', padx=5)
    ttk.Button(buttons, text="Exportar", command=lambda: export_config(app)).pack(side='right')

    return tab

def on_config_edit(app):
    iid = app.config_treeview.focus()
    if not iid: return
    d = ConfigWizardDialog(app.root, f"Editando: {iid}", iid, app.app_configs[iid], list(app.app_configs.keys()))
    if d.result: app.app_configs[iid] = d.result; app.modified_configs.add(iid); app._populate_config_treeview()

def save_config(app):
    if not app.modified_configs: messagebox.showinfo("Sin cambios", "No hay cambios para guardar.", parent=app.root); return
    cfg_file = app.conf_dir/"config_personalizada.json"; current = {}
    if cfg_file.exists():
        try:
            with open(cfg_file, 'r', encoding='utf-8') as f: current=json.load(f)
        except Exception: pass
    for name in app.modified_configs: current[name] = app.app_configs[name]
    with open(cfg_file, 'w', encoding='utf-8') as f: json.dump(current, f, indent=4)
    messagebox.showinfo("Guardado", "Configuración guardada.", parent=app.root); app.modified_configs.clear()

def import_config(app):
    src = filedialog.askopenfilename(filetypes=[("JSON", "*.json")], title="Importar configuración")
    if src: shutil.copy2(src, app.conf_dir/"config_personalizada.json"); messagebox.showinfo("Éxito", "Configuración importada. Reinicia para aplicar.", parent=app.root)

def export_config(app):
    cfg_file = app.conf_dir/"config_personalizada.json"
    if not cfg_file.exists():
        messagebox.showwarning("Vacío", "No hay configuración personalizada para exportar.", parent=app.root)
        return
    dest = filedialog.asksaveasfilename(defaultextension=".json", title="Exportar configuración")
    if dest: shutil.copy2(cfg_file, dest); messagebox.showinfo("Éxito", f"Configuración exportada.", parent=app.root)