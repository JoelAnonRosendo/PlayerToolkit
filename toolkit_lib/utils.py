# --- START OF FILE toolkit_lib/utils.py ---

import winreg
import ctypes
import logging
from datetime import datetime
import json
from pathlib import Path
import hashlib
import os
from .config import DRIVER_EXTENSIONS

CACHE_FILE = Path(os.getenv("APPDATA")) / "PlayerToolkit" / "scan_cache.json"

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def scan_installed_software():
    installed_software = {}
    uninstall_paths = [r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"]
    for path in uninstall_paths:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        sub_key_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, sub_key_name) as sub_key:
                            display_name = str(winreg.QueryValueEx(sub_key, "DisplayName")[0])
                            if not display_name or display_name.startswith("KB") or "Microsoft Visual C++" in display_name: continue
                            uninstall_string = str(winreg.QueryValueEx(sub_key, "UninstallString")[0])
                            version = str(winreg.QueryValueEx(sub_key, "DisplayVersion")[0]) if "DisplayVersion" in [winreg.EnumValue(sub_key,i)[0] for i in range(winreg.QueryInfoKey(sub_key)[1])] else ""
                            date_str = datetime.strptime(str(winreg.QueryValueEx(sub_key, "InstallDate")[0]), "%Y%m%d").strftime("%d-%m-%Y") if "InstallDate" in [winreg.EnumValue(sub_key,i)[0] for i in range(winreg.QueryInfoKey(sub_key)[1])] else ""
                            installed_software[display_name] = {"uninstall_string": uninstall_string, "version": version, "install_date": date_str}
                    except (OSError, FileNotFoundError, IndexError): continue
        except FileNotFoundError: continue
    return installed_software

def scan_drivers(drivers_base_dir: Path):
    """Escanea la carpeta de drivers y devuelve un diccionario de paquetes de drivers encontrados."""
    found_drivers = {}
    if not drivers_base_dir.is_dir(): return found_drivers
    for item in drivers_base_dir.iterdir():
        if item.is_dir():
            if any(item.glob(f"*{ext}")): found_drivers[item.name] = {"path": str(item)}
    return found_drivers

def get_programas_dir_hash(programas_dir: Path):
    if not programas_dir.is_dir(): return ""
    hasher = hashlib.md5()
    for item in sorted(programas_dir.iterdir(), key=lambda p: p.name):
        if item.is_dir():
            hasher.update(f"{item.name}:{len(list(item.iterdir()))}".encode())
    return hasher.hexdigest()

def load_cached_scan():
    if not CACHE_FILE.exists(): return None
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (IOError, json.JSONDecodeError): return None

def save_cached_scan(installed_software, scan_results, dir_hash):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    cache_data = {"timestamp": datetime.now().isoformat(), "hash": dir_hash, "installed_software": installed_software, "scan_results": scan_results}
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f: json.dump(cache_data, f, indent=2)
    except IOError as e: logging.error(f"No se pudo guardar caché: {e}")

def clear_cache():
    try:
        if CACHE_FILE.exists(): CACHE_FILE.unlink(); return True
    except OSError as e: logging.error(f"Error al eliminar caché: {e}")
    return False