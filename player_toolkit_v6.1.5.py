# --- START OF FILE main.py ---

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

# Importaciones desde la librería local
from toolkit_lib.config import *
# MODIFICADO: Se importa la constante de versión desde ui
from toolkit_lib.ui import PlayerToolkitApp, NewAppConfigDialog, APP_VERSION
from toolkit_lib.utils import is_admin, scan_installed_software

def get_base_path():
    """
    Obtiene la ruta base correcta tanto para el modo script como para
    el ejecutable empaquetado por PyInstaller (--onedir y --onefile).
    """
    if getattr(sys, 'frozen', False):
        # Si está empaquetado, la base es el directorio temporal _MEIPASS
        # donde PyInstaller extrae todos los datos.
        return Path(sys._MEIPASS)
    # Si es un script normal, es el directorio del archivo.
    return Path(__file__).parent

BASE_DIR = get_base_path()
# Al ejecutar el .exe, los directorios Programas, logs y conf estarán
# junto al .exe, no dentro del _MEIPASS. Por eso usamos una ruta diferente.
APP_ROOT_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else get_base_path()
PROGRAMAS_DIR = APP_ROOT_DIR / "Programas"
LOGS_DIR = APP_ROOT_DIR / "logs"
CONF_DIR = APP_ROOT_DIR / "conf"

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
    # Importación local para asegurar que la función de adivinación está disponible
    from toolkit_lib.config import build_app_configurations as builder, guess_initial_config

    # 1. Construir configuración inicial
    base_configs, new_apps_discovered = builder(PROGRAMAS_DIR, CONF_DIR)

    # 2. Si se descubren nuevas apps, preguntar al usuario
    if new_apps_discovered:
        if messagebox.askyesno("Nuevas Aplicaciones Encontradas", f"Se encontraron {len(new_apps_discovered)} carpetas de aplicaciones no configuradas.\n" "¿Deseas configurarlas ahora?"):

            custom_config_file = CONF_DIR / "config_personalizada.json"
            current_custom_config = {}
            if custom_config_file.exists():
                with open(custom_config_file, 'r', encoding='utf-8') as f:
                    current_custom_config = json.load(f)

            for app_name in new_apps_discovered:
                app_path = PROGRAMAS_DIR / app_name
                # Adivinar la configuración inicial basándose en el contenido de la carpeta
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
    scan_results = {}
    installed_software_raw = scan_installed_software()

    app_keys = list(app_configs.keys())
    total_apps = len(app_keys)
    if total_apps == 0:
        root.after(100, lambda: launch_main_application(root, loading_window, scan_results, app_configs, installed_software_raw))
        return

    for i, app_key in enumerate(app_keys):
        progress = (i + 1) * 100 / total_apps
        status = f"Escaneando: {app_key}..."
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

    root.after(100, lambda: launch_main_application(root, loading_window, scan_results, app_configs, installed_software_raw))

def launch_main_application(root, loading_window, scan_results, app_configs, installed_software):
    """Inicia la ventana principal de la aplicación."""
    loading_window.destroy()
    PlayerToolkitApp(root, scan_results, app_configs, installed_software)
    root.deiconify()
    root.eval('tk::PlaceWindow . center')

def main():
    """Punto de entrada principal de la aplicación."""
    setup_logging()
    # MODIFICADO: Usar la constante de versión
    logging.info(f"--- Iniciando PlayerToolkit {APP_VERSION} ---")

    # Modo GUI únicamente
    PROGRAMAS_DIR.mkdir(exist_ok=True)
    CONF_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)

    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()

    # Importación necesaria para Drag & Drop
    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD # type: ignore
        root = TkinterDnD.Tk()
    except ImportError:
        logging.error("tkinterdnd2 no encontrado. La función de arrastrar y soltar estará deshabilitada.")
        messagebox.showwarning("Dependencia Faltante", "La librería 'tkinterdnd2-universal' no está instalada.\n\npip install tkinterdnd2-universal\n\nLa función de arrastrar y soltar no funcionará.")
        root = tk.Tk()

    root.withdraw()
    sv_ttk.set_theme("dark")

    loading_window = tk.Toplevel(root)
    loading_window.title("Cargando PlayerToolkit...")
    loading_window.geometry("400x120")
    loading_window.resizable(False, False)
    loading_window.transient(root)
    loading_window.protocol("WM_DELETE_WINDOW", lambda: None)
    loading_window.grab_set()
    root.eval(f'tk::PlaceWindow {str(loading_window)} center')

    loading_frame = ttk.Frame(loading_window, padding="15")
    loading_frame.pack(expand=True, fill=tk.BOTH)
    status_label = ttk.Label(loading_frame, text="Cargando configuración...", font=("Segoe UI", 10))
    status_label.pack(pady=(0, 5), fill="x")
    progress_bar = ttk.Progressbar(loading_window, mode="determinate")
    progress_bar.pack(pady=5, fill="x", ipady=4)

    # El escaneo de configuración ahora requiere el `root` para los diálogos
    final_app_configs = build_app_configurations_with_discovery(root)

    threading.Thread(target=initial_scan, args=(root, loading_window, progress_bar, status_label, final_app_configs), daemon=True).start()

    root.mainloop()
    logging.info("--- PlayerToolkit cerrado ---")

if __name__ == "__main__":
    main()