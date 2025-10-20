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

# Importaciones relativas
from .config import *
from .tasks import TaskProcessor
from .utils import scan_installed_software

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD # type: ignore
    DND_SUPPORT = True
except ImportError:
    DND_SUPPORT = False


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
        if initial_config:
            self.config = initial_config
        else:
            self.config = DEFAULT_APP_CONFIG.copy()
        super().__init__(parent, title)

    def body(self, master):
        master.columnconfigure(1, weight=1)

        fields = {
            "Icono:": ("icon", self.config['icon']),
            "Categoría:": ("categoria", self.config['categoria']),
            "Tipo de Tarea:": ("tipo", self.config['tipo']),
            "Argumentos (lista JSON):": ("args_instalacion", str(self.config['args_instalacion'])),
            "Clave de Desinstalación:": ("uninstall_key", self.config['uninstall_key'] or ""),
            "URL de Descarga:": ("url", self.config['url'] or ""),
        }

        self.entries = {}
        row = 0
        first_widget = None  # Almacenará el primer widget para darle el foco

        for label_text, (key, default_val) in fields.items():
            ttk.Label(master, text=label_text).grid(row=row, column=0, sticky='w', padx=5, pady=3)
            current_widget = None
            if key == "tipo":
                var = tk.StringVar(value=default_val)
                combo = ttk.Combobox(master, textvariable=var, state='readonly', values=[
                    TASK_TYPE_LOCAL_INSTALL, TASK_TYPE_MANUAL_ASSISTED, TASK_TYPE_COPY_INTERACTIVE,
                    TASK_TYPE_CLEAN_TEMP, TASK_TYPE_POWER_CONFIG, TASK_TYPE_RUN_POWERSHELL
                ])
                combo.grid(row=row, column=1, sticky='ew', padx=5, pady=3)
                self.entries[key] = var
                current_widget = combo
            else:
                var = tk.StringVar(value=default_val)
                entry = ttk.Entry(master, textvariable=var)
                entry.grid(row=row, column=1, sticky='ew', padx=5, pady=3)
                self.entries[key] = var
                current_widget = entry

            if first_widget is None:
                first_widget = current_widget # Guarda el primer widget creado

            row += 1

        return first_widget # Devuelve el widget para el foco, no la variable

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

            # Copiar otros valores que no están en el formulario pero podrían haber sido adivinados
            for key in ['script_path']:
                if key in self.config:
                    self.result[key] = self.config[key]

        except (json.JSONDecodeError, ValueError) as e:
            messagebox.showerror("Error de Formato", f"El valor para 'Argumentos' no es una lista JSON válida.\nEjemplo: [\"/S\", \"/NORESTART\"]\n\nError: {e}", parent=self)
            self.result = None


class GroupEditorDialog(simpledialog.Dialog):
    def __init__(self, parent, title, app_configs, group_name=None, group_apps=None):
        self.app_configs = app_configs
        self.group_name = group_name
        self.group_apps = group_apps or []
        self.app_vars = {}
        super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text="Nombre del Grupo:").grid(row=0, sticky="w", padx=5, pady=5)
        self.name_entry = ttk.Entry(master, width=40)
        if self.group_name: self.name_entry.insert(0, self.group_name)
        self.name_entry.grid(row=0, column=1, padx=5, pady=5)

        scroll_frame = ScrollableFrame(master)
        scroll_frame.grid(row=1, columnspan=2, sticky='nsew', padx=5, pady=5)
        master.grid_rowconfigure(1, weight=1)
        master.grid_columnconfigure(1, weight=1)

        for app_name in sorted(self.app_configs.keys()):
            var = tk.BooleanVar(value=(app_name in self.group_apps))
            chk = ttk.Checkbutton(scroll_frame.scrollable_frame, text=app_name, variable=var)
            chk.pack(anchor="w", padx=10, pady=2)
            self.app_vars[app_name] = var
        return self.name_entry

    def apply(self):
        new_name = self.name_entry.get().strip()
        if not new_name:
            messagebox.showwarning("Nombre vacío", "El nombre del grupo no puede estar vacío.", parent=self)
            self.result = None
            return
        self.result = (new_name, [name for name, var in self.app_vars.items() if var.get()])

def open_group_manager(parent, callback_on_close, app_configs):
    win = tk.Toplevel(parent)
    win.title("Gestionar Grupos"); win.transient(parent); win.grab_set(); win.geometry("400x450")

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
        try:
            filepath = grupos_dir / f"{name}.txt"
            if filepath.exists(): filepath.unlink(); return True
        except IOError as e: messagebox.showerror("Error al Eliminar", f"No se pudo eliminar el grupo '{name}':\n{e}", parent=win); return False

    def populate_listbox():
        listbox.delete(0, tk.END)
        for name in sorted(groups.keys()): listbox.insert(tk.END, name)

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

    list_frame = ttk.Frame(win, padding=10); list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE, exportselection=False); listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview); scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    listbox.config(yscrollcommand=scrollbar.set)
    btn_frame = ttk.Frame(win, padding=10); btn_frame.pack(side=tk.RIGHT, fill=tk.Y)
    ttk.Button(btn_frame, text="Nuevo...", command=add_group).pack(pady=5, fill=tk.X)
    ttk.Button(btn_frame, text="Editar...", command=edit_group).pack(pady=5, fill=tk.X)
    ttk.Button(btn_frame, text="Eliminar", command=delete_group).pack(pady=5, fill=tk.X)
    populate_listbox()
    win.protocol("WM_DELETE_WINDOW", lambda: (callback_on_close(), win.destroy()))

class PlayerToolkitApp:
    def __init__(self, root, scan_results, app_configs, installed_software):
        self.root = root
        self.scan_results = scan_results
        self.app_configs = app_configs
        self.installed_software = installed_software
        self.app_tree = None
        self.extra_options = {}
        self.config_treeview = None
        self.modified_configs = set()
        self.uninstall_vars = {}
        self.log_queue = Queue()
        self.tree_editor = None # Para el editor de celdas en el Treeview

        self.CHECK_CHAR = "☑"
        self.UNCHECK_CHAR = "☐"

        if getattr(sys, 'frozen', False):
            self.user_data_dir = Path(sys.executable).parent
        else:
            self.user_data_dir = Path(__file__).parent.parent

        self.programas_dir = self.user_data_dir / "Programas"
        self.conf_dir = self.user_data_dir / "conf"

        self._setup_styles()
        self._setup_ui()
        self._check_installed_status()
        self._process_log_queue()

        if DND_SUPPORT:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind('<<Drop>>', self._on_drop)

    def _setup_styles(self):
        style = ttk.Style(self.root)
        style.configure('Muted.TLabel', foreground='gray')
        style.configure('Accent.TButton', font=("Segoe UI", 11, "bold"), padding=10)
        style.configure('Installed.TLabel', foreground='green')
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=28)
        style.configure("Category.Treeview", font=("Segoe UI", 10, "bold"))

    def _setup_ui(self):
        self.root.title("PlayerToolkit v6.1.3")
        self.root.geometry("850x650")
        self.root.minsize(700, 500)
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.rowconfigure(1, weight=1)
        main_frame.columnconfigure(0, weight=1)

        top_frame = ttk.Frame(main_frame)
        top_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(top_frame, text="PlayerToolkit", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Button(top_frame, text="🌙/☀️", command=sv_ttk.toggle_theme).pack(side="right")

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=1, column=0, sticky="nsew", pady=5)

        self.app_tab_frame = self._create_app_tab()
        self.groups_tab_frame = self._create_groups_tab()
        self.uninstall_tab_frame = self._create_uninstall_tab()
        self.log_tab_frame = self._create_log_tab()
        self.config_tab_frame = self._create_config_tab()

        self.bottom_frame = ttk.Frame(main_frame)
        self.bottom_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.continue_button = ttk.Button(self.bottom_frame, text="Ejecutar Tareas ➔", style='Accent.TButton', command=self._on_siguiente_click)

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self._on_tab_changed()

    def _on_tab_changed(self, event=None):
        # Destruir cualquier editor de celda si cambiamos de pestaña
        if self.tree_editor:
            self.tree_editor.destroy()
            self.tree_editor = None

        current_tab_text = self.notebook.tab(self.notebook.select(), "text")
        hide_button_tabs = ["Desinstalar", "Log", "Configuración"]
        if any(tab_text in current_tab_text for tab_text in hide_button_tabs):
            self.continue_button.pack_forget()
        else:
            self.continue_button.pack(side=tk.RIGHT)

    def _create_app_tab(self):
        app_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(app_tab, text='Aplicaciones 📦')

        controls_frame = ttk.Frame(app_tab)
        controls_frame.pack(fill='x', pady=(0, 10))

        ttk.Button(controls_frame, text="Refrescar 🔄", command=self._rescan_and_refresh_ui).pack(side="left", padx=(0, 10))
        self.search_var = tk.StringVar()
        ttk.Label(controls_frame, text="🔍 Buscar:").pack(side=tk.LEFT, padx=(0, 5))
        search_entry = ttk.Entry(controls_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill='x', expand=True)
        self.search_var.trace_add("write", lambda *args: self._filter_app_tree())

        tree_frame = ttk.Frame(app_tab)
        tree_frame.pack(fill='both', expand=True)

        self.app_tree = ttk.Treeview(tree_frame, columns=('status', 'selector'), show='tree headings')
        self.app_tree.heading('#0', text='Aplicación')
        self.app_tree.heading('status', text='Estado')
        self.app_tree.heading('selector', text='Versión / Archivo')
        self.app_tree.column('#0', width=300, stretch=tk.YES)
        self.app_tree.column('status', width=150, anchor='w')
        self.app_tree.column('selector', width=200, stretch=tk.YES, anchor='w')

        self.app_tree.tag_configure('disabled', foreground='gray')
        self.app_tree.tag_configure('installed', foreground='green')
        self.app_tree.tag_configure('category', font=("Segoe UI", 10, "bold"))

        self.app_tree.bind('<Button-1>', self._on_tree_click)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.app_tree.yview)
        self.app_tree.configure(yscrollcommand=scrollbar.set)

        self.app_tree.pack(side=tk.LEFT, fill='both', expand=True)
        scrollbar.pack(side=tk.RIGHT, fill='y')

        self._populate_app_tree()
        return app_tab

    def _create_log_tab(self):
        log_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(log_tab, text='Log de Actividad 📜')

        self.log_text = tk.Text(log_tab, wrap="word", font=("Consolas", 9), relief="flat", padx=5, pady=5, state="disabled")
        scrollbar = ttk.Scrollbar(log_tab, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill='y')
        self.log_text.pack(side=tk.LEFT, fill='both', expand=True)
        return log_tab

    def _populate_app_tree(self):
        for item in self.app_tree.get_children():
            self.app_tree.delete(item)

        categorized_apps = defaultdict(list)
        for name, config in self.app_configs.items():
            categorized_apps[config.get('categoria', 'Sin Categoría')].append(name)

        self.extra_options.clear()

        for category in sorted(categorized_apps.keys()):
            cat_id = self.app_tree.insert('', 'end', text=f"{self.UNCHECK_CHAR} {category}", open=True, tags=('category',))

            for app_key in sorted(categorized_apps[category]):
                config = self.app_configs[app_key]
                icon = config.get('icon', '📦')
                app_id = self.app_tree.insert(cat_id, 'end', iid=app_key, text=f"{self.UNCHECK_CHAR} {icon} {app_key}")

                scan_result = self.scan_results.get(app_key, [])
                task_type = config.get('tipo')
                status_msg = ""

                if task_type in [TASK_TYPE_LOCAL_INSTALL, TASK_TYPE_MANUAL_ASSISTED]:
                    if not scan_result or scan_result == [STATUS_FOLDER_NOT_FOUND]:
                        if config.get("url"): status_msg = "(Se descargará)"
                        else:
                            status_msg = "(Instalador no encontrado)"
                            self.app_tree.item(app_id, tags=('disabled',))
                    elif len(scan_result) > 1:
                        self.app_tree.set(app_id, 'selector', "[Haga clic para elegir...]")
                elif task_type == TASK_TYPE_COPY_INTERACTIVE:
                    if not scan_result or scan_result in [[STATUS_FOLDER_NOT_FOUND], [STATUS_NO_FILES_FOUND]]:
                        status_msg = "(No hay archivos)"
                        self.app_tree.item(app_id, tags=('disabled',))
                    else:
                        self.app_tree.set(app_id, 'selector', "[Haga clic para elegir...]")

                self.app_tree.set(app_id, 'status', status_msg)

    def _check_installed_status(self):
        installed_names_lower = {name.lower() for name in self.installed_software.keys()}

        for app_key, config in self.app_configs.items():
            if not self.app_tree.exists(app_key): continue

            uninstall_key = config.get("uninstall_key")
            if not uninstall_key: continue

            is_installed = any(uninstall_key.lower() in name for name in installed_names_lower)

            if is_installed:
                self.app_tree.set(app_key, 'status', "✔️ Instalado")
                self.app_tree.item(app_key, tags=('disabled', 'installed'))

    def _create_groups_tab(self):
        groups_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(groups_tab, text='Grupos 🗂️')
        main_frame = ttk.Frame(groups_tab)
        main_frame.pack(fill='both', expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        controls_frame = ttk.Frame(main_frame)
        controls_frame.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        ttk.Label(controls_frame, text="Seleccionar Grupo:").pack(side=tk.LEFT, padx=(0,5))
        group_combo = ttk.Combobox(controls_frame, state="readonly")
        group_combo.pack(side=tk.LEFT, fill='x', expand=True)
        contents_list = tk.Listbox(main_frame, font=("Segoe UI", 10))
        contents_list.grid(row=1, column=0, sticky='nsew')
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.grid(row=2, column=0, sticky='ew', pady=(10, 0))

        def refresh_group_combo():
            groups = self._load_groups()
            group_names = sorted(groups.keys())
            group_combo['values'] = group_names
            group_combo.set('')
            contents_list.delete(0, tk.END)

        def on_group_select(event):
            contents_list.delete(0, tk.END)
            selected = group_combo.get()
            if not selected: return
            groups = self._load_groups()
            apps_in_group = groups.get(selected, [])
            for app_name in sorted(apps_in_group):
                contents_list.insert(tk.END, app_name)

        def apply_group():
            selected_group = group_combo.get()
            if not selected_group:
                messagebox.showwarning("Sin selección", "Por favor, selecciona un grupo.", parent=self.root)
                return

            groups = self._load_groups()
            apps_in_group = set(groups.get(selected_group, []))

            for category_id in self.app_tree.get_children():
                for app_id in self.app_tree.get_children(category_id):
                    if 'disabled' not in self.app_tree.item(app_id, 'tags'):
                        is_in_group = app_id in apps_in_group
                        self._set_item_checked(app_id, is_in_group)
                self._update_parent_check_state(category_id)

            messagebox.showinfo("Grupo Aplicado", f"Grupo '{selected_group}' cargado.", parent=self.root)
            self.notebook.select(0)

        group_combo.bind('<<ComboboxSelected>>', on_group_select)
        ttk.Button(buttons_frame, text="Aplicar Grupo", command=apply_group).pack(side=tk.LEFT, expand=True, fill='x', padx=(0,5))
        ttk.Button(buttons_frame, text="Gestionar Grupos...", command=lambda: open_group_manager(self.root, refresh_group_combo, self.app_configs)).pack(side=tk.LEFT, expand=True, fill='x', padx=(5,0))
        refresh_group_combo()
        return groups_tab

    def _create_uninstall_tab(self):
        uninstall_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(uninstall_tab, text='Desinstalar 🗑️')
        controls_frame = ttk.Frame(uninstall_tab)
        controls_frame.pack(fill='x', pady=(0, 10))
        uninstall_search_var = tk.StringVar()
        ttk.Label(controls_frame, text="🔍 Buscar:").pack(side=tk.LEFT, padx=(0, 5))
        uninstall_search_entry = ttk.Entry(controls_frame, textvariable=uninstall_search_var)
        uninstall_search_entry.pack(side=tk.LEFT, fill='x', expand=True)
        uninstall_search_var.trace_add("write", lambda *args: self._filter_uninstall_list(uninstall_search_var))
        scroll_container = ScrollableFrame(uninstall_tab)
        scroll_container.pack(fill='both', expand=True)
        self.uninstall_frame = ttk.Frame(scroll_container.scrollable_frame, padding=10)
        self.uninstall_frame.pack(fill='both', expand=True)
        self._populate_uninstall_tab()
        bottom_frame = ttk.Frame(uninstall_tab)
        bottom_frame.pack(fill='x', pady=(10, 0))
        ttk.Button(bottom_frame, text="Desinstalar Seleccionados", style='Accent.TButton', command=self._on_uninstall_click).pack(side='right')
        return uninstall_tab

    def _populate_uninstall_tab(self):
        for widget in self.uninstall_frame.winfo_children():
            widget.destroy()
        self.uninstall_vars.clear()

        for name, data in sorted(self.installed_software.items(), key=lambda item: item[0].lower()):
            var = tk.BooleanVar()
            version_info = f" (v{data.get('version')})" if data.get('version') else ""
            date_info = f" [Instalado: {data.get('install_date')}]" if data.get('install_date') else ""
            display_text = f"{name}{version_info}{date_info}"
            chk = ttk.Checkbutton(self.uninstall_frame, text=display_text, variable=var)
            chk.pack(anchor='w', padx=5, pady=2)
            self.uninstall_vars[name] = {'var': var, 'data': data, 'chk': chk}

    def _create_config_tab(self):
        config_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(config_tab, text='Configuración ⚙️')
        config_frame = ttk.LabelFrame(config_tab, text="Editor de Comportamiento de Aplicaciones", padding=15)
        config_frame.pack(fill="both", expand=True)
        config_frame.rowconfigure(0, weight=1)
        config_frame.columnconfigure(0, weight=1)
        cols = ("Aplicación", "Categoría", "Tipo de Tarea", "Argumentos", "Icono")
        self.config_treeview = ttk.Treeview(config_frame, columns=cols, show='headings', selectmode='browse')
        for col in cols:
            self.config_treeview.heading(col, text=col)
            self.config_treeview.column(col, width=120, anchor='w')
        self.config_treeview.column("Argumentos", width=180)
        self.config_treeview.column("Aplicación", width=150)
        self.config_treeview.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(config_frame, orient="vertical", command=self.config_treeview.yview)
        self.config_treeview.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self._populate_config_treeview()
        self.config_treeview.bind("<Button-1>", self._on_config_tree_click)
        self.config_treeview.bind("<Double-1>", self._on_tree_double_click)

        buttons_frame = ttk.Frame(config_tab, padding=(0, 10, 0, 0))
        buttons_frame.pack(fill='x', side='bottom')

        ttk.Button(buttons_frame, text="❔ Ayuda", command=self._show_config_help).pack(side='left')
        ttk.Button(buttons_frame, text="Acerca de...", command=self._show_about_dialog).pack(side='left', padx=5)

        ttk.Button(buttons_frame, text="Exportar", command=self._export_config).pack(side='right')
        ttk.Button(buttons_frame, text="Importar", command=self._import_config).pack(side='right', padx=5)

        ttk.Button(buttons_frame, text="Guardar Cambios", command=self._save_custom_config).pack(side='right', padx=5)
        ttk.Button(buttons_frame, text="Restaurar Predeterminados", command=self._restore_default_config).pack(side='right')
        return config_tab

    def _rescan_and_refresh_ui(self, silent=False):
        loading_window = None
        if not silent:
            loading_window = tk.Toplevel(self.root)
            loading_window.title("Escaneando...")
            loading_window.geometry("250x100")
            loading_window.transient(self.root)
            loading_window.grab_set()
            loading_window.resizable(False, False)
            ttk.Label(loading_window, text="Actualizando listas...").pack(pady=20)
            progress = ttk.Progressbar(loading_window, mode='indeterminate')
            progress.pack(pady=5, padx=20, fill='x')
            progress.start(10)
            self.root.update_idletasks()

        def do_rescan():
            self.installed_software = scan_installed_software()
            new_scan_results = {}
            for app_key, config in self.app_configs.items():
                task_type = config.get('tipo')
                app_dir = self.programas_dir / app_key
                if task_type in [TASK_TYPE_LOCAL_INSTALL, TASK_TYPE_MANUAL_ASSISTED]:
                    if not app_dir.is_dir(): new_scan_results[app_key] = [STATUS_FOLDER_NOT_FOUND]
                    else:
                        found = [f.name for ext in INSTALLER_EXTENSIONS for f in app_dir.glob(f"*{ext}")]
                        new_scan_results[app_key] = found if found else []
                elif task_type == TASK_TYPE_COPY_INTERACTIVE:
                    if not app_dir.is_dir(): new_scan_results[app_key] = [STATUS_FOLDER_NOT_FOUND]
                    else:
                        found = [f.name for f in app_dir.iterdir() if f.is_file()]
                        new_scan_results[app_key] = found if found else [STATUS_NO_FILES_FOUND]
            self.scan_results = new_scan_results
            self.root.after(0, self._update_ui_after_rescan, loading_window, silent)

        threading.Thread(target=do_rescan, daemon=True).start()

    def _update_ui_after_rescan(self, loading_window, silent=False):
        self._populate_app_tree()
        self._check_installed_status()
        self._populate_uninstall_tab()

        if not silent:
            if loading_window:
                loading_window.destroy()
            messagebox.showinfo("Actualizado", "Las listas de aplicaciones han sido actualizadas.", parent=self.root)

    def _show_config_help(self):
        help_title = "Ayuda sobre la Configuración"
        help_text = (
            "Aquí puedes personalizar el comportamiento de cada tarea.\n"
            "Haz doble clic en una celda para editarla.\n\n"
            "--- TIPOS DE TAREA ---\n\n"
            " • instalar_local: Instalación estándar silenciosa.\n"
            " • instalar_manual_asistido: Pide confirmación manual.\n"
            " • copiar_archivo_interactivo: Copia un archivo a elección.\n"
            " • ejecutar_powershell: Corre un script .ps1.\n"
            " • modificar_registro: Cambia una clave del registro.\n"
            " • gestionar_servicio: Inicia, detiene, activa o desactiva un servicio.\n"
            " • crear_tarea_programada: Añade una tarea al Programador de Tareas.\n\n"
            "--- ARGUMENTOS COMUNES ---\n\n"
            " • /S, /s: El más común para instalación silenciosa.\n"
            " • /VERYSILENT, /SUPPRESSMSGBOXES: Para InnoSetup.\n"
            " • /qn, /quiet, /passive: Comunes en instaladores .MSI.\n\n"
            "Consejo: Busca en Google \"<programa> silent install\" para encontrar los correctos.\n"
        )
        messagebox.showinfo(help_title, help_text, parent=self.root)

    def _show_about_dialog(self):
        about_window = tk.Toplevel(self.root)
        about_window.title("Acerca de PlayerToolkit")
        about_window.geometry("400x300")
        about_window.transient(self.root)
        about_window.resizable(False, False)
        about_window.grab_set()

        ttk.Label(about_window, text="PlayerToolkit", font=("Segoe UI", 16, "bold")).pack(pady=(20, 5))
        ttk.Label(about_window, text="Versión 6.1.3").pack()

        ttk.Label(about_window, text="Desarrollado por [Tu Nombre/Alias Aquí]").pack(pady=20)

        link = ttk.Label(about_window, text="Visita el Proyecto en GitHub", foreground="blue", cursor="hand2")
        link.pack()
        link.bind("<Button-1>", lambda e: webbrowser.open_new("https://github.com/tu-usuario/PlayerToolkit"))

        ttk.Button(about_window, text="Cerrar", command=about_window.destroy).pack(side="bottom", pady=20)

    def _populate_config_treeview(self):
        for item in self.config_treeview.get_children(): self.config_treeview.delete(item)
        for app_name, config in sorted(self.app_configs.items()):
            values = (app_name, config.get('categoria', ''), config.get('tipo', ''), str(config.get('args_instalacion', '[]')), config.get('icon', ''))
            self.config_treeview.insert('', 'end', iid=app_name, values=values)

    def _on_tree_double_click(self, event):
        if self.tree_editor:
            self.tree_editor.destroy()
            self.tree_editor = None

        region = self.config_treeview.identify("region", event.x, event.y)
        if region != "cell": return
        item_id = self.config_treeview.focus()
        column_id_str = self.config_treeview.identify_column(event.x)
        column_name = self.config_treeview.heading(column_id_str, "text")

        # El doble clic es ahora solo para 'Icono' y 'Argumentos' (edición manual)
        if column_name not in ["Icono", "Argumentos"]:
            return

        key_to_edit = {'Icono': 'icon', 'Argumentos': 'args_instalacion'}[column_name]
        app_name = item_id
        current_value = self.app_configs[app_name].get(key_to_edit)

        prompt = f"Nuevo valor para '{key_to_edit}' en '{app_name}':"
        new_value_str = simpledialog.askstring(f"Editar {key_to_edit}", prompt, initialvalue=str(current_value), parent=self.root)

        if new_value_str is None: return
        try:
            new_value = new_value_str
            if key_to_edit == 'args_instalacion':
                new_value = json.loads(new_value_str.replace("'", '"'))

            self.app_configs[app_name][key_to_edit] = new_value
            self.modified_configs.add(app_name)
            self.config_treeview.set(item_id, column_name, str(new_value))
        except (json.JSONDecodeError, ValueError) as e:
            messagebox.showerror("Error de Formato", f"El valor introducido no es válido.\nEjemplo para argumentos: [\"/S\"]\nError: {e}", parent=self.root)

    def _on_config_tree_click(self, event):
        if self.tree_editor:
            self.tree_editor.destroy()
            self.tree_editor = None

        item_id = self.config_treeview.identify_row(event.y)
        column_id_str = self.config_treeview.identify_column(event.x)

        if not item_id or not column_id_str:
            return

        x, y, width, height = self.config_treeview.bbox(item_id, column_id_str)
        column_name = self.config_treeview.heading(column_id_str, "text")

        value = self.config_treeview.set(item_id, column_id_str)

        editor = None
        options = []

        if column_name == "Tipo de Tarea":
            options = [
                TASK_TYPE_LOCAL_INSTALL, TASK_TYPE_MANUAL_ASSISTED, TASK_TYPE_COPY_INTERACTIVE,
                TASK_TYPE_RUN_POWERSHELL, TASK_TYPE_MODIFY_REGISTRY, TASK_TYPE_MANAGE_SERVICE,
                TASK_TYPE_CREATE_SCHEDULED_TASK, TASK_TYPE_POWER_CONFIG, TASK_TYPE_CLEAN_TEMP
            ]
            editor = ttk.Combobox(self.config_treeview, values=options, state="readonly")
            editor.set(value)

        elif column_name == "Categoría":
            categories = sorted(list(set(cfg.get('categoria', 'Sin Categoría') for cfg in self.app_configs.values())))
            editor = ttk.Combobox(self.config_treeview, values=categories, state="normal")
            editor.set(value)

        elif column_name == "Argumentos":
            self.args_presets = {
                "Preset: Silencioso (InnoSetup)": '["/VERYSILENT", "/SUPPRESSMSGBOXES"]',
                "Preset: Silencioso (NSIS)": '["/S"]',
                "Preset: Silencioso (MSI)": '["/qn"]',
                "Preset: Vacío": '[]'
            }
            editor = ttk.Combobox(self.config_treeview, values=list(self.args_presets.keys()), state="readonly")

        if editor:
            self.tree_editor = editor
            editor.place(x=x, y=y, width=width, height=height)
            editor.focus_set()

            def on_commit(event):
                new_value = editor.get()

                # Manejar presets de argumentos
                if column_name == "Argumentos" and new_value in self.args_presets:
                    new_value = self.args_presets[new_value]

                app_name = item_id
                key_map = {"Categoría": "categoria", "Tipo de Tarea": "tipo", "Argumentos": "args_instalacion"}
                key_to_edit = key_map.get(column_name)

                if key_to_edit:
                    self.config_treeview.set(item_id, column_name, new_value)

                    try:
                        final_value = json.loads(new_value.replace("'", '"')) if key_to_edit == "args_instalacion" else new_value
                        self.app_configs[app_name][key_to_edit] = final_value
                        self.modified_configs.add(app_name)
                    except (json.JSONDecodeError, ValueError) as e:
                         messagebox.showerror("Error de Formato", f"Valor no válido para argumentos: {e}", parent=self.root)

                editor.destroy()
                self.tree_editor = None

            editor.bind("<<ComboboxSelected>>", on_commit)
            editor.bind("<FocusOut>", on_commit)

    def _save_custom_config(self):
        self.conf_dir.mkdir(exist_ok=True)
        config_file = self.conf_dir / "config_personalizada.json"

        if not self.modified_configs:
            messagebox.showinfo("Sin cambios", "No se han realizado cambios para guardar.", parent=self.root)
            return

        current_custom_config = {}
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                current_custom_config = json.load(f)

        for app_name in self.modified_configs:
            default_app_conf = DEFAULT_APP_CONFIG.copy()
            if app_name in APP_CONFIGURATIONS:
                default_app_conf.update(APP_CONFIGURATIONS[app_name])

            app_changes = {}
            for key, value in self.app_configs[app_name].items():
                if key not in default_app_conf or default_app_conf[key] != value:
                    app_changes[key] = value

            if app_changes:
                current_custom_config[app_name] = app_changes

        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(current_custom_config, f, indent=4, ensure_ascii=False)
            messagebox.showinfo("Guardado", "Configuración personalizada guardada.", parent=self.root)
            self.modified_configs.clear()
        except IOError as e:
            messagebox.showerror("Error al Guardar", f"No se pudo escribir el archivo de configuración:\n{e}", parent=self.root)

    def _restore_default_config(self):
        config_file = self.conf_dir / "config_personalizada.json"
        if not config_file.exists():
            messagebox.showinfo("Información", "No hay configuración personalizada para restaurar.", parent=self.root)
            return
        if messagebox.askyesno("Confirmar", "¿Eliminar toda la configuración personalizada?\nLa aplicación deberá reiniciarse.", parent=self.root):
            try:
                config_file.unlink()
                messagebox.showinfo("Éxito", "Configuración restaurada.\nReinicia la aplicación.", parent=self.root)
            except IOError as e:
                messagebox.showerror("Error", f"No se pudo eliminar el archivo de configuración:\n{e}", parent=self.root)

    def _export_config(self):
        config_file = self.conf_dir / "config_personalizada.json"
        if not config_file.exists():
            messagebox.showwarning("Sin configuración", "No hay configuración personalizada para exportar.", parent=self.root)
            return
        dest = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")], title="Exportar configuración")
        if dest:
            shutil.copy2(config_file, dest)
            messagebox.showinfo("Éxito", f"Configuración exportada a\n{dest}", parent=self.root)

    def _import_config(self, src_path=None):
        config_file = self.conf_dir / "config_personalizada.json"
        src = src_path or filedialog.askopenfilename(filetypes=[("JSON files", "*.json")], title="Importar configuración")
        if src:
            self.conf_dir.mkdir(exist_ok=True)
            shutil.copy2(src, config_file)
            messagebox.showinfo("Éxito", "Configuración importada. Por favor, reinicia la aplicación para aplicar los cambios.", parent=self.root)

    def _load_groups(self):
        groups_dir = self.programas_dir / "Grupos"
        groups_dir.mkdir(exist_ok=True)
        groups = {}
        try:
            for filepath in groups_dir.glob("*.txt"):
                with open(filepath, 'r', encoding='utf-8') as f:
                    groups[filepath.stem] = [line.strip() for line in f if line.strip()]
        except IOError as e:
            messagebox.showerror("Error de Lectura", f"No se pudieron cargar los grupos:\n{e}")
        return groups

    def _on_siguiente_click(self):
        selected_apps = []
        for cat_id in self.app_tree.get_children():
            for app_id in self.app_tree.get_children(cat_id):
                if self.app_tree.item(app_id, 'text').startswith(self.CHECK_CHAR):
                    selected_apps.append(app_id)

        if not selected_apps:
            messagebox.showwarning("Sin Selección", "No has seleccionado ninguna tarea.")
            return

        current_extra_options = {}
        resumen = "Se realizarán las siguientes acciones:\n\n"

        for key in selected_apps:
            config = self.app_configs[key]
            resumen_line = f"- {config['icon']} {key}"

            task_type = config.get("tipo")
            if task_type in [TASK_TYPE_LOCAL_INSTALL, TASK_TYPE_MANUAL_ASSISTED]:
                instaladores = self.scan_results.get(key, [])
                if instaladores and len(instaladores) == 1:
                    current_extra_options[key] = {'exe_filename': instaladores[0]}
                elif instaladores and len(instaladores) > 1:
                    version_elegida = self.extra_options.get(key, {}).get('selected')
                    if not version_elegida:
                        messagebox.showerror("Error", f"Para '{key}', por favor elige una versión del desplegable.")
                        return
                    current_extra_options[key] = {'exe_filename': version_elegida}
                    resumen_line += f" (Versión: {version_elegida})"
                elif config.get("url"):
                    url_path = Path(config.get("url", ""))
                    current_extra_options[key] = {'exe_filename': url_path.name}
                else:
                    messagebox.showerror("Error", f"No se encontró instalador para '{key}' y no hay URL.")
                    return
            elif task_type == TASK_TYPE_COPY_INTERACTIVE:
                archivo_elegido = self.extra_options.get(key, {}).get('selected')
                if not archivo_elegido:
                    messagebox.showerror("Error", f"Para '{key}', por favor elige un archivo del desplegable.")
                    return
                current_extra_options[key] = {'selected_filename': archivo_elegido}
                resumen_line += f" (Archivo: {archivo_elegido})"
            resumen += resumen_line + "\n"

        if any(self.app_configs[key].get("tipo") == TASK_TYPE_MANUAL_ASSISTED for key in selected_apps):
            resumen += "\nATENCIÓN: Las tareas manuales se procesarán primero."
        resumen += "\n\n¿Deseas continuar?"

        if messagebox.askyesno("Confirmar Acciones", resumen):
            self.notebook.select(self.log_tab_frame)
            processor = TaskProcessor(self.root, self.app_configs, selected_apps, current_extra_options, self.programas_dir, self.log_queue, completion_callback=lambda: self._rescan_and_refresh_ui(silent=True))
            threading.Thread(target=processor.run, daemon=True).start()

    def _on_uninstall_click(self):
        selected_to_uninstall = {name: data['data'] for name, data in self.uninstall_vars.items() if data['var'].get()}
        if not selected_to_uninstall:
            messagebox.showwarning("Sin Selección", "No has seleccionado ningún programa para desinstalar.")
            return

        resumen = "Se intentará desinstalar silenciosamente:\n\n"
        for name in selected_to_uninstall:
            resumen += f"- {name}\n"
        resumen += "\n¿Deseas continuar?"

        if messagebox.askyesno("Confirmar Desinstalación", resumen):
            self.notebook.select(self.log_tab_frame)
            app_configs = {name: {"tipo": TASK_TYPE_UNINSTALL, "uninstall_string": data["uninstall_string"]} for name, data in selected_to_uninstall.items()}
            selected_apps = list(selected_to_uninstall.keys())
            processor = TaskProcessor(self.root, app_configs, selected_apps, {}, self.programas_dir, self.log_queue, completion_callback=lambda: self._rescan_and_refresh_ui(silent=True))
            threading.Thread(target=processor.run, daemon=True).start()

    def _filter_uninstall_list(self, search_var):
        query = search_var.get().lower()
        for name, data in self.uninstall_vars.items():
            chk = data['chk']
            if query in name.lower():
                chk.pack(anchor='w', padx=5, pady=2)
            else:
                chk.pack_forget()

    def _set_item_checked(self, item_id, checked):
        current_text = self.app_tree.item(item_id, 'text')
        base_text = current_text.lstrip(f"{self.CHECK_CHAR} {self.UNCHECK_CHAR} ")
        new_char = self.CHECK_CHAR if checked else self.UNCHECK_CHAR
        self.app_tree.item(item_id, text=f"{new_char} {base_text}")

    def _update_parent_check_state(self, parent_id):
        children = self.app_tree.get_children(parent_id)
        if not children: return

        enabled_children = [cid for cid in children if 'disabled' not in self.app_tree.item(cid, 'tags')]
        if not enabled_children:
            self._set_item_checked(parent_id, False)
            return

        all_checked = all(self.app_tree.item(cid, 'text').startswith(self.CHECK_CHAR) for cid in enabled_children)
        self._set_item_checked(parent_id, all_checked)

    def _on_tree_click(self, event):
        item_id = self.app_tree.identify_row(event.y)
        column_id_str = self.app_tree.identify_column(event.x)
        region = self.app_tree.identify_region(event.x, event.y)

        if not item_id: return
        if 'disabled' in self.app_tree.item(item_id, 'tags'): return

        # *** CAMBIO PRINCIPAL AQUÍ ***
        column_name = self.app_tree.heading(column_id_str, "text")

        if column_name == "Versión / Archivo" and self.app_tree.parent(item_id):
            scan_result = self.scan_results.get(item_id, [])
            if scan_result and len(scan_result) > 1:
                dialog = ComboboxDialog(self.root, f"Seleccionar para {item_id}",
                                        "Elige una versión o archivo:", scan_result,
                                        initialvalue=self.extra_options.get(item_id, {}).get('selected'))
                if dialog.result:
                    if item_id not in self.extra_options: self.extra_options[item_id] = {}
                    self.extra_options[item_id]['selected'] = dialog.result
                    self.app_tree.set(item_id, 'selector', dialog.result)
            return

        if region == 'tree' or column_id_str == '#0':
            current_text = self.app_tree.item(item_id, 'text')
            is_checked = current_text.startswith(self.CHECK_CHAR)
            self._set_item_checked(item_id, not is_checked)

            if not self.app_tree.parent(item_id):
                for child_id in self.app_tree.get_children(item_id):
                    if 'disabled' not in self.app_tree.item(child_id, 'tags'):
                        self._set_item_checked(child_id, not is_checked)
            else:
                parent_id = self.app_tree.parent(item_id)
                self._update_parent_check_state(parent_id)

    def _filter_app_tree(self):
        query = self.search_var.get().lower().strip()

        for cat_id in list(self.app_tree.get_children()):
            self.app_tree.reattach(cat_id, '', 'end')
            for app_id in list(self.app_tree.get_children(cat_id)):
                self.app_tree.reattach(app_id, cat_id, 'end')

        if not query: return

        for cat_id in list(self.app_tree.get_children()):
            cat_text = self.app_tree.item(cat_id, 'text').lower()

            if query not in cat_text:
                any_child_visible = False
                for app_id in list(self.app_tree.get_children(cat_id)):
                    app_text = self.app_tree.item(app_id, 'text').lower()
                    if query in app_text:
                        any_child_visible = True
                    else:
                        self.app_tree.detach(app_id)

                if not any_child_visible:
                    self.app_tree.detach(cat_id)

    def _process_log_queue(self):
        try:
            while not self.log_queue.empty():
                message = self.log_queue.get_nowait()
                self.log_text.config(state="normal")
                self.log_text.insert(tk.END, message + "\n")
                self.log_text.config(state="disabled")
                self.log_text.see(tk.END)
        finally:
            self.root.after(100, self._process_log_queue)

    def _on_drop(self, event):
        filepath = event.data
        if filepath.startswith('{') and filepath.endswith('}'):
            filepath = filepath[1:-1]

        if filepath.lower().endswith("config_personalizada.json"):
            if messagebox.askyesno("Importar Configuración", f"¿Deseas importar el archivo de configuración?\n\n{filepath}\n\nLa aplicación deberá reiniciarse."):
                self._import_config(src_path=filepath)
        else:
            messagebox.showwarning("Archivo no válido", "Solo se pueden arrastrar archivos 'config_personalizada.json'.", parent=self.root)