# file: ui/video_preview.py
from __future__ import annotations
from typing import Optional

from PyQt6.QtCore import QUrl, Qt, QTimer
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QHBoxLayout,
    QPushButton,
    QSlider,
    QStackedLayout,
)

# OpenCV is optional; used only for the thumbnail fallback
try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore


class VideoPreview(QWidget):
    """QMediaPlayer preview with controls, fallback thumbnail, and correct play/pause icon."""

    STARTUP_STALL_MS = 2500

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # Banner
        self._banner = QLabel(self)
        self._banner.setVisible(False)
        self._banner.setWordWrap(True)
        self._banner.setStyleSheet(
            "QLabel { background: #332; color: #ffd; border: 1px solid #664; padding: 6px; }"
        )

        # Video/Thumb stack
        self._video_widget = QVideoWidget(self)
        self._thumb = QLabel(self)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setText("No preview available")
        self._stack = QStackedLayout()
        self._stack.addWidget(self._video_widget)  # 0
        self._stack.addWidget(self._thumb)         # 1
        self._stack.setCurrentIndex(0)

        # Player
        self._player = QMediaPlayer(self)
        self._player.setVideoOutput(self._video_widget)

        # Audio (guarded)
        self._audio: Optional[QAudioOutput] = None
        try:
            self._audio = QAudioOutput(self)
            self._player.setAudioOutput(self._audio)
        except Exception:
            self._audio = None

        # Controls
        self._btn_play = QPushButton("▶", self)
        self._btn_play.setFixedWidth(36)
        self._btn_play.clicked.connect(self._on_toggle_play)

        self._slider = QSlider(Qt.Orientation.Horizontal, self)
        self._slider.setRange(0, 0)
        self._slider.sliderPressed.connect(self._on_slider_pressed)
        self._slider.sliderReleased.connect(self._on_slider_released)

        self._lbl_time_now = QLabel("00:00", self)
        self._lbl_time_dur = QLabel("00:00", self)

        # Layout
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.addWidget(self._banner)
        vbox.addLayout(self._stack, 1)

        ctrls = QHBoxLayout()
        ctrls.setContentsMargins(0, 0, 0, 0)
        ctrls.addWidget(self._btn_play)
        ctrls.addWidget(self._lbl_time_now)
        ctrls.addWidget(self._slider, 1)
        ctrls.addWidget(self._lbl_time_dur)
        vbox.addLayout(ctrls)

        # State
        self._path: Optional[str] = None
        self._dragging_slider = False
        self._startup_timer = QTimer(self)
        self._startup_timer.setSingleShot(True)
        self._startup_timer.timeout.connect(self._on_startup_timeout)
        self._last_position = 0

        # Signals
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        # NEW: keep play/pause icon in sync with actual state
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)

        if hasattr(self._player, "errorOccurred"):
            try:
                self._player.errorOccurred.connect(self._on_player_error)  # type: ignore[attr-defined]
            except Exception:
                pass
        if hasattr(self._player, "errorChanged"):
            try:
                self._player.errorChanged.connect(lambda *_: self._on_player_error())  # type: ignore[attr-defined]
            except Exception:
                pass

    # --- Public API ---
    def set_source(self, path: str) -> None:
        self._path = path
        self._show_banner(False)
        self._thumb.clear()
        self._slider.setEnabled(False)
        self._slider.setRange(0, 0)
        self._lbl_time_now.setText("00:00")
        self._lbl_time_dur.setText("00:00")
        self._stack.setCurrentIndex(0)
        self._btn_play.setText("▶")  # will flip to ❚❚ once playback truly starts

        try:
            self._player.setSource(QUrl.fromLocalFile(path))
            self._player.play()
            self._startup_timer.start(self.STARTUP_STALL_MS)
            self._last_position = 0
        except Exception:
            self._fallback_to_thumbnail("Could not open media.")

    # --- Player events ---
    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._btn_play.setText("❚❚")
        else:
            self._btn_play.setText("▶")

    def _on_position_changed(self, pos_ms: int) -> None:
        if not self._dragging_slider:
            self._slider.setValue(pos_ms)
        self._lbl_time_now.setText(self._fmt_time(pos_ms))
        if pos_ms > self._last_position:
            self._last_position = pos_ms
            if self._startup_timer.isActive():
                self._startup_timer.stop()
            if self._stack.currentIndex() != 0:
                self._show_video()

    def _on_duration_changed(self, dur_ms: int) -> None:
        self._slider.setEnabled(dur_ms > 0)
        self._slider.setRange(0, max(0, dur_ms))
        self._lbl_time_dur.setText(self._fmt_time(dur_ms))
        if dur_ms > 0 and self._stack.currentIndex() != 0:
            self._show_video()

    def _on_media_status(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            # playbackStateChanged will flip icon to ▶ automatically
            pass

    def _on_player_error(self, *args) -> None:
        if self._last_position <= 0:
            self._fallback_to_thumbnail("Live preview not available for this codec; will still export correctly.")

    def _on_startup_timeout(self) -> None:
        if self._last_position <= 0:
            self._fallback_to_thumbnail("Live preview not available for this codec; showing first frame instead.")

    # --- Controls ---
    def _on_toggle_play(self) -> None:
        state = self._player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_slider_pressed(self) -> None:
        self._dragging_slider = True

    def _on_slider_released(self) -> None:
        self._dragging_slider = False
        self._player.setPosition(self._slider.value())

    # --- Fallback & View switching ---
    def _show_video(self) -> None:
        self._stack.setCurrentIndex(0)
        self._show_banner(False)

    def _fallback_to_thumbnail(self, reason: str) -> None:
        try:
            self._player.stop()
        except Exception:
            pass
        self._slider.setEnabled(False)
        self._show_banner(True, reason)
        self._show_thumbnail(self._path)

    def _show_banner(self, visible: bool, text: str | None = None) -> None:
        self._banner.setVisible(visible)
        if text:
            self._banner.setText(text)

    def _show_thumbnail(self, path: Optional[str]) -> None:
        if path and cv2 is not None:
            pix = self._read_first_frame_pixmap(path)
        else:
            pix = None
        if pix is not None:
            self._thumb.setPixmap(pix)
        else:
            self._thumb.setText("Preview not available for this file. It will still export correctly.")
        self._stack.setCurrentIndex(1)

    def _read_first_frame_pixmap(self, path: str) -> Optional[QPixmap]:
        try:
            cap = cv2.VideoCapture(path)
            ok, frame = cap.read()
            cap.release()
            if not ok or frame is None:
                return None
            rgb = frame[:, :, ::-1]
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            return QPixmap.fromImage(qimg)
        except Exception:
            return None

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