# --- START OF FILE toolkit_lib/config.py ---

import json
import logging
from tkinter import messagebox
from pathlib import Path

# Tipos de Tareas
TASK_TYPE_LOCAL_INSTALL = "instalar_local"
TASK_TYPE_MANUAL_ASSISTED = "instalar_manual_asistido"
TASK_TYPE_COPY_INTERACTIVE = "copiar_archivo_interactivo"
TASK_TYPE_POWER_CONFIG = "configurar_energia_actual"
TASK_TYPE_UNINSTALL = "desinstalar"
TASK_TYPE_CLEAN_TEMP = "limpiar_temp"
TASK_TYPE_RUN_POWERSHELL = "ejecutar_powershell"
TASK_TYPE_MODIFY_REGISTRY = "modificar_registro"
TASK_TYPE_MANAGE_SERVICE = "gestionar_servicio"
TASK_TYPE_CREATE_SCHEDULED_TASK = "crear_tarea_programada"
TASK_TYPE_INSTALL_DRIVER = "instalar_driver"

# Extensiones y Estados
INSTALLER_EXTENSIONS = ['.exe', '.msi', '.bat', '.cmd', '.ps1']
DRIVER_EXTENSIONS = ['.inf']
STATUS_FOLDER_NOT_FOUND = "CARPETA_NO_ENCONTRADA"
STATUS_NO_FILES_FOUND = "NO_HAY_ARCHIVOS"

DEFAULT_APP_CONFIG = {
    "tipo": TASK_TYPE_LOCAL_INSTALL, "args_instalacion": [], "wait_for_completion": True,
    "timeout": 300, "icon": "📦", "categoria": "Sin Categoría",
    "mensaje_usuario": "Se abrirá el instalador. Completa la instalación y haz clic en 'Aceptar' para continuar.",
    "uninstall_key": None, "url": None, "pre_task_script": None,
    "post_task_script": None, "dependencies": [], "script_path": None,
    "reg_path": None, "reg_key": None, "reg_value": None,
    "reg_type": "REG_SZ", "service_name": None, "service_action": "start",
    "task_name": None, "task_command": None, "task_trigger": "ONLOGON", "task_user": "SYSTEM"
}

APP_CONFIGURATIONS = {
    "AnyDesk": {"args_instalacion": ["/S"], "icon": "🖥️", "tipo": TASK_TYPE_MANUAL_ASSISTED, "uninstall_key": "AnyDesk", "categoria": "Acceso Remoto", "url": "https://download.anydesk.com/AnyDesk.exe"},
    "PlataformaUniversal": {"args_instalacion": ["/VERYSILENT", "/SUPPRESSMSGBOXES"], "icon": "🎬", "uninstall_key": "Plataforma Universal", "categoria": "Multimedia", "dependencies": ["Java"], "post_task_script": "copy_lsplayer_shortcut"},
    "LimpiarArchivosTemporales": {"tipo": TASK_TYPE_CLEAN_TEMP, "icon": "🧹", "categoria": "Utilidades del Sistema"},
    "InstalarDrivers": {"tipo": TASK_TYPE_INSTALL_DRIVER, "icon": "🔩", "categoria": "Sistema"},
    "TeamViewerHost": {"icon": "↔️", "tipo": TASK_TYPE_MANUAL_ASSISTED, "uninstall_key": "TeamViewer", "categoria": "Acceso Remoto"},
    "Autologon": {"icon": "🔑", "tipo": TASK_TYPE_MANUAL_ASSISTED, "categoria": "Utilidades del Sistema"},
    "Novalct": {"icon": "📺", "tipo": TASK_TYPE_MANUAL_ASSISTED, "categoria": "Control de Hardware"},
    "TeamViewerSetup": {"args_instalacion": ["/S"], "icon": "↔️", "uninstall_key": "TeamViewer", "categoria": "Acceso Remoto"},
    "Java": {"args_instalacion": ["/s"], "icon": "☕", "uninstall_key": "Java(", "categoria": "Software Básico"},
    "OpenVPN": {"args_instalacion": ["/qn"], "icon": "🛡️", "uninstall_key": "OpenVPN", "categoria": "Redes"},
    "Malwarebytes": {"args_instalacion": ["/SP-", "/VERYSILENT", "/NOCANCEL", "/NORESTART"], "icon": "🐞", "uninstall_key": "Malwarebytes version", "categoria": "Seguridad"},
    "CopiarArchivosUsuario": {"tipo": TASK_TYPE_COPY_INTERACTIVE, "icon": "📂", "categoria": "Utilidades"},
    "ConfigurarEnergiaNunca": {"tipo": TASK_TYPE_POWER_CONFIG, "icon": "⚡", "categoria": "Utilidades del Sistema"},
    "Chrome": {"icon": "🌐", "uninstall_key": "Google Chrome", "categoria": "Navegadores"},
    "VLC": {"icon": "⏯️", "uninstall_key": "VLC media player", "categoria": "Multimedia"},
    "Office365": {"icon": "💼", "uninstall_key": "Microsoft 365", "categoria": "Ofimática"},
    "AutoCAD": {"icon": "📏", "uninstall_key": "AutoCAD", "categoria": "Diseño"},
    "SketchUp": {"icon": "🏠", "uninstall_key": "SketchUp", "categoria": "Diseño"},
    "Lumion": {"icon": "💡", "uninstall_key": "Lumion", "categoria": "Diseño"},
    "Putty": {"args_instalacion": ["/qn"], "icon": "💻", "uninstall_key": "PuTTY", "categoria": "Redes"},
    "WinRAR": {"icon": "📚", "uninstall_key": "WinRAR", "categoria": "Utilidades"},
    "LedSet": {"icon": "💡", "categoria": "Control de Hardware"},
    "ViPlex": {"icon": "🖥️", "categoria": "Control de Hardware"},
}

def guess_initial_config(app_path: Path) -> dict:
    config = DEFAULT_APP_CONFIG.copy(); config['uninstall_key'] = app_path.name
    try:
        if not app_path.is_dir(): return config
        files = list(app_path.iterdir())
        if any(f.suffix.lower() == '.inf' for f in files):
            config.update({'tipo': TASK_TYPE_INSTALL_DRIVER, 'icon': '🔩', 'categoria': 'Drivers'}); return config
        ps1_files = [f for f in files if f.suffix.lower() == '.ps1']
        if ps1_files:
            config.update({'tipo': TASK_TYPE_RUN_POWERSHELL, 'script_path': ps1_files[0].name, 'icon': '📜'}); return config
        if any(f.suffix.lower() == '.msi' for f in files):
            config['args_instalacion'] = ['/qn']; return config
        if any(f.suffix.lower() == '.exe' for f in files):
            return config
        if files:
            config.update({'tipo': TASK_TYPE_COPY_INTERACTIVE, 'icon': '📂'}); return config
    except Exception as e:
        logging.warning(f"No se pudo analizar {app_path} para autocompletar: {e}")
    return config

def build_app_configurations(programas_dir: Path, conf_dir: Path):
    final_config, newly_discovered_apps = {}, []
    try:
        ignored_dirs = ["grupos", "__pycache__", "drivers"]
        discovered_apps_names = {d.name for d in programas_dir.iterdir() if d.is_dir() and d.name.lower() not in ignored_dirs}
    except FileNotFoundError:
        messagebox.showerror("Error Crítico", f"El directorio '{programas_dir}' no fue encontrado."); return {}, []

    all_app_names = sorted(list(discovered_apps_names.union(APP_CONFIGURATIONS.keys())))
    
    for app_name in all_app_names:
        config = DEFAULT_APP_CONFIG.copy()
        if app_name in APP_CONFIGURATIONS: config.update(APP_CONFIGURATIONS[app_name])
        else: newly_discovered_apps.append(app_name)
        final_config[app_name] = config
    
    custom_config_file = conf_dir / "config_personalizada.json"
    if custom_config_file.exists():
        try:
            with open(custom_config_file, 'r', encoding='utf-8') as f: custom_config = json.load(f)
            for app_name, custom_settings in custom_config.items():
                final_config.setdefault(app_name, DEFAULT_APP_CONFIG.copy()).update(custom_settings)
                if app_name in newly_discovered_apps: newly_discovered_apps.remove(app_name)
        except (IOError, json.JSONDecodeError) as e:
            logging.error(f"No se pudo cargar la configuración personalizada: {e}")
            
    return final_config, newly_discovered_apps