# --- START OF FILE toolkit_lib/utils.py ---

import winreg
import ctypes
import logging
from datetime import datetime
# NUEVO: Importaciones para caché
import json
from pathlib import Path
import hashlib
import os

# NUEVO: Constante para el archivo de caché
CACHE_FILE = Path(os.getenv("APPDATA")) / "PlayerToolkit" / "scan_cache.json"

def is_admin():
    """Verifica si el script se está ejecutando con privilegios de administrador."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def scan_installed_software():
    """
    Escanea el registro de Windows para obtener una lista de software instalado.
    """
    installed_software = {}
    uninstall_paths = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
    ]

    for path in uninstall_paths:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    sub_key_name = winreg.EnumKey(key, i)
                    try:
                        with winreg.OpenKey(key, sub_key_name) as sub_key:
                            display_name = winreg.QueryValueEx(sub_key, "DisplayName")[0]
                            
                            if not display_name or display_name.startswith("KB") or "Microsoft Visual C++" in display_name:
                                continue

                            uninstall_string = ""
                            try:
                                uninstall_string = winreg.QueryValueEx(sub_key, "UninstallString")[0]
                            except OSError:
                                continue # Imprescindible para desinstalar

                            version = ""
                            try: version = winreg.QueryValueEx(sub_key, "DisplayVersion")[0]
                            except OSError: pass

                            install_date_str = ""
                            try:
                                date_val = winreg.QueryValueEx(sub_key, "InstallDate")[0]
                                install_date_str = datetime.strptime(date_val, "%Y%m%d").strftime("%d-%m-%Y")
                            except (OSError, ValueError): pass
                            
                            installed_software[display_name] = {
                                "uninstall_string": uninstall_string, "version": version, "install_date": install_date_str
                            }
                    except OSError:
                        continue
        except FileNotFoundError:
            logging.warning(f"Ruta del registro no encontrada: {path}")
            continue

    return installed_software

# NUEVO: Funciones de caché
def get_programas_dir_hash(programas_dir: Path):
    """Genera un hash basado en los nombres y tamaños de los directorios de primer nivel."""
    if not programas_dir.is_dir():
        return ""
    
    hasher = hashlib.md5()
    # Ordenar para consistencia
    for item in sorted(programas_dir.iterdir(), key=lambda p: p.name):
        if item.is_dir():
            # Usar el nombre y el número de elementos para una detección simple de cambios
            content_signature = f"{item.name}:{len(list(item.iterdir()))}"
            hasher.update(content_signature.encode('utf-8'))
            
    return hasher.hexdigest()

def load_cached_scan():
    """Carga los resultados del escaneo desde un archivo de caché."""
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return None

def save_cached_scan(installed_software, scan_results, dir_hash):
    """Guarda los resultados del escaneo en un archivo de caché."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    cache_data = {
        "timestamp": datetime.now().isoformat(),
        "hash": dir_hash,
        "installed_software": installed_software,
        "scan_results": scan_results
    }
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2)
    except IOError as e:
        logging.error(f"No se pudo guardar el archivo de caché: {e}")

def clear_cache():
    """Elimina el archivo de caché."""
    try:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
            return True
    except OSError as e:
        logging.error(f"Error al eliminar el caché: {e}")
    return False