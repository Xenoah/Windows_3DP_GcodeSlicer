"""
Printer settings dialog.

Allows the user to add, edit, and delete printer profiles.
Profiles are stored in profiles/printers.json.
"""

import json
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QListWidget, QListWidgetItem, QPushButton, QLabel,
    QLineEdit, QDoubleSpinBox, QSpinBox,
    QPlainTextEdit, QDialogButtonBox, QGroupBox,
    QMessageBox, QInputDialog, QWidget, QFrame,
    QScrollArea, QSizePolicy, QSplitter
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


def _dspin(mn, mx, val, step=0.1, suffix="", decimals=2) -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setRange(mn, mx)
    w.setSingleStep(step)
    w.setValue(val)
    w.setDecimals(decimals)
    if suffix:
        w.setSuffix(suffix)
    return w


def _ispin(mn, mx, val, suffix="") -> QSpinBox:
    w = QSpinBox()
    w.setRange(mn, mx)
    w.setValue(val)
    if suffix:
        w.setSuffix(suffix)
    return w


class PrinterSettingsDialog(QDialog):
    """
    Dialog for adding, editing, and deleting printer profiles.

    Usage:
        dlg = PrinterSettingsDialog(profiles, profiles_path, parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            profiles = dlg.get_profiles()
    """

    def __init__(self, profiles: dict, profiles_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Printer Settings")
        self.setMinimumSize(760, 540)
        self.resize(820, 580)

        # Work on a deep copy; only write to disk on OK
        self._profiles = {k: dict(v) for k, v in profiles.items()}
        self._profiles_path = profiles_path
        self._current_name: str | None = None

        self._setup_ui()
        self._populate_list()
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Left column: list + buttons ──────────────────────────────
        left = QWidget()
        left.setFixedWidth(190)
        left.setObjectName("leftPane")
        left.setStyleSheet("#leftPane{background:#252525;}")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 8, 8)
        ll.setSpacing(6)

        lbl = QLabel("Printers")
        lbl.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        ll.addWidget(lbl)

        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget{background:#1e1e1e;border:1px solid #444;}"
            "QListWidget::item{padding:6px 4px;color:#ddd;}"
            "QListWidget::item:selected{background:#3a7bd5;color:white;}"
        )
        ll.addWidget(self._list, stretch=1)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("＋ Add")
        self._del_btn = QPushButton("Delete")
        self._add_btn.setToolTip("Add a new printer")
        self._del_btn.setToolTip("Delete selected printer")
        for b in (self._add_btn, self._del_btn):
            b.setFixedHeight(26)
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._del_btn)
        ll.addLayout(btn_row)

        root.addWidget(left)

        # ── Divider ──────────────────────────────────────────────────
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(div)

        # ── Right column: form ───────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(12, 8, 12, 8)
        rl.setSpacing(8)

        # Title
        self._title_lbl = QLabel("Select a printer to edit")
        self._title_lbl.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        rl.addWidget(self._title_lbl)

        # Scroll area for form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setSpacing(10)
        form_layout.setContentsMargins(0, 0, 0, 0)

        # ── Machine section ──────────────────────────────────────────
        machine_gb = QGroupBox("Machine")
        machine_form = QFormLayout(machine_gb)
        machine_form.setSpacing(6)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Printer name")
        machine_form.addRow("Name:", self._name_edit)

        # Bed size row
        bed_row = QHBoxLayout()
        self._bed_x = _dspin(10, 2000, 220, 10, " mm", 0)
        self._bed_y = _dspin(10, 2000, 220, 10, " mm", 0)
        self._bed_z = _dspin(10, 2000, 250, 10, " mm", 0)
        for lbl_txt, sp in [("W:", self._bed_x), ("D:", self._bed_y), ("H:", self._bed_z)]:
            bed_row.addWidget(QLabel(lbl_txt))
            bed_row.addWidget(sp)
        machine_form.addRow("Bed size:", bed_row)

        self._bed_temp_max = _ispin(0, 150, 100, " °C")
        self._bed_temp_max.setToolTip("0 = no heated bed")
        machine_form.addRow("Max bed temp:", self._bed_temp_max)

        form_layout.addWidget(machine_gb)

        # ── Extruder section ─────────────────────────────────────────
        ext_gb = QGroupBox("Extruder")
        ext_form = QFormLayout(ext_gb)
        ext_form.setSpacing(6)

        self._nozzle_diam = _dspin(0.1, 2.0, 0.4, 0.1, " mm")
        self._filament_diam = _dspin(1.0, 3.0, 1.75, 0.25, " mm")
        ext_form.addRow("Nozzle diameter:", self._nozzle_diam)
        ext_form.addRow("Filament diameter:", self._filament_diam)

        form_layout.addWidget(ext_gb)

        # ── Speed defaults section ────────────────────────────────────
        spd_gb = QGroupBox("Speed defaults")
        spd_form = QFormLayout(spd_gb)
        spd_form.setSpacing(6)

        self._max_speed     = _dspin(1, 1000, 200, 10, " mm/s", 0)
        self._default_speed = _dspin(1, 500,   60,  5, " mm/s", 0)
        self._default_layer = _dspin(0.05, 0.5, 0.2, 0.05, " mm")
        self._max_speed.setToolTip("Hardware maximum – UI sliders are capped to this")
        spd_form.addRow("Max print speed:", self._max_speed)
        spd_form.addRow("Default speed:",   self._default_speed)
        spd_form.addRow("Default layer height:", self._default_layer)

        form_layout.addWidget(spd_gb)

        # ── Retraction defaults ───────────────────────────────────────
        ret_gb = QGroupBox("Retraction defaults")
        ret_form = QFormLayout(ret_gb)
        ret_form.setSpacing(6)

        self._ret_dist  = _dspin(0, 15, 5.0, 0.5, " mm")
        self._ret_speed = _dspin(5, 120, 45, 5, " mm/s", 0)
        ret_form.addRow("Distance:", self._ret_dist)
        ret_form.addRow("Speed:",    self._ret_speed)

        form_layout.addWidget(ret_gb)

        # ── G-code ──────────────────────────────────────────────────
        gcode_gb = QGroupBox("G-code")
        gcode_vl = QVBoxLayout(gcode_gb)
        gcode_vl.setSpacing(4)

        mono = QFont("Courier New", 9)

        gcode_vl.addWidget(QLabel("Start G-code:"))
        self._start_gcode = QPlainTextEdit()
        self._start_gcode.setFont(mono)
        self._start_gcode.setFixedHeight(100)
        gcode_vl.addWidget(self._start_gcode)

        gcode_vl.addWidget(QLabel("End G-code:"))
        self._end_gcode = QPlainTextEdit()
        self._end_gcode.setFont(mono)
        self._end_gcode.setFixedHeight(80)
        gcode_vl.addWidget(self._end_gcode)

        hint = QLabel("Variables: {print_temp}  {bed_temp}  {nozzle_diameter}")
        hint.setStyleSheet("color:#888; font-size:10px;")
        gcode_vl.addWidget(hint)

        form_layout.addWidget(gcode_gb)
        form_layout.addStretch()

        scroll.setWidget(form_widget)
        rl.addWidget(scroll, stretch=1)

        # ── Apply button ─────────────────────────────────────────────
        apply_row = QHBoxLayout()
        self._apply_btn = QPushButton("Apply Changes")
        self._apply_btn.setFixedHeight(28)
        self._apply_btn.setStyleSheet(
            "QPushButton{background:#2a82da;color:white;border-radius:4px;padding:2px 12px;}"
            "QPushButton:hover{background:#3a92ea;}"
        )
        apply_row.addWidget(self._apply_btn)
        apply_row.addStretch()
        rl.addLayout(apply_row)

        # ── Dialog buttons ────────────────────────────────────────────
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._on_ok)
        btn_box.rejected.connect(self.reject)
        rl.addWidget(btn_box)

        root.addWidget(right, stretch=1)

        # Connections
        self._list.currentTextChanged.connect(self._on_printer_selected)
        self._add_btn.clicked.connect(self._on_add)
        self._del_btn.clicked.connect(self._on_delete)
        self._apply_btn.clicked.connect(self._on_apply)

    # ------------------------------------------------------------------
    # List management
    # ------------------------------------------------------------------

    def _populate_list(self):
        self._list.blockSignals(True)
        self._list.clear()
        for name in self._profiles:
            self._list.addItem(name)
        self._list.blockSignals(False)

    def _on_printer_selected(self, name: str):
        if not name or name not in self._profiles:
            return
        self._current_name = name
        self._title_lbl.setText(f"Editing: {name}")
        p = self._profiles[name]

        self._name_edit.setText(name)

        bed = p.get('bed_size', [220, 220])
        self._bed_x.setValue(float(bed[0]) if len(bed) > 0 else 220.0)
        self._bed_y.setValue(float(bed[1]) if len(bed) > 1 else 220.0)
        self._bed_z.setValue(float(p.get('bed_height', 250.0)))
        self._bed_temp_max.setValue(int(p.get('bed_temp_max', 100)))

        self._nozzle_diam.setValue(float(p.get('nozzle_diameter', 0.4)))
        self._filament_diam.setValue(float(p.get('filament_diameter', 1.75)))

        self._max_speed.setValue(float(p.get('max_print_speed', 200.0)))
        self._default_speed.setValue(float(p.get('default_print_speed', 60.0)))
        self._default_layer.setValue(float(p.get('default_layer_height', 0.2)))

        self._ret_dist.setValue(float(p.get('default_retraction_distance', 5.0)))
        self._ret_speed.setValue(float(p.get('default_retraction_speed', 45.0)))

        self._start_gcode.setPlainText(p.get('start_gcode', 'G28\nG92 E0'))
        self._end_gcode.setPlainText(p.get('end_gcode', 'M104 S0\nM140 S0\nM84'))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_apply(self):
        """Save form data to the in-memory profile dict."""
        if not self._current_name:
            return
        new_name = self._name_edit.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Invalid", "Printer name cannot be empty.")
            return

        data = {
            'bed_size':  [int(self._bed_x.value()), int(self._bed_y.value())],
            'bed_height': int(self._bed_z.value()),
            'bed_temp_max': self._bed_temp_max.value(),
            'nozzle_diameter': round(self._nozzle_diam.value(), 2),
            'filament_diameter': round(self._filament_diam.value(), 2),
            'max_print_speed': int(self._max_speed.value()),
            'default_print_speed': int(self._default_speed.value()),
            'default_layer_height': round(self._default_layer.value(), 2),
            'default_retraction_distance': round(self._ret_dist.value(), 1),
            'default_retraction_speed': int(self._ret_speed.value()),
            'start_gcode': self._start_gcode.toPlainText(),
            'end_gcode':   self._end_gcode.toPlainText(),
        }

        # Handle rename
        if new_name != self._current_name:
            if new_name in self._profiles:
                QMessageBox.warning(self, "Duplicate", f"'{new_name}' already exists.")
                return
            del self._profiles[self._current_name]
            self._current_name = new_name

        self._profiles[new_name] = data

        # Refresh list and re-select
        self._populate_list()
        items = self._list.findItems(new_name, Qt.MatchFlag.MatchExactly)
        if items:
            self._list.blockSignals(True)
            self._list.setCurrentItem(items[0])
            self._list.blockSignals(False)
        self._title_lbl.setText(f"Editing: {new_name}")

    def _on_add(self):
        name, ok = QInputDialog.getText(self, "Add Printer", "New printer name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self._profiles:
            QMessageBox.warning(self, "Exists", f"'{name}' already exists.")
            return

        self._profiles[name] = {
            'bed_size': [220, 220],
            'bed_height': 250,
            'bed_temp_max': 100,
            'nozzle_diameter': 0.4,
            'filament_diameter': 1.75,
            'max_print_speed': 200,
            'default_print_speed': 60,
            'default_layer_height': 0.2,
            'default_retraction_distance': 5.0,
            'default_retraction_speed': 45,
            'start_gcode': 'G28\nG92 E0',
            'end_gcode':   'M104 S0\nM140 S0\nM84',
        }
        self._populate_list()
        items = self._list.findItems(name, Qt.MatchFlag.MatchExactly)
        if items:
            self._list.setCurrentItem(items[0])

    def _on_delete(self):
        name = self._current_name
        if not name:
            return
        if len(self._profiles) <= 1:
            QMessageBox.information(self, "Cannot Delete", "At least one printer must remain.")
            return
        reply = QMessageBox.question(
            self, "Delete Printer",
            f"Delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            del self._profiles[name]
            self._current_name = None
            self._populate_list()
            if self._list.count() > 0:
                self._list.setCurrentRow(0)

    def _on_ok(self):
        # Auto-apply current form changes before saving
        if self._current_name:
            self._on_apply()

        # Write to printers.json
        try:
            # Only write the fields that printers.json uses
            out = {}
            for name, p in self._profiles.items():
                out[name] = {k: v for k, v in p.items()}
            with open(self._profiles_path, 'w', encoding='utf-8') as f:
                json.dump(out, f, indent=2, ensure_ascii=False)
        except Exception as e:
            QMessageBox.warning(self, "Save Error",
                                f"Could not write printers.json:\n{e}")
        self.accept()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_profiles(self) -> dict:
        """Return the (possibly modified) profiles dict."""
        return self._profiles
