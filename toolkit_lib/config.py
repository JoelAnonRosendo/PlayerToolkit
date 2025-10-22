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


# Extensiones y Estados
INSTALLER_EXTENSIONS = ['.exe', '.msi', '.bat', '.cmd', '.ps1'] # MODIFICADO: .cmd y .ps1 añadidos
STATUS_FOLDER_NOT_FOUND = "CARPETA_NO_ENCONTRADA"
STATUS_NO_FILES_FOUND = "NO_HAY_ARCHIVOS"

DEFAULT_APP_CONFIG = {
    "tipo": TASK_TYPE_LOCAL_INSTALL, "args_instalacion": [], "wait_for_completion": True,
    "timeout": 300, "icon": "📦", "categoria": "Sin Categoría",
    "mensaje_usuario": "Se abrirá el instalador. Completa la instalación y haz clic en 'Aceptar' para continuar.",
    "uninstall_key": None,
    "url": None,
    
    # MODIFICADO: Campos unificados y nuevos
    "pre_task_script": None,     # Script a ejecutar ANTES de la tarea principal
    "post_task_script": None,    # Script a ejecutar DESPUÉS de la tarea principal
    "dependencies": [],          # Lista de otras apps (claves) que deben instalarse antes

    # Campos específicos para tareas
    "script_path": None,        # Para ejecutar_powershell
    "reg_path": None,           # Para modificar_registro (ej. HKEY_LOCAL_MACHINE\\...)
    "reg_key": None,            # Nombre de la clave de registro
    "reg_value": None,          # Valor de la clave
    "reg_type": "REG_SZ",       # Tipo (REG_SZ, REG_DWORD, etc.)
    "service_name": None,       # Para gestionar_servicio
    "service_action": "start",  # start, stop, disable, enable
    "task_name": None,          # Para crear_tarea_programada
    "task_command": None,       # Comando a ejecutar
    "task_trigger": "ONLOGON",  # ONLOGON, DAILY, etc.
    "task_user": "SYSTEM"       # Usuario que ejecuta la tarea
}

APP_CONFIGURATIONS = {
    "AnyDesk": {
        "args_instalacion": ["/S"], "icon": "🖥️", "tipo": TASK_TYPE_MANUAL_ASSISTED,
        "uninstall_key": "AnyDesk", "categoria": "Acceso Remoto",
        "url": "https://download.anydesk.com/AnyDesk.exe"
    },
    "PlataformaUniversal": {
        "args_instalacion": ["/VERYSILENT", "/SUPPRESSMSGBOXES"], "icon": "🎬",
        "uninstall_key": "Plataforma Universal", "categoria": "Multimedia",
        # MODIFICADO: Usando el nuevo sistema de dependencias y scripts
        "dependencies": ["Java"],
        "post_task_script": "copy_lsplayer_shortcut"
    },
    "LimpiarArchivosTemporales": {"tipo": TASK_TYPE_CLEAN_TEMP, "icon": "🧹", "categoria": "Utilidades del Sistema"},
    "TeamViewerHost": {"icon": "↔️", "tipo": TASK_TYPE_MANUAL_ASSISTED, "uninstall_key": "TeamViewer", "categoria": "Acceso Remoto"},
    "Autologon": {"icon": "🔑", "tipo": TASK_TYPE_MANUAL_ASSISTED, "categoria": "Utilidades del Sistema"},
    "Novalct": {"icon": "📺", "tipo": TASK_TYPE_MANUAL_ASSISTED, "categoria": "Control de Hardware"},
    "TeamViewerSetup": {"args_instalacion": ["/S"], "icon": "↔️", "uninstall_key": "TeamViewer", "categoria": "Acceso Remoto"},
    "Java": {"args_instalacion": ["/s"], "icon": "☕", "uninstall_key": "Java(", "categoria": "Software Básico"},
    "OpenVPN": {"args_instalacion": ["/qn"], "icon": "🛡️", "uninstall_key": "OpenVPN", "categoria": "Redes"},
    "Malwarebytes": {
        "args_instalacion": ["/SP-", "/VERYSILENT", "/NOCANCEL", "/NORESTART"], "icon": "🐞",
        "uninstall_key": "Malwarebytes version", "categoria": "Seguridad"
    },
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
    """
    Intenta adivinar una configuración inicial para una nueva aplicación
    analizando el contenido de su carpeta.
    """
    config = DEFAULT_APP_CONFIG.copy()
    app_name = app_path.name

    config['uninstall_key'] = app_name

    try:
        if not app_path.is_dir():
            return config

        files = list(app_path.iterdir())

        ps1_files = [f for f in files if f.suffix.lower() == '.ps1']
        if ps1_files:
            config['tipo'] = TASK_TYPE_RUN_POWERSHELL
            config['script_path'] = ps1_files[0].name
            config['icon'] = '📜'
            return config

        msi_files = [f for f in files if f.suffix.lower() == '.msi']
        if msi_files:
            config['tipo'] = TASK_TYPE_LOCAL_INSTALL
            config['args_instalacion'] = ['/qn']
            return config

        exe_files = [f for f in files if f.suffix.lower() == '.exe']
        if exe_files:
            config['tipo'] = TASK_TYPE_LOCAL_INSTALL
            config['args_instalacion'] = []
            return config

        if files:
            config['tipo'] = TASK_TYPE_COPY_INTERACTIVE
            config['icon'] = '📂'
            return config

    except Exception as e:
        logging.warning(f"No se pudo analizar la carpeta {app_path} para autocompletar: {e}")

    return config

def build_app_configurations(programas_dir: Path, conf_dir: Path):
    """
    Construye la configuración final de apps, fusionando valores por defecto,
    descubiertos en carpetas y personalizaciones del usuario.
    Devuelve la configuración final y una lista de apps nuevas no configuradas.
    """
    final_config = {}
    newly_discovered_apps = []

    try:
        discovered_apps_names = {d.name for d in programas_dir.iterdir() if d.is_dir() and d.name.lower() not in ["grupos", "__pycache__"]}
    except FileNotFoundError:
        messagebox.showerror("Error Crítico", f"El directorio base '{programas_dir}' no fue encontrado.")
        return {}, []

    all_app_names = sorted(list(discovered_apps_names.union(APP_CONFIGURATIONS.keys())))
    
    for app_name in all_app_names:
        config = DEFAULT_APP_CONFIG.copy()
        if app_name in APP_CONFIGURATIONS:
            config.update(APP_CONFIGURATIONS[app_name])
        else:
            newly_discovered_apps.append(app_name)
        final_config[app_name] = config
    
    custom_config_file = conf_dir / "config_personalizada.json"
    if custom_config_file.exists():
        try:
            with open(custom_config_file, 'r', encoding='utf-8') as f:
                custom_config = json.load(f)
            for app_name, custom_settings in custom_config.items():
                if app_name in final_config:
                    final_config[app_name].update(custom_settings)
                else:
                    config = DEFAULT_APP_CONFIG.copy()
                    config.update(custom_settings)
                    final_config[app_name] = config
                if app_name in newly_discovered_apps:
                    newly_discovered_apps.remove(app_name)

        except (IOError, json.JSONDecodeError) as e:
            logging.error(f"No se pudo cargar la configuración personalizada: {e}")
            
    return final_config, newly_discovered_apps