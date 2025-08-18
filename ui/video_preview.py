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
        self._user_scrubbing = False  # why: avoid playhead "jump" feedback during drag
        self._duration_emitted_for: Optional[str] = None

        # throttle UI updates to reduce jitter (especially on Windows)
        self._pos_ms_latest = 0
        self._pos_timer = QTimer(self)
        self._pos_timer.setInterval(33)  # ~30fps
        self._pos_timer.timeout.connect(self._apply_latest_position_to_ui)
        self._pos_timer.start()

        # --- UI ---
        self._stack = QStackedLayout(self)

        # video widget page
        video_page = QWidget(self)
        vlay = QVBoxLayout(video_page)
        vlay.setContentsMargins(0, 0, 0, 0)

        self._video_widget = QVideoWidget(video_page)
        vlay.addWidget(self._video_widget, 1)

        # controls
        ctrl = QWidget(video_page)
        hlay = QHBoxLayout(ctrl)
        hlay.setContentsMargins(8, 4, 8, 4)

        self.btn_play = QPushButton("▶", ctrl)
        self.btn_play.setFixedWidth(28)
        self.btn_play.clicked.connect(self._toggle_play)

        self.lbl_time = QLabel("00:00", ctrl)

        self.slider = QSlider(Qt.Orientation.Horizontal, ctrl)
        self.slider.setMinimum(0)
        self.slider.setMaximum(100)
        self.slider.setSingleStep(1000)  # 1s
        self.slider.setPageStep(5000)    # 5s
        self.slider.setTracking(True)    # allow live scrubbing, but guarded by flag
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.slider.sliderMoved.connect(self._on_slider_moved)

        self.lbl_dur = QLabel("00:00", ctrl)

        hlay.addWidget(self.btn_play)
        hlay.addWidget(self.lbl_time)
        hlay.addWidget(self.slider, 1)
        hlay.addWidget(self.lbl_dur)

        vlay.addWidget(ctrl)

        # thumbnail/placeholder page
        thumb_page = QWidget(self)
        tlay = QVBoxLayout(thumb_page)
        tlay.setContentsMargins(0, 0, 0, 0)
        self._thumb_label = QLabel("", thumb_page)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setStyleSheet("background: #222; color: #bbb;")
        tlay.addWidget(self._thumb_label, 1)

        self._stack.addWidget(video_page)   # index 0
        self._stack.addWidget(thumb_page)   # index 1
        self._stack.setCurrentIndex(0)

        # connect signals after UI is ready
        self._player.setVideoOutput(self._video_widget)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(self._on_error)

    # --- public API ---
    def set_source(self, path: Optional[str]) -> None:
        if not path:
            self._clear()
            return
        if self._source_path == path:
            return
        self._source_path = path
        self._duration_ms = 0
        self._set_labels(0, 0)
        self.slider.setRange(0, 1)
        self.slider.setValue(0)
        self._stack.setCurrentIndex(0)
        self._thumb_label.clear()
        self._player.setSource(QUrl.fromLocalFile(path))
        # Autoplay for UX parity with earlier prompts
        self._player.play()
        self._update_play_icon()

    def current_position_ms(self) -> int:
        return int(self._player.position())

    # --- slots ---
    def _toggle_play(self) -> None:
        st = self._player.playbackState()
        if st == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()
        self._update_play_icon()

    def _on_duration_changed(self, dur: int) -> None:
        self._duration_ms = max(0, int(dur))
        if self._duration_ms <= 0:
            self.slider.setRange(0, 1)
        else:
            self.slider.setRange(0, self._duration_ms)
        self.lbl_dur.setText(self._fmt_time(self._duration_ms))
        # inform TrimPanel once per source
        if self._source_path and self._duration_emitted_for != self._source_path:
            self._duration_emitted_for = self._source_path
            self.durationKnown.emit(self._duration_ms)

    def _on_position_changed(self, pos: int) -> None:
        self._pos_ms_latest = int(max(0, pos))
        # defer UI update to timer; avoids fight with sliderMoved while dragging

    def _apply_latest_position_to_ui(self) -> None:
        if self._user_scrubbing:
            return
        pos = self._pos_ms_latest
        # keep slider/label in sync without oscillation
        if self.slider.maximum() > 0:
            self.slider.blockSignals(True)
            try:
                self.slider.setValue(pos)
            finally:
                self.slider.blockSignals(False)
        self._set_labels(pos, self._duration_ms)

    def _on_media_status(self, _status) -> None:
        # if video fails to render, show thumbnail fallback
        if self._player.mediaStatus() == QMediaPlayer.MediaStatus.InvalidMedia:
            self._show_thumbnail_fallback(self._source_path)

    def _on_error(self, _err, *_args) -> None:
        self._show_thumbnail_fallback(self._source_path)

    def _on_slider_pressed(self) -> None:
        self._user_scrubbing = True  # why: prevent positionChanged from fighting the drag

    def _on_slider_released(self) -> None:
        # seek when user releases the knob
        pos = int(self.slider.value())
        self._player.setPosition(pos)
        self._user_scrubbing = False
        # update UI immediately for responsiveness
        self._pos_ms_latest = pos
        self._apply_latest_position_to_ui()

    def _on_slider_moved(self, value: int) -> None:
        # live scrubbing; guarded by _user_scrubbing flag to avoid jitter
        self._player.setPosition(int(value))
        self._pos_ms_latest = int(value)
        self._apply_latest_position_to_ui()

    # --- helpers ---
    def _clear(self) -> None:
        self._player.stop()
        self._player.setSource(QUrl())
        self._source_path = None
        self._duration_ms = 0
        self._set_labels(0, 0)
        self.slider.setRange(0, 1)
        self.slider.setValue(0)
        self._update_play_icon()
        self._stack.setCurrentIndex(0)

    def _update_play_icon(self) -> None:
        st = self._player.playbackState()
        self.btn_play.setText("⏸" if st == QMediaPlayer.PlaybackState.PlayingState else "▶")

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
            self._thumb_label.setPixmap(pm.scaled(self._thumb_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self._stack.setCurrentIndex(1)

    def resizeEvent(self, e) -> None:  # type: ignore[override]
        super().resizeEvent(e)
        if self._stack.currentIndex() == 1 and not self._thumb_label.pixmap() is None:
            # rescale stored pixmap to fit label
            pm = self._thumb_label.pixmap()
            if pm:
                self._thumb_label.setPixmap(pm.scaled(self._thumb_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

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
