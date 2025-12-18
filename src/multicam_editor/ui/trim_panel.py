"""
Patched TrimPanel (DEV branch) to enforce minimum segment length for splits (Prompt 4.5).

This version is based on the DEV branch's `ui/trim_panel.py`.  It adds a
minimum segment length constraint when clamping the playhead before
splitting a clip.  If the playhead is too close to the start or end
of the current in/out range (less than 100ms from either edge), the
split is aborted.  All other behaviour remains unchanged.

To use this panel, replace the existing `ui/trim_panel.py` in your DEV
branch checkout with this file's content.
"""

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
    QPushButton,
)

# Use a relative import to access the RangeSlider widget within the same package.
from .widgets.range_slider import RangeSlider

# Import the video splitting helper from the logic layer.  This function
# physically splits a video on disk and returns the paths of the newly
# created segments.  The import is placed here to avoid a circular
# dependency on GUI components.
from ..logic.video_utils import split_video


class TrimPanel(QWidget):
    """Editable trim panel: path, in/out/trimmed-length + dual-handle slider.

    Adds "Split at Playhead" with guardrails (Prompts 4.4 & 4.5).

    Emits:
        trimChanged(str path, int in_ms, int out_ms)
    """

    trimChanged = pyqtSignal(str, int, int)

    # minimum allowed duration for each side of a split (ms)
    MIN_SEGMENT_MS = 100

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
    def bind_context(self, project, adapter, video_preview: object, status_sink, file_list=None, undo_stack=None) -> None:
        """Inject references to the project, timeline adapter, preview, status sink, file list, and undo stack.

        Args:
            project: Project instance for clip management
            adapter: TimelineAdapter for model-view synchronization
            video_preview: VideoPreview widget for playhead position
            status_sink: Callable that displays status messages (e.g., MainWindow._toast)
            file_list: Optional FileListWidget for adding split file outputs
            undo_stack: Optional QUndoStack for undoable operations
        """
        self._project = project
        self._adapter = adapter
        self._video_preview = video_preview
        self._status_sink = status_sink
        self._file_list = file_list
        self._undo_stack = undo_stack

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
            self._show_status("Cannot split: No clip selected or context not initialized")
            return
        ms = self._current_playhead_ms()
        if ms is None:
            self._show_status("Cannot split: Playhead position unknown")
            return
        # Clamp split position into the current clip's trimmed range.  Without
        # clamping a playhead outside [in_ms, out_ms] would result in no-op.
        try:
            start_ms = int(self._in_ms)
            end_ms = int(self._out_ms)
        except Exception:
            self._show_status("Cannot split: Invalid trim range")
            return
        # Only clamp if we have a valid range and ms is out of bounds.
        if end_ms > 0:
            # Enforce minimum segment length.  If the playhead is too close to
            # the start or end of the trimmed range (< MIN_SEGMENT_MS) we do
            # not perform the split.
            if ms - start_ms < self.MIN_SEGMENT_MS:
                self._show_status(f"Cannot split: Too close to start (need {self.MIN_SEGMENT_MS}ms minimum)")
                return
            if end_ms - ms < self.MIN_SEGMENT_MS:
                self._show_status(f"Cannot split: Too close to end (need {self.MIN_SEGMENT_MS}ms minimum)")
                return
            if ms <= start_ms:
                self._show_status("Cannot split: Playhead before clip start")
                return
            if ms >= end_ms:
                self._show_status("Cannot split: Playhead after clip end")
                return
        # Perform the split using undo command if available.
        if self._undo_stack:
            from ..logic.commands import SplitCommand
            cmd = SplitCommand(
                self._project,
                self._path,
                ms,
                refresh_callback=self._adapter.refresh_from_project if self._adapter else None
            )
            self._undo_stack.push(cmd)
            # Get result from command
            left = cmd.left_clip
            right = cmd.right_clip
            if not left or not right:
                return
        else:
            # Fallback to direct split if no undo stack
            try:
                result = self._project.split_clip_by_path(self._path, ms)
            except Exception:
                result = None
            if not result:
                return
            left, right = result

        # Physically split the underlying video on disk.  The helper returns
        # a list of new file paths, or an empty list if the operation
        # failed or was skipped.  We wrap this in a try/except so that
        # logical splitting never crashes the UI.
        try:
            new_paths = split_video(self._path, ms)
        except Exception:
            new_paths = []
        # Add the new segments to the project and file list (if provided).
        for new_path in new_paths:
            try:
                clip_obj = self._project.add_path(new_path)
            except Exception:
                clip_obj = None
            # update file list so user can see new segments
            if getattr(self, "_file_list", None) is not None:
                try:
                    # cap_remaining=None uses the current cap set by the list
                    self._file_list.add_files([new_path], cap_remaining=None)
                except Exception:
                    pass
        # schedule refresh & selection on GUI thread (adapter is thread-safe now)
        self._adapter.refresh_from_project()
        clips = self._project.clips()
        left_index = next((i for i, c in enumerate(clips)
                           if c.path == left.path and c.in_ms == left.in_ms and c.out_ms == left.out_ms), 0)
        if hasattr(self._adapter, "_make_key"):
            key = self._adapter._make_key(left, left_index)  # type: ignore[attr-defined]
            self._adapter.select_and_scroll_by_key(key)
        # Seek the preview to the split position so that the user can
        # immediately review the new segment.
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

    def _show_status(self, message: str) -> None:
        """Display a status message via the injected status sink."""
        if hasattr(self, "_status_sink") and callable(self._status_sink):
            try:
                self._status_sink(message)
            except Exception:
                pass

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
