"""
3D Slicer Pro - Main entry point.

Creates QApplication with dark Fusion style and launches MainWindow.
"""

import sys
import os

# Ensure the project root is on the Python path so `src` can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor, QSurfaceFormat
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


def apply_dark_theme(app: QApplication):
    """Apply a dark Fusion color palette."""
    app.setStyle("Fusion")

    palette = QPalette()

    dark_bg = QColor(30, 30, 30)
    mid_bg = QColor(45, 45, 45)
    light_bg = QColor(60, 60, 60)
    highlight = QColor(42, 130, 218)
    text_color = QColor(220, 220, 220)
    disabled_text = QColor(120, 120, 120)
    border = QColor(80, 80, 80)

    palette.setColor(QPalette.ColorRole.Window, dark_bg)
    palette.setColor(QPalette.ColorRole.WindowText, text_color)
    palette.setColor(QPalette.ColorRole.Base, mid_bg)
    palette.setColor(QPalette.ColorRole.AlternateBase, light_bg)
    palette.setColor(QPalette.ColorRole.ToolTipBase, dark_bg)
    palette.setColor(QPalette.ColorRole.ToolTipText, text_color)
    palette.setColor(QPalette.ColorRole.Text, text_color)
    palette.setColor(QPalette.ColorRole.Button, mid_bg)
    palette.setColor(QPalette.ColorRole.ButtonText, text_color)
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Link, highlight)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))

    # Disabled state
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(80, 80, 80))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, disabled_text)

    app.setPalette(palette)

    # Global stylesheet tweaks
    app.setStyleSheet("""
        QToolTip {
            color: #ddd;
            background-color: #2b2b2b;
            border: 1px solid #555;
            padding: 4px;
        }
        QGroupBox {
            border: 1px solid #555;
            border-radius: 4px;
            margin-top: 6px;
            padding-top: 4px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 3px;
        }
        QTabWidget::pane {
            border: 1px solid #555;
        }
        QTabBar::tab {
            background: #3a3a3a;
            color: #ccc;
            padding: 4px 10px;
            border: 1px solid #555;
        }
        QTabBar::tab:selected {
            background: #4a4a4a;
            color: white;
        }
        QSlider::groove:horizontal {
            height: 4px;
            background: #555;
            border-radius: 2px;
        }
        QSlider::handle:horizontal {
            background: #2a82da;
            width: 14px;
            height: 14px;
            margin: -5px 0;
            border-radius: 7px;
        }
        QScrollBar:vertical {
            background: #2d2d2d;
            width: 10px;
        }
        QScrollBar::handle:vertical {
            background: #555;
            border-radius: 4px;
        }
        QProgressBar {
            border: 1px solid #555;
            border-radius: 3px;
            text-align: center;
            color: white;
        }
        QProgressBar::chunk {
            background: #2a82da;
            border-radius: 2px;
        }
    """)


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

    apply_dark_theme(app)

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
