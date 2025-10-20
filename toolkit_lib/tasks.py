# --- START OF FILE toolkit_lib/tasks.py ---

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import subprocess
import threading
import time
import logging
import shutil
import requests # type: ignore
from pathlib import Path
import re
import winreg
from queue import Queue

# Importaciones relativas
from .config import *

def _expand_vars(value):
    """Expande variables de entorno en un string."""
    if isinstance(value, str):
        return os.path.expandvars(value)
    return value

class ProgressManager:
    def __init__(self, root_gui):
        self.root = root_gui
        self.window = None
        self.bar = None
        self.label_status = None
        self.label_percentage = None

    def create(self):
        if self.window and self.window.winfo_exists(): return
        self.window = tk.Toplevel(self.root)
        self.window.title("Procesando Tareas...")
        self.window.geometry("450x150")
        self.window.resizable(False, False)
        self.window.transient(self.root)
        self.window.protocol("WM_DELETE_WINDOW", lambda: None)
        self.window.grab_set()
        frame = ttk.Frame(self.window, padding="15")
        frame.pack(expand=True, fill=tk.BOTH)
        self.label_status = ttk.Label(frame, text="Iniciando...", font=("Segoe UI", 10), wraplength=400)
        self.label_status.pack(pady=(0, 10), fill="x")
        self.bar = ttk.Progressbar(frame, mode="determinate")
        self.bar.pack(pady=10, fill="x", ipady=4)
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
    def __init__(self, root_gui, app_configs, selected_apps, extra_options, programas_dir, log_queue: Queue, completion_callback=None):
        self.root = root_gui
        self.app_configs = app_configs
        self.selected_apps = selected_apps
        self.extra_options = extra_options
        self.programas_dir = programas_dir
        self.pm = ProgressManager(self.root)
        self.results = []
        self.log_queue = log_queue
        self.completion_callback = completion_callback

    def _log(self, message):
        """Envía un mensaje tanto al logger del archivo como a la cola de la UI."""
        logging.info(message)
        self.log_queue.put(message)

    def run(self):
        self.pm.create()
        total_tasks = len(self.selected_apps)
        
        manual_tasks = [k for k in self.selected_apps if self.app_configs.get(k, {}).get("tipo") == "instalar_manual_asistido"]
        auto_tasks = [k for k in self.selected_apps if k not in manual_tasks]
        sorted_tasks = manual_tasks + auto_tasks
        
        for i, app_key in enumerate(sorted_tasks):
            progress = (i / total_tasks) * 100
            status_msg = f"Procesando {i+1}/{total_tasks}: {app_key}"
            self.pm.update(barra=progress, status=status_msg, porcentaje=f"{int(progress)}%")
            self._log(f"--- Iniciando tarea: {app_key} ---")
            self._execute_task(app_key)
            self._log(f"--- Tarea finalizada: {app_key} ---")

        # FUTURO: Ejecución de Tareas en Paralelo
        # La implementación actual es secuencial. Para mejorar la velocidad, especialmente
        # con tareas de red (descargas) o I/O, se podría usar un ThreadPoolExecutor.
        #
        # Pasos para una implementación paralela:
        # 1. Sistema de Dependencias: Primero, se necesitaría añadir una clave "dependencias"
        #    en la configuración de cada app (ej. "dependencias": ["Java"]).
        # 2. Grafo de Tareas: Construir un grafo dirigido con las tareas como nodos y las
        #    dependencias como aristas.
        # 3. Ordenamiento Topológico: Usar un algoritmo de ordenamiento topológico (como el de
        #    la librería `toposort`) para obtener lotes de tareas que pueden ejecutarse
        #    en paralelo. Por ejemplo, todas las tareas sin dependencias pueden correr a la vez.
        # 4. ThreadPoolExecutor: Usar `concurrent.futures.ThreadPoolExecutor` para gestionar
        #    un pool de hilos de trabajo.
        # 5. Ejecución por Lotes: Enviar cada lote de tareas paralelas al executor y esperar a
        #    que todas terminen (`executor.map` o `futures.wait`) antes de pasar al
        #    siguiente lote.
        # 6. Gestión de Estado: La comunicación con la UI (barra de progreso, logs) se volvería
        #    más compleja y requeriría un uso cuidadoso de locks o colas para evitar
        #    condiciones de carrera al actualizar el estado compartido.
        #
        # Ejemplo conceptual:
        #
        # from concurrent.futures import ThreadPoolExecutor, as_completed
        #
        # ...
        # batches = toposort(dependency_graph)
        # with ThreadPoolExecutor(max_workers=4) as executor:
        #     for batch in batches:
        #         futures = {executor.submit(self._execute_task, task_key): task_key for task_key in batch}
        #         for future in as_completed(futures):
        #             task_key = futures[future]
        #             try:
        #                 result = future.result()
        #                 # Procesar resultado
        #             except Exception as exc:
        #                 # Manejar error
        
        self.pm.destroy()
        self._show_results_log()

        if self.completion_callback:
            self.root.after(100, self.completion_callback)

    def _execute_task(self, app_key):
        config = self.app_configs.get(app_key, {}).copy()
        if app_key in self.extra_options: config.update(self.extra_options[app_key])
        
        handler = self._get_task_handler(config.get("tipo"))
        if not handler:
            msg = f"⚠️ '{app_key}': Omitido (tipo de tarea desconocido)"
            self.results.append(msg)
            self._log(msg)
            return

        success = handler(app_key, config)
        
        if success and config.get("post_install_script"):
            self.root.after(0, lambda: self.pm.update(status=f"Ejecutando script post-instalación para {app_key}..."))
            self._log(f"Ejecutando script post-instalación para {app_key}...")
            script_handler = self._get_post_install_handler(config["post_install_script"])
            if script_handler:
                if not script_handler():
                    self.results.append(f"⚠️ '{app_key}': Script post-instalación falló.")
            else:
                self._log(f"Advertencia: No se encontró manejador para el script: {config['post_install_script']}")

        if success:
            self.results.append(f"✅ '{app_key}': Completado con éxito.")
        else:
            self.results.append(f"❌ '{app_key}': Falló o fue cancelado.")

    def _get_task_handler(self, task_type):
        return {
            "instalar_local": self._handle_local_install,
            "instalar_manual_asistido": self._handle_manual_assisted,
            "copiar_archivo_interactivo": self._handle_copy_interactive,
            "configurar_energia_actual": self._handle_power_config,
            TASK_TYPE_UNINSTALL: self._handle_uninstall,
            TASK_TYPE_CLEAN_TEMP: self._handle_clean_temp,
            TASK_TYPE_RUN_POWERSHELL: self._handle_run_powershell,
            TASK_TYPE_MODIFY_REGISTRY: self._handle_modify_registry,
            TASK_TYPE_MANAGE_SERVICE: self._handle_manage_service,
            TASK_TYPE_CREATE_SCHEDULED_TASK: self._handle_create_scheduled_task,
        }.get(task_type)

    def _get_post_install_handler(self, script_key):
        return {
            "copy_lsplayer_shortcut": self._script_copy_lsplayer_shortcut
        }.get(script_key)

    def _download_file(self, url, dest_path):
        try:
            self._log(f"Iniciando descarga desde {url} hacia {dest_path}")
            self.root.after(0, lambda: self.pm.update(status=f"Descargando: {dest_path.name}...", barra=0, porcentaje="0%"))
            with requests.get(url, stream=True, allow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'}) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0
                with open(dest_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            self.root.after(0, lambda p=progress: self.pm.update(barra=p, porcentaje=f"{int(p)}%"))
            self._log(f"Descarga completada con éxito.")
            return True
        except requests.RequestException as e:
            self._log(f"Error de descarga: {e}")
            messagebox.showerror("Error de Descarga", f"No se pudo descargar '{url}':\n{e}")
            return False

    def _prepare_installer(self, app_key, config):
        exe_filename = config.get("exe_filename")
        if not exe_filename:
            self._log(f"Error: No se encontró 'exe_filename' para '{app_key}'.")
            messagebox.showerror("Error Interno", f"No se encontró 'exe_filename' para '{app_key}'.")
            return None
            
        exe_path = self.programas_dir / app_key / exe_filename
        
        if not exe_path.exists():
            self._log(f"El instalador '{exe_path}' no existe localmente.")
            url = self.app_configs.get(app_key, {}).get("url")
            if url:
                exe_path.parent.mkdir(parents=True, exist_ok=True)
                if not self._download_file(url, exe_path):
                    return None
            else:
                self._log(f"Error: No hay URL de descarga configurada para '{app_key}'.")
                messagebox.showerror("Archivo no encontrado", f"El instalador '{exe_filename}' no se encontró y no hay URL de descarga configurada.")
                return None
        return exe_path

    def _handle_local_install(self, app_key, config):
        exe_path = self._prepare_installer(app_key, config)
        if not exe_path: return False
        
        self.root.after(0, lambda: self.pm.update(status=f"Instalando {app_key}..."))
        self._log(f"Iniciando instalación local para {app_key} desde {exe_path}")
        return self._run_command(exe_path, config.get("args_instalacion"), config.get("wait_for_completion"), config.get("timeout"))

    def _handle_manual_assisted(self, app_key, config):
        exe_path = self._prepare_installer(app_key, config)
        if not exe_path: return False
        
        self._log(f"Abriendo instalador para acción manual: {exe_path}")
        os.startfile(exe_path)
        self.root.after(0, lambda: self.pm.update(status=f"Esperando acción manual para {app_key}...", barra=50))
        self.pm.release_focus()
        confirmed = messagebox.askokcancel(f"Acción Manual Requerida: {app_key}", config["mensaje_usuario"])
        self.pm.regain_focus()
        self._log(f"Acción manual para {app_key} confirmada por el usuario: {'Sí' if confirmed else 'No'}")
        return confirmed

    def _handle_uninstall(self, app_key, config):
        uninstall_string = _expand_vars(config.get("uninstall_string"))
        if not uninstall_string: 
            self._log(f"Error: No hay 'uninstall_string' para {app_key}")
            return False
        
        self._log(f"Intentando desinstalar '{app_key}' con el comando: {uninstall_string}")
        args = []
        command = uninstall_string.replace('"', '')
        
        if "unins000" in command.lower():
            args = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
        elif "msiexec" in command.lower():
            match = re.search(r'\{([A-Fa-f0-9-]{36})\}', command, re.IGNORECASE)
            if match:
                product_code = match.group(0)
                command = "msiexec"
                args = ["/x", product_code, "/qn", "/norestart"]
            else:
                self._log(f"Advertencia: No se pudo extraer el ProductCode de: {uninstall_string}")
                parts = command.split()
                command = parts[0]
                args = parts[1:] + ["/qn"]
                
        self.root.after(0, lambda: self.pm.update(status=f"Desinstalando {app_key}..."))
        return self._run_command(command, args)

    def _run_command(self, command, args=None, wait=True, timeout=300):
        try:
            command_str = str(_expand_vars(command))
            args = [_expand_vars(arg) for arg in (args or [])]
            
            if "msiexec" in command_str.lower():
                full_cmd = [command_str] + args
            elif command_str.lower().endswith('.msi'):
                full_cmd = ["msiexec", "/i", command_str] + args
            else:
                full_cmd = [command_str] + args

            self._log(f"Ejecutando comando: {' '.join(full_cmd)}")
            
            proc = subprocess.Popen(full_cmd, creationflags=subprocess.CREATE_NO_WINDOW,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
            
            if wait:
                stdout, stderr = proc.communicate(timeout=timeout)
                if stdout: self._log(f"Salida del comando:\n{stdout}")
                if stderr: self._log(f"Error del comando:\n{stderr}")

                self._log(f"Comando finalizado con código de retorno: {proc.returncode}")
                is_success = proc.returncode in [0, 3010] # 3010 es reinicio necesario
                if not is_success:
                    self.results.append(f"El comando para '{Path(command).name}' finalizó con errores.")
                return is_success
            return True
        except Exception as e:
            self._log(f"Error crítico al ejecutar comando '{' '.join(full_cmd)}': {e}")
            messagebox.showerror("Error de Ejecución", f"No se pudo ejecutar el comando para '{Path(command).name}':\n{e}")
            return False

    def _show_results_log(self):
        log_window = tk.Toplevel(self.root)
        log_window.title("Resultados del Proceso")
        log_window.geometry("500x300")
        log_window.transient(self.root)
        log_window.grab_set()
        text_widget = tk.Text(log_window, wrap="word", font=("Segoe UI", 10), relief="flat", padx=10, pady=10)
        text_widget.pack(expand=True, fill="both")
        for result in self.results:
            text_widget.insert(tk.END, result + "\n")
        text_widget.config(state="disabled")
        ttk.Button(log_window, text="Cerrar", command=log_window.destroy).pack(pady=10)
    
    def _handle_copy_interactive(self, app_key, config):
        self.root.after(0, lambda: self.pm.update(status=f"Preparando para copiar archivo de '{app_key}'..."))
        origen_nombre = config.get("selected_filename")
        if not origen_nombre: return False
        ruta_origen = self.programas_dir / app_key / origen_nombre
        if not ruta_origen.exists():
            messagebox.showerror("Archivo no encontrado", f"El archivo de origen no fue encontrado:\n{ruta_origen}")
            return False
        self.pm.release_focus()
        ruta_destino_str = filedialog.asksaveasfilename(
            title=f"Selecciona dónde guardar '{origen_nombre}'", initialfile=origen_nombre,
            defaultextension=ruta_origen.suffix,
            filetypes=[(f"Archivos {ruta_origen.suffix.upper()}", f"*{ruta_origen.suffix}"), ("Todos los archivos", "*.*")]
        )
        self.pm.regain_focus()
        if not ruta_destino_str: return False
        try:
            ruta_destino = Path(_expand_vars(ruta_destino_str))
            ruta_destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ruta_origen, ruta_destino)
            self._log(f"Archivo '{origen_nombre}' copiado a '{ruta_destino}'")
            self.root.after(0, lambda: self.pm.update(status=f"Archivo '{origen_nombre}' copiado.", barra=100, porcentaje="Hecho ✓"))
            time.sleep(1)
            return True
        except Exception as e:
            self._log(f"Error al copiar archivo: {e}")
            messagebox.showerror("Error de Copia", f"No se pudo copiar el archivo a:\n{ruta_destino}\n\nError: {e}")
            return False

    def _handle_power_config(self, app_key, config):
        self._log("Configurando plan de energía a 'Nunca Apagar'.")
        self.root.after(0, lambda: self.pm.update(status=f"Configurando plan de energía a 'Nunca Apagar'..."))
        commands = [
            ["powercfg", "/change", "monitor-timeout-ac", "0"], ["powercfg", "/change", "standby-timeout-ac", "0"],
            ["powercfg", "/change", "hibernate-timeout-ac", "0"], ["powercfg", "/change", "monitor-timeout-dc", "0"],
            ["powercfg", "/change", "standby-timeout-dc", "0"], ["powercfg", "/change", "hibernate-timeout-dc", "0"],
        ]
        try:
            for cmd in commands:
                self._run_command(cmd[0], cmd[1:])
            self._log("Plan de energía configurado con éxito.")
            self.root.after(0, lambda: self.pm.update(status="Plan de energía configurado.", barra=100, porcentaje="Hecho ✓"))
            time.sleep(1.5)
            return True
        except Exception as e:
            self._log(f"Error al configurar la energía: {e}")
            messagebox.showerror("Error de Configuración", f"No se pudo configurar la energía:\n{e}")
            return False
            
    def _handle_clean_temp(self, app_key, config):
        self._log("Iniciando limpieza de archivos temporales.")
        self.root.after(0, lambda: self.pm.update(status="Limpiando archivos temporales..."))
        temp_folders = [os.environ.get('TEMP'), os.environ.get('TMP'), r'C:\Windows\Temp']
        deleted_files_count = 0
        deleted_size = 0

        for folder in filter(None, temp_folders):
            folder_path = Path(_expand_vars(folder))
            if not folder_path.is_dir(): continue
            
            self._log(f"Limpiando carpeta: {folder_path}")
            for item in folder_path.glob('*'):
                try:
                    if item.is_file() or item.is_symlink():
                        file_size = item.stat().st_size
                        item.unlink()
                        deleted_files_count += 1
                        deleted_size += file_size
                    elif item.is_dir():
                        dir_size = sum(f.stat().st_size for f in item.rglob('*'))
                        shutil.rmtree(item, ignore_errors=True)
                        deleted_files_count += 1 # Cuenta la carpeta como un item
                        deleted_size += dir_size
                except (OSError, PermissionError) as e:
                    self._log(f"No se pudo eliminar '{item}': {e}")
                    continue
        
        size_mb = deleted_size / (1024 * 1024)
        result_msg = f"Limpieza completada. {deleted_files_count} elementos eliminados ({size_mb:.2f} MB liberados)."
        self._log(result_msg)
        self.root.after(0, lambda: self.pm.update(status=result_msg))
        time.sleep(2.5)
        return True
    
    def _handle_run_powershell(self, app_key, config):
        script_name = config.get("script_path")
        if not script_name:
            self._log(f"Error en '{app_key}': no se especificó 'script_path'.")
            return False
        
        script_path = self.programas_dir / app_key / script_name
        if not script_path.exists():
            self._log(f"Error: No se encontró el script de PowerShell: {script_path}")
            return False
            
        self._log(f"Ejecutando script de PowerShell: {script_path}")
        command = "powershell.exe"
        args = ["-ExecutionPolicy", "Bypass", "-File", str(script_path)]
        return self._run_command(command, args)

    def _handle_modify_registry(self, app_key, config):
        reg_path = _expand_vars(config.get("reg_path"))
        key_name = _expand_vars(config.get("reg_key"))
        key_value = _expand_vars(config.get("reg_value"))
        key_type_str = config.get("reg_type", "REG_SZ")

        if not all([reg_path, key_name]):
            self._log(f"Error en '{app_key}': 'reg_path' y 'reg_key' son obligatorios.")
            return False

        hive_str, subkey_path = reg_path.split('\\', 1)
        hives = {
            "HKEY_CLASSES_ROOT": winreg.HKEY_CLASSES_ROOT,
            "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
            "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
            "HKEY_USERS": winreg.HKEY_USERS,
        }
        hive = hives.get(hive_str.upper())
        if not hive:
            self._log(f"Error: Hive de registro no válido: {hive_str}")
            return False

        reg_types = {
            "REG_SZ": winreg.REG_SZ,
            "REG_EXPAND_SZ": winreg.REG_EXPAND_SZ,
            "REG_DWORD": winreg.REG_DWORD,
            "REG_QWORD": winreg.REG_QWORD,
            "REG_BINARY": winreg.REG_BINARY,
            "REG_MULTI_SZ": winreg.REG_MULTI_SZ,
        }
        reg_type = reg_types.get(key_type_str.upper())
        if reg_type is None:
            self._log(f"Error: Tipo de registro no válido: {key_type_str}")
            return False

        try:
            self._log(f"Modificando registro: Estableciendo '{reg_path}\\{key_name}' en '{key_value}'")
            with winreg.CreateKey(hive, subkey_path) as key:
                winreg.SetValueEx(key, key_name, 0, reg_type, key_value)
            return True
        except Exception as e:
            self._log(f"Error al modificar el registro: {e}")
            return False
            
    def _handle_manage_service(self, app_key, config):
        service_name = config.get("service_name")
        action = config.get("service_action", "start").lower()

        if not service_name:
            self._log(f"Error en '{app_key}': 'service_name' es obligatorio.")
            return False

        commands = {
            "start": ["start", service_name],
            "stop": ["stop", service_name],
            "disable": ["config", service_name, "start=", "disabled"],
            "enable": ["config", service_name, "start=", "auto"], # o demand
        }
        
        if action not in commands:
            self._log(f"Error: Acción de servicio no válida '{action}'. Válidas: start, stop, disable, enable.")
            return False
            
        self._log(f"Gestionando servicio '{service_name}', acción: {action}")
        return self._run_command("sc.exe", commands[action])

    def _handle_create_scheduled_task(self, app_key, config):
        task_name = config.get("task_name")
        task_command = _expand_vars(config.get("task_command"))
        trigger = config.get("task_trigger", "ONLOGON").upper()
        user = config.get("task_user", "SYSTEM")

        if not all([task_name, task_command]):
            self._log(f"Error en '{app_key}': 'task_name' y 'task_command' son obligatorios.")
            return False
            
        self._log(f"Creando tarea programada '{task_name}' para ejecutar '{task_command}' en '{trigger}'")
        args = ["/Create", "/TN", task_name, "/TR", task_command, "/SC", trigger, "/RU", user, "/F"]
        
        return self._run_command("schtasks.exe", args)

    def _script_copy_lsplayer_shortcut(self):
        shortcut_name = "LSPlayerVideo.lnk"
        startup_folder = Path(_expand_vars("%PROGRAMDATA%")) / "Microsoft/Windows/Start Menu/Programs/Startup"
        
        user_desktop = Path.home() / "Desktop"
        public_desktop = Path(_expand_vars("%PUBLIC%")) / "Desktop"
        
        source_shortcut = None
        if (user_desktop / shortcut_name).exists():
            source_shortcut = user_desktop / shortcut_name
        elif (public_desktop / shortcut_name).exists():
            source_shortcut = public_desktop / shortcut_name
        
        if source_shortcut:
            try:
                shutil.copy2(source_shortcut, startup_folder)
                self._log(f"Acceso directo '{shortcut_name}' copiado a la carpeta de Inicio.")
                return True
            except (IOError, shutil.Error) as e:
                self._log(f"No se pudo copiar el acceso directo: {e}")
                return False
        else:
            self._log(f"Advertencia: No se encontró el acceso directo '{shortcut_name}' en ningún escritorio.")
            return True