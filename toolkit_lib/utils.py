# --- START OF FILE toolkit_lib/utils.py ---

import winreg
import ctypes
import logging
from datetime import datetime

def is_admin():
    """Verifica si el script se está ejecutando con privilegios de administrador."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def scan_installed_software():
    """
    Escanea el registro de Windows para obtener una lista de software instalado.
    Devuelve un diccionario: { 'nombre_display': {'uninstall_string': str, 'version': str, 'install_date': str} }
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
                                continue

                            version = ""
                            try:
                                version = winreg.QueryValueEx(sub_key, "DisplayVersion")[0]
                            except OSError:
                                pass

                            install_date_str = ""
                            try:
                                date_val = winreg.QueryValueEx(sub_key, "InstallDate")[0]
                                install_date_str = datetime.strptime(date_val, "%Y%m%d").strftime("%d-%m-%Y")
                            except (OSError, ValueError):
                                pass
                            
                            installed_software[display_name] = {
                                "uninstall_string": uninstall_string,
                                "version": version,
                                "install_date": install_date_str,
                            }
                    except OSError:
                        continue
        except FileNotFoundError:
            logging.warning(f"Ruta del registro no encontrada: {path}")
            continue

    return installed_software