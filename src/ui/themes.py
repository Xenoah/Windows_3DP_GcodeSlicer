"""Color theme system for 3D Slicer Pro.

Built-in palettes: Dark, Darker, Ocean, Solarized Dark, Light, High Contrast.
Custom palette: derived from three user-chosen colors (background, text, accent).
"""

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor

# ---------------------------------------------------------------------------
# Theme definitions
# ---------------------------------------------------------------------------

THEMES = {
    "Dark": {
        "window":     "#1e1e1e",
        "base":       "#2d2d2d",
        "alt_base":   "#3c3c3c",
        "text":       "#dcdcdc",
        "button":     "#2d2d2d",
        "highlight":  "#2a82da",
        "tooltip_bg": "#2b2b2b",
        "tab_bg":     "#3a3a3a",
        "tab_sel":    "#4a4a4a",
        "border":     "#555555",
        "scrollbar":  "#555555",
    },
    "Darker": {
        "window":     "#121212",
        "base":       "#1e1e1e",
        "alt_base":   "#282828",
        "text":       "#e0e0e0",
        "button":     "#1e1e1e",
        "highlight":  "#1565c0",
        "tooltip_bg": "#1a1a1a",
        "tab_bg":     "#252525",
        "tab_sel":    "#303030",
        "border":     "#444444",
        "scrollbar":  "#444444",
    },
    "Ocean": {
        "window":     "#0d1b2a",
        "base":       "#1b2838",
        "alt_base":   "#253546",
        "text":       "#c7d5e0",
        "button":     "#1b2838",
        "highlight":  "#4fc3f7",
        "tooltip_bg": "#0d1b2a",
        "tab_bg":     "#1e3448",
        "tab_sel":    "#2a4a67",
        "border":     "#4a6278",
        "scrollbar":  "#4a6278",
    },
    "Solarized Dark": {
        "window":     "#002b36",
        "base":       "#073642",
        "alt_base":   "#0d4454",
        "text":       "#839496",
        "button":     "#073642",
        "highlight":  "#268bd2",
        "tooltip_bg": "#002b36",
        "tab_bg":     "#073642",
        "tab_sel":    "#0e4558",
        "border":     "#586e75",
        "scrollbar":  "#586e75",
    },
    "Light": {
        "window":     "#f0f0f0",
        "base":       "#ffffff",
        "alt_base":   "#e8e8e8",
        "text":       "#202020",
        "button":     "#e0e0e0",
        "highlight":  "#1976d2",
        "tooltip_bg": "#fffde7",
        "tab_bg":     "#d8d8d8",
        "tab_sel":    "#ffffff",
        "border":     "#bbbbbb",
        "scrollbar":  "#aaaaaa",
    },
    "High Contrast": {
        "window":     "#000000",
        "base":       "#0a0a0a",
        "alt_base":   "#141414",
        "text":       "#ffffff",
        "button":     "#1a1a1a",
        "highlight":  "#ffff00",
        "tooltip_bg": "#000000",
        "tab_bg":     "#111111",
        "tab_sel":    "#222222",
        "border":     "#ffffff",
        "scrollbar":  "#888888",
    },
}

THEME_NAMES = list(THEMES.keys()) + ["Custom"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_theme(app: QApplication, name: str, custom_colors: dict = None):
    """Apply a named theme (or Custom) to the QApplication."""
    app.setStyle("Fusion")
    colors = _resolve_colors(name, custom_colors)
    _apply_palette(app, colors)
    _apply_stylesheet(app, colors)


def _resolve_colors(name: str, custom_colors: dict = None) -> dict:
    if name == "Custom" and custom_colors:
        return _derive_custom_palette(custom_colors)
    return THEMES.get(name, THEMES["Dark"])


def _derive_custom_palette(custom_colors: dict) -> dict:
    """Derive a full color dict from user-chosen bg / text / accent."""
    bg  = custom_colors.get("background", "#1e1e1e")
    txt = custom_colors.get("text",       "#dcdcdc")
    acc = custom_colors.get("accent",     "#2a82da")
    bg_c = QColor(bg)
    return {
        "window":     bg,
        "base":       bg_c.lighter(135).name(),
        "alt_base":   bg_c.lighter(115).name(),
        "text":       txt,
        "button":     bg_c.lighter(130).name(),
        "highlight":  acc,
        "tooltip_bg": bg_c.darker(110).name(),
        "tab_bg":     bg_c.lighter(125).name(),
        "tab_sel":    bg_c.lighter(148).name(),
        "border":     bg_c.lighter(160).name(),
        "scrollbar":  bg_c.lighter(155).name(),
    }


def _apply_palette(app: QApplication, colors: dict):
    palette = QPalette()
    c    = {k: QColor(v) for k, v in colors.items()}
    text = c["text"]
    dis  = text.darker(200)

    palette.setColor(QPalette.ColorRole.Window,         c["window"])
    palette.setColor(QPalette.ColorRole.WindowText,     text)
    palette.setColor(QPalette.ColorRole.Base,           c["base"])
    palette.setColor(QPalette.ColorRole.AlternateBase,  c["alt_base"])
    palette.setColor(QPalette.ColorRole.ToolTipBase,    c["tooltip_bg"])
    palette.setColor(QPalette.ColorRole.ToolTipText,    text)
    palette.setColor(QPalette.ColorRole.Text,           text)
    palette.setColor(QPalette.ColorRole.Button,         c["button"])
    palette.setColor(QPalette.ColorRole.ButtonText,     text)
    palette.setColor(QPalette.ColorRole.BrightText,     QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Link,           c["highlight"])
    palette.setColor(QPalette.ColorRole.Highlight,      c["highlight"])
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))

    g = QPalette.ColorGroup.Disabled
    palette.setColor(g, QPalette.ColorRole.WindowText,      dis)
    palette.setColor(g, QPalette.ColorRole.Text,            dis)
    palette.setColor(g, QPalette.ColorRole.ButtonText,      dis)
    palette.setColor(g, QPalette.ColorRole.Highlight,       c["button"])
    palette.setColor(g, QPalette.ColorRole.HighlightedText, dis)

    app.setPalette(palette)


def _apply_stylesheet(app: QApplication, colors: dict):
    c = colors
    app.setStyleSheet(f"""
        QToolTip {{
            color: {c['text']};
            background-color: {c['tooltip_bg']};
            border: 1px solid {c['border']};
            padding: 4px;
        }}
        QGroupBox {{
            border: 1px solid {c['border']};
            border-radius: 4px;
            margin-top: 6px;
            padding-top: 4px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 3px;
        }}
        QTabWidget::pane {{
            border: 1px solid {c['border']};
        }}
        QTabBar::tab {{
            background: {c['tab_bg']};
            color: {c['text']};
            padding: 4px 10px;
            border: 1px solid {c['border']};
        }}
        QTabBar::tab:selected {{
            background: {c['tab_sel']};
            color: {c['text']};
        }}
        QSlider::groove:horizontal {{
            height: 4px;
            background: {c['border']};
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {c['highlight']};
            width: 14px;
            height: 14px;
            margin: -5px 0;
            border-radius: 7px;
        }}
        QScrollBar:vertical {{
            background: {c['base']};
            width: 10px;
        }}
        QScrollBar::handle:vertical {{
            background: {c['scrollbar']};
            border-radius: 4px;
        }}
        QProgressBar {{
            border: 1px solid {c['border']};
            border-radius: 3px;
            text-align: center;
            color: {c['text']};
        }}
        QProgressBar::chunk {{
            background: {c['highlight']};
            border-radius: 2px;
        }}
    """)
