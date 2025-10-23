# --- START OF FILE toolkit_lib/ui/helpers.py ---

import tkinter as tk
from tkinter import ttk
import sys

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget; self.text = text; self.tooltip_window = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event):
        if self.tooltip_window or not self.text: return
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25; y += self.widget.winfo_rooty() + 20
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True); tw.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(tw, text=self.text, justify='left', background="#2e2e2e", foreground="#cccccc", relief='solid', borderwidth=1, font=("Segoe UI", 9), padding="4")
        label.pack(ipadx=1)

    def hide_tooltip(self, event):
        if self.tooltip_window: self.tooltip_window.destroy()
        self.tooltip_window = None

class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set); self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y"); self.canvas.bind('<Enter>', self._bind_mousewheel); self.canvas.bind('<Leave>', self._unbind_mousewheel)

    def _bind_mousewheel(self, event): self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
    def _unbind_mousewheel(self, event): self.canvas.unbind_all("<MouseWheel>")
    def _on_mousewheel(self, event): self.canvas.yview_scroll(int(-1*(event.delta/(120 if sys.platform != "darwin" else 1))), "units")