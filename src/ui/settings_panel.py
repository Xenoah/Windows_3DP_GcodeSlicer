"""
Right panel with print settings tabs.
"""

import json
import os
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTabWidget, QGroupBox, QFormLayout, QDoubleSpinBox,
    QSpinBox, QCheckBox, QSlider, QPushButton, QSizePolicy,
    QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from src.core.slicer import SliceSettings


class SettingsPanel(QWidget):
    """
    Right panel containing print settings organized in tabs.
    Emits settings_changed when any setting changes.
    Emits slice_requested when SLICE button is clicked.
    Emits export_requested when Export G-code button is clicked.
    """

    settings_changed = pyqtSignal(object)   # SliceSettings
    slice_requested = pyqtSignal()
    export_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(290)
        self._profiles_dir = self._find_profiles_dir()
        self._printer_profiles = self._load_printer_profiles()
        self._material_profiles = self._load_material_profiles()
        self._settings = SliceSettings()
        self._building = False  # suppress signals during setup
        self._setup_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # Profile loading
    # ------------------------------------------------------------------

    def _find_profiles_dir(self) -> str:
        here = os.path.dirname(os.path.abspath(__file__))
        # Go up to project root
        root = os.path.dirname(os.path.dirname(here))
        return os.path.join(root, 'profiles')

    def _load_printer_profiles(self) -> dict:
        path = os.path.join(self._profiles_dir, 'printers.json')
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            return {
                'Generic Printer': {
                    'bed_size': [220, 220],
                    'nozzle_diameter': 0.4,
                    'filament_diameter': 1.75,
                    'start_gcode': 'G28\nG92 E0',
                    'end_gcode': 'M104 S0\nM140 S0\nM84',
                }
            }

    def _load_material_profiles(self) -> dict:
        path = os.path.join(self._profiles_dir, 'materials.json')
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            return {
                'PLA': {'print_temp': 210, 'bed_temp': 60, 'fan_speed': 100, 'retraction': 5.0}
            }

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        # Printer selector
        printer_group = QGroupBox("Printer")
        printer_layout = QFormLayout(printer_group)
        printer_layout.setSpacing(4)

        self.printer_combo = QComboBox()
        for name in self._printer_profiles:
            self.printer_combo.addItem(name)
        printer_layout.addRow("Profile:", self.printer_combo)

        self.material_combo = QComboBox()
        for name in self._material_profiles:
            self.material_combo.addItem(name)
        printer_layout.addRow("Material:", self.material_combo)
        layout.addWidget(printer_group)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_print_tab(), "Print")
        self.tabs.addTab(self._build_support_tab(), "Support")
        self.tabs.addTab(self._build_speed_tab(), "Speed")
        self.tabs.addTab(self._build_temp_tab(), "Temp")
        layout.addWidget(self.tabs)

        # Spacer
        layout.addStretch(1)

        # SLICE button
        self.slice_btn = QPushButton("SLICE NOW")
        self.slice_btn.setMinimumHeight(44)
        self.slice_btn.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        self.slice_btn.setStyleSheet(
            "QPushButton { background: #E87722; color: white; border-radius: 6px; }"
            "QPushButton:hover { background: #FF8C32; }"
            "QPushButton:pressed { background: #C06010; }"
            "QPushButton:disabled { background: #555; color: #888; }"
        )
        layout.addWidget(self.slice_btn)

        # Export G-code button
        self.export_btn = QPushButton("Export G-code")
        self.export_btn.setMinimumHeight(32)
        self.export_btn.setEnabled(False)
        self.export_btn.setStyleSheet(
            "QPushButton { background: #2255AA; color: white; border-radius: 4px; }"
            "QPushButton:hover { background: #3366CC; }"
            "QPushButton:pressed { background: #1144AA; }"
            "QPushButton:disabled { background: #333; color: #666; }"
        )
        layout.addWidget(self.export_btn)

    def _build_print_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        layout.setSpacing(6)

        # Layer height
        self.layer_height_spin = QDoubleSpinBox()
        self.layer_height_spin.setRange(0.05, 0.5)
        self.layer_height_spin.setSingleStep(0.05)
        self.layer_height_spin.setValue(0.2)
        self.layer_height_spin.setSuffix(" mm")
        layout.addRow("Layer height:", self.layer_height_spin)

        # First layer height
        self.first_layer_spin = QDoubleSpinBox()
        self.first_layer_spin.setRange(0.1, 0.8)
        self.first_layer_spin.setSingleStep(0.05)
        self.first_layer_spin.setValue(0.3)
        self.first_layer_spin.setSuffix(" mm")
        layout.addRow("First layer:", self.first_layer_spin)

        # Wall count
        self.wall_count_spin = QSpinBox()
        self.wall_count_spin.setRange(1, 10)
        self.wall_count_spin.setValue(3)
        layout.addRow("Walls:", self.wall_count_spin)

        # Infill density
        infill_layout = QHBoxLayout()
        self.infill_slider = QSlider(Qt.Orientation.Horizontal)
        self.infill_slider.setRange(0, 100)
        self.infill_slider.setValue(20)
        self.infill_spin = QSpinBox()
        self.infill_spin.setRange(0, 100)
        self.infill_spin.setValue(20)
        self.infill_spin.setSuffix("%")
        self.infill_spin.setFixedWidth(60)
        infill_layout.addWidget(self.infill_slider)
        infill_layout.addWidget(self.infill_spin)
        layout.addRow("Infill:", infill_layout)

        # Infill pattern
        self.infill_pattern_combo = QComboBox()
        self.infill_pattern_combo.addItems(['grid', 'lines', 'honeycomb'])
        layout.addRow("Pattern:", self.infill_pattern_combo)

        # Top/Bottom layers
        self.top_layers_spin = QSpinBox()
        self.top_layers_spin.setRange(0, 20)
        self.top_layers_spin.setValue(4)
        layout.addRow("Top layers:", self.top_layers_spin)

        self.bottom_layers_spin = QSpinBox()
        self.bottom_layers_spin.setRange(0, 20)
        self.bottom_layers_spin.setValue(4)
        layout.addRow("Bottom layers:", self.bottom_layers_spin)

        # Brim
        brim_layout = QHBoxLayout()
        self.brim_check = QCheckBox("Enable")
        self.brim_width_spin = QDoubleSpinBox()
        self.brim_width_spin.setRange(1.0, 30.0)
        self.brim_width_spin.setValue(8.0)
        self.brim_width_spin.setSuffix(" mm")
        self.brim_width_spin.setEnabled(False)
        brim_layout.addWidget(self.brim_check)
        brim_layout.addWidget(self.brim_width_spin)
        layout.addRow("Brim:", brim_layout)

        # Retraction
        self.retraction_check = QCheckBox("Retraction")
        self.retraction_check.setChecked(True)
        layout.addRow("", self.retraction_check)

        self.retraction_dist_spin = QDoubleSpinBox()
        self.retraction_dist_spin.setRange(0.0, 15.0)
        self.retraction_dist_spin.setValue(5.0)
        self.retraction_dist_spin.setSuffix(" mm")
        layout.addRow("Retract dist:", self.retraction_dist_spin)

        return w

    def _build_support_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        layout.setSpacing(6)

        self.support_check = QCheckBox("Enable supports")
        self.support_check.setChecked(False)
        layout.addRow(self.support_check)

        # Overhang threshold
        thresh_layout = QHBoxLayout()
        self.support_thresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.support_thresh_slider.setRange(20, 80)
        self.support_thresh_slider.setValue(45)
        self.support_thresh_label = QLabel("45°")
        self.support_thresh_label.setFixedWidth(35)
        thresh_layout.addWidget(self.support_thresh_slider)
        thresh_layout.addWidget(self.support_thresh_label)
        layout.addRow("Overhang:", thresh_layout)

        # Support density
        self.support_density_spin = QSpinBox()
        self.support_density_spin.setRange(5, 50)
        self.support_density_spin.setValue(20)
        self.support_density_spin.setSuffix("%")
        layout.addRow("Support density:", self.support_density_spin)

        return w

    def _build_speed_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        layout.setSpacing(6)

        self.print_speed_spin = QDoubleSpinBox()
        self.print_speed_spin.setRange(10, 300)
        self.print_speed_spin.setValue(60)
        self.print_speed_spin.setSuffix(" mm/s")
        layout.addRow("Print speed:", self.print_speed_spin)

        self.first_layer_speed_spin = QDoubleSpinBox()
        self.first_layer_speed_spin.setRange(5, 100)
        self.first_layer_speed_spin.setValue(25)
        self.first_layer_speed_spin.setSuffix(" mm/s")
        layout.addRow("First layer:", self.first_layer_speed_spin)

        self.infill_speed_spin = QDoubleSpinBox()
        self.infill_speed_spin.setRange(10, 500)
        self.infill_speed_spin.setValue(80)
        self.infill_speed_spin.setSuffix(" mm/s")
        layout.addRow("Infill speed:", self.infill_speed_spin)

        self.travel_speed_spin = QDoubleSpinBox()
        self.travel_speed_spin.setRange(50, 500)
        self.travel_speed_spin.setValue(200)
        self.travel_speed_spin.setSuffix(" mm/s")
        layout.addRow("Travel speed:", self.travel_speed_spin)

        return w

    def _build_temp_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        layout.setSpacing(6)

        self.print_temp_spin = QSpinBox()
        self.print_temp_spin.setRange(150, 300)
        self.print_temp_spin.setValue(210)
        self.print_temp_spin.setSuffix(" °C")
        layout.addRow("Extruder:", self.print_temp_spin)

        self.bed_temp_spin = QSpinBox()
        self.bed_temp_spin.setRange(0, 150)
        self.bed_temp_spin.setValue(60)
        self.bed_temp_spin.setSuffix(" °C")
        layout.addRow("Bed:", self.bed_temp_spin)

        # Fan speed
        fan_layout = QHBoxLayout()
        self.fan_slider = QSlider(Qt.Orientation.Horizontal)
        self.fan_slider.setRange(0, 100)
        self.fan_slider.setValue(100)
        self.fan_label = QLabel("100%")
        self.fan_label.setFixedWidth(40)
        fan_layout.addWidget(self.fan_slider)
        fan_layout.addWidget(self.fan_label)
        layout.addRow("Fan:", fan_layout)

        return w

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self):
        # Printer/material
        self.printer_combo.currentTextChanged.connect(self._on_printer_changed)
        self.material_combo.currentTextChanged.connect(self._on_material_changed)

        # Print tab
        self.layer_height_spin.valueChanged.connect(self._on_settings_changed)
        self.first_layer_spin.valueChanged.connect(self._on_settings_changed)
        self.wall_count_spin.valueChanged.connect(self._on_settings_changed)
        self.infill_slider.valueChanged.connect(self._sync_infill_slider)
        self.infill_spin.valueChanged.connect(self._sync_infill_spin)
        self.infill_pattern_combo.currentTextChanged.connect(self._on_settings_changed)
        self.top_layers_spin.valueChanged.connect(self._on_settings_changed)
        self.bottom_layers_spin.valueChanged.connect(self._on_settings_changed)
        self.brim_check.toggled.connect(self._on_brim_toggled)
        self.brim_width_spin.valueChanged.connect(self._on_settings_changed)
        self.retraction_check.toggled.connect(self._on_settings_changed)
        self.retraction_dist_spin.valueChanged.connect(self._on_settings_changed)

        # Support tab
        self.support_check.toggled.connect(self._on_settings_changed)
        self.support_thresh_slider.valueChanged.connect(self._on_support_thresh_changed)
        self.support_density_spin.valueChanged.connect(self._on_settings_changed)

        # Speed tab
        self.print_speed_spin.valueChanged.connect(self._on_settings_changed)
        self.first_layer_speed_spin.valueChanged.connect(self._on_settings_changed)
        self.infill_speed_spin.valueChanged.connect(self._on_settings_changed)
        self.travel_speed_spin.valueChanged.connect(self._on_settings_changed)

        # Temp tab
        self.print_temp_spin.valueChanged.connect(self._on_settings_changed)
        self.bed_temp_spin.valueChanged.connect(self._on_settings_changed)
        self.fan_slider.valueChanged.connect(self._on_fan_changed)

        # Buttons
        self.slice_btn.clicked.connect(self.slice_requested)
        self.export_btn.clicked.connect(self.export_requested)

    def _sync_infill_slider(self, value):
        self.infill_spin.blockSignals(True)
        self.infill_spin.setValue(value)
        self.infill_spin.blockSignals(False)
        self._on_settings_changed()

    def _sync_infill_spin(self, value):
        self.infill_slider.blockSignals(True)
        self.infill_slider.setValue(value)
        self.infill_slider.blockSignals(False)
        self._on_settings_changed()

    def _on_brim_toggled(self, checked):
        self.brim_width_spin.setEnabled(checked)
        self._on_settings_changed()

    def _on_support_thresh_changed(self, value):
        self.support_thresh_label.setText(f"{value}°")
        self._on_settings_changed()

    def _on_fan_changed(self, value):
        self.fan_label.setText(f"{value}%")
        self._on_settings_changed()

    def _on_printer_changed(self, name):
        profile = self._printer_profiles.get(name, {})
        bed = profile.get('bed_size', [220, 220])
        self.settings_changed.emit(self.get_settings())

    def _on_material_changed(self, name):
        mat = self._material_profiles.get(name, {})
        self._building = True
        if 'print_temp' in mat:
            self.print_temp_spin.setValue(mat['print_temp'])
        if 'bed_temp' in mat:
            self.bed_temp_spin.setValue(mat['bed_temp'])
        if 'fan_speed' in mat:
            self.fan_slider.setValue(int(mat['fan_speed']))
            self.fan_label.setText(f"{int(mat['fan_speed'])}%")
        if 'retraction' in mat:
            self.retraction_dist_spin.setValue(mat['retraction'])
        self._building = False
        self._on_settings_changed()

    def _on_settings_changed(self):
        if self._building:
            return
        s = self.get_settings()
        self.settings_changed.emit(s)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_settings(self) -> SliceSettings:
        """Return current SliceSettings from UI state."""
        s = SliceSettings()
        s.layer_height = self.layer_height_spin.value()
        s.first_layer_height = self.first_layer_spin.value()
        s.wall_count = self.wall_count_spin.value()
        s.line_width = 0.4  # fixed for now (nozzle diameter)
        s.infill_density = float(self.infill_spin.value())
        s.infill_pattern = self.infill_pattern_combo.currentText()
        s.top_layers = self.top_layers_spin.value()
        s.bottom_layers = self.bottom_layers_spin.value()
        s.brim_enabled = self.brim_check.isChecked()
        s.brim_width = self.brim_width_spin.value()
        s.retraction_enabled = self.retraction_check.isChecked()
        s.retraction_distance = self.retraction_dist_spin.value()
        s.support_enabled = self.support_check.isChecked()
        s.support_threshold = float(self.support_thresh_slider.value())
        s.support_density = float(self.support_density_spin.value())
        s.print_speed = self.print_speed_spin.value()
        s.first_layer_speed = self.first_layer_speed_spin.value()
        s.infill_speed = self.infill_speed_spin.value()
        s.travel_speed = self.travel_speed_spin.value()
        s.print_temp = self.print_temp_spin.value()
        s.bed_temp = self.bed_temp_spin.value()
        s.fan_speed = self.fan_slider.value()

        # From printer profile
        printer_name = self.printer_combo.currentText()
        profile = self._printer_profiles.get(printer_name, {})
        s.filament_diameter = float(profile.get('filament_diameter', 1.75))
        s.nozzle_diameter = float(profile.get('nozzle_diameter', 0.4))
        s.line_width = s.nozzle_diameter

        return s

    def get_printer_profile(self) -> dict:
        """Return the currently selected printer profile dict."""
        name = self.printer_combo.currentText()
        return self._printer_profiles.get(name, {})

    def get_bed_size(self) -> tuple:
        """Return (x, y) bed size from current printer profile."""
        profile = self.get_printer_profile()
        bed = profile.get('bed_size', [220, 220])
        return float(bed[0]), float(bed[1])

    def set_export_enabled(self, enabled: bool):
        self.export_btn.setEnabled(enabled)

    def set_slice_enabled(self, enabled: bool):
        self.slice_btn.setEnabled(enabled)
