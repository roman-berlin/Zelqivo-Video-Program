"""Multi-View Dialog for synchronized camera preview.

Shows all cameras playing in sync with a 2x2 grid layout.
"""

import logging
import os
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class MultiViewDialog(QDialog):
    """Dialog showing all cameras synchronized in a grid."""

    def __init__(
        self,
        parent: Optional[QWidget],
        video_paths: List[str],
        sync_offsets_ms: Dict[int, float],
        waveform_data: Optional[Dict[int, list]] = None,
    ):
        """Initialize multi-view dialog.
        
        Args:
            parent: Parent widget
            video_paths: List of video file paths
            sync_offsets_ms: Dict mapping camera index to offset in ms
            waveform_data: Optional dict mapping camera index to waveform samples
        """
        super().__init__(parent)
        self.setWindowTitle("🎬 Multi-View Preview")
        self.setMinimumSize(900, 700)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        self._video_paths = video_paths
        self._sync_offsets = sync_offsets_ms
        self._waveform_data = waveform_data or {}
        
        # Media players for each camera
        self._players: List[QMediaPlayer] = []
        self._audio_outputs: List[QAudioOutput] = []
        self._video_widgets: List[QVideoWidget] = []
        
        # Playback state
        self._is_playing = False
        self._current_audio_source = 0
        self._duration_ms = 0
        
        # Update timer for position sync
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self._sync_positions)
        self._sync_timer.setInterval(100)  # 10 fps sync
        
        self._init_ui()
        self._load_videos()
    
    def _init_ui(self) -> None:
        """Initialize the UI layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # --- Video Grid (2x2) ---
        video_group = QGroupBox("Cameras")
        grid = QGridLayout(video_group)
        grid.setSpacing(4)
        
        num_cameras = min(len(self._video_paths), 4)
        for i in range(num_cameras):
            video_widget = QVideoWidget()
            video_widget.setMinimumSize(400, 225)  # 16:9 aspect
            self._video_widgets.append(video_widget)
            
            # Create container with label
            container = QVBoxLayout()
            label = QLabel(f"📷 Cam {i+1}: {os.path.basename(self._video_paths[i])}")
            label.setStyleSheet("font-weight: bold; color: #3498db;")
            container.addWidget(label)
            container.addWidget(video_widget)
            
            # 2x2 grid positioning
            row = i // 2
            col = i % 2
            
            wrapper = QWidget()
            wrapper.setLayout(container)
            grid.addWidget(wrapper, row, col)
        
        layout.addWidget(video_group)
        
        # --- Playback Controls ---
        controls_layout = QHBoxLayout()
        
        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setMinimumWidth(100)
        self.btn_play.clicked.connect(self._toggle_play)
        controls_layout.addWidget(self.btn_play)
        
        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_stop.clicked.connect(self._stop)
        controls_layout.addWidget(self.btn_stop)
        
        controls_layout.addSpacing(20)
        
        # Audio source selector
        controls_layout.addWidget(QLabel("🔊 Audio:"))
        self.cmb_audio = QComboBox()
        for i in range(len(self._video_paths)):
            self.cmb_audio.addItem(f"Cam {i+1}", i)
        self.cmb_audio.currentIndexChanged.connect(self._change_audio_source)
        controls_layout.addWidget(self.cmb_audio)
        
        controls_layout.addStretch()
        
        # Time display
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setStyleSheet("font-family: monospace;")
        controls_layout.addWidget(self.lbl_time)
        
        layout.addLayout(controls_layout)
        
        # --- Timeline Slider ---
        slider_layout = QHBoxLayout()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.slider.valueChanged.connect(self._on_slider_moved)
        slider_layout.addWidget(self.slider)
        layout.addLayout(slider_layout)
        
        # --- Waveform Section ---
        if self._waveform_data:
            waveform_group = QGroupBox("📊 Waveforms (Aligned)")
            waveform_layout = QVBoxLayout(waveform_group)
            
            # Simple text-based waveform representation
            for i in range(min(len(self._video_paths), 4)):
                offset = self._sync_offsets.get(i, 0)
                wf_label = QLabel(f"Cam {i+1} (offset: {offset:+.0f}ms)")
                wf_label.setStyleSheet("font-family: monospace; color: #2ecc71;")
                waveform_layout.addWidget(wf_label)
            
            layout.addWidget(waveform_group)
        
        # --- Close Button ---
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)
    
    def _load_videos(self) -> None:
        """Load videos into media players."""
        for i, path in enumerate(self._video_paths[:4]):
            player = QMediaPlayer()
            audio_output = QAudioOutput()
            
            # Only first camera has audio initially
            audio_output.setVolume(1.0 if i == 0 else 0.0)
            
            player.setAudioOutput(audio_output)
            if i < len(self._video_widgets):
                player.setVideoOutput(self._video_widgets[i])
            
            player.setSource(QUrl.fromLocalFile(path))
            
            # Get duration from first player
            if i == 0:
                player.durationChanged.connect(self._on_duration_changed)
                player.positionChanged.connect(self._on_position_changed)
            
            self._players.append(player)
            self._audio_outputs.append(audio_output)
        
        logger.info("Loaded %d cameras for multi-view preview", len(self._players))
    
    def _on_duration_changed(self, duration: int) -> None:
        """Handle duration change from primary player."""
        self._duration_ms = duration
        self._update_time_label()
    
    def _on_position_changed(self, position: int) -> None:
        """Handle position change from primary player."""
        if self._duration_ms > 0 and not self.slider.isSliderDown():
            slider_pos = int(position / self._duration_ms * 1000)
            self.slider.setValue(slider_pos)
        self._update_time_label()
    
    def _update_time_label(self) -> None:
        """Update the time display."""
        if self._players:
            pos = self._players[0].position()
            dur = self._duration_ms
            
            pos_str = f"{pos // 60000:02d}:{(pos // 1000) % 60:02d}"
            dur_str = f"{dur // 60000:02d}:{(dur // 1000) % 60:02d}"
            self.lbl_time.setText(f"{pos_str} / {dur_str}")
    
    def _toggle_play(self) -> None:
        """Toggle play/pause."""
        if self._is_playing:
            self._pause()
        else:
            self._play()
    
    def _play(self) -> None:
        """Start synchronized playback."""
        if not self._players:
            return
        
        # Apply sync offsets and start all players
        base_position = self._players[0].position()
        
        for i, player in enumerate(self._players):
            offset_ms = self._sync_offsets.get(i, 0)
            target_pos = max(0, int(base_position + offset_ms))
            player.setPosition(target_pos)
            player.play()
        
        self._is_playing = True
        self.btn_play.setText("⏸ Pause")
        self._sync_timer.start()
        logger.debug("Multi-view playback started")
    
    def _pause(self) -> None:
        """Pause all players."""
        for player in self._players:
            player.pause()
        
        self._is_playing = False
        self.btn_play.setText("▶ Play")
        self._sync_timer.stop()
    
    def _stop(self) -> None:
        """Stop and reset all players."""
        for player in self._players:
            player.stop()
            player.setPosition(0)
        
        self._is_playing = False
        self.btn_play.setText("▶ Play")
        self._sync_timer.stop()
        self.slider.setValue(0)
    
    def _sync_positions(self) -> None:
        """Periodically sync player positions to maintain alignment."""
        if not self._players or not self._is_playing:
            return
        
        base_pos = self._players[0].position()
        
        for i, player in enumerate(self._players[1:], start=1):
            offset_ms = self._sync_offsets.get(i, 0)
            target_pos = int(base_pos + offset_ms)
            current_pos = player.position()
            
            # Only correct if drift > 100ms
            if abs(current_pos - target_pos) > 100:
                player.setPosition(target_pos)
    
    def _change_audio_source(self, index: int) -> None:
        """Change which camera's audio is playing."""
        cam_index = self.cmb_audio.currentData()
        
        for i, audio_output in enumerate(self._audio_outputs):
            audio_output.setVolume(1.0 if i == cam_index else 0.0)
        
        self._current_audio_source = cam_index
        logger.debug("Audio source changed to Cam %d", cam_index + 1)
    
    def _on_slider_pressed(self) -> None:
        """Pause while scrubbing."""
        if self._is_playing:
            for player in self._players:
                player.pause()
            self._sync_timer.stop()
    
    def _on_slider_released(self) -> None:
        """Resume after scrubbing."""
        if self._is_playing:
            self._play()
    
    def _on_slider_moved(self, value: int) -> None:
        """Seek all players to slider position."""
        if self._duration_ms <= 0:
            return
        
        if self.slider.isSliderDown():
            base_pos = int(value / 1000 * self._duration_ms)
            
            for i, player in enumerate(self._players):
                offset_ms = self._sync_offsets.get(i, 0)
                target_pos = max(0, int(base_pos + offset_ms))
                player.setPosition(target_pos)
    
    def closeEvent(self, event) -> None:
        """Clean up on close."""
        self._sync_timer.stop()
        for player in self._players:
            player.stop()
        logger.debug("MultiViewDialog closed")
        super().closeEvent(event)
