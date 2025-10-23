# --- START OF FILE toolkit_lib/ui/main_app.py ---

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
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
from datetime import datetime
import subprocess
import requests
import re
from collections import defaultdict

from ..config import *
from ..tasks import TaskProcessor
from ..utils import scan_installed_software, clear_cache, scan_drivers
from .dialogs import ConfigWizardDialog, VariablesManagerDialog, open_group_manager, ComboboxDialog
from .helpers import ToolTip
from .tabs.tab_dashboard import create_dashboard_tab, refresh_dashboard
from .tabs.tab_apps import create_apps_tab
from .tabs.tab_drivers import create_drivers_tab
from .tabs.tab_groups import create_groups_tab
from .tabs.tab_uninstall import create_uninstall_tab
from .tabs.tab_log import create_log_tab
from .tabs.tab_config import create_config_tab

try:
    from tkinterdnd2 import DND_FILES
    DND_SUPPORT = True
except ImportError:
    DND_SUPPORT = False

APP_VERSION = "Versión 6.1.8"
GITHUB_OWNER = "JoelAnonRosendo"
GITHUB_REPO = "PlayerToolkit"
UPDATER_SCRIPT_NAME = "updater.bat"
STATUS_ICONS = {"pending": "▫️", "running": "⚙️", "success": "✅", "fail": "❌", "installed": "✔️"}

class PlayerToolkitApp:
    def __init__(self, root, scan_results, app_configs, installed_software):
        self.root, self.scan_results, self.app_configs, self.installed_software = root, scan_results, app_configs, installed_software
        self.app_tree = None; self.extra_options = {}; self.config_treeview = None; self.modified_configs = set()
        self.uninstall_vars = {}; self.log_queue = Queue(); self.CHECK_CHAR, self.UNCHECK_CHAR = "☑", "☐"
        self.update_status_label = None; self.is_downloading_update = False

        logging.info(f"--- Iniciando PlayerToolkit {APP_VERSION} ---")

        if getattr(sys, 'frozen', False): self.user_data_dir = Path(sys.executable).parent
        else: self.user_data_dir = Path(__file__).resolve().parent.parent.parent

        self.programas_dir = self.user_data_dir / "Programas"; self.conf_dir = self.user_data_dir / "conf"
        self.drivers_dir = self.programas_dir / "Drivers"; self.drivers_dir.mkdir(exist_ok=True)
        self.update_ready_path = self.user_data_dir / "update.zip"

        self._setup_styles(); self._setup_ui()

        self._populate_config_treeview()
        self.refresh_dashboard() 
        self._populate_app_tree(); self._check_installed_status(); self._populate_uninstall_tab(); self.scan_and_populate_drivers()
        self._process_log_queue()

        if DND_SUPPORT: self.root.drop_target_register(DND_FILES); self.root.dnd_bind('<<Drop>>', self._on_drop)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_styles(self):
        s = ttk.Style(self.root); s.configure('Muted.TLabel', foreground='gray'); s.configure('Accent.TButton', font=("Segoe UI", 11, "bold"), padding=10)
        s.configure("Treeview", font=("Segoe UI", 10), rowheight=28); s.configure("Category.Treeview", font=("Segoe UI", 10, "bold"))
        s.map("Treeview", background=[("selected", s.lookup("TButton", "background"))], foreground=[("selected", s.lookup("TButton", "foreground"))])
        s.configure('Success.TLabel', foreground='green'); s.configure('Warning.TLabel', foreground='orange')

    def _setup_ui(self):
        self.root.title(f"PlayerToolkit {APP_VERSION}")
        try:
            self.root.iconbitmap(self._get_resource_path("assets/img/icon.ico"))
        except Exception as e:
            logging.warning(f"No se pudo cargar el icono: {e}")
        
        self.root.geometry("1000x750"); self.root.minsize(850, 600)
        main = ttk.Frame(self.root, padding="10"); main.pack(expand=True, fill=tk.BOTH); main.rowconfigure(1, weight=1); main.columnconfigure(0, weight=1)
        top = ttk.Frame(main); top.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(top, text="PlayerToolkit", font=("Segoe UI", 16, "bold")).pack(side="left"); ttk.Button(top, text="🌙/☀️", command=sv_ttk.toggle_theme).pack(side="right")
        self.notebook = ttk.Notebook(main); self.notebook.grid(row=1, column=0, sticky="nsew", pady=5)

        self.dashboard_tab_frame = create_dashboard_tab(self.notebook, self)
        self.app_tab_frame = create_apps_tab(self.notebook, self)
        self.drivers_tab_frame = create_drivers_tab(self.notebook, self)
        self.groups_tab_frame = create_groups_tab(self.notebook, self)
        self.uninstall_tab_frame = create_uninstall_tab(self.notebook, self)
        self.log_tab_frame = create_log_tab(self.notebook, self)
        self.config_tab_frame = create_config_tab(self.notebook, self)
        self.refresh_dashboard = lambda: refresh_dashboard(self)

        bottom = ttk.Frame(main); bottom.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.continue_button = ttk.Button(bottom, text="Ejecutar Tareas ➔", style='Accent.TButton', command=self._on_siguiente_click)
        self.uninstall_button = ttk.Button(bottom, text="Desinstalar ➔", style='Accent.TButton', command=self._on_uninstall_click)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed); self._on_tab_changed()

    def _get_resource_path(self, relative_path):
        base_path = getattr(sys, '_MEIPASS', self.user_data_dir)
        return os.path.join(base_path, relative_path)
    
    def _show_about_dialog(self):
        about_window = tk.Toplevel(self.root); about_window.title("Acerca de PlayerToolkit"); about_window.geometry("400x320")
        about_window.transient(self.root); about_window.resizable(False, False); about_window.grab_set()
        ttk.Label(about_window, text="PlayerToolkit", font=("Segoe UI", 16, "bold")).pack(pady=(20, 5))
        ttk.Label(about_window, text=f"{APP_VERSION}").pack()
        ttk.Label(about_window, text="Una herramienta para simplificar instalaciones.").pack(pady=20)
        repo_url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"; link = ttk.Label(about_window, text="Visita el Proyecto en GitHub", foreground="cyan", cursor="hand2")
        link.pack(); link.bind("<Button-1>", lambda e: webbrowser.open_new(repo_url))
        self.update_status_label = ttk.Label(about_window, text="", justify='center'); self.update_status_label.pack(pady=(5, 0))
        ttk.Button(about_window, text="Buscar Actualizaciones", command=self._on_check_updates_click).pack(pady=(10, 5))
        ttk.Button(about_window, text="Cerrar", command=about_window.destroy).pack(side="bottom", pady=20)
        
    def _on_check_updates_click(self):
        if self.is_downloading_update:
            messagebox.showinfo("Información", "Ya se está descargando una actualización.", parent=self.root)
            return
        threading.Thread(target=self._check_for_updates, daemon=True).start()

    def _parse_version_string(self, version_string):
        if not isinstance(version_string, str): return (0, 0, 0), None
        match = re.search(r'(\d+)\.(\d+)\.(\d+)', version_string)
        if match: return tuple(map(int, match.groups())), match.group(0)
        return (0, 0, 0), None

    def _check_for_updates(self):
        api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
        self.root.after(0, self.update_status_label.config, {'text': 'Buscando actualizaciones...', 'foreground': 'white'})
        try:
            response = requests.get(api_url, timeout=10); response.raise_for_status(); latest_release = response.json()
            latest_version_tag = latest_release.get("tag_name")
            if not latest_version_tag: self.root.after(0, self._show_update_error, "No se encontró tag de versión."); return
            
            current_tuple, _ = self._parse_version_string(APP_VERSION)
            latest_tuple, latest_version_str = self._parse_version_string(latest_version_tag)

            if latest_tuple > current_tuple:
                if not latest_version_str: self.root.after(0, self._show_update_error, f"El tag '{latest_version_tag}' no es X.Y.Z."); return
                
                expected_asset_name = f"PlayerToolkit_v{latest_version_str}.zip"
                update_asset = next((asset for asset in latest_release.get("assets", []) if asset['name'] == expected_asset_name), None)
                
                if update_asset: self.root.after(0, self._show_update_available, latest_version_tag, update_asset)
                else: self.root.after(0, self._show_update_error, f"No se encontró el archivo '{expected_asset_name}'.")
            else:
                self.root.after(0, self._show_no_update)
        except requests.RequestException as e: self.root.after(0, self._show_update_error, f"Error de red: {e}")
        except Exception as e: self.root.after(0, self._show_update_error, f"Error: {e}")

    def _show_update_available(self, new_version, asset):
        msg = f"¡Nueva versión disponible: {new_version}!\n\n¿Descargar ahora?\nSe instalará al cerrar la aplicación."
        parent = self.update_status_label.winfo_toplevel() if self.update_status_label and self.update_status_label.winfo_exists() else self.root
        if messagebox.askyesno("Actualización Disponible", msg, parent=parent): self._start_background_download(asset)

    def _start_background_download(self, asset):
        if self.is_downloading_update: return
        self.is_downloading_update = True; self.update_status_label.config(text="Iniciando descarga...")
        threading.Thread(target=self._download_thread, args=(asset['browser_download_url'], asset['size']), daemon=True).start()

    def _download_thread(self, url, total_size):
        try:
            downloaded = 0
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(self.update_ready_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk); downloaded += len(chunk)
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            self.root.after(0, self.update_status_label.config, {'text': f'Descargando: {int(progress)}%'})
            self.root.after(0, self.update_status_label.config, {'text': 'Descarga completa.\nSe instalará al cerrar.', 'foreground': 'green'})
        except requests.RequestException as e:
            self.root.after(0, self.update_status_label.config, {'text': f'Error de descarga: {e}', 'foreground': 'red'})
            if self.update_ready_path.exists(): self.update_ready_path.unlink()
        finally: self.is_downloading_update = False

    def _show_no_update(self): 
        parent = self.update_status_label.winfo_toplevel() if self.update_status_label and self.update_status_label.winfo_exists() else self.root
        messagebox.showinfo("Actualizado", "Ya tienes la última versión.", parent=parent)
        if self.update_status_label: self.update_status_label.config(text="")

    def _show_update_error(self, err): 
        parent = self.update_status_label.winfo_toplevel() if self.update_status_label and self.update_status_label.winfo_exists() else self.root
        messagebox.showerror("Error", f"No se pudo comprobar si hay actualizaciones.\n\nError: {err}", parent=parent)
        if self.update_status_label: self.update_status_label.config(text="")
    
    # --- INICIO DEL CÓDIGO MODIFICADO ---

    def run_task_from_dashboard(self, task_key):
        self.notebook.select(self.log_tab_frame)
        self._update_task_ui(task_key, status='pending')
        # Tareas rápidas NO necesitan un re-escaneo completo, solo una actualización de la UI.
        processor = TaskProcessor(self.root, self.app_configs, [task_key], {}, self.programas_dir, self._load_custom_variables(), self.log_queue, self._update_task_ui, self._light_refresh_ui)
        threading.Thread(target=processor.run, daemon=True).start()

    def apply_group_from_dashboard(self, group_name):
        apps = set(self._load_groups().get(group_name, []))
        for cid in self.app_tree.get_children():
            for aid in self.app_tree.get_children(cid):
                if 'disabled' not in self.app_tree.item(aid,'tags'): self._set_item_checked(aid, aid in apps)
            self._update_parent_check_state(cid)
        self.notebook.select(self.app_tab_frame)

    def _on_siguiente_click(self):
        active_tab = self.notebook.tab(self.notebook.select(), "text")
        if "Aplicaciones" in active_tab:
            selected = [c for cat in self.app_tree.get_children() for c in self.app_tree.get_children(cat) if self.app_tree.item(c,'text').startswith(self.CHECK_CHAR)]
            if not selected: messagebox.showwarning("Sin Selección", "No ha seleccionado ninguna aplicación."); return
            extra_opts = {}; resumen = "Se realizarán las siguientes acciones:\n\n"
            for key in selected:
                cfg = self.app_configs[key]; line = f"- {cfg['icon']} {key}";
                res = self.scan_results.get(key, [])
                if cfg["tipo"] in [TASK_TYPE_LOCAL_INSTALL,TASK_TYPE_MANUAL_ASSISTED]:
                    if len(res) == 1: extra_opts[key] = {'exe_filename': res[0]}
                    elif len(res) > 1:
                        chosen = self.extra_options.get(key, {}).get('selected')
                        if not chosen: messagebox.showerror("Error", f"Para '{key}', por favor elija un archivo/versión."); return
                        line += f" ({chosen})"; extra_opts[key] = {'exe_filename': chosen}
                    elif cfg.get("url"): extra_opts[key] = {'exe_filename': Path(cfg["url"]).name}
                    else: messagebox.showerror("Error", f"No se encontró instalador para '{key}'."); return
                elif cfg["tipo"] == TASK_TYPE_COPY_INTERACTIVE:
                    chosen = self.extra_options.get(key, {}).get('selected')
                    if not chosen: messagebox.showerror("Error", f"Para '{key}', por favor elija un archivo."); return
                    extra_opts[key] = {'selected_filename': chosen}; line += f" (Archivo: {chosen})"
                resumen += line + "\n"

            if messagebox.askyesno("Confirmar Acciones", resumen):
                self.notebook.select(self.log_tab_frame)
                # La instalación sí requiere un re-escaneo completo al finalizar.
                processor = TaskProcessor(self.root, self.app_configs, selected, extra_opts, self.programas_dir, self._load_custom_variables(), self.log_queue, self._update_task_ui, lambda: self._rescan_and_refresh_ui(True))
                threading.Thread(target=processor.run, daemon=True).start()

        elif "Drivers" in active_tab:
            selected = [self.drivers_tree.item(i, 'tags')[0] for i in self.drivers_tree.selection()]
            if not selected: messagebox.showwarning("Sin Selección", "No ha seleccionado ningún driver."); return
            if messagebox.askyesno("Confirmar", f"Instalar los siguientes drivers:\n\n- {', '.join(selected)}\n\n¿Continuar?"):
                self.notebook.select(self.log_tab_frame)
                drv_cfgs = {name: {"tipo": TASK_TYPE_INSTALL_DRIVER, "driver_dir_name": name} for name in selected}
                # Los drivers NO necesitan un re-escaneo, solo una actualización de su propia lista.
                processor = TaskProcessor(self.root, drv_cfgs, selected, {}, self.programas_dir, self._load_custom_variables(), self.log_queue, None, self.scan_and_populate_drivers)
                threading.Thread(target=processor.run, daemon=True).start()
    
    def _on_uninstall_click(self):
        selected = {n:d['data'] for n,d in self.uninstall_vars.items() if d['var'].get()}
        if not selected or not messagebox.askyesno("Confirmar", "Desinstalar:\n" + "\n".join([f"- {n}" for n in selected]) + "\n\n¿Continuar?"): return
        self.notebook.select(self.log_tab_frame)
        cfgs = {n:{"tipo":TASK_TYPE_UNINSTALL, "uninstall_string":d["uninstall_string"]} for n,d in selected.items()}
        # La desinstalación requiere un re-escaneo completo.
        processor = TaskProcessor(self.root, cfgs, list(selected.keys()), {}, self.programas_dir, self._load_custom_variables(), self.log_queue, completion_callback=lambda:self._rescan_and_refresh_ui(True))
        threading.Thread(target=processor.run, daemon=True).start()

    # --- FIN DEL CÓDIGO MODIFICADO ---

    def _on_close(self):
        if self.update_ready_path.exists() and messagebox.askyesno("Instalar Actualización", "Actualización lista. ¿Cerrar e instalar ahora?"):
             self._launch_updater()
        self.root.destroy()

    def _launch_updater(self):
        script = f"""@echo off\ntaskkill /PID {os.getpid()} /F>nul\ntimeout /t 2>nul\npowershell Expand-Archive -Path '{self.update_ready_path}' -Dest '.' -Force\ndel "{self.update_ready_path}"\nstart "" "{os.path.basename(sys.executable)}"\ndel "%~f0" """;
        updater_path = self.user_data_dir / UPDATER_SCRIPT_NAME
        with open(updater_path, "w", encoding="utf-8") as f: f.write(script)
        subprocess.Popen([str(updater_path)], creationflags=subprocess.DETACHED_PROCESS)

    def _on_tab_changed(self, event=None):
        tab = self.notebook.tab(self.notebook.select(), "text")
        self.continue_button.pack_forget(); self.uninstall_button.pack_forget()
        if any(t in tab for t in ["Aplicaciones", "Drivers"]): self.continue_button.pack(side=tk.RIGHT)
        elif "Desinstalar" in tab: self.uninstall_button.pack(side=tk.RIGHT)

        if "Panel de Control" in tab: self.refresh_dashboard()
        if "Drivers" in tab: self.scan_and_populate_drivers()

    def _rescan_and_refresh_ui(self, silent=False):
        # Esta es la función LENTA y COMPLETA, solo para cambios de software.
        def do_rescan():
            clear_cache(); self.installed_software = scan_installed_software()
            self.scan_results.clear()
            for k,c in self.app_configs.items():
                if c.get('tipo') in [TASK_TYPE_LOCAL_INSTALL, TASK_TYPE_MANUAL_ASSISTED, TASK_TYPE_COPY_INTERACTIVE]:
                     self.scan_results[k] = [f.name for ext in INSTALLER_EXTENSIONS for f in (self.programas_dir/k).glob(f"*{ext}")] if (self.programas_dir/k).is_dir() else [STATUS_FOLDER_NOT_FOUND]
            self.root.after(0, self._update_ui_after_rescan, silent)
        threading.Thread(target=do_rescan, daemon=True).start()

    def _light_refresh_ui(self):
        # Esta es la nueva función de refresco RÁPIDA. Solo actualiza la UI, no escanea.
        self._check_installed_status() # Revisa el estado de instalado
        self.refresh_dashboard() # Actualiza los contadores del panel
    
    def _update_ui_after_rescan(self, silent=False):
        self._populate_app_tree(); self._check_installed_status(); self._populate_uninstall_tab()
        self.scan_and_populate_drivers(); self._populate_config_treeview(); self.refresh_dashboard()
        if not silent: messagebox.showinfo("Actualizado", "Listas actualizadas.")

    def _populate_app_tree(self):
        [self.app_tree.delete(i) for i in self.app_tree.get_children()]; cats = defaultdict(list)
        [cats[c.get('categoria','Sin Categoría')].append(n) for n,c in self.app_configs.items()]
        for cat in sorted(cats.keys()):
            cid = self.app_tree.insert('', 'end', text=f"{self.UNCHECK_CHAR} {cat}", open=True, tags=('category',))
            for key in sorted(cats[cat]):
                cfg = self.app_configs[key]
                aid = self.app_tree.insert(cid,'end', iid=key, text=f"{self.UNCHECK_CHAR} {cfg.get('icon','📦')} {key}")
                self.app_tree.set(aid, 'status_icon', STATUS_ICONS["pending"])
                res, msg = self.scan_results.get(key,[]), ""
                if cfg.get('tipo') in [TASK_TYPE_LOCAL_INSTALL,TASK_TYPE_MANUAL_ASSISTED]:
                    if not res or res == [STATUS_FOLDER_NOT_FOUND]:
                        msg = "(Se descargará)" if cfg.get("url") else "(No encontrado)";
                        if not cfg.get("url"): self.app_tree.item(aid, tags=('disabled',))
                    elif len(res)>1: self.app_tree.set(aid, 'selector', "[Elegir...]")
                self.app_tree.set(aid,'status_text', msg)

    def _check_installed_status(self):
        installed = {n.lower() for n in self.installed_software.keys()}
        for k, cfg in self.app_configs.items():
            if self.app_tree.exists(k):
                ukey = cfg.get("uninstall_key")
                if ukey and any(ukey.lower() in name for name in installed):
                    self.app_tree.set(k, 'status_icon', STATUS_ICONS["installed"]); self.app_tree.set(k, 'status_text', "Instalado"); self.app_tree.item(k, tags=('disabled','installed'))

    def _populate_uninstall_tab(self):
        [w.destroy() for w in self.uninstall_frame.winfo_children()]; self.uninstall_vars.clear()
        for n,d in sorted(self.installed_software.items(), key=lambda i:i[0].lower()):
            var=tk.BooleanVar(); v=f" (v{d.get('version')})" if d.get('version') else ""; dt=f" [{d.get('install_date')}]" if d.get('install_date') else ""
            chk=ttk.Checkbutton(self.uninstall_frame, text=f"{n}{v}{dt}", variable=var); chk.pack(anchor='w',padx=5, pady=2); self.uninstall_vars[n]={'var':var,'data':d,'chk':chk}

    def _populate_config_treeview(self):
        [self.config_treeview.delete(i) for i in self.config_treeview.get_children()]
        for n,c in sorted(self.app_configs.items()): self.config_treeview.insert('', 'end', iid=n, values=(n, c.get('categoria',''), c.get('tipo',''), str(c.get('args_instalacion',[])), str(c.get('dependencies',[]))))

    def _filter_uninstall_list(self, var):
        q = var.get().lower(); [d['chk'].pack(anchor='w',padx=5,pady=2) if q in n.lower() else d['chk'].pack_forget() for n,d in self.uninstall_vars.items()]

    def _set_item_checked(self, iid, chk):
        txt = self.app_tree.item(iid, 'text'); base = txt.lstrip(f"{self.CHECK_CHAR}{self.UNCHECK_CHAR} "); self.app_tree.item(iid, text=f"{self.CHECK_CHAR if chk else self.UNCHECK_CHAR} {base}")

    def _update_parent_check_state(self, pid):
        children = self.app_tree.get_children(pid)
        if children:
            enabled=[c for c in children if 'disabled' not in self.app_tree.item(c,'tags')]
            all_c = all(self.app_tree.item(c,'text').startswith(self.CHECK_CHAR) for c in enabled) if enabled else False
            self._set_item_checked(pid, all_c)

    def _on_tree_click(self, event):
        iid = self.app_tree.identify_row(event.y)
        if not iid or 'disabled' in self.app_tree.item(iid, 'tags'):
            return

        column = self.app_tree.identify_column(event.x)
        
        if column == '#4' and self.app_tree.parent(iid): # Columna del selector
            res = self.scan_results.get(iid, [])
            if len(res) > 1:
                dlg = ComboboxDialog(self.root, f"Seleccionar para {iid}", "Elige un archivo:", res, 
                                     initialvalue=self.extra_options.get(iid, {}).get('selected'))
                if dlg.result:
                    self.extra_options.setdefault(iid, {})['selected'] = dlg.result
                    self.app_tree.set(iid, 'selector', dlg.result)
            return

        if self.app_tree.identify_region(event.x, event.y) == 'tree':
            is_checked = self.app_tree.item(iid, 'text').startswith(self.CHECK_CHAR)
            self._set_item_checked(iid, not is_checked)
            
            if not self.app_tree.parent(iid):
                for child in self.app_tree.get_children(iid):
                    if 'disabled' not in self.app_tree.item(child, 'tags'):
                        self._set_item_checked(child, not is_checked)
            else:
                self._update_parent_check_state(self.app_tree.parent(iid))

    def _process_log_queue(self):
        try:
            while not self.log_queue.empty():
                level, msg = self.log_queue.get_nowait()
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.log_tree.insert("",0, values=(timestamp,level,msg), tags=(level,))
                if hasattr(self, 'original_log_data'):
                    self.original_log_data.insert(0, (timestamp, level, msg))
        finally: self.root.after(200, self._process_log_queue)

    def _update_task_ui(self, key, status=None, text=None, progress=None, phase='install'):
        if self.app_tree.exists(key):
            if status: self.app_tree.set(key, 'status_icon', STATUS_ICONS.get(status, "❓"))
            if text: self.app_tree.set(key, 'status_text', text)
            if progress is not None:
                prog_val = (progress / 2) if phase == 'download' else 50 + (progress / 2)
                bar = "█"*int(prog_val/10); empty="─"*(10-len(bar)); self.app_tree.set(key, 'progress', f"[{bar}{empty}] {int(prog_val)}%")
    
    def scan_and_populate_drivers(self):
        self.found_drivers = scan_drivers(self.drivers_dir)
        [self.drivers_tree.delete(i) for i in self.drivers_tree.get_children()]
        if not self.found_drivers:
            self.drivers_tree.insert('','end',text="No se encontraron paquetes de drivers en 'Programas/Drivers'.")
        else:
            for name in sorted(self.found_drivers.keys()):
                self.drivers_tree.insert('','end', text=f"🔩 {name}", tags=(name,))

    def _on_drop(self, event):
        fpath=event.data.strip('{}')
        if fpath.lower().endswith("config_personalizada.json") and messagebox.askyesno("Importar Configuración", f"¿Importar archivo?\n\n{fpath}\n\nSe requiere reinicio."): self._import_config(fpath)

    def _import_config(self, src_path):
        if src_path:
            shutil.copy2(src_path, self.conf_dir / "config_personalizada.json")
            messagebox.showinfo("Éxito", "Configuración importada. Reinicia para aplicar.")

    def _load_custom_variables(self):
        v_file=self.conf_dir/"variables.json"
        if not v_file.exists(): return {}
        try:
            with open(v_file, 'r', encoding='utf-8') as f: return json.load(f)
        except(IOError,json.JSONDecodeError): return {}
    
    def _save_custom_variables(self,variables):
        v_file = self.conf_dir/"variables.json"
        try:
            with open(v_file, 'w', encoding='utf-8') as f: json.dump(variables, f, indent=4); messagebox.showinfo("Guardado", "Variables guardadas.")
        except IOError as e: messagebox.showerror("Error", f"No se pudo guardar:\n{e}")

    def _load_groups(self):
        g_dir = self.programas_dir/"Grupos"; g_dir.mkdir(exist_ok=True); groups={}
        try:
            for f in g_dir.glob("*.txt"):
                with open(f, 'r', encoding='utf-8') as fi: groups[f.stem] = [l.strip() for l in fi if l.strip()]
        except IOError as e: messagebox.showerror("Error",f"No se pudieron cargar los grupos:\n{e}")
        return groups