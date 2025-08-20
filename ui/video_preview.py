# file: ui/video_preview.py
from __future__ import annotations
from typing import Optional

from PyQt6.QtCore import QUrl, Qt, QTimer, pyqtSignal
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


class VideoPreview(QWidget):
    """Video preview with play/pause/seek and OpenCV thumbnail fallback.

    Signals
    -------
    durationKnown(int): emitted when the media duration (ms) becomes available.

    Why relevant changes:
    - Smooth playhead: timer-driven UI + capped step per tick avoids visible jumps
      from irregular backend `positionChanged` bursts on Windows.
    - During slider drag we don't continuously seek; we seek once on release.
    """

    durationKnown = pyqtSignal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # --- backend ---
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)

        self._duration_ms = 0
        self._source_path: Optional[str] = None
        self._user_scrubbing = False
        self._pending_seek_ms: int = 0
        self._duration_emitted_for: Optional[str] = None

        # UI-smoothed position (ms). We gently approach the real player position.
        self._ui_pos_ms: int = 0
        self._MAX_STEP_MS: int = 40  # cap UI change per tick (smooths bursty updates)

        # steady UI refresh (≈60fps) for smooth playhead
        self._tick = QTimer(self)
        self._tick.setInterval(16)
        self._tick.timeout.connect(self._update_ui_from_player)
        self._tick.start()

        # --- UI ---
        self._stack = QStackedLayout(self)

        # video page
        video_page = QWidget(self)
        vlay = QVBoxLayout(video_page)
        vlay.setContentsMargins(0, 0, 0, 0)

        self._video_widget = QVideoWidget(video_page)
        vlay.addWidget(self._video_widget, 1)

        ctrl = QWidget(video_page)
        hlay = QHBoxLayout(ctrl)
        hlay.setContentsMargins(8, 4, 8, 4)

        self.btn_play = QPushButton("▶", ctrl)
        self.btn_play.setFixedWidth(28)
        self.btn_play.clicked.connect(self._toggle_play)

        self.lbl_time = QLabel("00:00", ctrl)

        self.slider = QSlider(Qt.Orientation.Horizontal, ctrl)
        self.slider.setMinimum(0)
        self.slider.setMaximum(1)
        self.slider.setSingleStep(250)  # finer keyboard step, doesn't affect mouse drag
        self.slider.setPageStep(2000)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.slider.sliderMoved.connect(self._on_slider_moved)

        self.lbl_dur = QLabel("00:00", ctrl)

        hlay.addWidget(self.btn_play)
        hlay.addWidget(self.lbl_time)
        hlay.addWidget(self.slider, 1)
        hlay.addWidget(self.lbl_dur)

        vlay.addWidget(ctrl)

        # thumbnail page (fallback)
        thumb_page = QWidget(self)
        tlay = QVBoxLayout(thumb_page)
        tlay.setContentsMargins(0, 0, 0, 0)
        self._thumb_label = QLabel("", thumb_page)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setStyleSheet("background: #222; color: #bbb;")
        tlay.addWidget(self._thumb_label, 1)

        self._stack.addWidget(video_page)   # 0
        self._stack.addWidget(thumb_page)   # 1
        self._stack.setCurrentIndex(0)

        # connect after UI ready
        self._player.setVideoOutput(self._video_widget)
        self._player.positionChanged.connect(self._on_player_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(self._on_error)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)

    # --- public API ---
    def set_source(self, path: Optional[str]) -> None:
        if not path:
            self._clear()
            return
        if self._source_path == path:
            return
        self._source_path = path
        self._duration_ms = 0
        self._ui_pos_ms = 0
        self._set_labels(0, 0)
        self.slider.setRange(0, 1)
        self.slider.setValue(0)
        self._stack.setCurrentIndex(0)
        self._thumb_label.clear()
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()  # autoplay for UX
        # icon will update via playbackState

    def current_position_ms(self) -> int:
        return int(self._player.position())

    # --- slots / handlers ---
    def _toggle_play(self) -> None:
        st = self._player.playbackState()
        if st == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()
        # icon updates in _on_playback_state_changed

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        # correct icon: pause when playing, play otherwise
        self.btn_play.setText("⏸" if state == QMediaPlayer.PlaybackState.PlayingState else "▶")
        # ensure UI pos matches actual when pausing/stopping
        if state != QMediaPlayer.PlaybackState.PlayingState and not self._user_scrubbing:
            self._ui_pos_ms = int(self._player.position())
            self._apply_ui_position()

    def _on_duration_changed(self, dur: int) -> None:
        self._duration_ms = max(0, int(dur))
        self.slider.setRange(0, self._duration_ms if self._duration_ms > 0 else 1)
        self.lbl_dur.setText(self._fmt_time(self._duration_ms))
        if self._source_path and self._duration_emitted_for != self._source_path:
            self._duration_emitted_for = self._source_path
            self.durationKnown.emit(self._duration_ms)

    def _on_player_position_changed(self, _pos: int) -> None:
        # ignored; we drive UI at a steady rate for smoothness
        pass

    def _on_media_status(self, _status) -> None:
        if self._player.mediaStatus() == QMediaPlayer.MediaStatus.InvalidMedia:
            self._show_thumbnail_fallback(self._source_path)

    def _on_error(self, _err, *_args) -> None:
        self._show_thumbnail_fallback(self._source_path)

    def _on_slider_pressed(self) -> None:
        self._user_scrubbing = True  # prevent timer from overwriting knob during drag

    def _on_slider_moved(self, value: int) -> None:
        self._pending_seek_ms = int(value)
        # show time at knob while dragging
        self._set_labels(self._pending_seek_ms, self._duration_ms)

    def _on_slider_released(self) -> None:
        pos = int(self._pending_seek_ms)
        self._player.setPosition(pos)  # single seek at release
        self._user_scrubbing = False
        self._ui_pos_ms = pos  # immediate UI match post-seek
        self._apply_ui_position()

    # --- periodic UI updater ---
    def _update_ui_from_player(self) -> None:
        if self._user_scrubbing:
            return
        actual = int(max(0, self._player.position()))
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            # move UI towards the actual pos with a capped step per tick
            diff = actual - self._ui_pos_ms
            if diff != 0:
                step = max(-self._MAX_STEP_MS, min(self._MAX_STEP_MS, diff))
                self._ui_pos_ms += step
        else:
            # paused/stopped: match exactly
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
        self._player.stop()
        self._player.setSource(QUrl())
        self._source_path = None
        self._duration_ms = 0
        self._ui_pos_ms = 0
        self._set_labels(0, 0)
        self.slider.setRange(0, 1)
        self.slider.setValue(0)
        self.btn_play.setText("▶")
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
