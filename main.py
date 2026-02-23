"""
3D Slicer Pro - Main entry point.

Creates QApplication with dark Fusion style and launches MainWindow.
"""

import sys
import os

# Ensure the project root is on the Python path so `src` can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtCore import Qt


def _set_opengl_format():
    """
    Set OpenGL surface format BEFORE QApplication is created.
    Qt requires this to take effect for QOpenGLWidget.
    Try OpenGL 3.3 Core; if the driver doesn't support it the widget
    will fall back gracefully.
    """
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setSamples(4)           # MSAA x4
    fmt.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
    QSurfaceFormat.setDefaultFormat(fmt)


# *** MUST be called before QApplication ***
_set_opengl_format()


def _apply_initial_theme(app: QApplication):
    """Apply the theme saved in session.json (falls back to Dark)."""
    import json as _json
    from src.ui.themes import apply_theme

    theme_name    = 'Dark'
    custom_colors = None

    here         = os.path.dirname(os.path.abspath(__file__))
    session_path = os.path.join(here, 'profiles', 'session.json')

    if os.path.isfile(session_path):
        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                data = _json.load(f)
            theme_name    = data.get('_theme', 'Dark')
            custom_colors = data.get('_custom_colors')
        except Exception:
            pass

    apply_theme(app, theme_name, custom_colors)


def main():
    # High DPI support
    if hasattr(Qt.ApplicationAttribute, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("3D Slicer Pro")
    app.setOrganizationName("SlicerPro")
    app.setApplicationVersion("1.0.0")

    _apply_initial_theme(app)

    # Import here (after path setup) to catch import errors gracefully
    try:
        from src.ui.main_window import MainWindow
    except ImportError as e:
        from PyQt6.QtWidgets import QMessageBox
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle("Import Error")
        msg.setText(f"Failed to load application:\n\n{e}\n\nPlease run setup.bat to install dependencies.")
        msg.exec()
        return 1

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
