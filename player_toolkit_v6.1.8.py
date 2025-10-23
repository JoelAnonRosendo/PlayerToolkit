# --- START OF FILE player_toolkit_v6.1.8.py ---

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import logging
from logging.handlers import RotatingFileHandler
import sys
import os
import ctypes
from pathlib import Path
import sv_ttk # type: ignore
import json
import traceback
from datetime import datetime

# Importaciones desde la librería local reestructurada
from toolkit_lib.config import *
from toolkit_lib.ui.main_app import PlayerToolkitApp
from toolkit_lib.ui.dialogs import NewAppConfigDialog
from toolkit_lib.utils import is_admin, scan_installed_software, load_cached_scan, save_cached_scan, get_programas_dir_hash

def get_base_path():
    """
    Obtiene la ruta base correcta tanto para el modo script como para
    el ejecutable empaquetado por PyInstaller (--onedir y --onefile).
    """
    if getattr(sys, 'frozen', False):
        # Para ejecutables de PyInstaller
        return Path(sys.executable).parent
    # Para ejecución como script
    return Path(__file__).parent

APP_ROOT_DIR = get_base_path()
PROGRAMAS_DIR = APP_ROOT_DIR / "Programas"
LOGS_DIR = APP_ROOT_DIR / "logs"
CONF_DIR = APP_ROOT_DIR / "conf"

# MODIFICADO: Sacamos APP_VERSION de ui.py y lo ponemos en main_app.py
# El main no necesita saber la versión directamente.

def setup_logging():
    """Configura el logging para que escriba en un archivo en la carpeta logs."""
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / "PlayerToolkit.log"

    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=2, encoding='utf-8')
    file_handler.setFormatter(log_formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)

def build_app_configurations_with_discovery(root):
    """
    Construye la configuración y maneja el descubrimiento de nuevas apps
    mostrando diálogos al usuario si es necesario.
    """
    from toolkit_lib.config import build_app_configurations as builder, guess_initial_config

    base_configs, new_apps_discovered = builder(PROGRAMAS_DIR, CONF_DIR)

    if new_apps_discovered:
        if messagebox.askyesno("Nuevas Aplicaciones Encontradas", f"Se encontraron {len(new_apps_discovered)} carpetas de aplicaciones no configuradas.\n" "¿Deseas configurarlas ahora?"):

            custom_config_file = CONF_DIR / "config_personalizada.json"
            current_custom_config = {}
            if custom_config_file.exists():
                with open(custom_config_file, 'r', encoding='utf-8') as f:
                    try:
                        current_custom_config = json.load(f)
                    except json.JSONDecodeError:
                        pass # Si está corrupto, lo sobreescribimos

            for app_name in new_apps_discovered:
                app_path = PROGRAMAS_DIR / app_name
                guessed_config = guess_initial_config(app_path)

                dialog = NewAppConfigDialog(root, f"Configurar: {app_name}", app_name, initial_config=guessed_config)
                if dialog.result:
                    base_configs[app_name] = dialog.result
                    current_custom_config[app_name] = dialog.result

            try:
                with open(custom_config_file, 'w', encoding='utf-8') as f:
                    json.dump(current_custom_config, f, indent=4, ensure_ascii=False)
                messagebox.showinfo("Guardado",
                                    "La configuración para las nuevas aplicaciones se ha guardado en 'config_personalizada.json'.",
                                    parent=root)
            except IOError as e:
                messagebox.showerror("Error al Guardar", f"No se pudo escribir el archivo de configuración:\n{e}", parent=root)

    return base_configs

def initial_scan(root, loading_window, progress_bar, status_label, app_configs):
    """Realiza el escaneo inicial de archivos e instalaciones del sistema."""
    status_label.config(text="Escaneando software instalado...")
    root.update_idletasks()
    installed_software_raw = scan_installed_software()
    
    scan_results = {}
    app_keys = list(app_configs.keys())
    total_apps = len(app_keys)
    if total_apps == 0:
        save_cached_scan(installed_software_raw, scan_results, get_programas_dir_hash(PROGRAMAS_DIR))
        root.after(100, lambda: launch_main_application(root, loading_window, scan_results, app_configs, installed_software_raw))
        return

    for i, app_key in enumerate(app_keys):
        progress = (i + 1) * 100 / total_apps
        status = f"Escaneando archivos: {app_key}..."
        root.after(0, lambda p=progress, s=status: (progress_bar.config(value=p), status_label.config(text=s)))

        config = app_configs[app_key]
        task_type = config.get('tipo')
        app_dir = PROGRAMAS_DIR / app_key

        if task_type in [TASK_TYPE_LOCAL_INSTALL, TASK_TYPE_MANUAL_ASSISTED]:
            if not app_dir.is_dir():
                scan_results[app_key] = [STATUS_FOLDER_NOT_FOUND]
            else:
                found = [f.name for ext in INSTALLER_EXTENSIONS for f in app_dir.glob(f"*{ext}")]
                scan_results[app_key] = found if found else []
        elif task_type == TASK_TYPE_COPY_INTERACTIVE:
            if not app_dir.is_dir():
                scan_results[app_key] = [STATUS_FOLDER_NOT_FOUND]
            else:
                found = [f.name for f in app_dir.iterdir() if f.is_file()]
                scan_results[app_key] = found if found else [STATUS_NO_FILES_FOUND]
        else:
            scan_results[app_key] = []
        time.sleep(0.01)

    save_cached_scan(installed_software_raw, scan_results, get_programas_dir_hash(PROGRAMAS_DIR))
    root.after(100, lambda: launch_main_application(root, loading_window, scan_results, app_configs, installed_software_raw))

def launch_main_application(root, loading_window, scan_results, app_configs, installed_software):
    """Inicia la ventana principal de la aplicación."""
    if loading_window:
        loading_window.destroy()
    PlayerToolkitApp(root, scan_results, app_configs, installed_software)
    root.deiconify()
    root.eval('tk::PlaceWindow . center')

def main():
    """Punto de entrada principal de la aplicación."""
    # En PyInstaller, el logging se configura solo si no es el lanzador
    is_pyinstaller_launcher = "_PYINSTALLER_LAUNCHER_" in os.environ
    if not is_pyinstaller_launcher:
        setup_logging()
        # El log de inicio se moverá a dentro de PlayerToolkitApp para acceso a la versión
    
    PROGRAMAS_DIR.mkdir(exist_ok=True)
    CONF_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)

    if not is_admin():
        try:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        except Exception as e:
            messagebox.showerror("Error de Privilegios", f"No se pudo re-lanzar la aplicación como administrador.\n\nError: {e}")
        sys.exit(0)

    try:
        from tkinterdnd2 import TkinterDnD # type: ignore
        root = TkinterDnD.Tk()
    except ImportError:
        logging.error("tkinterdnd2 no encontrado. La función de arrastrar y soltar estará deshabilitada.")
        root = tk.Tk()

    root.withdraw()
    sv_ttk.set_theme("dark")

    cached_data = load_cached_scan()
    current_hash = get_programas_dir_hash(PROGRAMAS_DIR)
    
    final_app_configs = build_app_configurations_with_discovery(root)

    if cached_data and cached_data.get("hash") == current_hash:
        logging.info("Cargando datos desde caché.")
        launch_main_application(root, None, cached_data["scan_results"], final_app_configs, cached_data["installed_software"])
    else:
        logging.info("Caché no encontrado o inválido. Realizando escaneo completo.")
        loading_window = tk.Toplevel(root)
        loading_window.title("Cargando PlayerToolkit...")
        loading_window.geometry("400x120")
        loading_window.resizable(False, False)
        loading_window.transient(root)
        loading_window.protocol("WM_DELETE_WINDOW", lambda: None) # Evitar cerrar
        loading_window.grab_set()
        root.eval(f'tk::PlaceWindow {str(loading_window)} center')

        loading_frame = ttk.Frame(loading_window, padding="15")
        loading_frame.pack(expand=True, fill=tk.BOTH)
        status_label = ttk.Label(loading_frame, text="Cargando configuración...", font=("Segoe UI", 10))
        status_label.pack(pady=(0, 5), fill="x")
        progress_bar = ttk.Progressbar(loading_window, mode="determinate")
        progress_bar.pack(pady=5, fill="x", ipady=4)
        
        scan_thread = threading.Thread(target=initial_scan, args=(root, loading_window, progress_bar, status_label, final_app_configs), daemon=True)
        scan_thread.start()

    root.mainloop()
    logging.info("--- PlayerToolkit cerrado ---")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Log de errores fatales de arranque
        error_log_path = APP_ROOT_DIR / "startup_error.log"
        error_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(error_log_path, "a", encoding="utf-8") as f:
            f.write(f"--- ERROR FATAL en {error_time} ---\n")
            f.write(traceback.format_exc())
            f.write("\n\n")
        traceback.print_exc()
        messagebox.showerror("Error Crítico", f"Ha ocurrido un error fatal al iniciar la aplicación.\n\nConsulte el archivo 'startup_error.log' para más detalles.\n\n{e}")
        sys.exit(1)