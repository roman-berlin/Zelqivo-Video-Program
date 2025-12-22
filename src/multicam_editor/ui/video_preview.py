# file: ui/video_preview.py
from __future__ import annotations
import logging
import threading
from typing import Optional

from PyQt6.QtCore import QUrl, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QSlider, QStackedLayout
)

# Note: QMediaPlayer/QAudioOutput imported lazily to avoid early native crashes.

logger = logging.getLogger(__name__)


class VideoPreview(QWidget):
    """Video preview with smooth playhead and correct play/pause icon.

    Lazy-creates QMediaPlayer on first source load to avoid startup crashes.
    """

    durationKnown = pyqtSignal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # backend (lazy)
        self._player = None           # type: Optional["QMediaPlayer"]
        self._audio = None            # type: Optional["QAudioOutput"]

        self._duration_ms = 0
        self._source_path: Optional[str] = None
        self._user_scrubbing = False
        self._pending_seek_ms: int = 0
        self._duration_emitted_for: Optional[str] = None

        self._ui_pos_ms: int = 0
        self._MAX_STEP_MS: int = 40
        self._always_restart_on_play: bool = True  # set False to resume instead

        # Fallback timer for ffprobe duration when QMediaPlayer fails
        self._fallback_timer: Optional[QTimer] = None
        self._fallback_path: Optional[str] = None

        self._tick = QTimer(self); self._tick.setInterval(16)
        self._tick.timeout.connect(self._update_ui_from_player); self._tick.start()

        # UI
        self._stack = QStackedLayout(self)

        video_page = QWidget(self)
        vlay = QVBoxLayout(video_page); vlay.setContentsMargins(0, 0, 0, 0)
        self._video_widget = QVideoWidget(video_page)
        vlay.addWidget(self._video_widget, 1)

        ctrl = QWidget(video_page); hlay = QHBoxLayout(ctrl); hlay.setContentsMargins(8, 4, 8, 4)
        self.btn_play = QPushButton(ctrl)
        self.btn_play.setFixedWidth(36)
        self._set_play_icon(playing=False)
        self.btn_play.clicked.connect(self._toggle_play)
        self.lbl_time = QLabel("00:00", ctrl)

        self.slider = QSlider(Qt.Orientation.Horizontal, ctrl)
        self.slider.setMinimum(0); self.slider.setMaximum(1)
        self.slider.setSingleStep(250); self.slider.setPageStep(2000)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.slider.sliderMoved.connect(self._on_slider_moved)

        self.lbl_dur = QLabel("00:00", ctrl)

        hlay.addWidget(self.btn_play); hlay.addWidget(self.lbl_time)
        hlay.addWidget(self.slider, 1); hlay.addWidget(self.lbl_dur)
        vlay.addWidget(ctrl)

        thumb_page = QWidget(self)
        self._thumb_label = QLabel("", thumb_page)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setStyleSheet("background: #222; color: #bbb;")
        tlay = QVBoxLayout(thumb_page); tlay.setContentsMargins(0, 0, 0, 0)
        tlay.addWidget(self._thumb_label, 1)

        self._stack.addWidget(video_page); self._stack.addWidget(thumb_page)
        self._stack.setCurrentIndex(0)

    # --- lazy backend setup ---
    def _ensure_player(self) -> None:
        if self._player is not None:
            return
        # Import here to avoid early DLL/plugin init
        from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._video_widget)

        # signals (now safe)
        self._player.positionChanged.connect(self._on_player_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(self._on_error)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)

    # --- public API ---
    def set_source(self, path: Optional[str]) -> None:
        if not path:
            self._clear(); return
        if self._source_path == path:
            return
        self._source_path = path
        self._duration_ms = 0
        self._ui_pos_ms = 0
        self._set_labels(0, 0)
        self.slider.setRange(0, 1); self.slider.setValue(0)
        self._stack.setCurrentIndex(0); self._thumb_label.clear()

        self._ensure_player()
        assert self._player is not None
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()

        # Start fallback timer to check if QMediaPlayer reports duration
        # If not, use ffprobe to get duration
        self._start_duration_fallback(path)

    def current_position_ms(self) -> int:
        return int(self._player.position()) if self._player else 0

    # playback control -------------------------------------------------
    def seek_ms(self, ms: int) -> None:
        """Seek the underlying player to ``ms`` milliseconds and update the UI.

        Several components in the GUI call into ``VideoPreview`` using
        different method names (``seek_ms``, ``set_position_ms``, ``set_position`` or
        ``seek``).  Qt's ``QMediaPlayer`` exposes a ``setPosition`` API which
        expects a position in milliseconds.  This helper normalises the
        input, guards against missing players and updates internal state
        and labels accordingly.
        """
        if not self._player:
            return
        try:
            pos = max(0, int(ms))
        except Exception:
            pos = 0
        try:
            self._player.setPosition(pos)
        except Exception:
            pass
        # Reset scrubbing state so that the periodic timer reflects the new position
        self._user_scrubbing = False
        self._ui_pos_ms = pos
        self._apply_ui_position()

    # Provide common aliases for seek operations so that callers can use
    # whichever name they expect.  Each alias delegates to ``seek_ms``.
    def set_position_ms(self, ms: int) -> None:
        self.seek_ms(ms)

    def set_position(self, ms: int) -> None:
        self.seek_ms(ms)

    def seek(self, ms: int) -> None:
        self.seek_ms(ms)

    # --- handlers ---
    def _toggle_play(self) -> None:
        if not self._player:
            return
        st = self._player.playbackState()
        if st == self._player.PlaybackState.PlayingState:
            self._player.pause()
        else:
            if self._always_restart_on_play:
                self._player.setPosition(0)
                self._ui_pos_ms = 0
                self._apply_ui_position()
            self._player.play()

    def _on_playback_state_changed(self, state) -> None:
        is_playing = self._player and state == self._player.PlaybackState.PlayingState
        self._set_play_icon(playing=is_playing)
        if self._player and not self._user_scrubbing:
            self._ui_pos_ms = int(self._player.position())
            self._apply_ui_position()

    def _set_play_icon(self, playing: bool) -> None:
        """Set Play/Pause icon using Qt standard icons with tooltip."""
        from PyQt6.QtWidgets import QStyle
        style = self.style()
        if playing:
            icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPause)
            self.btn_play.setToolTip("Pause")
        else:
            icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
            self.btn_play.setToolTip("Play")
        self.btn_play.setIcon(icon)

    def _on_duration_changed(self, dur: int) -> None:
        self._duration_ms = max(0, int(dur))
        self.slider.setRange(0, self._duration_ms if self._duration_ms > 0 else 1)
        self.lbl_dur.setText(self._fmt_time(self._duration_ms))
        if self._source_path and self._duration_emitted_for != self._source_path:
            self._duration_emitted_for = self._source_path
            self.durationKnown.emit(self._duration_ms)

    def _on_player_position_changed(self, _pos: int) -> None:
        # UI updates on steady timer
        pass

    def _on_media_status(self, _status) -> None:
        if not self._player:
            return
        if self._player.mediaStatus() == self._player.MediaStatus.InvalidMedia:
            self._show_thumbnail_fallback(self._source_path)

    def _on_error(self, *_args) -> None:
        self._show_thumbnail_fallback(self._source_path)

    def _on_slider_pressed(self) -> None:
        self._user_scrubbing = True

    def _on_slider_moved(self, value: int) -> None:
        self._pending_seek_ms = int(value)
        self._set_labels(self._pending_seek_ms, self._duration_ms)

    def _on_slider_released(self) -> None:
        if not self._player:
            return
        pos = int(self._pending_seek_ms)
        self._player.setPosition(pos)
        self._user_scrubbing = False
        self._ui_pos_ms = pos
        self._apply_ui_position()

    # --- periodic UI updater ---
    def _update_ui_from_player(self) -> None:
        if self._user_scrubbing or not self._player:
            return
        actual = int(max(0, self._player.position()))
        if self._player.playbackState() == self._player.PlaybackState.PlayingState:
            diff = actual - self._ui_pos_ms
            if diff != 0:
                step = max(-self._MAX_STEP_MS, min(self._MAX_STEP_MS, diff))
                self._ui_pos_ms += step
        else:
            self._ui_pos_ms = actual
        self._apply_ui_position()

    def _apply_ui_position(self) -> None:
        pos = max(0, min(self._ui_pos_ms, self._duration_ms if self._duration_ms > 0 else self._ui_pos_ms))
        self.slider.blockSignals(True)
        try:
            self.slider.setValue(pos)
        finally:
            self.slider.blockSignals(False)
        self._set_labels(pos, self._duration_ms)

    # --- helpers ---
    def _clear(self) -> None:
        if self._player:
            self._player.stop()
            self._player.setSource(QUrl())
        self._source_path = None
        self._duration_ms = 0
        self._ui_pos_ms = 0
        self._set_labels(0, 0)
        self.slider.setRange(0, 1); self.slider.setValue(0)
        self._set_play_icon(playing=False)
        self._stack.setCurrentIndex(0)

    def _set_labels(self, pos_ms: int, dur_ms: int) -> None:
        self.lbl_time.setText(self._fmt_time(pos_ms))
        self.lbl_dur.setText(self._fmt_time(dur_ms))

    def _show_thumbnail_fallback(self, path: Optional[str]) -> None:
        if not path:
            self._thumb_label.setText("No media")
            self._stack.setCurrentIndex(1)
            return
        pm = self._read_thumb_with_cv(path)
        if pm is None:
            self._thumb_label.setText("(no preview available)")
        else:
            self._thumb_label.setPixmap(
                pm.scaled(
                    self._thumb_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self._stack.setCurrentIndex(1)

    def resizeEvent(self, e) -> None:  # type: ignore[override]
        super().resizeEvent(e)
        if self._stack.currentIndex() == 1:
            pm = self._thumb_label.pixmap()
            if pm:
                self._thumb_label.setPixmap(
                    pm.scaled(
                        self._thumb_label.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )

    @staticmethod
    def _read_thumb_with_cv(path: str) -> Optional[QPixmap]:
        try:
            import cv2  # optional
            cap = cv2.VideoCapture(path)
            ok, frame = cap.read()
            cap.release()
            if not ok or frame is None:
                return None
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, _ = frame.shape
            qimg = QImage(frame.data, w, h, w * 3, QImage.Format.Format_RGB888)
            return QPixmap.fromImage(qimg)
        except Exception:
            return None

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

    # --- ffprobe duration fallback ---
    def _start_duration_fallback(self, path: str) -> None:
        """Start a timer to check if QMediaPlayer reports duration.

        If duration is still 0 after timeout, use ffprobe as fallback.
        """
        # Cancel any existing fallback timer
        if self._fallback_timer is not None:
            self._fallback_timer.stop()
            self._fallback_timer = None

        self._fallback_path = path
        self._fallback_timer = QTimer(self)
        self._fallback_timer.setSingleShot(True)
        self._fallback_timer.timeout.connect(self._check_duration_fallback)
        self._fallback_timer.start(800)  # Check after 800ms

    def _check_duration_fallback(self) -> None:
        """Check if duration was reported; if not, use ffprobe."""
        path = self._fallback_path
        self._fallback_timer = None
        self._fallback_path = None

        # If duration already known or path changed, skip
        if not path or path != self._source_path:
            return
        if self._duration_ms > 0:
            return  # QMediaPlayer reported duration, no fallback needed

        # Run ffprobe in background thread to avoid UI freeze
        def probe_in_thread():
            try:
                from ..utils.ffprobe import get_duration_ms
                duration = get_duration_ms(path)
            except Exception as e:
                logger.debug(f"ffprobe import/call failed: {e}")
                duration = None
            # Post result back to GUI thread
            QTimer.singleShot(0, lambda: self._on_ffprobe_result(path, duration))

        thread = threading.Thread(target=probe_in_thread, daemon=True)
        thread.start()

    def _on_ffprobe_result(self, path: str, duration_ms: Optional[int]) -> None:
        """Handle ffprobe result on GUI thread."""
        # Verify path still matches current source
        if path != self._source_path:
            return
        # If QMediaPlayer reported duration in the meantime, skip
        if self._duration_ms > 0:
            return

        if duration_ms is None or duration_ms <= 0:
            logger.debug(f"ffprobe fallback failed for {path}")
            return

        # Apply duration from ffprobe
        logger.debug(f"Using ffprobe duration for {path}: {duration_ms}ms")
        self._duration_ms = duration_ms
        self.slider.setRange(0, duration_ms)
        self.lbl_dur.setText(self._fmt_time(duration_ms))

        # Emit durationKnown if not already emitted for this path
        if self._duration_emitted_for != path:
            self._duration_emitted_for = path
            self.durationKnown.emit(duration_ms)
