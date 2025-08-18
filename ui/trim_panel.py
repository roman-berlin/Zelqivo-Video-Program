# file: ui/trim_panel.py
from __future__ import annotations
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFormLayout, QFrame

from ui.widgets.range_slider import RangeSlider


class TrimPanel(QWidget):
    """Read-only trim panel to display clip path and in/out over duration.

    This step only shows information; editing is enabled in later prompts.
    """
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path: Optional[str] = None
        self._duration_ms: int = 0
        self._in_ms: int = 0
        self._out_ms: int = 0

        # Header: path
        self.lbl_path = QLabel("-", self)
        self.lbl_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_path.setToolTip("Selected clip path")

        # Info row
        self.lbl_in = QLabel("00:00", self)
        self.lbl_out = QLabel("00:00", self)
        self.lbl_dur = QLabel("00:00", self)

        # Range slider (read-only for this step)
        self.slider = RangeSlider(self)
        self.slider.setEnabled(False)

        # Layout
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow("Path:", self.lbl_path)

        info_row = QWidget(self)
        info_lay = QHBoxLayout(info_row)
        info_lay.setContentsMargins(0, 0, 0, 0)
        info_lay.addWidget(QLabel("In:", info_row))
        info_lay.addWidget(self.lbl_in)
        info_lay.addSpacing(12)
        info_lay.addWidget(QLabel("Out:", info_row))
        info_lay.addWidget(self.lbl_out)
        info_lay.addSpacing(12)
        info_lay.addWidget(QLabel("Duration:", info_row))
        info_lay.addWidget(self.lbl_dur)
        info_lay.addStretch(1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addLayout(form)
        root.addWidget(info_row)
        root.addWidget(self.slider)

        # Separator to match MainWindow style
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

    # --- Public API ---
    def load(self, path: str, duration_ms: int, in_ms: int, out_ms: int) -> None:
        """Populate the panel; slider remains read-only."""
        self._path = path
        self._duration_ms = max(0, int(duration_ms))
        self._in_ms = max(0, int(in_ms))
        self._out_ms = max(self._in_ms, int(out_ms))

        self.lbl_path.setText(path)
        self.lbl_in.setText(self._fmt_time(self._in_ms))
        self.lbl_out.setText(self._fmt_time(self._out_ms))
        self.lbl_dur.setText(self._fmt_time(self._duration_ms))

        self.slider.setRange(0, self._duration_ms if self._duration_ms > 0 else 1)
        self.slider.setValues(self._in_ms, self._out_ms)

    # --- Utils ---
    @staticmethod
    def _fmt_time(ms: int) -> str:
        if ms <= 0:
            return "00:00"
        s = ms // 1000
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"