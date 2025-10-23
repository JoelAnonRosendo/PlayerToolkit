# --- START OF FILE toolkit_lib/ui/dialogs.py ---

import tkinter as tk
from tkinter import ttk, simpledialog, filedialog, messagebox
import json
from pathlib import Path
import sys
from .helpers import ScrollableFrame, ToolTip
from ..config import *

class ComboboxDialog(simpledialog.Dialog):
    def __init__(self, parent, title, prompt, options, initialvalue=None, readonly=True):
        self.prompt, self.options, self._initialvalue, self.readonly = prompt, options, initialvalue, readonly
        super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text=self.prompt, wraplength=300).pack(pady=10, padx=10)
        self.combo = ttk.Combobox(master, values=self.options, state="readonly" if self.readonly else "normal", width=40)
        self.combo.pack(padx=10, pady=(0, 10))
        if self._initialvalue is not None: self.combo.set(self._initialvalue)
        elif self.options: self.combo.current(0)
        return self.combo

    def apply(self): self.result = self.combo.get()

class NewAppConfigDialog(simpledialog.Dialog):
    def __init__(self, parent, title, app_name, initial_config=None):
        self.app_name, self.config = app_name, initial_config or DEFAULT_APP_CONFIG.copy()
        super().__init__(parent, title)

    def body(self, master):
        master.columnconfigure(1, weight=1); self.entries = {}
        fields = {"Icono:": ("icon", self.config['icon']), "Categoría:": ("categoria", self.config['categoria']),
                  "Tipo:": ("tipo", self.config['tipo']), "Args (JSON):": ("args_instalacion", str(self.config['args_instalacion'])),
                  "Clave Desinst.:": ("uninstall_key", self.config.get('uninstall_key') or ""),"URL:": ("url", self.config.get('url') or "")}
        for i, (label_text, (key, val)) in enumerate(fields.items()):
            ttk.Label(master, text=label_text).grid(row=i, column=0, sticky='w', padx=5, pady=3)
            var = tk.StringVar(value=val)
            if key == "tipo": widget = ttk.Combobox(master, textvariable=var, state='readonly', values=[TASK_TYPE_LOCAL_INSTALL, TASK_TYPE_MANUAL_ASSISTED, TASK_TYPE_COPY_INTERACTIVE, TASK_TYPE_CLEAN_TEMP, TASK_TYPE_POWER_CONFIG, TASK_TYPE_RUN_POWERSHELL])
            else: widget = ttk.Entry(master, textvariable=var)
            widget.grid(row=i, column=1, sticky='ew', padx=5, pady=3); self.entries[key] = var
        return master

    def apply(self):
        self.result = DEFAULT_APP_CONFIG.copy()
        try:
            self.result['icon'] = self.entries['icon'].get()
            self.result['categoria'] = self.entries['categoria'].get()
            self.result['tipo'] = self.entries['tipo'].get()
            self.result['args_instalacion'] = json.loads(self.entries['args_instalacion'].get() or "[]")
            self.result['uninstall_key'] = self.entries['uninstall_key'].get() or None
            self.result['url'] = self.entries['url'].get() or None
            if 'script_path' in self.config: self.result['script_path'] = self.config['script_path']
        except (json.JSONDecodeError, ValueError) as e: messagebox.showerror("Error", f"Argumentos no es una lista JSON válida.\n{e}", parent=self); self.result = None

class ConfigWizardDialog(simpledialog.Dialog):
    def __init__(self, parent, title, app_name, app_config, all_app_keys):
        self.app_name, self.config, self.all_app_keys = app_name, app_config.copy(), all_app_keys
        self.current_step, self.steps, self.entries = 0, [], {}
        super().__init__(parent, title)

    def body(self, master):
        self.main_frame = ttk.Frame(master); self.main_frame.pack(expand=True, fill="both", padx=10, pady=10)
        self.steps = [self._create_step_general(self.main_frame), self._create_step_advanced(self.main_frame), self._create_step_dependencies(self.main_frame)]
        self.steps[0].pack(expand=True, fill="both")
        self.button_frame = ttk.Frame(master); self.button_frame.pack(fill='x', padx=10, pady=(0, 10))
        self.back_button = ttk.Button(self.button_frame, text="< Atrás", command=self.prev_step, state=tk.DISABLED); self.back_button.pack(side="left")
        self.next_button = ttk.Button(self.button_frame, text="Siguiente >", command=self.next_step); self.next_button.pack(side="left", padx=5)
        return self.main_frame

    def _create_step_general(self, parent):
        frame = ttk.Frame(parent, padding=10); frame.columnconfigure(1, weight=1); ttk.Label(frame, text="Configuración General", font=("Segoe UI", 12, "bold")).grid(row=0, columnspan=2, pady=(0, 10))
        fields = {"Icono:": ("icon", self.config['icon']), "Categoría:": ("categoria", self.config['categoria']),"Tipo:": ("tipo", self.config['tipo']), "Clave Desinst.:": ("uninstall_key", self.config.get('uninstall_key') or ""),"URL:": ("url", self.config.get('url') or "")}
        for i, (label, (key, val)) in enumerate(fields.items()):
            ttk.Label(frame, text=label).grid(row=i+1, column=0, sticky='w', padx=5, pady=5); var = tk.StringVar(value=val)
            if key == "tipo": widget = ttk.Combobox(frame, textvariable=var, state='readonly', values=[TASK_TYPE_LOCAL_INSTALL, TASK_TYPE_MANUAL_ASSISTED, TASK_TYPE_COPY_INTERACTIVE, TASK_TYPE_CLEAN_TEMP, TASK_TYPE_POWER_CONFIG, TASK_TYPE_RUN_POWERSHELL, TASK_TYPE_INSTALL_DRIVER, TASK_TYPE_UNINSTALL])
            else: widget = ttk.Entry(frame, textvariable=var)
            widget.grid(row=i+1, column=1, sticky='ew', padx=5, pady=5); self.entries[key] = var
        return frame

    def _create_step_advanced(self, parent):
        frame = ttk.Frame(parent, padding=10); frame.columnconfigure(1, weight=1); ttk.Label(frame, text="Avanzado y Scripts", font=("Segoe UI", 12, "bold")).grid(row=0, columnspan=2, pady=(0, 10))
        fields = {"Args (JSON):": ("args_instalacion", json.dumps(self.config.get('args_instalacion', []))),"Script Pre-Tarea:": ("pre_task_script", self.config.get('pre_task_script') or ""),"Script Post-Tarea:": ("post_task_script", self.config.get('post_task_script') or ""),"Script PowerShell:": ("script_path", self.config.get('script_path') or "")}
        for i, (label, (key, val)) in enumerate(fields.items()):
            ttk.Label(frame, text=label).grid(row=i+1, column=0, sticky='w', padx=5, pady=5); var = tk.StringVar(value=val)
            entry = ttk.Entry(frame, textvariable=var); entry.grid(row=i+1, column=1, sticky='ew', padx=5, pady=5); self.entries[key] = var
            ToolTip(entry, "Para listas, usar formato JSON. Ej: [\"/S\", \"-D=C:\\\\\"]")
        return frame

    def _create_step_dependencies(self, parent):
        frame = ttk.Frame(parent, padding=10); ttk.Label(frame, text="Dependencias", font=("Segoe UI", 12, "bold")).pack(anchor='w'); ttk.Label(frame, text="Selecciona las apps a instalar ANTES que esta.").pack(anchor='w', pady=(0,10))
        scroll_frame = ScrollableFrame(frame); scroll_frame.pack(expand=True, fill='both')
        self.dep_vars, current_deps = {}, self.config.get('dependencies', [])
        for app_key in sorted([key for key in self.all_app_keys if key != self.app_name]):
            var = tk.BooleanVar(value=(app_key in current_deps))
            chk = ttk.Checkbutton(scroll_frame.scrollable_frame, text=app_key, variable=var); chk.pack(anchor="w", padx=10, pady=2)
            self.dep_vars[app_key] = var
        return frame

    def show_step(self, step_num):
        [step.pack_forget() for step in self.steps]; self.steps[step_num].pack(expand=True, fill="both"); self.current_step = step_num
        self.back_button.config(state=tk.NORMAL if self.current_step > 0 else tk.DISABLED)
        self.next_button.config(state=tk.NORMAL if self.current_step < len(self.steps) - 1 else tk.DISABLED)

    def next_step(self):
        if self.current_step < len(self.steps) - 1: self.show_step(self.current_step + 1)
            
    def prev_step(self):
        if self.current_step > 0: self.show_step(self.current_step - 1)

    def buttonbox(self):
        box = ttk.Frame(self)
        ttk.Button(box, text="Guardar y Cerrar", width=15, command=self.ok, default=tk.ACTIVE).pack(side=tk.RIGHT, padx=5, pady=5)
        ttk.Button(box, text="Cancelar", width=10, command=self.cancel).pack(side=tk.RIGHT, padx=5)
        self.bind("<Escape>", self.cancel); box.pack()

    def apply(self):
        try:
            new_config = self.config.copy()
            for key, var in self.entries.items():
                value = var.get()
                if key == "args_instalacion": new_config[key] = json.loads(value or "[]")
                else: new_config[key] = value if value else None
            new_config['dependencies'] = [name for name, var in self.dep_vars.items() if var.get()]
            self.result = new_config
        except json.JSONDecodeError as e: messagebox.showerror("Error de Formato", f"Valor JSON no válido.\n{e}", parent=self); self.result = None
        except Exception as e: messagebox.showerror("Error", f"Ocurrió un error al guardar: {e}", parent=self); self.result = None

class VariablesManagerDialog(simpledialog.Dialog):
    def __init__(self, parent, title, parent_app):
        self.parent_app = parent_app; self.variables = self.parent_app._load_custom_variables()
        super().__init__(parent, title)

    def body(self, master):
        self.tree = ttk.Treeview(master, columns=('var', 'value'), show='headings', height=8); self.tree.heading('var', text='Variable (ej: %MY_PATH%)'); self.tree.heading('value', text='Valor'); self.tree.pack(padx=10, pady=10, fill="both", expand=True); self.populate_tree()
        btn_frame = ttk.Frame(master); btn_frame.pack(fill='x', padx=10, pady=(0, 10))
        ttk.Button(btn_frame, text="Añadir", command=self.add_var).pack(side="left"); ttk.Button(btn_frame, text="Editar", command=self.edit_var).pack(side="left", padx=5); ttk.Button(btn_frame, text="Eliminar", command=self.delete_var).pack(side="left")
        return self.tree

    def populate_tree(self):
        [self.tree.delete(i) for i in self.tree.get_children()]; [self.tree.insert('', 'end', values=(f"%{var}%", val)) for var, val in sorted(self.variables.items())]

    def add_var(self):
        name = simpledialog.askstring("Nueva Variable", "Nombre (sin %):", parent=self)
        if name and name not in self.variables:
            value = simpledialog.askstring("Valor", f"Valor para %{name}%:", parent=self)
            if value is not None: self.variables[name] = value; self.populate_tree()

    def edit_var(self):
        sel = self.tree.focus();
        if not sel: return
        item = self.tree.item(sel); name, old_val = item['values'][0].strip('%'), item['values'][1]
        new_val = simpledialog.askstring("Editar Valor", f"Nuevo valor para %{name}%:", initialvalue=old_val, parent=self)
        if new_val is not None: self.variables[name] = new_val; self.populate_tree()

    def delete_var(self):
        sel = self.tree.focus();
        if not sel: return
        name = self.tree.item(sel)['values'][0].strip('%')
        if messagebox.askyesno("Confirmar", f"¿Eliminar %{name}%?", parent=self): del self.variables[name]; self.populate_tree()

    def apply(self): self.parent_app._save_custom_variables(self.variables)

class GroupEditorDialog(simpledialog.Dialog):
    def __init__(self, parent, title, app_configs, group_name=None, group_apps=None):
        self.app_configs, self.group_name, self.group_apps, self.app_vars = app_configs, group_name, group_apps or [], {}; super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text="Nombre:").grid(row=0, sticky="w", padx=5, pady=5); self.name_entry = ttk.Entry(master, width=40)
        if self.group_name: self.name_entry.insert(0, self.group_name)
        self.name_entry.grid(row=0, column=1, padx=5, pady=5); scroll = ScrollableFrame(master); scroll.grid(row=1, columnspan=2, sticky='nsew', padx=5, pady=5)
        master.grid_rowconfigure(1, weight=1); master.grid_columnconfigure(1, weight=1)
        for name in sorted(self.app_configs.keys()):
            var = tk.BooleanVar(value=(name in self.group_apps)); chk = ttk.Checkbutton(scroll.scrollable_frame, text=name, variable=var); chk.pack(anchor="w", padx=10, pady=2); self.app_vars[name] = var
        return self.name_entry

    def apply(self):
        name = self.name_entry.get().strip()
        if not name: messagebox.showwarning("Vacío", "El nombre no puede estar vacío.", parent=self); self.result = None; return
        self.result = (name, [n for n, v in self.app_vars.items() if v.get()])

def open_group_manager(parent, callback_on_close, app_configs):
    win = tk.Toplevel(parent); win.title("Gestionar Grupos"); win.transient(parent); win.grab_set(); win.geometry("450x450")
    base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(sys.argv[0]).parent
    grupos_dir = base / "Programas" / "Grupos"
    def load_groups():
        grupos_dir.mkdir(exist_ok=True); groups = {}
        for f in grupos_dir.glob("*.txt"): groups[f.stem] = [l.strip() for l in open(f, 'r', encoding='utf-8') if l.strip()]
        return groups
    groups = load_groups()
    def save(name, apps): open(grupos_dir / f"{name}.txt", 'w', encoding='utf-8').write("\n".join(apps))
    def delete(name): (grupos_dir / f"{name}.txt").unlink(missing_ok=True)
    def populate(): listbox.delete(0, tk.END); [listbox.insert(tk.END, n) for n in sorted(groups.keys())]
    def add():
        d = GroupEditorDialog(win, "Crear Grupo", app_configs)
        if d.result: name, apps = d.result; save(name, apps); groups[name] = apps; populate()
    def edit():
        if not listbox.curselection(): return
        old = listbox.get(listbox.curselection()[0])
        d = GroupEditorDialog(win, f"Editar {old}", app_configs, old, groups.get(old))
        if d.result: new, apps = d.result; 
        if new != old: delete(old); del groups[old]
        save(new, apps); groups[new] = apps; populate()
    def delete_selected():
        if not listbox.curselection(): return
        name = listbox.get(listbox.curselection()[0])
        if messagebox.askyesno("Confirmar", f"¿Eliminar '{name}'?", parent=win): delete(name); del groups[name]; populate()
    
    list_frame = ttk.Frame(win, padding=10); list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    listbox = tk.Listbox(list_frame); listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    btn_frame = ttk.Frame(win, padding=10); btn_frame.pack(side=tk.RIGHT, fill=tk.Y)
    ttk.Button(btn_frame, text="Nuevo...", command=add).pack(pady=5, fill=tk.X)
    ttk.Button(btn_frame, text="Editar...", command=edit).pack(pady=5, fill=tk.X)
    ttk.Button(btn_frame, text="Eliminar", command=delete_selected).pack(pady=5, fill=tk.X)
    populate(); win.protocol("WM_DELETE_WINDOW", lambda: (callback_on_close(), win.destroy()))