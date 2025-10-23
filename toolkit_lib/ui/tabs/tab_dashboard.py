# --- START OF FILE toolkit_lib/ui/tabs/tab_dashboard.py ---

import tkinter as tk
from tkinter import ttk
from ..helpers import ToolTip, ScrollableFrame

def create_dashboard_tab(notebook, app):
    tab = ttk.Frame(notebook, padding="15")
    notebook.add(tab, text='Panel de Control 🏠')
    
    tab.columnconfigure(0, weight=1); tab.columnconfigure(1, weight=1); tab.rowconfigure(1, weight=1)

    top = ttk.Frame(tab); top.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 20))
    ttk.Label(top, text="Resumen del Sistema", font=("Segoe UI", 16, "bold")).pack(side='left')
    ttk.Button(top, text="Refrescar 🔄", command=lambda: app._rescan_and_refresh_ui()).pack(side='right')

    left = ttk.Frame(tab); left.grid(row=1, column=0, sticky='nsew', padx=(0, 10)); left.rowconfigure(1, weight=1)
    status_lf = ttk.LabelFrame(left, text="Estado Actual", padding=10); status_lf.grid(row=0, column=0, sticky='ew')
    
    app.dashboard_labels = {
        'total': ttk.Label(status_lf, text="..."), 'installed': ttk.Label(status_lf, text="..."), 'drivers': ttk.Label(status_lf, text="...")
    }
    [v.pack(anchor='w') for v in app.dashboard_labels.values()]

    tasks_lf = ttk.LabelFrame(left, text="Tareas Rápidas", padding=10); tasks_lf.grid(row=1, column=0, sticky='nsew', pady=(10, 0))

    common_tasks = {'LimpiarArchivosTemporales': '🧹', 'ConfigurarEnergiaNunca': '⚡'}
    for task, icon in common_tasks.items():
        if task in app.app_configs: ttk.Button(tasks_lf, text=f"{app.app_configs[task].get('icon', icon)} {task}", command=lambda t=task: app.run_task_from_dashboard(t)).pack(fill='x', pady=5)
    
    right = ttk.Frame(tab); right.grid(row=1, column=1, sticky='nsew', padx=(10, 0)); right.rowconfigure(0, weight=1)
    groups_lf = ttk.LabelFrame(right, text="Grupos", padding=10); groups_lf.grid(row=0, column=0, sticky='nsew')
    app.dashboard_groups_frame = ScrollableFrame(groups_lf); app.dashboard_groups_frame.pack(expand=True, fill='both')
    
    return tab

def refresh_dashboard(app):
    labels = app.dashboard_labels
    total, installed = len(app.app_configs), len([t for i in app.app_tree.get_children('') for c in app.app_tree.get_children(i) for t in app.app_tree.item(c,'tags') if 'installed' in t])
    labels['total'].config(text=f"Apps conocidas: {total}")
    labels['installed'].config(text=f"Instaladas (detectadas): {installed}")
    
    # --- LÍNEA CORREGIDA ---
    # Convertimos el generador de app.drivers_dir.glob('*') a una lista para poder usar len()
    driver_count = len(list(app.drivers_dir.glob('*')))
    labels['drivers'].config(text=f"Paquetes de drivers: {driver_count}")
    # --- FIN DE LA CORRECCIÓN ---

    [w.destroy() for w in app.dashboard_groups_frame.scrollable_frame.winfo_children()]
    groups = app._load_groups()
    if not groups: ttk.Label(app.dashboard_groups_frame.scrollable_frame, text="No hay grupos.", style='Muted.TLabel').pack()
    else:
        for name, apps in sorted(groups.items())[:5]:
            ttk.Button(app.dashboard_groups_frame.scrollable_frame, text=f"📂 Aplicar '{name}' ({len(apps)} apps)", command=lambda n=name: app.apply_group_from_dashboard(n)).pack(fill='x',pady=3,padx=5)