"""
Main application window.
"""

import os
import sys
import time
import traceback
from typing import List, Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QPushButton,
    QFileDialog, QStatusBar, QProgressBar, QLabel,
    QToolBar, QMenuBar, QMenu, QMessageBox, QGroupBox,
    QSizePolicy, QFrame, QButtonGroup
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QObject, QSize
)
from PyQt6.QtGui import QAction, QIcon, QFont, QKeySequence

from src.core.mesh import Mesh
from src.core.slicer import Slicer, SliceSettings
from src.core.gcode import GCodeGenerator, load_printer_profiles
from src.loaders.loader import load_file
from src.ui.viewport import Viewport3D, ViewMode
from src.ui.settings_panel import SettingsPanel
from src.ui.layer_slider import LayerSlider


# ---------------------------------------------------------------------------
# Slicing worker thread
# ---------------------------------------------------------------------------

class SlicerWorker(QObject):
    """Runs slicing in a background thread."""

    progress = pyqtSignal(int, int, str)       # current, total, message
    finished = pyqtSignal(list, float, float)  # layers, print_time_s, filament_g
    error = pyqtSignal(str)

    def __init__(self, mesh_obj, settings: SliceSettings):
        super().__init__()
        self.mesh_obj = mesh_obj
        self.settings = settings
        self._slicer = Slicer()

    def run(self):
        try:
            layers = self._slicer.slice(
                self.mesh_obj,
                self.settings,
                progress_callback=self._on_progress
            )
            print_time = Slicer.estimate_print_time(layers, self.settings)
            filament_g = Slicer.estimate_filament(layers, self.settings)
            self.finished.emit(layers, print_time, filament_g)
        except Exception as e:
            self.error.emit(f"Slicing error: {e}\n{traceback.format_exc()}")

    def _on_progress(self, current: int, total: int, msg: str):
        self.progress.emit(current, total, msg)


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """Main application window for 3D Slicer Pro."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D Slicer Pro")
        self.resize(1400, 900)

        # State
        self._meshes: List[Mesh] = []           # loaded mesh objects
        self._sliced_layers: List = []           # SlicedLayer list
        self._gcode_str: Optional[str] = None   # generated G-code
        self._slice_thread: Optional[QThread] = None
        self._slice_worker: Optional[SlicerWorker] = None
        self._active_mesh_idx: int = -1

        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_statusbar()
        self._connect_signals()

        # Initial state
        self.status_label.setText("Ready - Open a model to start")

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(2)

        # Main horizontal splitter
        hsplitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(hsplitter, stretch=1)

        # --- Left panel: model list ---
        left_panel = self._build_left_panel()
        hsplitter.addWidget(left_panel)

        # --- Center: viewport + layer slider ---
        center_panel = self._build_center_panel()
        hsplitter.addWidget(center_panel)

        # --- Right panel: settings ---
        self.settings_panel = SettingsPanel()
        hsplitter.addWidget(self.settings_panel)

        # Set splitter sizes
        hsplitter.setSizes([200, 900, 290])
        hsplitter.setStretchFactor(0, 0)
        hsplitter.setStretchFactor(1, 1)
        hsplitter.setStretchFactor(2, 0)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(200)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Title
        title = QLabel("Models")
        title.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(title)

        # Model list
        self.model_list = QListWidget()
        self.model_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.model_list, stretch=1)

        # Buttons
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add")
        self.add_btn.setToolTip("Load a 3D model file")
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setToolTip("Remove selected model")
        self.remove_btn.setEnabled(False)
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.remove_btn)
        layout.addLayout(btn_layout)

        return panel

    def _build_center_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Viewport
        self.viewport = Viewport3D()
        layout.addWidget(self.viewport, stretch=1)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # Layer slider
        self.layer_slider = LayerSlider()
        self.layer_slider.setFixedHeight(36)
        layout.addWidget(self.layer_slider)

        return panel

    def _setup_menu(self):
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        self.action_open = QAction("Open Model...", self)
        self.action_open.setShortcut(QKeySequence("Ctrl+O"))
        file_menu.addAction(self.action_open)

        file_menu.addSeparator()

        self.action_export_gcode = QAction("Export G-code...", self)
        self.action_export_gcode.setShortcut(QKeySequence("Ctrl+S"))
        self.action_export_gcode.setEnabled(False)
        file_menu.addAction(self.action_export_gcode)

        file_menu.addSeparator()

        self.action_exit = QAction("Exit", self)
        self.action_exit.setShortcut(QKeySequence("Alt+F4"))
        file_menu.addAction(self.action_exit)

        # View menu
        view_menu = menubar.addMenu("View")

        self.action_reset_cam = QAction("Reset Camera", self)
        self.action_reset_cam.setShortcut(QKeySequence("R"))
        view_menu.addAction(self.action_reset_cam)

        self.action_toggle_grid = QAction("Toggle Grid", self)
        self.action_toggle_grid.setCheckable(True)
        self.action_toggle_grid.setChecked(True)
        view_menu.addAction(self.action_toggle_grid)

        # Help menu
        help_menu = menubar.addMenu("Help")
        self.action_about = QAction("About", self)
        help_menu.addAction(self.action_about)

    def _setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        # Open
        tb_open = QAction("📂 Open", self)
        tb_open.triggered.connect(self._on_open_file)
        toolbar.addAction(tb_open)

        toolbar.addSeparator()

        # Slice
        self.tb_slice = QAction("⚙ Slice", self)
        self.tb_slice.setEnabled(False)
        self.tb_slice.triggered.connect(self._on_slice)
        toolbar.addAction(self.tb_slice)

        # Export G-code
        self.tb_export = QAction("💾 Export G-code", self)
        self.tb_export.setEnabled(False)
        self.tb_export.triggered.connect(self._on_export_gcode)
        toolbar.addAction(self.tb_export)

        toolbar.addSeparator()

        # ---- View mode toggle buttons ----
        toolbar.addWidget(QLabel(" View: "))

        self._view_btn_model = QPushButton("3D Model")
        self._view_btn_model.setCheckable(True)
        self._view_btn_model.setChecked(True)
        self._view_btn_model.setToolTip("Show 3D mesh only")
        self._view_btn_model.setFixedHeight(26)
        self._view_btn_model.setStyleSheet(
            "QPushButton{padding:2px 8px;}"
            "QPushButton:checked{background:#3a7bd5;color:white;border-radius:3px;}"
        )
        toolbar.addWidget(self._view_btn_model)

        self._view_btn_layers = QPushButton("Layer Preview")
        self._view_btn_layers.setCheckable(True)
        self._view_btn_layers.setToolTip("Show sliced layer paths only")
        self._view_btn_layers.setFixedHeight(26)
        self._view_btn_layers.setStyleSheet(
            "QPushButton{padding:2px 8px;}"
            "QPushButton:checked{background:#3a7bd5;color:white;border-radius:3px;}"
        )
        toolbar.addWidget(self._view_btn_layers)

        self._view_btn_both = QPushButton("Both")
        self._view_btn_both.setCheckable(True)
        self._view_btn_both.setToolTip("Show transparent mesh + layer paths")
        self._view_btn_both.setFixedHeight(26)
        self._view_btn_both.setStyleSheet(
            "QPushButton{padding:2px 8px;}"
            "QPushButton:checked{background:#3a7bd5;color:white;border-radius:3px;}"
        )
        toolbar.addWidget(self._view_btn_both)

        # Exclusive group
        self._view_group = QButtonGroup(self)
        self._view_group.addButton(self._view_btn_model,  0)
        self._view_group.addButton(self._view_btn_layers, 1)
        self._view_group.addButton(self._view_btn_both,   2)
        self._view_group.setExclusive(True)
        self._view_group.idClicked.connect(self._on_view_mode_changed)

        toolbar.addSeparator()

        # Reset camera
        tb_reset_cam = QAction("⟳ Camera", self)
        tb_reset_cam.triggered.connect(self.viewport.reset_camera)
        toolbar.addAction(tb_reset_cam)

    def _setup_statusbar(self):
        statusbar = QStatusBar()
        self.setStatusBar(statusbar)

        # Status message
        self.status_label = QLabel("Ready")
        statusbar.addWidget(self.status_label, 1)

        # Separator
        statusbar.addWidget(QLabel("|"))

        # Layer count
        self.layers_label = QLabel("Layers: -")
        statusbar.addWidget(self.layers_label)

        statusbar.addWidget(QLabel("|"))

        # Print time
        self.time_label = QLabel("Est: --")
        statusbar.addWidget(self.time_label)

        statusbar.addWidget(QLabel("|"))

        # Filament
        self.filament_label = QLabel("Filament: --")
        statusbar.addWidget(self.filament_label)

        statusbar.addWidget(QLabel("|"))

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        statusbar.addPermanentWidget(self.progress_bar)

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self):
        # Menu
        self.action_open.triggered.connect(self._on_open_file)
        self.action_export_gcode.triggered.connect(self._on_export_gcode)
        self.action_exit.triggered.connect(self.close)
        self.action_reset_cam.triggered.connect(self.viewport.reset_camera)
        self.action_about.triggered.connect(self._on_about)

        # Left panel
        self.add_btn.clicked.connect(self._on_open_file)
        self.remove_btn.clicked.connect(self._on_remove_model)
        self.model_list.currentRowChanged.connect(self._on_model_selected)

        # Settings panel
        self.settings_panel.slice_requested.connect(self._on_slice)
        self.settings_panel.export_requested.connect(self._on_export_gcode)

        # Layer slider
        self.layer_slider.layer_changed.connect(self._on_layer_changed)

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def _on_open_file(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open 3D Model",
            "",
            "3D Models (*.stl *.obj *.ply *.3mf *.fbx *.step *.stp);;"
            "STL Files (*.stl);;"
            "OBJ Files (*.obj);;"
            "All Files (*)"
        )
        for path in paths:
            self._load_model(path)

    def _load_model(self, path: str):
        self.status_label.setText(f"Loading {os.path.basename(path)}...")
        try:
            tri_mesh = load_file(path)
            mesh = Mesh(tri_mesh, name=os.path.basename(path))

            # Center on bed
            bed_x, bed_y = self.settings_panel.get_bed_size()
            mesh.center_on_bed((bed_x, bed_y))

            self._meshes.append(mesh)

            # Add to list
            item = QListWidgetItem(mesh.name)
            item.setCheckState(Qt.CheckState.Checked)
            self.model_list.addItem(item)
            self.model_list.setCurrentRow(len(self._meshes) - 1)

            # Load into viewport
            self.viewport.load_mesh(tri_mesh)
            self.viewport.set_bed_size(bed_x, bed_y)

            # Enable slice
            self.tb_slice.setEnabled(True)
            self.settings_panel.set_slice_enabled(True)
            self.remove_btn.setEnabled(True)

            info = f"Loaded: {mesh.name} | {len(tri_mesh.vertices):,} verts | {len(tri_mesh.faces):,} faces"
            if mesh.is_watertight:
                info += f" | Vol: {mesh.volume/1000:.1f} cm³"
            self.status_label.setText(info)

        except Exception as e:
            self.status_label.setText(f"Error loading file: {e}")
            QMessageBox.critical(self, "Load Error",
                                 f"Failed to load {os.path.basename(path)}:\n\n{str(e)}")

    def _on_remove_model(self):
        row = self.model_list.currentRow()
        if row < 0 or row >= len(self._meshes):
            return
        self._meshes.pop(row)
        self.model_list.takeItem(row)

        if not self._meshes:
            self.viewport.clear_mesh()
            self.viewport.clear_layers()
            self.layer_slider.reset()
            self.tb_slice.setEnabled(False)
            self.tb_export.setEnabled(False)
            self.action_export_gcode.setEnabled(False)
            self.settings_panel.set_slice_enabled(False)
            self.settings_panel.set_export_enabled(False)
            self.remove_btn.setEnabled(False)
            self._gcode_str = None
            self._sliced_layers = []
        else:
            # Load new selection
            new_row = min(row, len(self._meshes) - 1)
            self.model_list.setCurrentRow(new_row)

    def _on_model_selected(self, row: int):
        if row < 0 or row >= len(self._meshes):
            return
        self._active_mesh_idx = row
        mesh = self._meshes[row]
        self.viewport.load_mesh(mesh.trimesh)

    # ------------------------------------------------------------------
    # Slicing
    # ------------------------------------------------------------------

    def _on_slice(self):
        if not self._meshes:
            QMessageBox.warning(self, "No Model", "Please load a 3D model first.")
            return

        if self._slice_thread and self._slice_thread.isRunning():
            return  # Already slicing

        # Get active mesh
        row = self.model_list.currentRow()
        if row < 0:
            row = 0
        mesh = self._meshes[row]

        settings = self.settings_panel.get_settings()

        # Reset layer view
        self.viewport.clear_layers()
        self.layer_slider.reset()
        self._sliced_layers = []
        self._gcode_str = None

        # Disable export
        self.tb_export.setEnabled(False)
        self.action_export_gcode.setEnabled(False)
        self.settings_panel.set_export_enabled(False)

        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText("Slicing...")

        # Create worker + thread
        self._slice_thread = QThread()
        self._slice_worker = SlicerWorker(mesh, settings)
        self._slice_worker.moveToThread(self._slice_thread)

        self._slice_thread.started.connect(self._slice_worker.run)
        self._slice_worker.progress.connect(self._on_slice_progress)
        self._slice_worker.finished.connect(self._on_slice_finished)
        self._slice_worker.error.connect(self._on_slice_error)
        self._slice_worker.finished.connect(self._slice_thread.quit)
        self._slice_worker.error.connect(self._slice_thread.quit)
        self._slice_thread.finished.connect(self._slice_thread.deleteLater)

        self._slice_thread.start()

    def _on_slice_progress(self, current: int, total: int, msg: str):
        if total > 0:
            pct = int(current * 100 / total)
            self.progress_bar.setValue(pct)
        self.status_label.setText(msg)

    def _on_slice_finished(self, layers: list, print_time_s: float, filament_g: float):
        self._sliced_layers = layers
        self.progress_bar.setValue(100)

        # Update layer slider
        self.layer_slider.set_layer_count(len(layers))

        # Upload layer paths to viewport
        self.viewport.load_layer_paths(layers)
        self.viewport.set_layer_preview(len(layers) - 1)

        # Auto-switch to "Both" view after slicing
        self._view_btn_both.setChecked(True)
        self.viewport.set_view_mode(ViewMode.BOTH)

        # Update status
        self.layers_label.setText(f"Layers: {len(layers)}")
        mins = int(print_time_s // 60)
        secs = int(print_time_s % 60)
        self.time_label.setText(f"Est: {mins}m {secs}s")
        self.filament_label.setText(f"Filament: {filament_g:.1f}g")

        self.status_label.setText(
            f"Slicing complete: {len(layers)} layers | "
            f"~{mins}m {secs}s | {filament_g:.1f}g"
        )

        # Hide progress after a moment
        self.progress_bar.setVisible(False)

        # Enable export
        self.tb_export.setEnabled(True)
        self.action_export_gcode.setEnabled(True)
        self.settings_panel.set_export_enabled(True)

    def _on_slice_error(self, msg: str):
        self.progress_bar.setVisible(False)
        self.status_label.setText("Slicing failed!")
        QMessageBox.critical(self, "Slice Error", msg)

    # ------------------------------------------------------------------
    # G-code export
    # ------------------------------------------------------------------

    def _on_export_gcode(self):
        if not self._sliced_layers:
            QMessageBox.warning(self, "No Layers", "Please slice the model first.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export G-code", "", "G-code Files (*.gcode *.g);;All Files (*)"
        )
        if not path:
            return

        try:
            settings = self.settings_panel.get_settings()
            printer_profile = self.settings_panel.get_printer_profile()

            gen = GCodeGenerator()
            gcode = gen.generate(self._sliced_layers, settings, printer_profile)
            self._gcode_str = gcode

            with open(path, 'w', encoding='utf-8') as f:
                f.write(gcode)

            size_kb = os.path.getsize(path) / 1024
            self.status_label.setText(
                f"G-code exported: {os.path.basename(path)} ({size_kb:.1f} KB)"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Error",
                                 f"Failed to export G-code:\n\n{str(e)}\n\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # View mode
    # ------------------------------------------------------------------

    def _on_view_mode_changed(self, btn_id: int):
        mode_map = {0: ViewMode.MODEL, 1: ViewMode.LAYERS, 2: ViewMode.BOTH}
        self.viewport.set_view_mode(mode_map.get(btn_id, ViewMode.MODEL))

    # ------------------------------------------------------------------
    # Layer preview
    # ------------------------------------------------------------------

    def _on_layer_changed(self, layer_idx: int):
        self.viewport.set_layer_preview(layer_idx)

    # ------------------------------------------------------------------
    # About dialog
    # ------------------------------------------------------------------

    def _on_about(self):
        QMessageBox.about(
            self,
            "About 3D Slicer Pro",
            "<h2>3D Slicer Pro</h2>"
            "<p>A production-quality 3D printer slicer application.</p>"
            "<p><b>Supported formats:</b> STL, OBJ, PLY, 3MF, FBX, STEP</p>"
            "<p><b>Output:</b> Marlin/Klipper compatible G-code</p>"
            "<hr>"
            "<p><b>Controls:</b><br>"
            "Left drag: Orbit camera<br>"
            "Middle drag: Pan camera<br>"
            "Scroll wheel: Zoom</p>"
        )

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_R:
            self.viewport.reset_camera()
        elif key == Qt.Key.Key_Delete:
            self._on_remove_model()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Close event
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        # Stop any running thread
        if self._slice_thread and self._slice_thread.isRunning():
            if self._slice_worker:
                self._slice_worker._slicer.cancel()
            self._slice_thread.quit()
            self._slice_thread.wait(3000)
        super().closeEvent(event)
