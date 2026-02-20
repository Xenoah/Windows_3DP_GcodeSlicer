"""
Layer preview slider widget.

Shows a horizontal slider that lets the user scrub through sliced layers.
Includes play/stop animation functionality.
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSlider, QLabel,
    QPushButton, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont


class LayerSlider(QWidget):
    """
    Horizontal layer preview slider.

    Signals:
        layer_changed(int): emitted when the selected layer changes
    """

    layer_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._total_layers = 0
        self._playing = False
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(100)  # ms per layer during animation
        self._play_timer.timeout.connect(self._advance_layer)
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # Layer label
        self.layer_label = QLabel("Layers:")
        self.layer_label.setFixedWidth(45)
        layout.addWidget(self.layer_label)

        # Slider
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(0)
        self.slider.setValue(0)
        self.slider.setEnabled(False)
        self.slider.setTickPosition(QSlider.TickPosition.NoTicks)
        self.slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.slider)

        # Layer counter label
        self.count_label = QLabel("0/0")
        self.count_label.setFixedWidth(60)
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setFamily("Courier New")
        self.count_label.setFont(font)
        layout.addWidget(self.count_label)

        # Play/Stop button
        self.play_btn = QPushButton("Play")
        self.play_btn.setFixedWidth(50)
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._toggle_play)
        layout.addWidget(self.play_btn)

        # Connect slider
        self.slider.valueChanged.connect(self._on_slider_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_layer_count(self, count: int):
        """Set the total number of layers. Enables the slider."""
        self._total_layers = count
        self._play_timer.stop()
        self._playing = False
        self.play_btn.setText("Play")

        if count <= 0:
            self.slider.setMaximum(0)
            self.slider.setValue(0)
            self.slider.setEnabled(False)
            self.play_btn.setEnabled(False)
            self.count_label.setText("0/0")
        else:
            self.slider.setMaximum(count - 1)
            self.slider.setValue(count - 1)
            self.slider.setEnabled(True)
            self.play_btn.setEnabled(True)
            self.count_label.setText(f"{count}/{count}")

    def current_layer(self) -> int:
        return self.slider.value()

    def reset(self):
        """Reset slider to initial state (no layers)."""
        self.set_layer_count(0)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_slider_changed(self, value):
        total = self._total_layers
        if total > 0:
            self.count_label.setText(f"{value + 1}/{total}")
        self.layer_changed.emit(value)

    def _toggle_play(self):
        if self._playing:
            self._play_timer.stop()
            self._playing = False
            self.play_btn.setText("Play")
        else:
            if self._total_layers <= 0:
                return
            # Start from beginning if at end
            if self.slider.value() >= self._total_layers - 1:
                self.slider.setValue(0)
            self._playing = True
            self.play_btn.setText("Stop")
            self._play_timer.start()

    def _advance_layer(self):
        current = self.slider.value()
        if current < self._total_layers - 1:
            self.slider.setValue(current + 1)
        else:
            # Stop at end
            self._play_timer.stop()
            self._playing = False
            self.play_btn.setText("Play")
