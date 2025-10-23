# --- START OF FILE toolkit_lib/tasks.py ---

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import subprocess
import logging
import shutil
import requests # type: ignore
from pathlib import Path
import re
from queue import Queue
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

from .config import *

def _expand_vars(value, custom_vars=None):
    if not isinstance(value, str): return value
    expanded_value = os.path.expandvars(value)
    if custom_vars:
        for var, var_value in custom_vars.items():
            expanded_value = expanded_value.replace(f"%{var}%", var_value)
    return expanded_value

class ProgressManager:
    def __init__(self, root_gui):
        self.root, self.window, self.bar, self.label_status, self.label_percentage = root_gui, None, None, None, None

    def create(self):
        if self.window and self.window.winfo_exists(): return
        self.window = tk.Toplevel(self.root)
        self.window.title("Procesando Tareas..."); self.window.geometry("450x150"); self.window.resizable(False, False)
        self.window.transient(self.root); self.window.protocol("WM_DELETE_WINDOW", lambda: None); self.window.grab_set()
        frame = ttk.Frame(self.window, padding="15"); frame.pack(expand=True, fill=tk.BOTH)
        self.label_status = ttk.Label(frame, text="Iniciando...", font=("Segoe UI", 10), wraplength=400)
        self.label_status.pack(pady=(0, 10), fill="x")
        self.bar = ttk.Progressbar(frame, mode="determinate"); self.bar.pack(pady=10, fill="x", ipady=4)
        self.label_percentage = ttk.Label(frame, text="", font=("Segoe UI", 9, "bold"), anchor="e")
        self.label_percentage.pack(pady=5, fill="x")

    def update(self, barra=None, status=None, porcentaje=None):
        if not (self.window and self.window.winfo_exists()): return
        if barra is not None: self.bar['value'] = barra
        if status: self.label_status.config(text=status)
        if porcentaje is not None: self.label_percentage.config(text=porcentaje)
        self.window.update_idletasks()

    def destroy(self):
        if self.window and self.window.winfo_exists(): self.window.destroy()

    def release_focus(self):
        if self.window and self.window.winfo_exists(): self.window.grab_release()

    def regain_focus(self):
        if self.window and self.window.winfo_exists(): self.window.grab_set()

class TaskProcessor:
    def __init__(self, root_gui, app_configs, selected_apps, extra_options, programas_dir, custom_variables, log_queue: Queue, ui_update_callback=None, completion_callback=None):
        self.root, self.app_configs, self.selected_apps, self.extra_options = root_gui, app_configs, selected_apps, extra_options
        self.programas_dir, self.custom_variables, self.pm = programas_dir, custom_variables, ProgressManager(self.root)
        self.results, self.log_queue, self.ui_update_callback = {}, log_queue, ui_update_callback
        self.completion_callback = completion_callback

    def _log(self, message, level="INFO"):
        logging.info(message); self.log_queue.put((level, message))

    def _safe_ui_update(self, *args, **kwargs):
        if self.ui_update_callback: self.root.after(0, lambda: self.ui_update_callback(*args, **kwargs))
    
    def _resolve_dependencies_sequentially(self):
        graph = {app: set(self.app_configs.get(app, {}).get("dependencies", [])) for app in self.selected_apps}
        for app, deps in graph.items():
            for dep in list(deps):
                if dep not in self.selected_apps:
                    self._log(f"Advertencia: Dependencia '{dep}' de '{app}' no seleccionada. Ignorando.", "WARNING"); deps.remove(dep)
        ordered_list, visited = [], set()
        def visit(app):
            if app in visited: return True
            if app in visiting: self._log(f"Error: Dependencia circular detectada con '{app}'.", "ERROR"); return False
            visiting.add(app)
            for dep in graph.get(app, []):
                if not visit(dep): return False
            visiting.remove(app); visited.add(app); ordered_list.append(app)
            return True
        visiting = set()
        for app in self.selected_apps:
            if app not in visited:
                if not visit(app): messagebox.showerror("Error de Dependencias", "Se detectó una dependencia circular."); return None
        return ordered_list

    def run(self):
        self.root.after(0, self.pm.create)
        tasks_to_run = self._resolve_dependencies_sequentially()
        if tasks_to_run is None: self.root.after(0, self.pm.destroy); return
        total_tasks = len(tasks_to_run)
        for i, app_key in enumerate(tasks_to_run):
            self._execute_task(app_key)
            progress = ((i + 1) / total_tasks) * 100
            self.root.after(0, lambda p=progress, idx=i: self.pm.update(barra=p, status=f"Completadas {idx+1}/{total_tasks} tareas...", porcentaje=f"{int(p)}%"))
        self.root.after(0, self.pm.destroy); self.root.after(10, self._show_results_log)
        if self.completion_callback: self.root.after(100, self.completion_callback)

    def _execute_task(self, app_key):
        self._safe_ui_update(app_key, status='running', text="En cola...")
        self._log(f"--- Iniciando: {app_key} ---"); config = self.app_configs.get(app_key, {}).copy()
        if app_key in self.extra_options: config.update(self.extra_options[app_key])
        success = True
        if config.get("pre_task_script"): success = self._run_script(config["pre_task_script"])
        if success:
            handler = self._get_task_handler(config.get("tipo"))
            success = handler(app_key, config) if handler else False
        if success and config.get("post_task_script"):
            if not self._run_script(config["post_task_script"]): self.results[app_key] = f"⚠️ '{app_key}': Tarea OK, script POST falló."
        
        if success: self.results.setdefault(app_key, f"✅ '{app_key}': Completado con éxito."); self._log(f"--- ÉXITO: {app_key} ---", "SUCCESS"); self._safe_ui_update(app_key, status='success', text="Completado")
        else: self.results.setdefault(app_key, f"❌ '{app_key}': Falló."); self._log(f"--- ERROR: {app_key} ---", "ERROR"); self._safe_ui_update(app_key, status='fail', text="Falló")
        return success

    def _get_task_handler(self, task_type):
        return {
            TASK_TYPE_LOCAL_INSTALL: self._handle_local_install, TASK_TYPE_MANUAL_ASSISTED: self._handle_manual_assisted,
            TASK_TYPE_COPY_INTERACTIVE: self._handle_copy_interactive, TASK_TYPE_POWER_CONFIG: self._handle_power_config,
            TASK_TYPE_UNINSTALL: self._handle_uninstall, TASK_TYPE_CLEAN_TEMP: self._handle_clean_temp,
            TASK_TYPE_RUN_POWERSHELL: self._handle_run_powershell, TASK_TYPE_MODIFY_REGISTRY: self._handle_unimplemented,
            TASK_TYPE_MANAGE_SERVICE: self._handle_unimplemented, TASK_TYPE_CREATE_SCHEDULED_TASK: self._handle_unimplemented,
            TASK_TYPE_INSTALL_DRIVER: self._handle_install_driver
        }.get(task_type)

    def _run_script(self, script_key):
        handler = {"copy_lsplayer_shortcut": self._script_copy_lsplayer_shortcut}.get(script_key)
        if handler: return handler()
        self._log(f"Advertencia: Script no encontrado: {script_key}", "WARNING"); return True

    def _download_file(self, url, dest_path, app_key):
        try:
            self._log(f"Descargando desde {url}"); self._safe_ui_update(app_key, phase='download', text="Descargando...")
            with requests.get(url, stream=True, timeout=30) as r:
                r.raise_for_status(); total_size = int(r.headers.get('content-length', 0)); downloaded = 0
                with open(dest_path, 'wb') as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk); downloaded += len(chunk)
                        if total_size: self._safe_ui_update(app_key, phase='download', text=f"Descargando {int((downloaded/total_size)*100)}%", progress=int((downloaded/total_size)*100))
            return True
        except requests.RequestException as e: self._log(f"Error de descarga: {e}", "ERROR"); messagebox.showerror("Error", f"Fallo en '{url}':\n{e}"); return False

    def _prepare_installer(self, app_key, config):
        filename = config.get("exe_filename")
        if not filename: return None
        exe_path = self.programas_dir / app_key / filename
        if not exe_path.exists():
            if not config.get("url") or not self._download_file(config["url"], exe_path, app_key): return None
        return exe_path

    def _handle_local_install(self, app_key, config):
        exe_path = self._prepare_installer(app_key, config)
        if not exe_path: return False
        self._safe_ui_update(app_key, phase='install', text="Instalando...")
        return self._run_command(exe_path, config.get("args_instalacion",[]))

    def _handle_manual_assisted(self, app_key, config):
        exe_path = self._prepare_installer(app_key, config)
        if not exe_path: return False
        os.startfile(exe_path)
        self._safe_ui_update(app_key, phase='install', text="Esperando...")
        self.pm.release_focus()
        confirmed = messagebox.askokcancel(f"Acción Requerida: {app_key}", config.get("mensaje_usuario"))
        self.pm.regain_focus()
        return confirmed

    def _handle_uninstall(self, app_key, config):
        cmd_str = _expand_vars(config.get("uninstall_string"), self.custom_variables)
        if not cmd_str: return False
        args = []; cmd = cmd_str.replace('"', '')
        if "unins000" in cmd.lower(): args = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
        elif "msiexec" in cmd.lower():
            match = re.search(r'\{([A-Fa-f0-9-]{36})\}', cmd, re.I)
            if match: cmd, args = "msiexec", ["/x", match.group(0), "/qn", "/norestart"]
        return self._run_command(cmd, args)
    
    def _handle_install_driver(self, app_key, config):
        driver_dir = config.get("driver_dir_name")
        if not driver_dir: return False
        driver_path = self.programas_dir / "Drivers" / driver_dir
        if not driver_path.is_dir(): return False
        self._safe_ui_update(app_key, phase='install', text="Instalando drivers...")
        return self._run_command("pnputil", ["/add-driver", str(driver_path / "*.inf"), "/install"])

    # --- INICIO DEL CÓDIGO CORREGIDO ---
    def _run_command(self, command, args=None, wait=True, timeout=600):
        try:
            cmd_str = str(_expand_vars(command, self.custom_variables))
            args = [_expand_vars(a, self.custom_variables) for a in (args or [])]
            
            # Lógica corregida para manejar .msi
            if cmd_str.lower().endswith('.msi'):
                full_cmd = ["msiexec", "/i", cmd_str] + args
            else:
                full_cmd = [cmd_str] + args

            self._log(f"Ejecutando: {' '.join(full_cmd)}")

            proc = subprocess.Popen(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
            if not wait: return True 

            stdout, stderr = proc.communicate(timeout=timeout)
            if stdout: self._log(f"Salida de '{Path(command).name}':\n{stdout.strip()}")
            if stderr: self._log(f"Errores de '{Path(command).name}':\n{stderr.strip()}", level="ERROR")
            self._log(f"Comando finalizado con código: {proc.returncode}")
            return proc.returncode in [0, 3010]
        except Exception as e:
            self._log(f"Error crítico ejecutando '{Path(command).name}': {e}", "ERROR")
            return False
    # --- FIN DEL CÓDIGO CORREGIDO ---

    def _show_results_log(self):
        log_win = tk.Toplevel(self.root); log_win.title("Resultados"); log_win.geometry("600x400"); log_win.transient(self.root); log_win.grab_set()
        text = tk.Text(log_win, wrap="word", font=("Segoe UI", 10), padx=10, pady=10)
        text.pack(expand=True, fill="both"); text.tag_configure("success", foreground="green"); text.tag_configure("fail", foreground="red")
        for res in sorted(self.results.values()): text.insert(tk.END, res + "\n", "success" if "✅" in res else "fail")
        text.config(state="disabled"); ttk.Button(log_win, text="Cerrar", command=log_win.destroy).pack(pady=10)
    
    def _handle_copy_interactive(self, app_key, config):
        filename = config.get("selected_filename");
        if not filename: return False
        src = self.programas_dir / app_key / filename
        if not src.exists(): messagebox.showerror("Error", f"Archivo no encontrado:\n{src}"); return False
        
        self.pm.release_focus(); dest_str = filedialog.asksaveasfilename(title=f"Guardar '{filename}'", initialfile=filename); self.pm.regain_focus()
        if not dest_str: return False
        try:
            dest = Path(_expand_vars(dest_str, self.custom_variables)); dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest); self._log(f"Archivo copiado a '{dest}'"); return True
        except Exception as e: messagebox.showerror("Error", f"No se pudo copiar:\n{e}"); return False

    def _handle_power_config(self, app_key, config):
        cmds = [["powercfg", "/change", opt, "0"] for opt in ["monitor-timeout-ac", "standby-timeout-ac", "hibernate-timeout-ac", "monitor-timeout-dc", "standby-timeout-dc", "hibernate-timeout-dc"]]
        try:
            all_ok = True
            for i, cmd in enumerate(cmds):
                if not self._run_command(cmd[0], cmd[1:]): all_ok = False
                self._safe_ui_update(app_key, progress=int(((i+1)/len(cmds))*100))
            if all_ok: self._log("Plan de energía configurado."); return True
            return False
        except Exception as e: self._log(f"Error al configurar energía: {e}", "ERROR"); return False
            
    def _handle_clean_temp(self, app_key, config):
        temp_folders = [os.environ.get(v) for v in ('TEMP', 'TMP') if os.environ.get(v)] + [r'C:\Windows\Temp']
        count = 0; size = 0
        for folder in temp_folders:
            p = Path(_expand_vars(folder)); 
            if not p.is_dir(): continue
            for item in p.glob('*'):
                try:
                    if item.is_file(): size+=item.stat().st_size; item.unlink(missing_ok=True); count+=1
                    elif item.is_dir(): size+=sum(f.stat().st_size for f in item.rglob('*')); shutil.rmtree(item, ignore_errors=True); count+=1
                except (OSError, PermissionError) as e: self._log(f"No se pudo eliminar '{item}': {e}", "WARNING")
        self._log(f"Limpieza completada. {count} elementos ({size/1024**2:.2f}MB) eliminados.", "SUCCESS"); return True
    
    def _handle_run_powershell(self, app_key, config):
        script = config.get("script_path")
        if not script: self._log("Error: No se definió 'script_path'.", "ERROR"); return False
        script_path = self.programas_dir / app_key / script
        if not script_path.exists(): self._log(f"Error: No se encontró script '{script_path}'.", "ERROR"); return False
        return self._run_command("powershell.exe", ["-ExecutionPolicy", "Bypass", "-File", str(script_path)])

    def _handle_unimplemented(self, app_key, config): self._log(f"Tarea '{config.get('tipo')}' no implementada."); return True

    def _script_copy_lsplayer_shortcut(self):
        s_name = "LSPlayerVideo.lnk"; startup = Path(_expand_vars("%PROGRAMDATA%")) / "Microsoft/Windows/Start Menu/Programs/Startup"
        src = next((p / s_name for p in [Path.home()/"Desktop", Path(_expand_vars("%PUBLIC%"))/"Desktop"] if (p/s_name).exists()), None)
        if src:
            try: shutil.copy2(src, startup); self._log(f"Acceso directo copiado a {startup}"); return True
            except Exception as e: self._log(f"Error copiando acceso directo: {e}", "ERROR"); return False
        self._log(f"No se encontró el acceso directo '{s_name}' en el escritorio.", "WARNING")
        return True