# file: ui/trim_panel.py
from __future__ import annotations
from typing import Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFormLayout, QFrame, QLineEdit, QPushButton
)

from ui.widgets.range_slider import RangeSlider


class TrimPanel(QWidget):
    """Editable trim panel: path, in/out/trimmed-length + dual-handle slider.
    Adds 'Split at Playhead' (Prompt 4.4).

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
        self._loading: bool = False

        # injected context (bind_context)
        self._project = None            # type: ignore[assignment]
        self._adapter = None            # type: ignore[assignment]
        self._video_preview: Optional[object] = None

        self.lbl_path = QLabel("-", self)
        self.lbl_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.edit_in = QLineEdit("00:00", self)
        self.edit_out = QLineEdit("00:00", self)
        for e in (self.edit_in, self.edit_out):
            e.setMaximumWidth(80)
            e.setPlaceholderText("mm:ss")
        self.edit_in.editingFinished.connect(self._on_in_edit_finished)
        self.edit_out.editingFinished.connect(self._on_out_edit_finished)

        self.slider = RangeSlider(self)
        self.slider.setEnabled(True)
        self.slider.valuesChanged.connect(self._on_slider_changed)

        self.lbl_dur = QLabel("00:00", self)
        self.lbl_dur.setToolTip("Trimmed length: Out − In")

        self.btn_split = QPushButton("Split at Playhead", self)
        self.btn_split.setToolTip("Split current clip at the preview playhead")
        self.btn_split.clicked.connect(self._on_split_clicked)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow("Path:", self.lbl_path)

        info_row = QWidget(self)
        info_lay = QHBoxLayout(info_row); info_lay.setContentsMargins(0, 0, 0, 0)
        info_lay.addWidget(QLabel("In:", info_row));  info_lay.addWidget(self.edit_in)
        info_lay.addSpacing(12)
        info_lay.addWidget(QLabel("Out:", info_row)); info_lay.addWidget(self.edit_out)
        info_lay.addSpacing(12)
        info_lay.addWidget(QLabel("Duration:", info_row)); info_lay.addWidget(self.lbl_dur)
        info_lay.addStretch(1)
        info_lay.addWidget(self.btn_split)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addLayout(form)
        root.addWidget(info_row)
        root.addWidget(self.slider)
        sep = QFrame(self); sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

    # context injection
    def bind_context(self, project, adapter, video_preview: object) -> None:
        self._project = project
        self._adapter = adapter
        self._video_preview = video_preview

    # Public API
    def load(self, path: str, duration_ms: int, in_ms: int, out_ms: int) -> None:
        self._loading = True
        try:
            self._path = path
            self._duration_ms = max(0, int(duration_ms))
            self._in_ms, self._out_ms = self._clamp_pair(int(in_ms), int(out_ms))
            self.lbl_path.setText(path)
            self._update_duration_label()
            self.edit_in.setText(self._fmt_time(self._in_ms))
            self.edit_out.setText(self._fmt_time(self._out_ms))
            self.slider.setEnabled(self._duration_ms > 0)
            self.slider.setRange(0, self._duration_ms if self._duration_ms > 0 else 1)
            self.slider.setValues(self._in_ms, self._out_ms)
        finally:
            self._loading = False

    # Slots
    def _on_slider_changed(self, left: int, right: int) -> None:
        left, right = self._clamp_pair(left, right)
        self._in_ms, self._out_ms = left, right
        self.edit_in.setText(self._fmt_time(left))
        self.edit_out.setText(self._fmt_time(right))
        self._update_duration_label()
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
        self._update_duration_label()
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
        self._update_duration_label()
        if self._path:
            self.trimChanged.emit(self._path, left, right)

    def _on_split_clicked(self) -> None:
        if not self._path or self._project is None or self._adapter is None:
            return
        ms = self._current_playhead_ms()
        if ms is None:
            return
        try:
            result = self._project.split_clip_by_path(self._path, ms)  # (left, right) or None
        except Exception:
            result = None
        if not result:
            return
        left, right = result  # noqa: F841

        # schedule refresh & selection on GUI thread (adapter is thread-safe now)
        self._adapter.refresh_from_project()
        clips = self._project.clips()
        left_index = next((i for i, c in enumerate(clips)
                           if c.path == left.path and c.in_ms == left.in_ms and c.out_ms == left.out_ms), 0)
        if hasattr(self._adapter, "_make_key"):
            key = self._adapter._make_key(left, left_index)  # type: ignore[attr-defined]
            self._adapter.select_and_scroll_by_key(key)
        self._seek_preview(ms)

    # Utils
    def _update_duration_label(self) -> None:
        trimmed = max(0, self._out_ms - self._in_ms)
        self.lbl_dur.setText(self._fmt_time(trimmed))
        self.lbl_dur.setToolTip(
            f"Trimmed: {self._fmt_time(trimmed)}  |  Full: {self._fmt_time(self._duration_ms)}"
        )

    def _clamp_pair(self, left: int, right: int) -> Tuple[int, int]:
        dur = self._duration_ms if self._duration_ms > 0 else 1
        left = max(0, min(left, dur))
        right = max(left, min(right, dur))
        return int(left), int(right)

    def _current_playhead_ms(self) -> Optional[int]:
        if self._video_preview is None:
            return None
        if hasattr(self._video_preview, "current_position_ms"):
            try:
                return int(self._video_preview.current_position_ms())
            except Exception:
                return None
        return None

    def _seek_preview(self, ms: int) -> None:
        if self._video_preview is None:
            return
        for name in ("seek_ms", "set_position_ms", "set_position", "seek"):
            if hasattr(self._video_preview, name):
                try:
                    getattr(self._video_preview, name)(int(ms))
                except Exception:
                    pass
                break

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
        """Accepts ss, mm:ss, or hh:mm:ss (mm/ss may be >59)."""
        t = text.strip()
        if not t:
            return None
        try:
            if ":" not in t:
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
