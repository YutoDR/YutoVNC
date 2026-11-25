"""Theme and styling configuration for YutoVNC.

Supports Modern Dark and Modern Light themes with sleek colors,
consistent typography, card surfaces, and polished TTK styles.
"""

import tkinter as tk
from tkinter import ttk

DARK_THEME = {
    "name": "dark",
    "bg": "#181825",            # Base background
    "surface": "#1e1e2e",       # Cards and panels
    "surface_variant": "#2a2a3e",# Hover and secondary surface
    "sidebar": "#11111b",       # Darker sidebar
    "text": "#cdd6f4",          # Primary text
    "text_muted": "#a6adc8",    # Secondary text
    "text_dim": "#6c7086",      # Placeholder / disabled
    "accent": "#89b4fa",        # Primary blue/indigo accent
    "accent_hover": "#b4befe",  # Lighter hover
    "accent_btn_bg": "#4338ca", # Button accent background
    "accent_btn_fg": "#ffffff",
    "border": "#313244",        # Border stroke
    "entry_bg": "#313244",      # Input background
    "entry_fg": "#cdd6f4",
    "online": "#a6e3a1",        # Emerald green
    "offline": "#f38ba8",       # Coral red
    "warning": "#f9e2af",       # Amber
    "header_bg": "#181825",
    "tree_selected": "#45475a"
}

LIGHT_THEME = {
    "name": "light",
    "bg": "#f8fafc",
    "surface": "#ffffff",
    "surface_variant": "#f1f5f9",
    "sidebar": "#f8fafc",
    "text": "#0f172a",
    "text_muted": "#475569",
    "text_dim": "#94a3b8",
    "accent": "#3b82f6",
    "accent_hover": "#2563eb",
    "accent_btn_bg": "#2563eb",
    "accent_btn_fg": "#ffffff",
    "border": "#cbd5e1",
    "entry_bg": "#ffffff",
    "entry_fg": "#0f172a",
    "online": "#16a34a",
    "offline": "#dc2626",
    "warning": "#d97706",
    "header_bg": "#ffffff",
    "tree_selected": "#e2e8f0"
}

def get_theme_colors(theme_name: str = "dark") -> dict:
    return DARK_THEME if theme_name == "dark" else LIGHT_THEME

def apply_theme(root: tk.Tk, theme_name: str = "dark"):
    """Configure TTK style hierarchy for the entire application."""
    colors = get_theme_colors(theme_name)
    style = ttk.Style(root)

    # Use clam as base engine across all Windows versions
    try:
        style.theme_use("clam")
    except Exception:
        pass

    root.configure(bg=colors["bg"])

    # Base TFrame
    style.configure("TFrame", background=colors["bg"])
    style.configure("Surface.TFrame", background=colors["surface"])
    style.configure("Sidebar.TFrame", background=colors["sidebar"])

    # TLabel
    style.configure("TLabel", background=colors["bg"], foreground=colors["text"], font=("Segoe UI", 10))
    style.configure("Surface.TLabel", background=colors["surface"], foreground=colors["text"], font=("Segoe UI", 10))
    style.configure("Muted.TLabel", background=colors["bg"], foreground=colors["text_muted"], font=("Segoe UI", 9))
    style.configure("SurfaceMuted.TLabel", background=colors["surface"], foreground=colors["text_muted"], font=("Segoe UI", 9))
    style.configure("Title.TLabel", background=colors["bg"], foreground=colors["text"], font=("Segoe UI", 14, "bold"))
    style.configure("Subtitle.TLabel", background=colors["bg"], foreground=colors["text_muted"], font=("Segoe UI", 10))

    # TButton
    style.configure(
        "TButton",
        background=colors["surface_variant"],
        foreground=colors["text"],
        borderwidth=1,
        bordercolor=colors["border"],
        relief="flat",
        font=("Segoe UI", 9, "bold"),
        padding=(10, 6)
    )
    style.map(
        "TButton",
        background=[("active", colors["border"]), ("disabled", colors["bg"])],
        foreground=[("disabled", colors["text_dim"])]
    )

    # Primary Action Button
    style.configure(
        "Primary.TButton",
        background=colors["accent_btn_bg"],
        foreground=colors["accent_btn_fg"],
        borderwidth=0,
        relief="flat",
        font=("Segoe UI", 9, "bold"),
        padding=(12, 6)
    )
    style.map(
        "Primary.TButton",
        background=[("active", colors["accent_hover"])],
        foreground=[("active", "#ffffff")]
    )

    # Success Button (e.g. Connect)
    style.configure(
        "Success.TButton",
        background="#059669",
        foreground="#ffffff",
        borderwidth=0,
        relief="flat",
        font=("Segoe UI", 9, "bold"),
        padding=(12, 6)
    )
    style.map(
        "Success.TButton",
        background=[("active", "#10b981")]
    )

    # Danger Button (e.g. Delete)
    style.configure(
        "Danger.TButton",
        background="#b91c1c",
        foreground="#ffffff",
        borderwidth=0,
        relief="flat",
        font=("Segoe UI", 9, "bold"),
        padding=(10, 6)
    )
    style.map(
        "Danger.TButton",
        background=[("active", "#ef4444")]
    )

    # Warning Button (e.g. active View-Only ON state)
    style.configure(
        "Warning.TButton",
        background="#d97706",
        foreground="#ffffff",
        borderwidth=0,
        relief="flat",
        font=("Segoe UI", 9, "bold"),
        padding=(10, 6)
    )
    style.map(
        "Warning.TButton",
        background=[("active", "#f59e0b")]
    )

    # Compact Small Button (e.g. Clear search X, sidebar icons)
    style.configure(
        "Small.TButton",
        background=colors["surface_variant"],
        foreground=colors["text"],
        borderwidth=1,
        bordercolor=colors["border"],
        relief="flat",
        font=("Segoe UI", 9, "bold"),
        padding=(6, 4)
    )
    style.map(
        "Small.TButton",
        background=[("active", colors["border"]), ("disabled", colors["bg"])],
        foreground=[("disabled", colors["text_dim"])]
    )

    # TEntry
    style.configure(
        "TEntry",
        fieldbackground=colors["entry_bg"],
        foreground=colors["entry_fg"],
        bordercolor=colors["border"],
        lightcolor=colors["border"],
        darkcolor=colors["border"],
        padding=6,
        font=("Segoe UI", 10)
    )

    # TCombobox
    style.configure(
        "TCombobox",
        fieldbackground=colors["entry_bg"],
        background=colors["surface_variant"],
        foreground=colors["entry_fg"],
        arrowcolor=colors["text"],
        bordercolor=colors["border"],
        padding=5,
        font=("Segoe UI", 9)
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", colors["entry_bg"])],
        foreground=[("readonly", colors["entry_fg"])]
    )

    # Treeview (Address Book table)
    style.configure(
        "Treeview",
        background=colors["surface"],
        foreground=colors["text"],
        fieldbackground=colors["surface"],
        bordercolor=colors["border"],
        font=("Segoe UI", 10),
        rowheight=28
    )
    style.map(
        "Treeview",
        background=[("selected", colors["tree_selected"])],
        foreground=[("selected", "#ffffff")]
    )
    style.configure(
        "Treeview.Heading",
        background=colors["sidebar"],
        foreground=colors["text"],
        font=("Segoe UI", 9, "bold"),
        padding=(6, 6),
        relief="flat"
    )
    style.map(
        "Treeview.Heading",
        background=[("active", colors["surface_variant"])]
    )

    # TNotebook (Tabs)
    style.configure(
        "TNotebook",
        background=colors["bg"],
        tabmargins=(4, 4, 4, 0),
        borderwidth=0
    )
    style.configure(
        "TNotebook.Tab",
        background=colors["surface_variant"],
        foreground=colors["text_muted"],
        padding=(14, 8),
        font=("Segoe UI", 9, "bold"),
        borderwidth=0
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", colors["surface"]), ("active", colors["border"])],
        foreground=[("selected", colors["accent"]), ("active", colors["text"])]
    )

    # TCheckbutton & TRadiobutton
    style.configure("TCheckbutton", background=colors["bg"], foreground=colors["text"], font=("Segoe UI", 9))
    style.configure("Surface.TCheckbutton", background=colors["surface"], foreground=colors["text"], font=("Segoe UI", 9))
    style.configure("TRadiobutton", background=colors["bg"], foreground=colors["text"], font=("Segoe UI", 9))
    style.configure("Surface.TRadiobutton", background=colors["surface"], foreground=colors["text"], font=("Segoe UI", 9))

    return colors
