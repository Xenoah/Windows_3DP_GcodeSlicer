"""
Settings panel – right sidebar.

Tabs:
  Print    – layer, walls, infill, brim
  Quality  – line width, seam, overlaps, retraction, z-hop
  Speed    – per-feature speeds, min layer time
  Support  – support structure settings
  Temp/Fan – temperatures + cooling fan

Preset system:
  Built-in presets live in profiles/presets/_builtin/
  User presets saved to profiles/presets/<name>.json
"""

import json
import os
import sys
import dataclasses

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QTabWidget, QGroupBox,
    QDoubleSpinBox, QSpinBox, QCheckBox, QSlider,
    QPushButton, QSizePolicy, QScrollArea, QFrame,
    QButtonGroup, QRadioButton, QInputDialog, QMessageBox,
    QTextEdit, QColorDialog, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor

from src.core.slicer import SliceSettings
from src.ui.printer_dialog import PrinterSettingsDialog
try:
    from src.ui.themes import THEME_NAMES
except ImportError:
    THEME_NAMES = ["Dark", "Darker", "Ocean", "Solarized Dark", "Light", "High Contrast", "Custom"]


MIT_LICENSE_TEXT = """\
MIT License

Copyright (c) 2026 Xenoah

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

_DEFAULT_CUSTOM_COLORS = {
    'background': '#1e1e1e',
    'text':       '#dcdcdc',
    'accent':     '#2a82da',
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scroll(inner: QWidget) -> QScrollArea:
    """Wrap a widget in a scroll area."""
    sa = QScrollArea()
    sa.setWidget(inner)
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    return sa


def _group(title: str, layout_type=QFormLayout) -> tuple:
    """Return (QGroupBox, layout)."""
    gb = QGroupBox(title)
    gb.setStyleSheet("QGroupBox{font-weight:bold;margin-top:6px;}"
                     "QGroupBox::title{subcontrol-origin:margin;left:6px;}")
    lo = layout_type(gb)
    lo.setSpacing(5)
    lo.setContentsMargins(6, 14, 6, 6)
    return gb, lo


def _dspin(mn, mx, val, step=0.05, suffix="", decimals=2) -> QDoubleSpinBox:
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


def _slider_row(mn, mx, val, label_fmt="{} %") -> tuple:
    """Return (QHBoxLayout, QSlider, QLabel) for a slider+value row."""
    row = QHBoxLayout()
    sl = QSlider(Qt.Orientation.Horizontal)
    sl.setRange(mn, mx)
    sl.setValue(val)
    lbl = QLabel(label_fmt.format(val))
    lbl.setFixedWidth(44)
    row.addWidget(sl)
    row.addWidget(lbl)
    return row, sl, lbl


# ---------------------------------------------------------------------------
# SettingsPanel
# ---------------------------------------------------------------------------

class SettingsPanel(QWidget):
    """
    Expanded settings panel with 5 tabs.
    Signals:
        settings_changed(SliceSettings)
        slice_requested()
        export_requested()
    """

    settings_changed = pyqtSignal(object)
    slice_requested  = pyqtSignal()
    export_requested = pyqtSignal()
    theme_changed    = pyqtSignal(str, dict)   # (theme_name, custom_colors)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(300)

        self._profiles_dir        = self._find_profiles_dir()
        self._printer_profiles    = self._load_json('printers.json',  _default_printers())
        self._material_profiles   = self._load_json('materials.json', _default_materials())
        self._building            = False
        self._current_theme       = 'Dark'
        self._custom_colors       = dict(_DEFAULT_CUSTOM_COLORS)

        # セッション自動保存タイマー（最後の変更から 600ms 後に保存）
        self._session_timer = QTimer(self)
        self._session_timer.setSingleShot(True)
        self._session_timer.setInterval(600)
        self._session_timer.timeout.connect(self._save_session)

        self._setup_ui()
        self._build_theme_dialog()   # theme widgets created here (not in a tab)
        self._connect_signals()
        # Apply initial printer defaults (suppresses spurious signals)
        self._on_printer_changed(self.printer_combo.currentText())

    # -----------------------------------------------------------------------
    # Profile loading
    # -----------------------------------------------------------------------

    def _find_profiles_dir(self) -> str:
        # When running as a PyInstaller frozen exe, sys._MEIPASS is the
        # extracted bundle root; data files live there.
        if getattr(sys, 'frozen', False):
            return os.path.join(sys._MEIPASS, 'profiles')
        here = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(os.path.dirname(os.path.dirname(here)), 'profiles')

    def _load_json(self, filename: str, fallback: dict) -> dict:
        # profiles/ ディレクトリがなければ作成（EXE 配布・初回起動時対策）
        os.makedirs(self._profiles_dir, exist_ok=True)
        path = os.path.join(self._profiles_dir, filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            # ファイルがなければデフォルト内容で新規作成
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(fallback, f, indent=2, ensure_ascii=False)
                print(f"[Settings] Created default {filename}")
            except Exception as e:
                print(f"[Settings] Could not create {filename}: {e}")
            return fallback
        except Exception as e:
            print(f"[Settings] Failed to load {filename}: {e}")
            return fallback

    # -----------------------------------------------------------------------
    # UI setup
    # -----------------------------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(4)
        root.setContentsMargins(4, 4, 4, 4)

        # ── Printer / Material selectors ──────────────────────────────────
        top_gb, top_lo = _group("Machine", QFormLayout)

        # Printer row: combo + settings button
        printer_row = QHBoxLayout()
        self.printer_combo = QComboBox()
        for n in self._printer_profiles:
            self.printer_combo.addItem(n)
        self.printer_settings_btn = QPushButton("⚙")
        self.printer_settings_btn.setFixedSize(24, 24)
        self.printer_settings_btn.setToolTip("Edit / add printer profiles")
        self.printer_settings_btn.setStyleSheet(
            "QPushButton{background:#444;border-radius:3px;font-size:12px;}"
            "QPushButton:hover{background:#3a7bd5;}"
        )
        printer_row.addWidget(self.printer_combo, stretch=1)
        printer_row.addWidget(self.printer_settings_btn)

        self.material_combo = QComboBox()
        for n in self._material_profiles:
            self.material_combo.addItem(n)
        top_lo.addRow("Printer:", printer_row)
        top_lo.addRow("Material:", self.material_combo)
        root.addWidget(top_gb)

        # ── Preset bar ────────────────────────────────────────────────────
        preset_gb, preset_lo = _group("Presets", QVBoxLayout)
        pr_row1 = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(140)
        self._refresh_preset_combo()
        pr_row1.addWidget(self.preset_combo, stretch=1)
        preset_lo.addLayout(pr_row1)

        pr_row2 = QHBoxLayout()
        self.preset_load_btn   = QPushButton("Load")
        self.preset_save_btn   = QPushButton("Save…")
        self.preset_delete_btn = QPushButton("Delete")
        self.preset_delete_btn.setToolTip("Delete selected user preset")
        for b in (self.preset_load_btn, self.preset_save_btn, self.preset_delete_btn):
            b.setFixedHeight(24)
        pr_row2.addWidget(self.preset_load_btn)
        pr_row2.addWidget(self.preset_save_btn)
        pr_row2.addWidget(self.preset_delete_btn)
        preset_lo.addLayout(pr_row2)
        root.addWidget(preset_gb)

        # ── Settings tools ────────────────────────────────────────────────
        tools_row = QHBoxLayout()
        self.reset_btn           = QPushButton("↺ Reset")
        self.import_settings_btn = QPushButton("Import…")
        self.export_settings_btn = QPushButton("Export…")
        for b in (self.reset_btn, self.import_settings_btn, self.export_settings_btn):
            b.setFixedHeight(24)
        self.reset_btn.setToolTip("Reset all settings to defaults (Generic Printer)")
        self.import_settings_btn.setToolTip("Import settings from a JSON file")
        self.export_settings_btn.setToolTip("Export current settings to a JSON file")
        tools_row.addWidget(self.reset_btn)
        tools_row.addWidget(self.import_settings_btn)
        tools_row.addWidget(self.export_settings_btn)
        root.addLayout(tools_row)

        # ── Tabs ─────────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.addTab(_scroll(self._tab_print()),   "Print")
        self.tabs.addTab(_scroll(self._tab_quality()), "Quality")
        self.tabs.addTab(_scroll(self._tab_speed()),   "Speed")
        self.tabs.addTab(_scroll(self._tab_support()), "Support")
        self.tabs.addTab(_scroll(self._tab_tempfan()), "Temp/Fan")
        root.addWidget(self.tabs, stretch=1)

        # ── Buttons ──────────────────────────────────────────────────────
        self.slice_btn = QPushButton("SLICE NOW")
        self.slice_btn.setEnabled(False)
        self.slice_btn.setMinimumHeight(44)
        self.slice_btn.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        self.slice_btn.setStyleSheet(
            "QPushButton{background:#E87722;color:white;border-radius:6px;}"
            "QPushButton:hover{background:#FF8C32;}"
            "QPushButton:pressed{background:#C06010;}"
            "QPushButton:disabled{background:#555;color:#888;}"
        )
        root.addWidget(self.slice_btn)

        self.export_btn = QPushButton("Export G-code")
        self.export_btn.setMinimumHeight(32)
        self.export_btn.setEnabled(False)
        self.export_btn.setStyleSheet(
            "QPushButton{background:#2255AA;color:white;border-radius:4px;}"
            "QPushButton:hover{background:#3366CC;}"
            "QPushButton:disabled{background:#333;color:#666;}"
        )
        root.addWidget(self.export_btn)

    # -----------------------------------------------------------------------
    # Tab: Print
    # -----------------------------------------------------------------------

    def _tab_print(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(4, 4, 4, 4)
        vl.setSpacing(6)

        # Layer heights
        gb1, lo1 = _group("Layer")
        self.layer_height_spin       = _dspin(0.05, 0.50, 0.20, 0.05, " mm")
        self.first_layer_height_spin = _dspin(0.10, 0.80, 0.30, 0.05, " mm")
        lo1.addRow("Layer height:",       self.layer_height_spin)
        lo1.addRow("First layer height:", self.first_layer_height_spin)
        vl.addWidget(gb1)

        # Walls
        gb2, lo2 = _group("Walls")
        self.wall_count_spin = _ispin(1, 10, 3)
        self.outer_before_inner_chk = QCheckBox("Outer wall first")
        self.outer_before_inner_chk.setChecked(False)
        lo2.addRow("Wall count:", self.wall_count_spin)
        lo2.addRow("", self.outer_before_inner_chk)
        vl.addWidget(gb2)

        # Spiralize (Non-stop / Vase) mode
        gb_sp, lo_sp = _group("Non-stop (Spiralize / Vase)")
        self.spiralize_chk = QCheckBox("ノンストップ印刷モード（つなぎ目なし）")
        self.spiralize_chk.setToolTip(
            "各層の外周を連続螺旋状に印刷します。\n"
            "Z上昇と横移動を同時に行うためつなぎ目がなくなります。\n"
            "インフィル・トップ層は無視され、ベース層のみソリッドになります。"
        )
        lo_sp.addRow("", self.spiralize_chk)
        vl.addWidget(gb_sp)

        # Infill
        gb3, lo3 = _group("Infill")
        row_inf, self.infill_slider, self.infill_val_lbl = _slider_row(0, 100, 20, "{} %")
        self.infill_pattern_combo = QComboBox()
        self.infill_pattern_combo.addItems(['grid', 'lines', 'honeycomb'])
        self.infill_angle_spin = _dspin(0, 90, 45, 5, " °", 0)
        lo3.addRow("Infill density:", row_inf)
        lo3.addRow("Pattern:",        self.infill_pattern_combo)
        lo3.addRow("Angle:",          self.infill_angle_spin)
        vl.addWidget(gb3)

        # Top / Bottom
        gb4, lo4 = _group("Top / Bottom layers")
        self.top_layers_spin    = _ispin(0, 20, 4)
        self.bottom_layers_spin = _ispin(0, 20, 4)
        lo4.addRow("Top layers:",    self.top_layers_spin)
        lo4.addRow("Bottom layers:", self.bottom_layers_spin)
        vl.addWidget(gb4)

        # Brim
        gb5, lo5 = _group("Brim")
        self.brim_check      = QCheckBox("Enable brim")
        self.brim_width_spin = _dspin(1.0, 30.0, 8.0, 1.0, " mm")
        self.brim_width_spin.setEnabled(False)
        lo5.addRow("", self.brim_check)
        lo5.addRow("Brim width:", self.brim_width_spin)
        vl.addWidget(gb5)

        vl.addStretch()
        return w

    # -----------------------------------------------------------------------
    # Tab: Quality
    # -----------------------------------------------------------------------

    def _tab_quality(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(4, 4, 4, 4)
        vl.setSpacing(6)

        # Line width
        gb1, lo1 = _group("Extrusion width")
        self.line_width_pct_spin = _dspin(70, 150, 100, 5, " %", 0)
        self.line_width_pct_spin.setToolTip("% of nozzle diameter (100% = 0.4mm for 0.4mm nozzle)")
        lo1.addRow("Line width:", self.line_width_pct_spin)
        vl.addWidget(gb1)

        # Seam
        gb2, lo2 = _group("Seam position")
        self.seam_combo = QComboBox()
        self.seam_combo.addItems(['back', 'random', 'sharpest'])
        self.seam_combo.setToolTip(
            "back: seam always at the back of the model\n"
            "random: random position each layer\n"
            "sharpest: nearest sharp corner"
        )
        lo2.addRow("Seam:", self.seam_combo)
        vl.addWidget(gb2)

        # Overlap
        gb3, lo3 = _group("Overlap / adhesion")
        self.infill_overlap_spin  = _dspin(0, 50, 10, 1, " %", 0)
        self.skin_overlap_spin    = _dspin(0, 50,  5, 1, " %", 0)
        self.infill_overlap_spin.setToolTip("How far infill extends into the perimeter")
        self.skin_overlap_spin.setToolTip("How far top/bottom extends into the perimeter")
        lo3.addRow("Infill overlap:", self.infill_overlap_spin)
        lo3.addRow("Skin overlap:",   self.skin_overlap_spin)
        vl.addWidget(gb3)

        # Retraction
        gb4, lo4 = _group("Retraction")
        self.retraction_check         = QCheckBox("Enable retraction")
        self.retraction_check.setChecked(True)
        self.retraction_dist_spin     = _dspin(0, 15, 5.0, 0.5, " mm")
        self.retraction_speed_spin    = _dspin(5, 120, 45, 5, " mm/s", 0)
        self.retraction_min_dist_spin = _dspin(0, 10, 1.5, 0.5, " mm")
        self.retraction_extra_spin    = _dspin(0, 2.0, 0.0, 0.05, " mm")
        lo4.addRow("", self.retraction_check)
        lo4.addRow("Distance:",       self.retraction_dist_spin)
        lo4.addRow("Speed:",          self.retraction_speed_spin)
        lo4.addRow("Min travel:",     self.retraction_min_dist_spin)
        lo4.addRow("Extra prime:",    self.retraction_extra_spin)
        self.retraction_min_dist_spin.setToolTip("Minimum travel distance to trigger retraction")
        self.retraction_extra_spin.setToolTip("Extra filament extruded after de-retraction")
        vl.addWidget(gb4)

        # Z-hop
        gb5, lo5 = _group("Z-hop (lift on travel)")
        self.z_hop_spin = _dspin(0, 2.0, 0.0, 0.05, " mm")
        self.z_hop_spin.setToolTip("Lift nozzle this height during travel moves (0 = off)")
        lo5.addRow("Z-hop height:", self.z_hop_spin)
        vl.addWidget(gb5)

        vl.addStretch()
        return w

    # -----------------------------------------------------------------------
    # Tab: Speed
    # -----------------------------------------------------------------------

    def _tab_speed(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(4, 4, 4, 4)
        vl.setSpacing(6)

        gb1, lo1 = _group("Print speeds")
        self.outer_perim_speed_spin = _dspin(5, 300, 40, 5, " mm/s", 0)
        self.print_speed_spin       = _dspin(5, 300, 60, 5, " mm/s", 0)
        self.top_bottom_speed_spin  = _dspin(5, 300, 40, 5, " mm/s", 0)
        self.infill_speed_spin      = _dspin(5, 500, 80, 5, " mm/s", 0)
        self.bridge_speed_spin      = _dspin(5, 200, 25, 5, " mm/s", 0)
        self.outer_perim_speed_spin.setToolTip("Outer wall – slower for better surface quality")
        self.bridge_speed_spin.setToolTip("Speed when bridging gaps without support")
        lo1.addRow("Outer wall:",   self.outer_perim_speed_spin)
        lo1.addRow("Inner wall:",   self.print_speed_spin)
        lo1.addRow("Top/Bottom:",   self.top_bottom_speed_spin)
        lo1.addRow("Infill:",       self.infill_speed_spin)
        lo1.addRow("Bridge:",       self.bridge_speed_spin)
        vl.addWidget(gb1)

        gb2, lo2 = _group("First layer & travel")
        self.first_layer_speed_spin = _dspin(5, 100, 25, 5, " mm/s", 0)
        self.travel_speed_spin      = _dspin(20, 500, 200, 10, " mm/s", 0)
        self.first_layer_speed_spin.setToolTip("All features are printed at this speed on layer 1")
        lo2.addRow("First layer:",  self.first_layer_speed_spin)
        lo2.addRow("Travel:",       self.travel_speed_spin)
        vl.addWidget(gb2)

        gb3, lo3 = _group("Layer time")
        self.min_layer_time_spin = _dspin(0, 60, 5, 1, " s", 0)
        self.min_layer_time_spin.setToolTip(
            "Minimum time per layer. Print speed is reduced if layer would finish faster."
        )
        lo3.addRow("Min layer time:", self.min_layer_time_spin)
        vl.addWidget(gb3)

        vl.addStretch()
        return w

    # -----------------------------------------------------------------------
    # Tab: Support
    # -----------------------------------------------------------------------

    def _tab_support(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(4, 4, 4, 4)
        vl.setSpacing(6)

        gb1, lo1 = _group("Support structure")
        self.support_check = QCheckBox("Enable supports")
        row_thr, self.support_thresh_slider, self.support_thresh_lbl = \
            _slider_row(20, 80, 45, "{}°")
        self.support_thresh_slider.setToolTip(
            "Faces angled more than this from vertical get support"
        )
        self.support_pattern_combo = QComboBox()
        self.support_pattern_combo.addItems(['lines', 'grid', 'zigzag'])
        row_den, self.support_density_slider, self.support_density_lbl = \
            _slider_row(5, 50, 15, "{} %")
        lo1.addRow("", self.support_check)
        lo1.addRow("Overhang angle:", row_thr)
        lo1.addRow("Pattern:", self.support_pattern_combo)
        lo1.addRow("Density:", row_den)
        vl.addWidget(gb1)

        gb2, lo2 = _group("Support distance")
        self.support_z_dist_spin  = _dspin(0, 2.0, 0.20, 0.05, " mm")
        self.support_xy_dist_spin = _dspin(0, 3.0, 0.70, 0.05, " mm")
        self.support_z_dist_spin.setToolTip("Gap between support top/bottom and model")
        self.support_xy_dist_spin.setToolTip("Horizontal gap between support and model sides")
        lo2.addRow("Z distance:",  self.support_z_dist_spin)
        lo2.addRow("XY distance:", self.support_xy_dist_spin)
        vl.addWidget(gb2)

        gb3, lo3 = _group("Support interface")
        self.support_iface_check  = QCheckBox("Interface layers")
        self.support_iface_check.setChecked(True)
        self.support_iface_layers = _ispin(1, 8, 2, " layers")
        self.support_iface_check.setToolTip(
            "Dense layers at the top of supports for easier removal"
        )
        lo3.addRow("", self.support_iface_check)
        lo3.addRow("Count:", self.support_iface_layers)
        vl.addWidget(gb3)

        vl.addStretch()
        return w

    # -----------------------------------------------------------------------
    # Tab: Temp / Fan
    # -----------------------------------------------------------------------

    def _tab_tempfan(self) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(4, 4, 4, 4)
        vl.setSpacing(6)

        gb1, lo1 = _group("Extruder temperature")
        self.print_temp_spin            = _ispin(150, 310, 210, " °C")
        self.print_temp_first_layer_spin = _ispin(150, 310, 215, " °C")
        self.print_temp_first_layer_spin.setToolTip(
            "Higher temp on first layer improves bed adhesion"
        )
        lo1.addRow("Normal temp:",      self.print_temp_spin)
        lo1.addRow("First layer temp:", self.print_temp_first_layer_spin)
        vl.addWidget(gb1)

        gb2, lo2 = _group("Bed temperature")
        self.bed_temp_spin = _ispin(0, 150, 60, " °C")
        lo2.addRow("Bed:", self.bed_temp_spin)
        vl.addWidget(gb2)

        gb3, lo3 = _group("Cooling fan")
        row_fan, self.fan_slider, self.fan_lbl = _slider_row(0, 100, 100)
        row_fl,  self.fan_fl_slider, self.fan_fl_lbl = _slider_row(0, 100, 0)
        self.fan_kick_layer_spin = _ispin(1, 20, 2, " layers")
        self.fan_kick_layer_spin.setToolTip("Fan starts at this layer number")
        lo3.addRow("Normal speed:",       row_fan)
        lo3.addRow("First layer speed:",  row_fl)
        lo3.addRow("Start fan at layer:", self.fan_kick_layer_spin)
        vl.addWidget(gb3)

        vl.addStretch()
        return w

    # -----------------------------------------------------------------------
    # Theme dialog (accessed via Setting > Theme… in the menu bar)
    # -----------------------------------------------------------------------

    def _build_theme_dialog(self):
        """Create the persistent theme dialog and all theme widgets."""
        from PyQt6.QtWidgets import QDialog
        from PyQt6.QtCore import Qt as _Qt

        dlg = QDialog(self)
        dlg.setWindowTitle("Theme Settings")
        dlg.setMinimumWidth(300)
        dlg.setWindowFlag(_Qt.WindowType.WindowContextHelpButtonHint, False)

        lo = QVBoxLayout(dlg)
        lo.setSpacing(8)
        lo.setContentsMargins(10, 10, 10, 10)

        # ── Theme combo ───────────────────────────────────────────────────
        theme_row = QHBoxLayout()
        theme_lbl = QLabel("Theme:")
        theme_lbl.setFixedWidth(70)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(THEME_NAMES)
        idx = self.theme_combo.findText(self._current_theme)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        theme_row.addWidget(theme_lbl)
        theme_row.addWidget(self.theme_combo, stretch=1)
        lo.addLayout(theme_row)

        # ── Custom color pickers (shown only when "Custom" selected) ──────
        self.custom_colors_widget = QWidget()
        cl = QFormLayout(self.custom_colors_widget)
        cl.setContentsMargins(0, 4, 0, 0)
        cl.setSpacing(6)

        self.color_bg_btn     = QPushButton()
        self.color_text_btn   = QPushButton()
        self.color_accent_btn = QPushButton()
        for b in (self.color_bg_btn, self.color_text_btn, self.color_accent_btn):
            b.setFixedHeight(24)

        cl.addRow("Background:", self.color_bg_btn)
        cl.addRow("Text:",       self.color_text_btn)
        cl.addRow("Accent:",     self.color_accent_btn)
        lo.addWidget(self.custom_colors_widget)
        self.custom_colors_widget.setVisible(False)

        self._update_color_swatches()

        # ── Close button ──────────────────────────────────────────────────
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.hide)
        lo.addStretch()
        lo.addWidget(close_btn)

        self._theme_dlg = dlg

    def show_theme_dialog(self):
        """Show the theme dialog (called from main_window Setting menu)."""
        self._theme_dlg.show()
        self._theme_dlg.raise_()
        self._theme_dlg.activateWindow()

    # -----------------------------------------------------------------------
    # Signal connections
    # -----------------------------------------------------------------------

    def _connect_signals(self):
        self.printer_combo.currentTextChanged.connect(self._on_printer_changed)
        self.material_combo.currentTextChanged.connect(self._on_material_changed)
        self.printer_settings_btn.clicked.connect(self._on_printer_settings)

        # Print tab
        self.layer_height_spin.valueChanged.connect(self._emit)
        self.first_layer_height_spin.valueChanged.connect(self._emit)
        self.wall_count_spin.valueChanged.connect(self._emit)
        self.outer_before_inner_chk.toggled.connect(self._emit)
        self.infill_slider.valueChanged.connect(self._on_infill_slider)
        self.infill_pattern_combo.currentTextChanged.connect(self._emit)
        self.infill_angle_spin.valueChanged.connect(self._emit)
        self.top_layers_spin.valueChanged.connect(self._emit)
        self.bottom_layers_spin.valueChanged.connect(self._emit)
        self.spiralize_chk.toggled.connect(self._emit)
        self.brim_check.toggled.connect(self._on_brim_toggle)
        self.brim_width_spin.valueChanged.connect(self._emit)

        # Quality tab
        self.line_width_pct_spin.valueChanged.connect(self._emit)
        self.seam_combo.currentTextChanged.connect(self._emit)
        self.infill_overlap_spin.valueChanged.connect(self._emit)
        self.skin_overlap_spin.valueChanged.connect(self._emit)
        self.retraction_check.toggled.connect(self._on_retraction_toggle)
        self.retraction_dist_spin.valueChanged.connect(self._emit)
        self.retraction_speed_spin.valueChanged.connect(self._emit)
        self.retraction_min_dist_spin.valueChanged.connect(self._emit)
        self.retraction_extra_spin.valueChanged.connect(self._emit)
        self.z_hop_spin.valueChanged.connect(self._emit)

        # Speed tab
        self.outer_perim_speed_spin.valueChanged.connect(self._emit)
        self.print_speed_spin.valueChanged.connect(self._emit)
        self.top_bottom_speed_spin.valueChanged.connect(self._emit)
        self.infill_speed_spin.valueChanged.connect(self._emit)
        self.bridge_speed_spin.valueChanged.connect(self._emit)
        self.first_layer_speed_spin.valueChanged.connect(self._emit)
        self.travel_speed_spin.valueChanged.connect(self._emit)
        self.min_layer_time_spin.valueChanged.connect(self._emit)

        # Support tab
        self.support_check.toggled.connect(self._emit)
        self.support_thresh_slider.valueChanged.connect(self._on_support_thresh)
        self.support_pattern_combo.currentTextChanged.connect(self._emit)
        self.support_density_slider.valueChanged.connect(self._on_support_density)
        self.support_z_dist_spin.valueChanged.connect(self._emit)
        self.support_xy_dist_spin.valueChanged.connect(self._emit)
        self.support_iface_check.toggled.connect(self._emit)
        self.support_iface_layers.valueChanged.connect(self._emit)

        # Temp/Fan tab
        self.print_temp_spin.valueChanged.connect(self._emit)
        self.print_temp_first_layer_spin.valueChanged.connect(self._emit)
        self.bed_temp_spin.valueChanged.connect(self._emit)
        self.fan_slider.valueChanged.connect(self._on_fan)
        self.fan_fl_slider.valueChanged.connect(self._on_fan_fl)
        self.fan_kick_layer_spin.valueChanged.connect(self._emit)

        # Tools row (reset / import / export settings)
        self.reset_btn.clicked.connect(self._on_reset)
        self.import_settings_btn.clicked.connect(self._on_import_settings)
        self.export_settings_btn.clicked.connect(self._on_export_settings)

        # Preset buttons
        self.preset_load_btn.clicked.connect(self._on_preset_load)
        self.preset_save_btn.clicked.connect(self._on_preset_save)
        self.preset_delete_btn.clicked.connect(self._on_preset_delete)

        # Help tab – theme
        self.theme_combo.currentTextChanged.connect(self._on_theme_combo_changed)
        self.color_bg_btn.clicked.connect(lambda: self._pick_color('background'))
        self.color_text_btn.clicked.connect(lambda: self._pick_color('text'))
        self.color_accent_btn.clicked.connect(lambda: self._pick_color('accent'))

        # Buttons
        self.slice_btn.clicked.connect(self.slice_requested)
        self.export_btn.clicked.connect(self.export_requested)

    # -----------------------------------------------------------------------
    # Slot helpers
    # -----------------------------------------------------------------------

    def _emit(self, *_):
        if not self._building:
            self.settings_changed.emit(self.get_settings())
            self._session_timer.start()  # デバウンス: 600ms 後に自動保存

    def _on_infill_slider(self, v):
        self.infill_val_lbl.setText(f"{v} %")
        self._emit()

    def _on_brim_toggle(self, checked):
        self.brim_width_spin.setEnabled(checked)
        self._emit()

    def _on_retraction_toggle(self, checked):
        for w in (self.retraction_dist_spin, self.retraction_speed_spin,
                  self.retraction_min_dist_spin, self.retraction_extra_spin,
                  self.z_hop_spin):
            w.setEnabled(checked)
        self._emit()

    def _on_support_thresh(self, v):
        self.support_thresh_lbl.setText(f"{v}°")
        self._emit()

    def _on_support_density(self, v):
        self.support_density_lbl.setText(f"{v} %")
        self._emit()

    def _on_fan(self, v):
        self.fan_lbl.setText(f"{v} %")
        self._emit()

    def _on_fan_fl(self, v):
        self.fan_fl_lbl.setText(f"{v} %")
        self._emit()

    # -----------------------------------------------------------------------
    # Reset / Import / Export settings
    # -----------------------------------------------------------------------

    def _on_reset(self):
        """Reset all settings to defaults using Generic Printer."""
        reply = QMessageBox.question(
            self, "Reset Settings",
            "Reset all settings to defaults?\n\nPrinter will be set to Generic Printer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._apply_preset_data(self._get_default_data())
        self._session_timer.start()

    def _get_default_data(self) -> dict:
        return {
            '_printer': 'Generic Printer', '_material': 'PLA',
            'layer_height': 0.2,   'first_layer_height': 0.3,
            'wall_count': 3,       'outer_before_inner': False,
            'spiralize_mode': False,
            'infill_density': 20,  'infill_pattern': 'grid', 'infill_angle': 45.0,
            'top_layers': 4,       'bottom_layers': 4,
            'brim_enabled': False, 'brim_width': 8.0,
            'line_width_pct': 100.0, 'seam_position': 'back',
            'infill_overlap': 10.0, 'skin_overlap': 5.0,
            'retraction_enabled': True,
            'retraction_distance': 5.0,   'retraction_speed': 45.0,
            'retraction_min_distance': 1.5, 'retraction_extra_prime': 0.0,
            'retraction_z_hop': 0.0,
            'outer_perimeter_speed': 40.0, 'print_speed': 60.0,
            'top_bottom_speed': 40.0,      'infill_speed': 80.0,
            'bridge_speed': 25.0,          'first_layer_speed': 25.0,
            'travel_speed': 200.0,         'min_layer_time': 5.0,
            'support_enabled': False,      'support_threshold': 45,
            'support_pattern': 'lines',    'support_density': 15,
            'support_z_distance': 0.2,     'support_xy_distance': 0.7,
            'support_interface_enabled': True, 'support_interface_layers': 2,
            'print_temp': 210, 'print_temp_first_layer': 215, 'bed_temp': 60,
            'fan_speed': 100,  'fan_first_layer': 0,          'fan_kick_in_layer': 2,
        }

    def _on_import_settings(self):
        """Import settings from a user-chosen JSON file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Settings", "",
            "Settings files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._apply_preset_data(data)
            # Restore theme if present
            if '_theme' in data:
                self._current_theme   = data['_theme']
                self._custom_colors   = data.get('_custom_colors', dict(_DEFAULT_CUSTOM_COLORS))
                idx = self.theme_combo.findText(self._current_theme)
                if idx >= 0:
                    self.theme_combo.blockSignals(True)
                    self.theme_combo.setCurrentIndex(idx)
                    self.theme_combo.blockSignals(False)
                self.custom_colors_widget.setVisible(self._current_theme == 'Custom')
                self._update_color_swatches()
                self.theme_changed.emit(self._current_theme, self._custom_colors)
            self._session_timer.start()
        except Exception as e:
            QMessageBox.warning(self, "Import Error", f"Failed to import settings:\n{e}")

    def _on_export_settings(self):
        """Export current settings to a user-chosen JSON file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Settings", "settings.json",
            "Settings files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            s    = self.get_settings()
            data = dataclasses.asdict(s)
            data['_printer']      = self.printer_combo.currentText()
            data['_material']     = self.material_combo.currentText()
            data['_theme']        = self._current_theme
            data['_custom_colors'] = self._custom_colors
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Exported",
                                    f"Settings saved to:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Export Error", f"Failed to export settings:\n{e}")

    # -----------------------------------------------------------------------
    # Printer / Material changed
    # -----------------------------------------------------------------------

    def _on_printer_changed(self, name: str):
        profile = self._printer_profiles.get(name, {})
        self._building = True

        # Bed temp constraints
        bed_max = int(profile.get('bed_temp_max', 100))
        self.bed_temp_spin.setMaximum(max(bed_max, 0))
        has_bed = bed_max > 0
        self.bed_temp_spin.setEnabled(has_bed)
        self.bed_temp_spin.setToolTip("" if has_bed else "No heated bed on this printer")
        if not has_bed:
            self.bed_temp_spin.setValue(0)

        # Speed constraints
        max_spd = float(profile.get('max_print_speed', 300))
        for sp in (self.outer_perim_speed_spin, self.print_speed_spin,
                   self.top_bottom_speed_spin, self.bridge_speed_spin,
                   self.first_layer_speed_spin):
            sp.setMaximum(max_spd)
        self.infill_speed_spin.setMaximum(max_spd * 1.5)
        self.travel_speed_spin.setMaximum(max_spd * 3)

        # Apply printer-specific defaults
        if 'default_print_speed' in profile:
            spd = float(profile['default_print_speed'])
            self.outer_perim_speed_spin.setValue(spd * 0.6)
            self.print_speed_spin.setValue(spd)
            self.top_bottom_speed_spin.setValue(spd * 0.6)
            self.infill_speed_spin.setValue(min(spd * 1.3, max_spd))
            self.bridge_speed_spin.setValue(spd * 0.5)
            self.first_layer_speed_spin.setValue(spd * 0.5)
            self.travel_speed_spin.setValue(min(spd * 3, 200))

        if 'default_layer_height' in profile:
            lh = float(profile['default_layer_height'])
            self.layer_height_spin.setValue(lh)
            self.first_layer_height_spin.setValue(lh)

        if 'default_retraction_distance' in profile:
            self.retraction_dist_spin.setValue(float(profile['default_retraction_distance']))

        if 'default_retraction_speed' in profile:
            self.retraction_speed_spin.setValue(float(profile['default_retraction_speed']))

        self._building = False
        self._emit()  # settings_changed emit + セッション保存タイマー起動

    def _on_printer_settings(self):
        """Open the printer configuration dialog."""
        profiles_path = os.path.join(self._profiles_dir, 'printers.json')
        dlg = PrinterSettingsDialog(
            self._printer_profiles, profiles_path, parent=self
        )
        if dlg.exec() == PrinterSettingsDialog.DialogCode.Accepted:
            # Reload profiles and refresh the combo
            current = self.printer_combo.currentText()
            self._printer_profiles = dlg.get_profiles()

            self.printer_combo.blockSignals(True)
            self.printer_combo.clear()
            for n in self._printer_profiles:
                self.printer_combo.addItem(n)
            # Restore selection if still present
            idx = self.printer_combo.findText(current)
            self.printer_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.printer_combo.blockSignals(False)

            # Re-apply printer defaults
            self._on_printer_changed(self.printer_combo.currentText())

    def _on_material_changed(self, name: str):
        mat = self._material_profiles.get(name, {})
        self._building = True
        if 'print_temp' in mat:
            t = int(mat['print_temp'])
            self.print_temp_spin.setValue(t)
            self.print_temp_first_layer_spin.setValue(min(t + 5, 310))
        if 'bed_temp' in mat and self.bed_temp_spin.isEnabled():
            self.bed_temp_spin.setValue(int(mat['bed_temp']))
        if 'fan_speed' in mat:
            self.fan_slider.setValue(int(mat['fan_speed']))
        if 'retraction' in mat:
            self.retraction_dist_spin.setValue(float(mat['retraction']))
        self._building = False
        self._emit()

    # -----------------------------------------------------------------------
    # Preset system
    # -----------------------------------------------------------------------

    def _presets_dir(self) -> str:
        d = os.path.join(self._profiles_dir, 'presets')
        os.makedirs(d, exist_ok=True)
        return d

    def _user_preset_files(self) -> dict:
        """Return {display_name: filepath} for all user presets."""
        d = self._presets_dir()
        result = {}
        for fn in sorted(os.listdir(d)):
            if fn.endswith('.json') and not fn.startswith('_'):
                name = fn[:-5]  # strip .json
                result[name] = os.path.join(d, fn)
        return result

    def _refresh_preset_combo(self):
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()

        # Built-in presets
        for name in _BUILTIN_PRESETS:
            self.preset_combo.addItem(f"[Built-in] {name}")

        # User presets
        for name in self._user_preset_files():
            self.preset_combo.addItem(name)

        self.preset_combo.blockSignals(False)

    def _on_preset_load(self):
        text = self.preset_combo.currentText()
        if not text:
            return

        if text.startswith("[Built-in] "):
            key = text[len("[Built-in] "):]
            data = _BUILTIN_PRESETS.get(key, {})
            self._apply_preset_data(data)
            return

        # User preset
        files = self._user_preset_files()
        path = files.get(text)
        if path and os.path.isfile(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._apply_preset_data(data)
            except Exception as e:
                QMessageBox.warning(self, "Preset Error", f"Failed to load preset:\n{e}")

    def _on_preset_save(self):
        # Get name from user
        name, ok = QInputDialog.getText(
            self, "Save Preset", "Preset name:",
            text=self.preset_combo.currentText().replace("[Built-in] ", "")
        )
        if not ok or not name.strip():
            return
        name = name.strip().replace('/', '_').replace('\\', '_')

        s = self.get_settings()
        data = dataclasses.asdict(s)
        # Also store which printer/material is selected
        data['_printer'] = self.printer_combo.currentText()
        data['_material'] = self.material_combo.currentText()

        path = os.path.join(self._presets_dir(), f"{name}.json")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            self._refresh_preset_combo()
            # Select the saved preset
            idx = self.preset_combo.findText(name)
            if idx >= 0:
                self.preset_combo.setCurrentIndex(idx)
            QMessageBox.information(self, "Saved", f"Preset '{name}' saved.")
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Could not save preset:\n{e}")

    def _on_preset_delete(self):
        text = self.preset_combo.currentText()
        if text.startswith("[Built-in] "):
            QMessageBox.information(self, "Cannot Delete", "Built-in presets cannot be deleted.")
            return
        files = self._user_preset_files()
        path = files.get(text)
        if not path:
            return
        reply = QMessageBox.question(
            self, "Delete Preset",
            f"Delete preset '{text}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                os.remove(path)
                self._refresh_preset_combo()
            except Exception as e:
                QMessageBox.warning(self, "Delete Error", str(e))

    def _apply_preset_data(self, data: dict):
        """Apply a preset dict to all UI controls."""
        self._building = True
        try:
            # Printer / material
            if '_printer' in data:
                idx = self.printer_combo.findText(data['_printer'])
                if idx >= 0:
                    self.printer_combo.setCurrentIndex(idx)
            if '_material' in data:
                idx = self.material_combo.findText(data['_material'])
                if idx >= 0:
                    self.material_combo.setCurrentIndex(idx)

            def sv(spin, key):
                if key in data and spin is not None:
                    try: spin.setValue(data[key])
                    except Exception: pass

            def sc(chk, key):
                if key in data and chk is not None:
                    chk.setChecked(bool(data[key]))

            def scombo(combo, key):
                if key in data and combo is not None:
                    idx = combo.findText(str(data[key]))
                    if idx >= 0: combo.setCurrentIndex(idx)

            # Print tab
            sc(self.spiralize_chk,           'spiralize_mode')
            sv(self.layer_height_spin,       'layer_height')
            sv(self.first_layer_height_spin, 'first_layer_height')
            sv(self.wall_count_spin,         'wall_count')
            sc(self.outer_before_inner_chk,  'outer_before_inner')
            if 'infill_density' in data:
                self.infill_slider.setValue(int(data['infill_density']))
            scombo(self.infill_pattern_combo,'infill_pattern')
            sv(self.infill_angle_spin,       'infill_angle')
            sv(self.top_layers_spin,         'top_layers')
            sv(self.bottom_layers_spin,      'bottom_layers')
            sc(self.brim_check,              'brim_enabled')
            sv(self.brim_width_spin,         'brim_width')

            # Quality tab
            sv(self.line_width_pct_spin,      'line_width_pct')
            scombo(self.seam_combo,           'seam_position')
            sv(self.infill_overlap_spin,      'infill_overlap')
            sv(self.skin_overlap_spin,        'skin_overlap')
            sc(self.retraction_check,         'retraction_enabled')
            sv(self.retraction_dist_spin,     'retraction_distance')
            sv(self.retraction_speed_spin,    'retraction_speed')
            sv(self.retraction_min_dist_spin, 'retraction_min_distance')
            sv(self.retraction_extra_spin,    'retraction_extra_prime')
            sv(self.z_hop_spin,               'retraction_z_hop')

            # Speed tab
            sv(self.outer_perim_speed_spin,  'outer_perimeter_speed')
            sv(self.print_speed_spin,        'print_speed')
            sv(self.top_bottom_speed_spin,   'top_bottom_speed')
            sv(self.infill_speed_spin,       'infill_speed')
            sv(self.bridge_speed_spin,       'bridge_speed')
            sv(self.first_layer_speed_spin,  'first_layer_speed')
            sv(self.travel_speed_spin,       'travel_speed')
            sv(self.min_layer_time_spin,     'min_layer_time')

            # Support tab
            sc(self.support_check,           'support_enabled')
            if 'support_threshold' in data:
                self.support_thresh_slider.setValue(int(data['support_threshold']))
            scombo(self.support_pattern_combo,'support_pattern')
            if 'support_density' in data:
                self.support_density_slider.setValue(int(data['support_density']))
            sv(self.support_z_dist_spin,     'support_z_distance')
            sv(self.support_xy_dist_spin,    'support_xy_distance')
            sc(self.support_iface_check,     'support_interface_enabled')
            sv(self.support_iface_layers,    'support_interface_layers')

            # Temp/Fan tab
            sv(self.print_temp_spin,              'print_temp')
            sv(self.print_temp_first_layer_spin,  'print_temp_first_layer')
            if self.bed_temp_spin.isEnabled():
                sv(self.bed_temp_spin,            'bed_temp')
            if 'fan_speed' in data:
                self.fan_slider.setValue(int(data['fan_speed']))
            if 'fan_first_layer' in data:
                self.fan_fl_slider.setValue(int(data['fan_first_layer']))
            sv(self.fan_kick_layer_spin,          'fan_kick_in_layer')

        finally:
            self._building = False
            self._emit()

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def get_settings(self) -> SliceSettings:
        s = SliceSettings()

        # Printer profile
        pname = self.printer_combo.currentText()
        prof  = self._printer_profiles.get(pname, {})
        s.nozzle_diameter   = float(prof.get('nozzle_diameter',   0.4))
        s.filament_diameter = float(prof.get('filament_diameter', 1.75))

        # Layer / extrusion
        s.layer_height       = self.layer_height_spin.value()
        s.first_layer_height = self.first_layer_height_spin.value()
        s.line_width_pct     = self.line_width_pct_spin.value()
        s.line_width         = s.nozzle_diameter * s.line_width_pct / 100.0

        # Spiralize mode
        s.spiralize_mode = self.spiralize_chk.isChecked()

        # Walls
        s.wall_count         = self.wall_count_spin.value()
        s.outer_before_inner = self.outer_before_inner_chk.isChecked()
        s.seam_position      = self.seam_combo.currentText()

        # Infill
        s.infill_density  = float(self.infill_slider.value())
        s.infill_pattern  = self.infill_pattern_combo.currentText()
        s.infill_angle    = self.infill_angle_spin.value()
        s.infill_overlap  = self.infill_overlap_spin.value()

        # Top/bottom
        s.top_layers    = self.top_layers_spin.value()
        s.bottom_layers = self.bottom_layers_spin.value()
        s.skin_overlap  = self.skin_overlap_spin.value()

        # Brim
        s.brim_enabled = self.brim_check.isChecked()
        s.brim_width   = self.brim_width_spin.value()

        # Retraction
        s.retraction_enabled      = self.retraction_check.isChecked()
        s.retraction_distance     = self.retraction_dist_spin.value()
        s.retraction_speed        = self.retraction_speed_spin.value()
        s.retraction_min_distance = self.retraction_min_dist_spin.value()
        s.retraction_extra_prime  = self.retraction_extra_spin.value()
        s.retraction_z_hop        = self.z_hop_spin.value()

        # Speeds
        s.outer_perimeter_speed = self.outer_perim_speed_spin.value()
        s.print_speed           = self.print_speed_spin.value()
        s.top_bottom_speed      = self.top_bottom_speed_spin.value()
        s.infill_speed          = self.infill_speed_spin.value()
        s.bridge_speed          = self.bridge_speed_spin.value()
        s.first_layer_speed     = self.first_layer_speed_spin.value()
        s.travel_speed          = self.travel_speed_spin.value()
        s.min_layer_time        = self.min_layer_time_spin.value()

        # Support
        s.support_enabled           = self.support_check.isChecked()
        s.support_threshold         = float(self.support_thresh_slider.value())
        s.support_pattern           = self.support_pattern_combo.currentText()
        s.support_density           = float(self.support_density_slider.value())
        s.support_z_distance        = self.support_z_dist_spin.value()
        s.support_xy_distance       = self.support_xy_dist_spin.value()
        s.support_interface_enabled = self.support_iface_check.isChecked()
        s.support_interface_layers  = self.support_iface_layers.value()

        # Temp / fan
        s.print_temp             = self.print_temp_spin.value()
        s.print_temp_first_layer = self.print_temp_first_layer_spin.value()
        s.bed_temp               = self.bed_temp_spin.value()
        s.fan_speed              = self.fan_slider.value()
        s.fan_first_layer        = self.fan_fl_slider.value()
        s.fan_kick_in_layer      = self.fan_kick_layer_spin.value()

        return s

    # -----------------------------------------------------------------------
    # Theme handling
    # -----------------------------------------------------------------------

    def _on_theme_combo_changed(self, name: str):
        self._current_theme = name
        self.custom_colors_widget.setVisible(name == 'Custom')
        self.theme_changed.emit(name, self._custom_colors)
        self._session_timer.start()

    def _pick_color(self, key: str):
        """Open a color picker and update the custom color for key."""
        current = QColor(self._custom_colors.get(key, '#888888'))
        color = QColorDialog.getColor(current, self, f"Pick {key} color")
        if color.isValid():
            self._custom_colors[key] = color.name()
            self._update_color_swatches()
            if self._current_theme == 'Custom':
                self.theme_changed.emit('Custom', self._custom_colors)
                self._session_timer.start()

    def _update_color_swatches(self):
        """Update button backgrounds to show chosen custom colors."""
        def _swatch(btn, key):
            col = self._custom_colors.get(key, '#888888')
            c   = QColor(col)
            lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
            txt = '#000000' if lum > 128 else '#ffffff'
            btn.setText(col)
            btn.setStyleSheet(
                f"background-color:{col};color:{txt};border:1px solid #888;"
                "border-radius:2px;"
            )
        _swatch(self.color_bg_btn,     'background')
        _swatch(self.color_text_btn,   'text')
        _swatch(self.color_accent_btn, 'accent')

    # -----------------------------------------------------------------------
    # Session persistence (auto-save / restore)
    # -----------------------------------------------------------------------

    def _session_path(self) -> str:
        """セッション保存ファイルのパス。"""
        return os.path.join(self._profiles_dir, 'session.json')

    def _save_session(self):
        """現在の全設定を session.json へ保存する（タイマーから呼ばれる）。"""
        try:
            s = self.get_settings()
            data = dataclasses.asdict(s)
            data['_printer']       = self.printer_combo.currentText()
            data['_material']      = self.material_combo.currentText()
            data['_theme']         = self._current_theme
            data['_custom_colors'] = self._custom_colors
            with open(self._session_path(), 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Settings] Session save failed: {e}")

    def load_session(self):
        """session.json から前回の設定を復元する（起動時に呼ぶ）。"""
        path = self._session_path()
        if not os.path.isfile(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._apply_preset_data(data)

            # Restore theme
            if '_theme' in data:
                self._current_theme = data['_theme']
                if '_custom_colors' in data:
                    self._custom_colors = data['_custom_colors']
                self._update_color_swatches()
                self.theme_combo.blockSignals(True)
                idx = self.theme_combo.findText(self._current_theme)
                if idx >= 0:
                    self.theme_combo.setCurrentIndex(idx)
                self.theme_combo.blockSignals(False)
                self.custom_colors_widget.setVisible(self._current_theme == 'Custom')
                # Emit so main_window applies theme on startup
                self.theme_changed.emit(self._current_theme, self._custom_colors)
        except Exception as e:
            print(f"[Settings] Session load failed: {e}")

    def get_printer_profile(self) -> dict:
        return self._printer_profiles.get(self.printer_combo.currentText(), {})

    def get_bed_size(self) -> tuple:
        bed = self.get_printer_profile().get('bed_size', [220, 220])
        return float(bed[0]), float(bed[1])

    def set_slice_enabled(self, enabled: bool):
        self.slice_btn.setEnabled(enabled)

    def set_export_enabled(self, enabled: bool):
        self.export_btn.setEnabled(enabled)


# ---------------------------------------------------------------------------
# Fallback defaults
# ---------------------------------------------------------------------------

def _default_printers() -> dict:
    """Full printer list – used as fallback AND to recreate printers.json if missing."""
    return {
        'Bambu Lab X1C': {
            'bed_size': [256, 256], 'bed_temp_max': 120,
            'nozzle_diameter': 0.4, 'filament_diameter': 1.75,
            'max_print_speed': 500, 'default_print_speed': 200,
            'default_layer_height': 0.2,
            'default_retraction_distance': 1.0, 'default_retraction_speed': 45,
            'start_gcode': 'G28\nG29\nG92 E0',
            'end_gcode': 'M104 S0\nM140 S0\nG28 X0\nM84',
        },
        'Bambu Lab P1P': {
            'bed_size': [256, 256], 'bed_temp_max': 100,
            'nozzle_diameter': 0.4, 'filament_diameter': 1.75,
            'max_print_speed': 500, 'default_print_speed': 200,
            'default_layer_height': 0.2,
            'default_retraction_distance': 1.0, 'default_retraction_speed': 45,
            'start_gcode': 'G28\nG92 E0',
            'end_gcode': 'M104 S0\nM140 S0\nG28 X0\nM84',
        },
        'Prusa MK4': {
            'bed_size': [250, 210], 'bed_temp_max': 110,
            'nozzle_diameter': 0.4, 'filament_diameter': 1.75,
            'max_print_speed': 300, 'default_print_speed': 60,
            'default_layer_height': 0.2,
            'default_retraction_distance': 2.0, 'default_retraction_speed': 45,
            'start_gcode': 'G28\nG29\nG92 E0',
            'end_gcode': 'M104 S0\nM140 S0\nG91\nG1 E-1 F300\nG1 Z1\nG90\nM84',
        },
        'Creality Ender-3': {
            'bed_size': [220, 220], 'bed_temp_max': 110,
            'nozzle_diameter': 0.4, 'filament_diameter': 1.75,
            'max_print_speed': 150, 'default_print_speed': 50,
            'default_layer_height': 0.2,
            'default_retraction_distance': 5.0, 'default_retraction_speed': 45,
            'start_gcode': 'G28\nG92 E0\nG1 Z2.0 F3000\nG1 X0.1 Y20 Z0.3 F5000\nG1 X0.1 Y150 E15 F1500\nG92 E0',
            'end_gcode': 'G91\nG1 E-5 F300\nG1 Z10 F3000\nG90\nG28 X0\nM84\nM104 S0\nM140 S0',
        },
        'Easythreed K9': {
            'bed_size': [100, 100], 'bed_temp_max': 0,
            'nozzle_diameter': 0.4, 'filament_diameter': 1.75,
            'max_print_speed': 40, 'default_print_speed': 30,
            'default_layer_height': 0.3,
            'default_retraction_distance': 6.5, 'default_retraction_speed': 25,
            'start_gcode': 'T0\nM104 S{print_temp}\nM105\nM109 S{print_temp}\nM82\nG28\nG1 Z15.0 F6000\nG92 E0\nG1 F200 E3\nG92 E0\nG1 F1500 E-6.5',
            'end_gcode': 'M104 S0\nM140 S0\nG28 X0 Y0\nM84\nM82\nM104 S0',
        },
        'Generic Printer': {
            'bed_size': [220, 220], 'bed_temp_max': 100,
            'nozzle_diameter': 0.4, 'filament_diameter': 1.75,
            'max_print_speed': 300, 'default_print_speed': 60,
            'default_layer_height': 0.2,
            'default_retraction_distance': 5.0, 'default_retraction_speed': 45,
            'start_gcode': 'G28\nG92 E0',
            'end_gcode': 'M104 S0\nM140 S0\nM84',
        },
    }


def _default_materials() -> dict:
    """Full material list – used as fallback AND to recreate materials.json if missing."""
    return {
        'PLA':  {'print_temp': 210, 'bed_temp': 60,  'fan_speed': 100, 'retraction': 5.0},
        'PETG': {'print_temp': 235, 'bed_temp': 80,  'fan_speed': 50,  'retraction': 6.0},
        'ABS':  {'print_temp': 240, 'bed_temp': 100, 'fan_speed': 0,   'retraction': 5.0},
        'TPU':  {'print_temp': 225, 'bed_temp': 60,  'fan_speed': 50,  'retraction': 1.0},
        'ASA':  {'print_temp': 245, 'bed_temp': 100, 'fan_speed': 20,  'retraction': 5.0},
    }


# ---------------------------------------------------------------------------
# Built-in presets
# ---------------------------------------------------------------------------

_BUILTIN_PRESETS = {
    # ─── Generic ──────────────────────────────────────────────────────────
    "Draft (0.3mm, 10%, Fast)": {
        'layer_height': 0.3, 'first_layer_height': 0.35,
        'wall_count': 2, 'infill_density': 10, 'infill_pattern': 'lines',
        'top_layers': 3, 'bottom_layers': 3,
        'outer_perimeter_speed': 60, 'print_speed': 80, 'infill_speed': 100,
        'top_bottom_speed': 60, 'first_layer_speed': 30, 'travel_speed': 200,
        'print_temp': 210, 'print_temp_first_layer': 215, 'bed_temp': 60,
        'fan_speed': 100, 'fan_first_layer': 0, 'fan_kick_in_layer': 2,
        'retraction_enabled': True, 'retraction_distance': 5.0,
        'retraction_speed': 45, 'retraction_z_hop': 0.0,
        'brim_enabled': False, 'support_enabled': False,
        '_material': 'PLA',
    },
    "Normal Quality (0.2mm, 20%)": {
        'layer_height': 0.2, 'first_layer_height': 0.3,
        'wall_count': 3, 'infill_density': 20, 'infill_pattern': 'grid',
        'top_layers': 4, 'bottom_layers': 4,
        'outer_perimeter_speed': 40, 'print_speed': 60, 'infill_speed': 80,
        'top_bottom_speed': 40, 'first_layer_speed': 25, 'travel_speed': 200,
        'print_temp': 210, 'print_temp_first_layer': 215, 'bed_temp': 60,
        'fan_speed': 100, 'fan_first_layer': 0, 'fan_kick_in_layer': 2,
        'retraction_enabled': True, 'retraction_distance': 5.0,
        'retraction_speed': 45, 'retraction_z_hop': 0.0,
        'brim_enabled': False, 'support_enabled': False,
        '_material': 'PLA',
    },
    "High Quality (0.15mm, 30%)": {
        'layer_height': 0.15, 'first_layer_height': 0.2,
        'wall_count': 4, 'infill_density': 30, 'infill_pattern': 'grid',
        'top_layers': 5, 'bottom_layers': 5,
        'outer_perimeter_speed': 25, 'print_speed': 40, 'infill_speed': 60,
        'top_bottom_speed': 30, 'first_layer_speed': 20, 'travel_speed': 150,
        'print_temp': 205, 'print_temp_first_layer': 210, 'bed_temp': 60,
        'fan_speed': 100, 'fan_first_layer': 0, 'fan_kick_in_layer': 3,
        'retraction_enabled': True, 'retraction_distance': 5.0,
        'retraction_speed': 45, 'retraction_z_hop': 0.05,
        'brim_enabled': False, 'support_enabled': False,
        '_material': 'PLA',
    },
    "Strong (0.2mm, 50%, Honeycomb)": {
        'layer_height': 0.2, 'first_layer_height': 0.3,
        'wall_count': 4, 'infill_density': 50, 'infill_pattern': 'honeycomb',
        'top_layers': 5, 'bottom_layers': 5,
        'outer_perimeter_speed': 40, 'print_speed': 60, 'infill_speed': 80,
        'top_bottom_speed': 40, 'first_layer_speed': 25, 'travel_speed': 200,
        'print_temp': 210, 'print_temp_first_layer': 215, 'bed_temp': 60,
        'fan_speed': 100, 'fan_first_layer': 0, 'fan_kick_in_layer': 2,
        'retraction_enabled': True, 'retraction_distance': 5.0,
        'retraction_speed': 45, 'retraction_z_hop': 0.0,
        'brim_enabled': True, 'brim_width': 6.0, 'support_enabled': False,
        '_material': 'PLA',
    },
    "With Support (Normal)": {
        'layer_height': 0.2, 'first_layer_height': 0.3,
        'wall_count': 3, 'infill_density': 20, 'infill_pattern': 'grid',
        'top_layers': 4, 'bottom_layers': 4,
        'outer_perimeter_speed': 40, 'print_speed': 60, 'infill_speed': 80,
        'top_bottom_speed': 40, 'first_layer_speed': 25, 'travel_speed': 200,
        'print_temp': 210, 'print_temp_first_layer': 215, 'bed_temp': 60,
        'fan_speed': 100, 'fan_first_layer': 0, 'fan_kick_in_layer': 2,
        'retraction_enabled': True, 'retraction_distance': 6.0,
        'retraction_speed': 45, 'retraction_z_hop': 0.2,
        'brim_enabled': False,
        'support_enabled': True, 'support_threshold': 45.0,
        'support_density': 15, 'support_z_distance': 0.2, 'support_xy_distance': 0.7,
        '_material': 'PLA',
    },
    # ─── Easythreed K9 ────────────────────────────────────────────────────
    "K9 – Draft (0.3mm, 10%)": {
        '_printer': 'Easythreed K9', '_material': 'PLA',
        'layer_height': 0.3, 'first_layer_height': 0.3,
        'wall_count': 2, 'infill_density': 10, 'infill_pattern': 'lines',
        'top_layers': 3, 'bottom_layers': 3,
        'outer_perimeter_speed': 20, 'print_speed': 30, 'infill_speed': 35,
        'top_bottom_speed': 20, 'first_layer_speed': 15, 'travel_speed': 60,
        'print_temp': 200, 'print_temp_first_layer': 205, 'bed_temp': 0,
        'fan_speed': 100, 'fan_first_layer': 0, 'fan_kick_in_layer': 3,
        'retraction_enabled': True, 'retraction_distance': 6.5,
        'retraction_speed': 25, 'retraction_z_hop': 0.0,
        'brim_enabled': False, 'support_enabled': False,
    },
    "K9 – Normal (0.2mm, 20%)": {
        '_printer': 'Easythreed K9', '_material': 'PLA',
        'layer_height': 0.2, 'first_layer_height': 0.25,
        'wall_count': 3, 'infill_density': 20, 'infill_pattern': 'grid',
        'top_layers': 4, 'bottom_layers': 4,
        'outer_perimeter_speed': 18, 'print_speed': 25, 'infill_speed': 30,
        'top_bottom_speed': 18, 'first_layer_speed': 12, 'travel_speed': 60,
        'print_temp': 200, 'print_temp_first_layer': 205, 'bed_temp': 0,
        'fan_speed': 100, 'fan_first_layer': 0, 'fan_kick_in_layer': 3,
        'retraction_enabled': True, 'retraction_distance': 6.5,
        'retraction_speed': 25, 'retraction_z_hop': 0.0,
        'brim_enabled': True, 'brim_width': 5.0, 'support_enabled': False,
    },
    "K9 – Quality (0.15mm, 30%)": {
        '_printer': 'Easythreed K9', '_material': 'PLA',
        'layer_height': 0.15, 'first_layer_height': 0.2,
        'wall_count': 3, 'infill_density': 30, 'infill_pattern': 'grid',
        'top_layers': 5, 'bottom_layers': 5,
        'outer_perimeter_speed': 15, 'print_speed': 20, 'infill_speed': 25,
        'top_bottom_speed': 15, 'first_layer_speed': 10, 'travel_speed': 50,
        'print_temp': 200, 'print_temp_first_layer': 205, 'bed_temp': 0,
        'fan_speed': 100, 'fan_first_layer': 0, 'fan_kick_in_layer': 3,
        'retraction_enabled': True, 'retraction_distance': 6.5,
        'retraction_speed': 25, 'retraction_z_hop': 0.1,
        'brim_enabled': True, 'brim_width': 5.0, 'support_enabled': False,
    },
    # ─── PETG ─────────────────────────────────────────────────────────────
    "PETG Normal (0.2mm, 20%)": {
        'layer_height': 0.2, 'first_layer_height': 0.3,
        'wall_count': 3, 'infill_density': 20, 'infill_pattern': 'grid',
        'top_layers': 4, 'bottom_layers': 4,
        'outer_perimeter_speed': 35, 'print_speed': 50, 'infill_speed': 60,
        'top_bottom_speed': 35, 'first_layer_speed': 20, 'travel_speed': 180,
        'print_temp': 235, 'print_temp_first_layer': 240, 'bed_temp': 80,
        'fan_speed': 50, 'fan_first_layer': 0, 'fan_kick_in_layer': 3,
        'retraction_enabled': True, 'retraction_distance': 6.0,
        'retraction_speed': 40, 'retraction_z_hop': 0.2,
        'brim_enabled': False, 'support_enabled': False,
        '_material': 'PETG',
    },
}
