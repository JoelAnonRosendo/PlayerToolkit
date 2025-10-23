# --- START OF FILE toolkit_lib/ui.py ---

import tkinter as tk
from tkinter import ttk, simpledialog, filedialog, messagebox
import json
import shutil
import sv_ttk # type: ignore
import logging
from pathlib import Path
import sys
import os
import threading
import webbrowser
from queue import Queue
from collections import defaultdict
import requests
import re
from datetime import datetime
import subprocess

# Importaciones relativas
from .config import *
from .tasks import TaskProcessor
from .utils import scan_installed_software, clear_cache

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD # type: ignore
    DND_SUPPORT = True
except ImportError:
    DND_SUPPORT = False

APP_VERSION = "Versión 6.1.7"
GITHUB_OWNER = "JoelAnonRosendo"
GITHUB_REPO = "PlayerToolkit"
UPDATER_SCRIPT_NAME = "updater.bat"

STATUS_ICONS = {
    "pending": "▫️", "running": "⚙️", "success": "✅",
    "fail": "❌", "installed": "✔️"
}

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event):
        if self.tooltip_window or not self.text:
            return
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20

        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        
        label = ttk.Label(self.tooltip_window, text=self.text, justify='left',
                          background="#2e2e2e", foreground="#cccccc", relief='solid', borderwidth=1,
                          font=("Segoe UI", 9), padding="4 4 4 4")
        label.pack(ipadx=1)

    def hide_tooltip(self, event):
        if self.tooltip_window:
            self.tooltip_window.destroy()
        self.tooltip_window = None


class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind('<Enter>', self._bind_mousewheel)
        self.canvas.bind('<Leave>', self._unbind_mousewheel)

    def _bind_mousewheel(self, event):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, event):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        scroll_speed_multiplier = 120 if sys.platform != "darwin" else 1
        self.canvas.yview_scroll(int(-1*(event.delta/scroll_speed_multiplier)), "units")

class ComboboxDialog(simpledialog.Dialog):
    def __init__(self, parent, title, prompt, options, initialvalue=None, readonly=True):
        self.prompt = prompt
        self.options = options
        self._initialvalue = initialvalue
        self.readonly = readonly
        super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text=self.prompt, wraplength=300).pack(pady=10, padx=10)
        combo_state = "readonly" if self.readonly else "normal"
        self.combo = ttk.Combobox(master, values=self.options, state=combo_state, width=40)
        self.combo.pack(padx=10, pady=(0, 10))
        if self._initialvalue is not None: self.combo.set(self._initialvalue)
        elif not self.readonly and self.options: self.combo.set(self.options[0])
        elif self.readonly and self.options: self.combo.current(0)
        return self.combo

    def apply(self):
        self.result = self.combo.get()

class NewAppConfigDialog(simpledialog.Dialog):
    def __init__(self, parent, title, app_name, initial_config=None):
        self.app_name = app_name
        self.config = initial_config or DEFAULT_APP_CONFIG.copy()
        super().__init__(parent, title)

    def body(self, master):
        master.columnconfigure(1, weight=1)
        fields = {"Icono:": ("icon", self.config['icon']), "Categoría:": ("categoria", self.config['categoria']),
                  "Tipo de Tarea:": ("tipo", self.config['tipo']), "Argumentos (lista JSON):": ("args_instalacion", str(self.config['args_instalacion'])),
                  "Clave de Desinstalación:": ("uninstall_key", self.config.get('uninstall_key') or ""),"URL de Descarga:": ("url", self.config.get('url') or ""),}
        self.entries = {}
        first_widget = None
        for i, (label_text, (key, default_val)) in enumerate(fields.items()):
            ttk.Label(master, text=label_text).grid(row=i, column=0, sticky='w', padx=5, pady=3)
            var = tk.StringVar(value=default_val)
            if key == "tipo":
                widget = ttk.Combobox(master, textvariable=var, state='readonly', values=[TASK_TYPE_LOCAL_INSTALL, TASK_TYPE_MANUAL_ASSISTED, TASK_TYPE_COPY_INTERACTIVE, TASK_TYPE_CLEAN_TEMP, TASK_TYPE_POWER_CONFIG, TASK_TYPE_RUN_POWERSHELL])
            else:
                widget = ttk.Entry(master, textvariable=var)
            widget.grid(row=i, column=1, sticky='ew', padx=5, pady=3)
            self.entries[key] = var
            if first_widget is None: first_widget = widget
        return first_widget

    def apply(self):
        self.result = DEFAULT_APP_CONFIG.copy()
        try:
            self.result['icon'] = self.entries['icon'].get()
            self.result['categoria'] = self.entries['categoria'].get()
            self.result['tipo'] = self.entries['tipo'].get()
            args_str = self.entries['args_instalacion'].get()
            self.result['args_instalacion'] = json.loads(args_str.replace("'", '"')) if args_str else []
            self.result['uninstall_key'] = self.entries['uninstall_key'].get() or None
            self.result['url'] = self.entries['url'].get() or None
            if 'script_path' in self.config: self.result['script_path'] = self.config['script_path']
        except (json.JSONDecodeError, ValueError) as e:
            messagebox.showerror("Error de Formato", f"El valor para 'Argumentos' no es una lista JSON válida.\nEjemplo: [\"/S\", \"/NORESTART\"]\n\nError: {e}", parent=self)
            self.result = None

class AdvancedConfigDialog(simpledialog.Dialog):
    def __init__(self, parent, title, app_name, app_config, all_app_keys):
        self.app_name = app_name; self.config = app_config.copy(); self.all_app_keys = all_app_keys
        super().__init__(parent, title)

    def body(self, master):
        self.entries = {}; notebook = ttk.Notebook(master); notebook.pack(expand=True, fill="both", padx=10, pady=10)
        general_frame = ttk.Frame(notebook, padding=10); notebook.add(general_frame, text="General"); general_frame.columnconfigure(1, weight=1)
        fields_general = {"Icono:": ("icon", self.config['icon']), "Categoría:": ("categoria", self.config['categoria']),"Tipo de Tarea:": ("tipo", self.config['tipo']), "Clave de Desinstalación:": ("uninstall_key", self.config.get('uninstall_key') or ""),"URL de Descarga:": ("url", self.config.get('url') or ""),}
        for i, (label, (key, val)) in enumerate(fields_general.items()):
            ttk.Label(general_frame, text=label).grid(row=i, column=0, sticky='w', padx=5, pady=5); var = tk.StringVar(value=val)
            if key == "tipo": widget = ttk.Combobox(general_frame, textvariable=var, state='readonly', values=[TASK_TYPE_LOCAL_INSTALL, TASK_TYPE_MANUAL_ASSISTED, TASK_TYPE_COPY_INTERACTIVE, TASK_TYPE_CLEAN_TEMP, TASK_TYPE_POWER_CONFIG, TASK_TYPE_RUN_POWERSHELL, TASK_TYPE_MODIFY_REGISTRY, TASK_TYPE_MANAGE_SERVICE, TASK_TYPE_CREATE_SCHEDULED_TASK, TASK_TYPE_UNINSTALL])
            else: widget = ttk.Entry(general_frame, textvariable=var)
            widget.grid(row=i, column=1, sticky='ew', padx=5, pady=5); self.entries[key] = var
        advanced_frame = ttk.Frame(notebook, padding=10); notebook.add(advanced_frame, text="Avanzado"); advanced_frame.columnconfigure(1, weight=1)
        fields_advanced = {"Argumentos (JSON):": ("args_instalacion", json.dumps(self.config.get('args_instalacion', []))),"Dependencias (JSON):": ("dependencies", json.dumps(self.config.get('dependencies', []))),"Script Pre-Tarea:": ("pre_task_script", self.config.get('pre_task_script') or ""),"Script Post-Tarea:": ("post_task_script", self.config.get('post_task_script') or ""),"Script PowerShell:": ("script_path", self.config.get('script_path') or ""),}
        for i, (label, (key, val)) in enumerate(fields_advanced.items()):
            ttk.Label(advanced_frame, text=label).grid(row=i, column=0, sticky='w', padx=5, pady=5); var = tk.StringVar(value=val)
            entry = ttk.Entry(advanced_frame, textvariable=var); entry.grid(row=i, column=1, sticky='ew', padx=5, pady=5); self.entries[key] = var
        return notebook

    def apply(self):
        try:
            new_config = self.config.copy()
            for key, var in self.entries.items():
                value = var.get()
                if key in ["args_instalacion", "dependencies"]: new_config[key] = json.loads(value or "[]")
                elif not value: new_config[key] = None
                else: new_config[key] = value
            self.result = new_config
        except json.JSONDecodeError as e: messagebox.showerror("Error de Formato", f"El valor para un campo JSON no es válido.\nError: {e}", parent=self); self.result = None
        except Exception as e: messagebox.showerror("Error", f"Ocurrió un error al guardar: {e}", parent=self); self.result = None

class VariablesManagerDialog(simpledialog.Dialog):
    def __init__(self, parent, title, parent_app):
        self.parent_app = parent_app; self.variables = self.parent_app._load_custom_variables()
        super().__init__(parent, title)

    def body(self, master):
        self.tree = ttk.Treeview(master, columns=('var', 'value'), show='headings', height=8); self.tree.heading('var', text='Variable (ej: %MY_PATH%)'); self.tree.heading('value', text='Valor')
        self.tree.pack(padx=10, pady=10, fill="both", expand=True); self.populate_tree()
        btn_frame = ttk.Frame(master); btn_frame.pack(fill='x', padx=10, pady=(0, 10))
        ttk.Button(btn_frame, text="Añadir...", command=self.add_var).pack(side="left"); ttk.Button(btn_frame, text="Editar...", command=self.edit_var).pack(side="left", padx=5); ttk.Button(btn_frame, text="Eliminar", command=self.delete_var).pack(side="left")
        return self.tree

    def populate_tree(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        for var, val in sorted(self.variables.items()): self.tree.insert('', 'end', values=(f"%{var}%", val))

    def add_var(self):
        name = simpledialog.askstring("Nueva Variable", "Nombre de la variable (sin %):", parent=self)
        if name and name not in self.variables:
            value = simpledialog.askstring("Valor", f"Valor para %{name}%:", parent=self)
            if value is not None: self.variables[name] = value; self.populate_tree()

    def edit_var(self):
        selected = self.tree.focus();
        if not selected: return
        item = self.tree.item(selected); name = item['values'][0].strip('%'); old_value = item['values'][1]
        new_value = simpledialog.askstring("Editar Valor", f"Nuevo valor para {item['values'][0]}:", initialvalue=old_value, parent=self)
        if new_value is not None: self.variables[name] = new_value; self.populate_tree()

    def delete_var(self):
        selected = self.tree.focus();
        if not selected: return
        name = self.tree.item(selected)['values'][0].strip('%')
        if messagebox.askyesno("Confirmar", f"¿Eliminar la variable %{name}%?", parent=self):
            del self.variables[name]; self.populate_tree()

    def apply(self): self.parent_app._save_custom_variables(self.variables)


class GroupEditorDialog(simpledialog.Dialog):
    def __init__(self, parent, title, app_configs, group_name=None, group_apps=None):
        self.app_configs = app_configs; self.group_name = group_name; self.group_apps = group_apps or []
        self.app_vars = {}; super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text="Nombre del Grupo:").grid(row=0, sticky="w", padx=5, pady=5); self.name_entry = ttk.Entry(master, width=40)
        if self.group_name: self.name_entry.insert(0, self.group_name)
        self.name_entry.grid(row=0, column=1, padx=5, pady=5); scroll_frame = ScrollableFrame(master)
        scroll_frame.grid(row=1, columnspan=2, sticky='nsew', padx=5, pady=5); master.grid_rowconfigure(1, weight=1); master.grid_columnconfigure(1, weight=1)
        for app_name in sorted(self.app_configs.keys()):
            var = tk.BooleanVar(value=(app_name in self.group_apps)); chk = ttk.Checkbutton(scroll_frame.scrollable_frame, text=app_name, variable=var)
            chk.pack(anchor="w", padx=10, pady=2); self.app_vars[app_name] = var
        return self.name_entry

    def apply(self):
        new_name = self.name_entry.get().strip()
        if not new_name: messagebox.showwarning("Nombre vacío", "El nombre del grupo no puede estar vacío.", parent=self); self.result = None; return
        self.result = (new_name, [name for name, var in self.app_vars.items() if var.get()])

def open_group_manager(parent, callback_on_close, app_configs):
    win = tk.Toplevel(parent); win.title("Gestionar Grupos"); win.transient(parent); win.grab_set(); win.geometry("450x450")
    base_path = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(sys.argv[0]).parent
    grupos_dir = base_path / "Programas" / "Grupos"
    def load_groups_local():
        grupos_dir.mkdir(exist_ok=True); groups = {}
        try:
            for filepath in grupos_dir.glob("*.txt"):
                with open(filepath, 'r', encoding='utf-8') as f: groups[filepath.stem] = [line.strip() for line in f if line.strip()]
        except IOError as e: messagebox.showerror("Error", f"No se pudieron cargar los grupos:\n{e}", parent=win)
        return groups
    groups = load_groups_local()
    def save_group(name, apps):
        try:
            with open(grupos_dir / f"{name}.txt", 'w', encoding='utf-8') as f: f.write("\n".join(apps)); return True
        except IOError as e: messagebox.showerror("Error al Guardar", f"No se pudo guardar el grupo '{name}':\n{e}", parent=win); return False
    def delete_group_file(name):
        try: (grupos_dir / f"{name}.txt").unlink(missing_ok=True); return True
        except IOError as e: messagebox.showerror("Error al Eliminar", f"No se pudo eliminar el grupo '{name}':\n{e}", parent=win); return False
    def populate_listbox(): listbox.delete(0, tk.END); [listbox.insert(tk.END, name) for name in sorted(groups.keys())]
    def add_group():
        dialog = GroupEditorDialog(win, "Crear Nuevo Grupo", app_configs)
        if dialog.result:
            name, apps = dialog.result
            if name in groups: messagebox.showwarning("Duplicado", f"El grupo '{name}' ya existe.", parent=win); return
            if save_group(name, apps): groups[name] = apps; populate_listbox()
    def edit_group():
        selected_idx = listbox.curselection()
        if not selected_idx: return
        old_name = listbox.get(selected_idx[0])
        dialog = GroupEditorDialog(win, f"Editar Grupo: {old_name}", app_configs, group_name=old_name, group_apps=groups.get(old_name))
        if dialog.result:
            new_name, apps = dialog.result
            if new_name != old_name:
                if not delete_group_file(old_name): return
                del groups[old_name]
            if save_group(new_name, apps): groups[new_name] = apps; populate_listbox()
    def delete_group():
        selected_idx = listbox.curselection()
        if not selected_idx: return
        name = listbox.get(selected_idx[0])
        if messagebox.askyesno("Confirmar", f"¿Estás seguro de que quieres eliminar el grupo '{name}'?", parent=win):
            if delete_group_file(name): del groups[name]; populate_listbox()
    def export_group():
        selected_idx = listbox.curselection()
        if not selected_idx: return
        name = listbox.get(selected_idx[0]); apps = groups.get(name)
        if not apps: return
        filepath = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Archivos de Grupo", "*.txt")], initialfile=f"{name}_grupo.txt", title=f"Exportar grupo '{name}'")
        if not filepath: return
        try:
            with open(filepath, 'w', encoding='utf-8') as f: f.write("\n".join(apps)); messagebox.showinfo("Éxito", "Grupo exportado.", parent=win)
        except IOError as e: messagebox.showerror("Error", f"No se pudo guardar el archivo:\n{e}", parent=win)
    def import_group():
        filepath = filedialog.askopenfilename(filetypes=[("Archivos de Grupo", "*.txt")], title="Importar grupo")
        if not filepath: return
        try:
            p = Path(filepath); name = p.stem.replace("_grupo", "")
            if name in groups and not messagebox.askyesno("Confirmar", f"El grupo '{name}' ya existe. ¿Sobrescribir?", parent=win): return
            with open(filepath, 'r', encoding='utf-8') as f: apps = [line.strip() for line in f if line.strip() and line.strip() in app_configs]
            if save_group(name, apps): groups[name] = apps; populate_listbox(); messagebox.showinfo("Éxito", f"Grupo '{name}' importado.", parent=win)
        except IOError as e: messagebox.showerror("Error", f"No se pudo leer el archivo:\n{e}", parent=win)
    list_frame = ttk.Frame(win, padding=10); list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE, exportselection=False); listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview); scrollbar.pack(side=tk.RIGHT, fill=tk.Y); listbox.config(yscrollcommand=scrollbar.set)
    btn_frame = ttk.Frame(win, padding=10); btn_frame.pack(side=tk.RIGHT, fill=tk.Y); ttk.Button(btn_frame, text="Nuevo...", command=add_group).pack(pady=5, fill=tk.X); ttk.Button(btn_frame, text="Editar...", command=edit_group).pack(pady=5, fill=tk.X)
    ttk.Button(btn_frame, text="Eliminar", command=delete_group).pack(pady=5, fill=tk.X); ttk.Button(btn_frame, text="Importar...", command=import_group).pack(pady=(15, 5), fill=tk.X); ttk.Button(btn_frame, text="Exportar...", command=export_group).pack(pady=5, fill=tk.X)
    populate_listbox(); win.protocol("WM_DELETE_WINDOW", lambda: (callback_on_close(), win.destroy()))

class PlayerToolkitApp:
    def __init__(self, root, scan_results, app_configs, installed_software):
        self.root = root
        self.scan_results = scan_results; self.app_configs = app_configs; self.installed_software = installed_software
        self.app_tree = None; self.extra_options = {}; self.config_treeview = None; self.modified_configs = set()
        self.uninstall_vars = {}; self.log_queue = Queue(); self.CHECK_CHAR = "☑"; self.UNCHECK_CHAR = "☐"
        self.update_status_label = None; self.is_downloading_update = False
        
        if getattr(sys, 'frozen', False): self.user_data_dir = Path(sys.executable).parent
        else: self.user_data_dir = Path(__file__).parent.parent
        self.programas_dir = self.user_data_dir / "Programas"; self.conf_dir = self.user_data_dir / "conf"
        self.update_ready_path = self.user_data_dir / "update.zip"

        self._setup_styles(); self._setup_ui()
        self._populate_app_tree(); self._check_installed_status()
        self._process_log_queue()
        if DND_SUPPORT: self.root.drop_target_register(DND_FILES); self.root.dnd_bind('<<Drop>>', self._on_drop)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_styles(self):
        style = ttk.Style(self.root)
        style.configure('Muted.TLabel', foreground='gray'); style.configure('Accent.TButton', font=("Segoe UI", 11, "bold"), padding=10)
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=28); style.configure("Category.Treeview", font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", style.lookup("TButton", "background"))], foreground=[("selected", style.lookup("TButton", "foreground"))])

    def _setup_ui(self):
        self.root.title(f"PlayerToolkit {APP_VERSION}")
        try: self.root.iconbitmap(self._get_resource_path("assets/img/icon.ico"))
        except Exception as e: logging.warning(f"No se pudo cargar el icono: {e}")
        self.root.geometry("950x700"); self.root.minsize(800, 550)
        main_frame = ttk.Frame(self.root, padding="10"); main_frame.pack(expand=True, fill=tk.BOTH); main_frame.rowconfigure(1, weight=1); main_frame.columnconfigure(0, weight=1)
        top_frame = ttk.Frame(main_frame); top_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(top_frame, text="PlayerToolkit", font=("Segoe UI", 16, "bold")).pack(side="left"); ttk.Button(top_frame, text="🌙/☀️", command=sv_ttk.toggle_theme).pack(side="right")
        self.notebook = ttk.Notebook(main_frame); self.notebook.grid(row=1, column=0, sticky="nsew", pady=5)
        self.app_tab_frame = self._create_app_tab(); self.groups_tab_frame = self._create_groups_tab(); self.uninstall_tab_frame = self._create_uninstall_tab()
        self.log_tab_frame = self._create_log_tab(); self.config_tab_frame = self._create_config_tab()
        self.bottom_frame = ttk.Frame(main_frame); self.bottom_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.continue_button = ttk.Button(self.bottom_frame, text="Ejecutar Tareas ➔", style='Accent.TButton', command=self._on_siguiente_click)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed); self._on_tab_changed()

    def _on_close(self):
        if self.update_ready_path.exists():
            if messagebox.askyesno("Instalar Actualización", "La actualización descargada está lista.\n\n¿Quieres cerrar e instalarla ahora?", parent=self.root):
                self._launch_updater(); self.root.destroy()
            else: self.root.destroy()
        else: self.root.destroy()

    def _launch_updater(self):
        updater_path = self.user_data_dir / UPDATER_SCRIPT_NAME
        script_content = f"""@echo off
echo Actualizando PlayerToolkit...
echo [1/5] Finalizando la aplicacion...
taskkill /PID {os.getpid()} /F > nul 2>&1
timeout /t 3 /nobreak > nul
echo [2/5] Extrayendo actualizacion...
powershell -Command "Expand-Archive -Path '{self.update_ready_path}' -DestinationPath '_update' -Force"
echo [3/5] Reemplazando archivos...
robocopy "_update" "." /E /MOVE /NFL /NDL /NJH /NJS > nul
echo [4/5] Limpiando...
del "{self.update_ready_path}" > nul 2>&1
rd /s /q "_update" > nul 2>&1
echo [5/5] Reiniciando la aplicacion...
start "" "{os.path.basename(sys.executable)}"
(goto) 2>nul & del "%~f0"
"""
        try:
            with open(updater_path, "w", encoding="utf-8") as f: f.write(script_content)
            subprocess.Popen([str(updater_path)], creationflags=subprocess.DETACHED_PROCESS, close_fds=True)
            logging.info("Lanzador de actualizacion ejecutado.")
        except Exception as e:
            logging.error(f"No se pudo lanzar el actualizador: {e}")
            messagebox.showerror("Error", f"No se pudo iniciar el actualizador.\nError: {e}\n\nExtraiga 'update.zip' manualmente.", parent=self.root)

    def _on_tab_changed(self, event=None):
        current_tab_text = self.notebook.tab(self.notebook.select(), "text")
        if any(tab in current_tab_text for tab in ["Desinstalar", "Log", "Configuración"]): self.continue_button.pack_forget()
        else: self.continue_button.pack(side=tk.RIGHT)
            
    def _create_app_tab(self):
        app_tab = ttk.Frame(self.notebook, padding="10"); self.notebook.add(app_tab, text='Aplicaciones 📦')
        controls_frame = ttk.Frame(app_tab); controls_frame.pack(fill='x', pady=(0, 10))
        refresh_btn = ttk.Button(controls_frame, text="Refrescar 🔄", command=self._rescan_and_refresh_ui); refresh_btn.pack(side="left", padx=(0, 10))
        ToolTip(refresh_btn, "Borra la caché y vuelve a escanear\narchivos y programas instalados.")
        self.search_var = tk.StringVar(); self.search_var.trace_add("write", lambda *a: self._filter_app_tree())
        ttk.Label(controls_frame, text="🔍 Buscar:").pack(side=tk.LEFT, padx=(0, 5)); ttk.Entry(controls_frame, textvariable=self.search_var).pack(side=tk.LEFT, fill='x', expand=True)
        tree_frame = ttk.Frame(app_tab); tree_frame.pack(fill='both', expand=True)
        self.app_tree = ttk.Treeview(tree_frame, columns=('status_icon', 'status_text', 'progress', 'selector'), show='tree headings')
        self.app_tree.heading('#0', text='Aplicación'); self.app_tree.heading('status_icon', text='Estado'); self.app_tree.heading('status_text', text=''); self.app_tree.heading('progress', text='Progreso'); self.app_tree.heading('selector', text='Versión / Archivo')
        self.app_tree.column('#0', width=250, stretch=tk.YES); self.app_tree.column('status_icon', width=40, anchor='center', stretch=tk.NO); self.app_tree.column('status_text', width=100, anchor='w'); self.app_tree.column('progress', width=120, anchor='w'); self.app_tree.column('selector', width=180, stretch=tk.YES, anchor='w')
        self.app_tree.tag_configure('disabled', foreground='gray'); self.app_tree.tag_configure('category', font=("Segoe UI", 10, "bold")); self.app_tree.bind('<Button-1>', self._on_tree_click)
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.app_tree.yview); self.app_tree.configure(yscrollcommand=scrollbar.set)
        self.app_tree.pack(side=tk.LEFT, fill='both', expand=True); scrollbar.pack(side=tk.RIGHT, fill='y')
        return app_tab
        
    def _create_log_tab(self):
        log_tab = ttk.Frame(self.notebook, padding="10"); self.notebook.add(log_tab, text='Log de Actividad 📜'); self.log_tree = ttk.Treeview(log_tab, columns=('time', 'level', 'message'), show='headings')
        self.log_tree.heading('time', text='Hora'); self.log_tree.heading('level', text='Nivel'); self.log_tree.heading('message', text='Mensaje'); self.log_tree.column('time', width=140, anchor='w', stretch=tk.NO); self.log_tree.column('level', width=80, anchor='center', stretch=tk.NO); self.log_tree.column('message', width=500)
        self.log_tree.tag_configure('INFO', foreground='white'); self.log_tree.tag_configure('SUCCESS', foreground='#40c840'); self.log_tree.tag_configure('WARNING', foreground='orange'); self.log_tree.tag_configure('ERROR', foreground='#ff5353')
        scrollbar = ttk.Scrollbar(log_tab, command=self.log_tree.yview); self.log_tree.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill='y'); self.log_tree.pack(side=tk.LEFT, fill='both', expand=True)
        return log_tab

    def _populate_app_tree(self):
        for item in self.app_tree.get_children(): self.app_tree.delete(item)
        categorized_apps = defaultdict(list); [categorized_apps[cfg.get('categoria', 'Sin Categoría')].append(name) for name, cfg in self.app_configs.items()]
        self.extra_options.clear()
        for category in sorted(categorized_apps.keys()):
            cat_id = self.app_tree.insert('', 'end', text=f"{self.UNCHECK_CHAR} {category}", open=True, tags=('category',))
            for app_key in sorted(categorized_apps[category]):
                cfg = self.app_configs[app_key]
                app_id = self.app_tree.insert(cat_id, 'end', iid=app_key, text=f"{self.UNCHECK_CHAR} {cfg.get('icon', '📦')} {app_key}")
                self.app_tree.set(app_id, 'status_icon', STATUS_ICONS["pending"]); self.app_tree.set(app_id, 'progress', '')
                scan_result, status_msg = self.scan_results.get(app_key, []), ""
                if cfg.get('tipo') in [TASK_TYPE_LOCAL_INSTALL, TASK_TYPE_MANUAL_ASSISTED]:
                    if not scan_result or scan_result == [STATUS_FOLDER_NOT_FOUND]:
                        status_msg = "(Se descargará)" if cfg.get("url") else "(No encontrado)"
                        if not cfg.get("url"): self.app_tree.item(app_id, tags=('disabled',))
                    elif len(scan_result) > 1: self.app_tree.set(app_id, 'selector', "[Haga clic para elegir...]")
                elif cfg.get('tipo') == TASK_TYPE_COPY_INTERACTIVE:
                    if not scan_result or scan_result in [[STATUS_FOLDER_NOT_FOUND], [STATUS_NO_FILES_FOUND]]:
                        status_msg = "(No hay archivos)"; self.app_tree.item(app_id, tags=('disabled',))
                    else: self.app_tree.set(app_id, 'selector', "[Haga clic para elegir...]")
                self.app_tree.set(app_id, 'status_text', status_msg)

    def _check_installed_status(self):
        installed = {name.lower() for name in self.installed_software.keys()}
        for key, cfg in self.app_configs.items():
            if self.app_tree.exists(key):
                ukey = cfg.get("uninstall_key")
                if ukey and any(ukey.lower() in name for name in installed):
                    self.app_tree.set(key, 'status_icon', STATUS_ICONS["installed"]); self.app_tree.set(key, 'status_text', "Instalado"); self.app_tree.item(key, tags=('disabled', 'installed'))

    def _create_groups_tab(self):
        groups_tab = ttk.Frame(self.notebook, padding="10"); self.notebook.add(groups_tab, text='Grupos 🗂️'); main_frame = ttk.Frame(groups_tab); main_frame.pack(fill='both', expand=True); main_frame.columnconfigure(0, weight=1); main_frame.rowconfigure(1, weight=1); controls_frame = ttk.Frame(main_frame); controls_frame.grid(row=0, column=0, sticky='ew', pady=(0, 10)); ttk.Label(controls_frame, text="Seleccionar Grupo:").pack(side=tk.LEFT, padx=(0,5)); group_combo = ttk.Combobox(controls_frame, state="readonly"); group_combo.pack(side=tk.LEFT, fill='x', expand=True)
        contents_list = tk.Listbox(main_frame, font=("Segoe UI", 10)); contents_list.grid(row=1, column=0, sticky='nsew'); buttons_frame = ttk.Frame(main_frame); buttons_frame.grid(row=2, column=0, sticky='ew', pady=(10, 0))
        def refresh_group_combo(): groups = self._load_groups(); group_names = sorted(groups.keys()); group_combo['values'] = group_names; group_combo.set(''); contents_list.delete(0, tk.END)
        def on_group_select(event): contents_list.delete(0, tk.END); selected = group_combo.get(); [contents_list.insert(tk.END, name) for name in sorted(self._load_groups().get(selected, []))] if selected else None
        def apply_group():
            selected_group = group_combo.get()
            if not selected_group: messagebox.showwarning("Sin selección", "Por favor, selecciona un grupo.", parent=self.root); return
            apps_in_group = set(self._load_groups().get(selected_group, []))
            for cat_id in self.app_tree.get_children():
                for app_id in self.app_tree.get_children(cat_id):
                    if 'disabled' not in self.app_tree.item(app_id, 'tags'): self._set_item_checked(app_id, app_id in apps_in_group)
                self._update_parent_check_state(cat_id)
            messagebox.showinfo("Grupo Aplicado", f"Grupo '{selected_group}' cargado.", parent=self.root); self.notebook.select(0)
        group_combo.bind('<<ComboboxSelected>>', on_group_select)
        ttk.Button(buttons_frame, text="Aplicar Grupo", command=apply_group).pack(side=tk.LEFT, expand=True, fill='x', padx=(0,5))
        ttk.Button(buttons_frame, text="Gestionar Grupos...", command=lambda: open_group_manager(self.root, refresh_group_combo, self.app_configs)).pack(side=tk.LEFT, expand=True, fill='x', padx=(5,0))
        refresh_group_combo(); return groups_tab
    
    def _create_uninstall_tab(self):
        uninstall_tab = ttk.Frame(self.notebook, padding="10"); self.notebook.add(uninstall_tab, text='Desinstalar 🗑️'); controls_frame = ttk.Frame(uninstall_tab); controls_frame.pack(fill='x', pady=(0, 10)); uninstall_search_var = tk.StringVar(); uninstall_search_var.trace_add("write", lambda *a: self._filter_uninstall_list(uninstall_search_var)); ttk.Label(controls_frame, text="🔍 Buscar:").pack(side=tk.LEFT, padx=(0, 5)); ttk.Entry(controls_frame, textvariable=uninstall_search_var).pack(side=tk.LEFT, fill='x', expand=True); scroll_container = ScrollableFrame(uninstall_tab); scroll_container.pack(fill='both', expand=True)
        self.uninstall_frame = ttk.Frame(scroll_container.scrollable_frame, padding=10); self.uninstall_frame.pack(fill='both', expand=True); self._populate_uninstall_tab(); bottom_frame = ttk.Frame(uninstall_tab); bottom_frame.pack(fill='x', pady=(10, 0)); ttk.Button(bottom_frame, text="Desinstalar Seleccionados", style='Accent.TButton', command=self._on_uninstall_click).pack(side='right'); return uninstall_tab

    def _populate_uninstall_tab(self):
        for widget in self.uninstall_frame.winfo_children(): widget.destroy()
        self.uninstall_vars.clear()
        for name, data in sorted(self.installed_software.items(), key=lambda i: i[0].lower()):
            var = tk.BooleanVar(); version = f" (v{data.get('version')})" if data.get('version') else ""; date = f" [Instalado: {data.get('install_date')}]" if data.get('install_date') else ""
            chk = ttk.Checkbutton(self.uninstall_frame, text=f"{name}{version}{date}", variable=var); chk.pack(anchor='w', padx=5, pady=2); self.uninstall_vars[name] = {'var': var, 'data': data, 'chk': chk}

    def _create_config_tab(self):
        config_tab = ttk.Frame(self.notebook, padding="10"); self.notebook.add(config_tab, text='Configuración ⚙️'); config_frame = ttk.LabelFrame(config_tab, text="Editor de Comportamiento de Aplicaciones", padding=15); config_frame.pack(fill="both", expand=True); config_frame.rowconfigure(0, weight=1); config_frame.columnconfigure(0, weight=1); cols = ("Aplicación", "Categoría", "Tipo", "Argumentos", "Dependencias"); self.config_treeview = ttk.Treeview(config_frame, columns=cols, show='headings', selectmode='browse')
        for col in cols: self.config_treeview.heading(col, text=col); self.config_treeview.column(col, width=120, anchor='w')
        self.config_treeview.column("Argumentos", width=180); self.config_treeview.column("Aplicación", width=150); self.config_treeview.grid(row=0, column=0, sticky='nsew'); scrollbar = ttk.Scrollbar(config_frame, orient="vertical", command=self.config_treeview.yview); self.config_treeview.configure(yscrollcommand=scrollbar.set); scrollbar.grid(row=0, column=1, sticky='ns'); self._populate_config_treeview(); self.config_treeview.bind("<Double-1>", self._on_config_tree_double_click)
        buttons_frame = ttk.Frame(config_tab, padding=(0, 10, 0, 0)); buttons_frame.pack(fill='x', side='bottom'); ttk.Button(buttons_frame, text="❔ Ayuda", command=self._show_config_help).pack(side='left'); ttk.Button(buttons_frame, text="Acerca de...", command=self._show_about_dialog).pack(side='left', padx=5); btn_vars = ttk.Button(buttons_frame, text="Gestionar Variables...", command=self._open_variables_manager); btn_vars.pack(side='left', padx=5); ToolTip(btn_vars, "Define variables personalizadas (ej: %MY_PATH%)\npara usar en los argumentos de las tareas.")
        ttk.Button(buttons_frame, text="Exportar", command=self._export_config).pack(side='right'); ttk.Button(buttons_frame, text="Importar", command=self._import_config).pack(side='right', padx=5); ttk.Button(buttons_frame, text="Guardar Cambios", command=self._save_custom_config).pack(side='right', padx=5); ttk.Button(buttons_frame, text="Restaurar Predeterminados", command=self._restore_default_config).pack(side='right'); return config_tab
    
    def _rescan_and_refresh_ui(self, silent=False):
        loading_window = None
        if not silent: loading_window = tk.Toplevel(self.root); loading_window.title("Escaneando..."); loading_window.geometry("250x100"); loading_window.transient(self.root); loading_window.grab_set(); loading_window.resizable(False, False); ttk.Label(loading_window, text="Actualizando listas...").pack(pady=20); progress = ttk.Progressbar(loading_window, mode='indeterminate'); progress.pack(pady=5, padx=20, fill='x'); progress.start(10); self.root.update_idletasks()
        def do_rescan():
            clear_cache(); self.installed_software = scan_installed_software()
            new_scan_results = {}
            for key, cfg in self.app_configs.items():
                app_dir = self.programas_dir / key
                if cfg.get('tipo') in [TASK_TYPE_LOCAL_INSTALL, TASK_TYPE_MANUAL_ASSISTED]: new_scan_results[key] = [f.name for ext in INSTALLER_EXTENSIONS for f in app_dir.glob(f"*{ext}")] if app_dir.is_dir() else [STATUS_FOLDER_NOT_FOUND]
                elif cfg.get('tipo') == TASK_TYPE_COPY_INTERACTIVE: new_scan_results[key] = [f.name for f in app_dir.iterdir() if f.is_file()] if app_dir.is_dir() else [STATUS_FOLDER_NOT_FOUND]
            self.scan_results = new_scan_results; self.root.after(0, self._update_ui_after_rescan, loading_window, silent)
        threading.Thread(target=do_rescan, daemon=True).start()

    def _update_ui_after_rescan(self, loading_window, silent=False):
        self._populate_app_tree(); self._check_installed_status(); self._populate_uninstall_tab()
        if not silent:
            if loading_window: loading_window.destroy()
            messagebox.showinfo("Actualizado", "Las listas de aplicaciones han sido actualizadas.", parent=self.root)
        
    def _show_config_help(self): messagebox.showinfo("Ayuda", "Haz doble clic para abrir el editor avanzado.\n\n" "DEPENDENCIAS: Asegura el orden de instalación.\n\n" "VARIABLES: Define variables como '%DRIVE%' para usarlas en los argumentos.", parent=self.root)
    
    def _show_about_dialog(self):
        about_window = tk.Toplevel(self.root); about_window.title("Acerca de PlayerToolkit"); about_window.geometry("400x320"); about_window.transient(self.root); about_window.resizable(False, False); about_window.grab_set(); ttk.Label(about_window, text="PlayerToolkit", font=("Segoe UI", 16, "bold")).pack(pady=(20, 5)); ttk.Label(about_window, text=f"{APP_VERSION}").pack(); ttk.Label(about_window, text="Una herramienta para simplificar instalaciones.").pack(pady=20)
        repo_url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"; link = ttk.Label(about_window, text="Visita el Proyecto en GitHub", foreground="cyan", cursor="hand2"); link.pack(); link.bind("<Button-1>", lambda e: webbrowser.open_new(repo_url)); self.update_status_label = ttk.Label(about_window, text="", justify='center'); self.update_status_label.pack(pady=(5, 0)); ttk.Button(about_window, text="Buscar Actualizaciones", command=self._on_check_updates_click).pack(pady=(10, 5)); ttk.Button(about_window, text="Cerrar", command=about_window.destroy).pack(side="bottom", pady=20); about_window.update_idletasks()

    def _on_check_updates_click(self):
        if self.is_downloading_update: messagebox.showinfo("Información", "Ya se está descargando una actualización.", parent=self.root); return
        messagebox.showinfo("Buscando Actualizaciones", "Contactando con GitHub...", parent=self.root)
        threading.Thread(target=self._check_for_updates, daemon=True).start()

    def _parse_version_string(self, version_string):
        if not isinstance(version_string, str): return (0, 0, 0), None
        match = re.search(r'(\d+)\.(\d+)\.(\d+)', version_string)
        if match: return tuple(map(int, match.groups())), match.group(0)
        return (0, 0, 0), None

    def _check_for_updates(self):
        api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
        try:
            response = requests.get(api_url, timeout=10); response.raise_for_status(); latest_release = response.json()
            latest_version_tag = latest_release.get("tag_name")
            if not latest_version_tag: self.root.after(0, self._show_update_error, "No se encontró tag de versión."); return
            
            current_tuple, _ = self._parse_version_string(APP_VERSION)
            latest_tuple, latest_version_str = self._parse_version_string(latest_version_tag)

            if latest_tuple > current_tuple:
                if not latest_version_str: self.root.after(0, self._show_update_error, f"El tag '{latest_version_tag}' no tiene un formato X.Y.Z."); return
                
                # MODIFICADO: Construir dinámicamente el nombre del asset
                expected_asset_name = f"PlayerToolkit_v{latest_version_str}.zip"
                update_asset = next((asset for asset in latest_release.get("assets", []) if asset['name'] == expected_asset_name), None)
                
                if update_asset: self.root.after(0, self._show_update_available, latest_version_tag, update_asset)
                else: self.root.after(0, self._show_update_error, f"No se encontró el archivo '{expected_asset_name}' en la release.")
            else: self.root.after(0, self._show_no_update)
        except requests.RequestException as e: self.root.after(0, self._show_update_error, f"Error de red: {e}")
        except Exception as e: self.root.after(0, self._show_update_error, f"Error inesperado: {e}")

    def _show_update_available(self, new_version, asset):
        msg = f"¡Nueva versión disponible: {new_version}!\n\n¿Descargar ahora?\nSe instalará al cerrar la aplicación."; parent = self.update_status_label.winfo_toplevel() if self.update_status_label and self.update_status_label.winfo_exists() else self.root
        if messagebox.askyesno("Actualización Disponible", msg, parent=parent): self._start_background_download(asset)

    def _start_background_download(self, asset):
        if self.is_downloading_update: return
        self.is_downloading_update = True; self.update_status_label.config(text="Iniciando descarga...")
        threading.Thread(target=self._download_thread, args=(asset['browser_download_url'], asset['size']), daemon=True).start()

    def _download_thread(self, url, total_size):
        try:
            downloaded = 0
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(self.update_ready_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk); downloaded += len(chunk); progress = (downloaded / total_size) * 100
                        self.root.after(0, self.update_status_label.config, {'text': f'Descargando: {int(progress)}%'})
            self.root.after(0, self.update_status_label.config, {'text': 'Descarga completa.\nSe instalará al cerrar.', 'foreground': 'green'})
        except requests.RequestException as e:
            self.root.after(0, self.update_status_label.config, {'text': f'Error de descarga: {e}', 'foreground': 'red'})
            if self.update_ready_path.exists(): self.update_ready_path.unlink()
        finally: self.is_downloading_update = False

    def _show_no_update(self): messagebox.showinfo("Actualizado", "Ya tienes la última versión.", parent=self.root)
    def _show_update_error(self, err): messagebox.showerror("Error", f"No se pudo comprobar si hay actualizaciones.\n\nError: {err}", parent=self.root)
        
    def _populate_config_treeview(self):
        for i in self.config_treeview.get_children(): self.config_treeview.delete(i)
        for name, cfg in sorted(self.app_configs.items()): self.config_treeview.insert('', 'end', iid=name, values=(name, cfg.get('categoria',''), cfg.get('tipo',''), str(cfg.get('args_instalacion',[])), str(cfg.get('dependencies',[]))))

    def _on_config_tree_double_click(self, event):
        item_id = self.config_treeview.focus()
        if not item_id: return
        dialog = AdvancedConfigDialog(self.root, f"Editando: {item_id}", item_id, self.app_configs[item_id], list(self.app_configs.keys()))
        if dialog.result: self.app_configs[item_id] = dialog.result; self.modified_configs.add(item_id); self._populate_config_treeview()

    def _open_variables_manager(self): VariablesManagerDialog(self.root, "Gestionar Variables Personalizadas", self)

    def _save_custom_config(self):
        config_file = self.conf_dir / "config_personalizada.json"
        if not self.modified_configs: messagebox.showinfo("Sin cambios", "No se han realizado cambios para guardar.", parent=self.root); return
        current_cfg = {} 
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f: current_cfg = json.load(f)
            except (IOError, json.JSONDecodeError): pass
        for name in self.modified_configs:
            default_conf = DEFAULT_APP_CONFIG.copy()
            if name in APP_CONFIGURATIONS: default_conf.update(APP_CONFIGURATIONS[name])
            changes = {k: v for k, v in self.app_configs[name].items() if k not in default_conf or default_conf[k] != v or (k in default_conf and isinstance(v, (list, dict)) and v != default_conf[k])}
            if changes: current_cfg.setdefault(name, {}).update(changes)
        try:
            with open(config_file, 'w', encoding='utf-8') as f: json.dump(current_cfg, f, indent=4, ensure_ascii=False)
            messagebox.showinfo("Guardado", "Configuración personalizada guardada.", parent=self.root); self.modified_configs.clear()
        except IOError as e: messagebox.showerror("Error", f"No se pudo escribir el archivo de configuración:\n{e}", parent=self.root)

    def _restore_default_config(self):
        config_file = self.conf_dir / "config_personalizada.json"
        if not config_file.exists(): messagebox.showinfo("Información", "No hay configuración personalizada para restaurar.", parent=self.root); return
        if messagebox.askyesno("Confirmar", "¿Eliminar toda la configuración personalizada?\nLa aplicación deberá reiniciarse.", parent=self.root):
            try: config_file.unlink(); messagebox.showinfo("Éxito", "Configuración restaurada.\nReinicia la aplicación.", parent=self.root)
            except IOError as e: messagebox.showerror("Error", f"No se pudo eliminar el archivo:\n{e}", parent=self.root)

    def _export_config(self):
        config_file = self.conf_dir / "config_personalizada.json"
        if not config_file.exists(): messagebox.showwarning("Sin configuración", "No hay configuración personalizada.", parent=self.root); return
        dest = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")], title="Exportar configuración")
        if dest: shutil.copy2(config_file, dest); messagebox.showinfo("Éxito", f"Configuración exportada a\n{dest}", parent=self.root)

    def _import_config(self, src_path=None):
        config_file = self.conf_dir / "config_personalizada.json"
        src = src_path or filedialog.askopenfilename(filetypes=[("JSON files", "*.json")], title="Importar configuración")
        if src: self.conf_dir.mkdir(exist_ok=True); shutil.copy2(src, config_file); messagebox.showinfo("Éxito", "Configuración importada. Reinicia para aplicar cambios.", parent=self.root)

    def _load_groups(self):
        groups_dir = self.programas_dir / "Grupos"; groups_dir.mkdir(exist_ok=True); groups = {}
        try:
            for fpath in groups_dir.glob("*.txt"):
                with open(fpath, 'r', encoding='utf-8') as f: groups[fpath.stem] = [line.strip() for line in f if line.strip()]
        except IOError as e: messagebox.showerror("Error", f"No se pudieron cargar los grupos:\n{e}")
        return groups
        
    def _on_siguiente_click(self):
        selected_apps = [child for cat in self.app_tree.get_children() for child in self.app_tree.get_children(cat) if self.app_tree.item(child, 'text').startswith(self.CHECK_CHAR)]
        if not selected_apps: messagebox.showwarning("Sin Selección", "No has seleccionado ninguna tarea."); return
        custom_vars = self._load_custom_variables(); resumen = "Se realizarán las siguientes acciones:\n\n"; current_extra_options = {}
        for key in selected_apps:
            cfg = self.app_configs[key]; resumen_line = f"- {cfg['icon']} {key}"
            if cfg.get("tipo") in [TASK_TYPE_LOCAL_INSTALL, TASK_TYPE_MANUAL_ASSISTED]:
                installers = self.scan_results.get(key, []);
                if len(installers) == 1: current_extra_options[key] = {'exe_filename': installers[0]}
                elif len(installers) > 1:
                    chosen = self.extra_options.get(key, {}).get('selected');
                    if not chosen: messagebox.showerror("Error", f"Para '{key}', elige una versión."); return
                    current_extra_options[key] = {'exe_filename': chosen}; resumen_line += f" (Versión: {chosen})"
                elif cfg.get("url"): current_extra_options[key] = {'exe_filename': Path(cfg["url"]).name}
                else: messagebox.showerror("Error", f"No se encontró instalador para '{key}'."); return
            elif cfg.get("tipo") == TASK_TYPE_COPY_INTERACTIVE:
                chosen = self.extra_options.get(key, {}).get('selected');
                if not chosen: messagebox.showerror("Error", f"Para '{key}', elige un archivo."); return
                current_extra_options[key] = {'selected_filename': chosen}; resumen_line += f" (Archivo: {chosen})"
            resumen += resumen_line + "\n"
        if messagebox.askyesno("Confirmar Acciones", resumen + "\n¿Deseas continuar?"):
            self.notebook.select(3); [self._update_task_ui(app, status='pending', progress=0, text="En cola...") for app in selected_apps]
            processor = TaskProcessor(self.root, self.app_configs, selected_apps, current_extra_options, self.programas_dir, custom_vars, self.log_queue, ui_update_callback=self._update_task_ui, completion_callback=lambda: self._rescan_and_refresh_ui(silent=True))
            threading.Thread(target=processor.run, daemon=True).start()

    def _on_uninstall_click(self):
        selected = {n: d['data'] for n, d in self.uninstall_vars.items() if d['var'].get()};
        if not selected: messagebox.showwarning("Sin Selección", "No has seleccionado ningún programa para desinstalar."); return
        if messagebox.askyesno("Confirmar Desinstalación", "Se intentará desinstalar:\n\n" + "\n".join([f"- {n}" for n in selected]) + "\n\n¿Continuar?"):
            self.notebook.select(3)
            app_cfgs = {n: {"tipo": TASK_TYPE_UNINSTALL, "uninstall_string": d["uninstall_string"]} for n, d in selected.items()}
            proc = TaskProcessor(self.root, app_cfgs, list(selected.keys()), {}, self.programas_dir, self._load_custom_variables(), self.log_queue, completion_callback=lambda: self._rescan_and_refresh_ui(silent=True))
            threading.Thread(target=proc.run, daemon=True).start()

    def _filter_uninstall_list(self, search_var): query = search_var.get().lower(); [d['chk'].pack(anchor='w', padx=5, pady=2) if query in n.lower() else d['chk'].pack_forget() for n, d in self.uninstall_vars.items()]

    def _set_item_checked(self, iid, chk): text = self.app_tree.item(iid, 'text'); base = text.lstrip(f"{self.CHECK_CHAR}{self.UNCHECK_CHAR} "); char = self.CHECK_CHAR if chk else self.UNCHECK_CHAR; self.app_tree.item(iid, text=f"{char} {base}")

    def _update_parent_check_state(self, pid):
        children = self.app_tree.get_children(pid)
        if children: enabled = [cid for cid in children if 'disabled' not in self.app_tree.item(cid,'tags')]; all_c = all(self.app_tree.item(cid,'text').startswith(self.CHECK_CHAR) for cid in enabled) if enabled else False; self._set_item_checked(pid, all_c)

    def _on_tree_click(self, event):
        iid = self.app_tree.identify_row(event.y); cid = self.app_tree.identify_column(event.x)
        if not iid or 'disabled' in self.app_tree.item(iid, 'tags'): return
        if self.app_tree.heading(cid, "text") == "Versión / Archivo" and self.app_tree.parent(iid):
            res = self.scan_results.get(iid, [])
            if len(res) > 1:
                dlg = ComboboxDialog(self.root, f"Seleccionar para {iid}", "Elige:", res, initialvalue=self.extra_options.get(iid, {}).get('selected'))
                if dlg.result: self.extra_options.setdefault(iid, {})['selected'] = dlg.result; self.app_tree.set(iid, 'selector', dlg.result)
            return
        if self.app_tree.identify_region(event.x, event.y) == 'tree' or cid == '#0':
            is_c = self.app_tree.item(iid, 'text').startswith(self.CHECK_CHAR); self._set_item_checked(iid, not is_c)
            if not self.app_tree.parent(iid): [self._set_item_checked(child, not is_c) for child in self.app_tree.get_children(iid) if 'disabled' not in self.app_tree.item(child,'tags')]
            else: self._update_parent_check_state(self.app_tree.parent(iid))

    def _filter_app_tree(self):
        query = self.search_var.get().lower().strip()
        for cat_id in self.app_tree.get_children(''): 
            [self.app_tree.reattach(app_id, cat_id, 'end') for app_id in self.app_tree.get_children(cat_id)]
            self.app_tree.reattach(cat_id, '', 'end')
        if not query: return
        for cat_id in list(self.app_tree.get_children('')):
            cat_match = query in self.app_tree.item(cat_id, 'text').lower(); any_child_match = False; children_to_hide = []
            for app_id in self.app_tree.get_children(cat_id):
                if query in self.app_tree.item(app_id, 'text').lower(): any_child_match = True
                else: children_to_hide.append(app_id)
            if not cat_match and not any_child_match: self.app_tree.detach(cat_id)
            elif not cat_match and any_child_match: [self.app_tree.detach(app_id) for app_id in children_to_hide]
    
    def _process_log_queue(self):
        try:
            while not self.log_queue.empty():
                level, message = self.log_queue.get_nowait(); timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.log_tree.insert("", 0, values=(timestamp, level.upper(), message), tags=(level.upper(),))
        finally: self.root.after(200, self._process_log_queue)

    def _on_drop(self, event):
        fpath = event.data.strip('{}')
        if fpath.lower().endswith("config_personalizada.json") and messagebox.askyesno("Importar Configuración", f"¿Importar archivo?\n\n{fpath}\n\nSe requiere reinicio."): self._import_config(src_path=fpath)
        else: messagebox.showwarning("Archivo no válido", "Solo se aceptan archivos 'config_personalizada.json'.", parent=self.root)

    def _update_task_ui(self, key, status=None, progress=None, text=None):
        if self.app_tree.exists(key):
            if status: self.app_tree.set(key, 'status_icon', STATUS_ICONS.get(status, "❓"))
            if text is not None: self.app_tree.set(key, 'status_text', text)
            if progress is not None: bar = "█" * int(progress / 10); empty = "─" * (10 - len(bar)); self.app_tree.set(key, 'progress', f"[{bar}{empty}] {progress}%")

    def _load_custom_variables(self):
        vars_file = self.conf_dir / "variables.json"
        if not vars_file.exists(): return {}
        try:
            with open(vars_file, 'r', encoding='utf-8') as f: return json.load(f)
        except (IOError, json.JSONDecodeError): return {}
    
    def _save_custom_variables(self, variables):
        vars_file = self.conf_dir / "variables.json"
        try:
            with open(vars_file, 'w', encoding='utf-8') as f: json.dump(variables, f, indent=4); messagebox.showinfo("Guardado", "Variables personalizadas guardadas.", parent=self.root)
        except IOError as e: messagebox.showerror("Error", f"No se pudo guardar el archivo de variables:\n{e}", parent=self.root)

    def _get_resource_path(self, relative_path):
        base_path = getattr(sys, '_MEIPASS', self.user_data_dir)
        return os.path.join(base_path, relative_path)