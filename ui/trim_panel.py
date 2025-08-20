# file: ui/trim_panel.py
from __future__ import annotations
from typing import Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QFrame,
    QLineEdit,
)

from ui.widgets.range_slider import RangeSlider


class TrimPanel(QWidget):
    """Editable trim panel: path, in/out/duration + dual‑handle slider.

    Emits:
        trimChanged(str path, int in_ms, int out_ms)
    """

    trimChanged = pyqtSignal(str, int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path: Optional[str] = None
        self._duration_ms: int = 0
        self._in_ms: int = 0
        self._out_ms: int = 0
        self._loading: bool = False  # suppress user signals during load

        # Header: path
        self.lbl_path = QLabel("-", self)
        self.lbl_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_path.setToolTip("Selected clip path")

        # Time fields
        self.edit_in = QLineEdit("00:00", self)
        self.edit_out = QLineEdit("00:00", self)
        for e in (self.edit_in, self.edit_out):
            e.setMaximumWidth(80)
            e.setPlaceholderText("mm:ss")
        self.edit_in.editingFinished.connect(self._on_in_edit_finished)
        self.edit_out.editingFinished.connect(self._on_out_edit_finished)

        # Range slider (editable now)
        self.slider = RangeSlider(self)
        self.slider.setEnabled(True)
        self.slider.valuesChanged.connect(self._on_slider_changed)

        # Duration label
        self.lbl_dur = QLabel("00:00", self)

        # Layout
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow("Path:", self.lbl_path)

        info_row = QWidget(self)
        info_lay = QHBoxLayout(info_row)
        info_lay.setContentsMargins(0, 0, 0, 0)
        info_lay.addWidget(QLabel("In:", info_row))
        info_lay.addWidget(self.edit_in)
        info_lay.addSpacing(12)
        info_lay.addWidget(QLabel("Out:", info_row))
        info_lay.addWidget(self.edit_out)
        info_lay.addSpacing(12)
        info_lay.addWidget(QLabel("Duration:", info_row))
        info_lay.addWidget(self.lbl_dur)
        info_lay.addStretch(1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addLayout(form)
        root.addWidget(info_row)
        root.addWidget(self.slider)

        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

    # --- Public API ---
    def load(self, path: str, duration_ms: int, in_ms: int, out_ms: int) -> None:
        """Populate the panel and enable editing."""
        self._loading = True
        try:
            self._path = path
            self._duration_ms = max(0, int(duration_ms))
            self._in_ms, self._out_ms = self._clamp_pair(int(in_ms), int(out_ms))
            self.lbl_path.setText(path)
            self.lbl_dur.setText(self._fmt_time(self._duration_ms))
            self.edit_in.setText(self._fmt_time(self._in_ms))
            self.edit_out.setText(self._fmt_time(self._out_ms))
            self.slider.setEnabled(self._duration_ms > 0)
            self.slider.setRange(0, self._duration_ms if self._duration_ms > 0 else 1)
            self.slider.setValues(self._in_ms, self._out_ms)
        finally:
            self._loading = False

    # --- Slots ---
    def _on_slider_changed(self, left: int, right: int) -> None:
        # called on user drag and programmatic setValues; gate with _loading
        left, right = self._clamp_pair(left, right)
        self._in_ms, self._out_ms = left, right
        self.edit_in.setText(self._fmt_time(left))
        self.edit_out.setText(self._fmt_time(right))
        if not self._loading and self._path:
            self.trimChanged.emit(self._path, left, right)

    def _on_in_edit_finished(self) -> None:
        v = self._parse_time(self.edit_in.text())
        if v is None:
            v = self._in_ms
        left, right = self._clamp_pair(v, self._out_ms)
        self._in_ms, self._out_ms = left, right
        self.edit_in.setText(self._fmt_time(left))
        self.edit_out.setText(self._fmt_time(right))
        self.slider.setValues(left, right)
        if self._path:
            self.trimChanged.emit(self._path, left, right)

    def _on_out_edit_finished(self) -> None:
        v = self._parse_time(self.edit_out.text())
        if v is None:
            v = self._out_ms
        left, right = self._clamp_pair(self._in_ms, v)
        self._in_ms, self._out_ms = left, right
        self.edit_in.setText(self._fmt_time(left))
        self.edit_out.setText(self._fmt_time(right))
        self.slider.setValues(left, right)
        if self._path:
            self.trimChanged.emit(self._path, left, right)

    # --- Utils ---
    def _clamp_pair(self, left: int, right: int) -> Tuple[int, int]:
        dur = self._duration_ms if self._duration_ms > 0 else max(1, self.slider._max)
        left = max(0, min(left, dur))
        right = max(left, min(right, dur))
        return int(left), int(right)

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

    @staticmethod
    def _parse_time(text: str) -> Optional[int]:
        """Accepts ss, mm:ss, or hh:mm:ss (optionally mm or ss can be >59)."""
        t = text.strip()
        if not t:
            return None
        try:
            if ":" not in t:
                # seconds only, allow float
                if "." in t:
                    secs = float(t)
                    return max(0, int(round(secs * 1000)))
                return max(0, int(t) * 1000)
            parts = [p for p in t.split(":") if p != ""]
            parts = [int(float(p)) for p in parts]
            if len(parts) == 2:
                mm, ss = parts
                total = mm * 60 + ss
            elif len(parts) == 3:
                hh, mm, ss = parts
                total = hh * 3600 + mm * 60 + ss
            else:
                return None
            return max(0, int(total) * 1000)
        except Exception:
            return None
