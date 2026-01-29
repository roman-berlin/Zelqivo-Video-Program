
import logging
import os
import numpy as np
import soundfile as sf
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QWidget, QScrollArea, QLabel, 
    QHBoxLayout, QPushButton, QSizePolicy
)

logger = logging.getLogger(__name__)

class WaveformWidget(QWidget):
    """Widget to draw a single audio waveform with offset."""
    
    def __init__(self, name: str, wav_path: str, offset_ms: float, color: QColor, parent=None):
        super().__init__(parent)
        self.name = name
        self.wav_path = wav_path
        self.offset_ms = offset_ms
        self.color = color
        self.audio_data = None
        self.sr = 16000
        self.duration_ms = 0
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self._load_audio()
        
    def _load_audio(self):
        try:
            # Read audio data
            data, sr = sf.read(self.wav_path, dtype='float32', always_2d=True)
            # Mix to mono if needed
            if data.shape[1] > 1:
                data = np.mean(data, axis=1)
            else:
                data = data.flatten()
                
            self.sr = sr
            self.audio_data = data
            self.duration_ms = (len(data) / sr) * 1000.0
            
            # Downsample for display (e.g. 1 sample per pixel at max zoom?)
            # For now, just keep full data or decimate
            if len(self.audio_data) > 100000:
                # Decimate to ~100k samples for performance
                step = len(self.audio_data) // 100000
                self.audio_data = self.audio_data[::step]
                self.sr = self.sr / step
                
        except Exception as e:
            logger.error("Failed to load waveform: %s", e)
            self.audio_data = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        width = rect.width()
        height = rect.height()
        
        # Background
        painter.fillRect(rect, QColor("#2b2b2b"))
        
        # Draw Label
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(5, 20, f"{self.name} ({self.offset_ms:+.0f}ms)")
        
        if self.audio_data is None:
            painter.drawText(rect.center(), "Failed to load audio")
            return

        # Calculate scales
        # Global timeline: 0 is reference start. 
        # If offset_ms > 0, this track starts late.
        # Check parent dialog for global max duration/scale?
        # For simplicity, assume widget width covers global max duration
        
        # We need a shared scale factor passed from parent.
        # But this widget is independent. Let's start simple:
        # Just draw the waveform. Handling absolute alignment requires knowing global start/end.
        
        # Refactor: Move drawing logic to main dialog to coordinate alignment?
        # Or pass 'pixels_per_ms' and 'global_start_ms' to paintEvent.
        pass

class WaveformView(QWidget):
    """Main view for stacking aligned waveforms."""
    
    def __init__(self, alignments: list, parent=None):
        super().__init__(parent)
        self.alignments = alignments
        self.tracks = []
        self.min_offset = 0.0
        self.max_end = 0.0
        
        self.load_data()
        
    def load_data(self):
        # Load all tracks
        for align in self.alignments:
            if not align.wav_path or not os.path.exists(align.wav_path):
                continue
                
            try:
                data, sr = sf.read(align.wav_path, dtype='float32')
                if data.ndim > 1:
                    data = np.mean(data, axis=1)
                
                # Decimate strongly for visualization (e.g., max 5000 points per track for smooth resize)
                # target ~4000 points
                step = max(1, len(data) // 4000)
                data = data[::step]
                
                duration_ms = (len(data) * step / sr) * 1000.0
                
                self.tracks.append({
                    "name": os.path.basename(align.video_path),
                    "data": data,
                    "offset_ms": align.offset_ms,
                    "duration_ms": duration_ms
                })
            except Exception as e:
                logger.error("Error loading %s: %s", align.video_path, e)

        if not self.tracks:
            return

        # Calculate global timeline bounds
        start_times = [t["offset_ms"] for t in self.tracks]
        end_times = [t["offset_ms"] + t["duration_ms"] for t in self.tracks]
        
        self.min_offset = min(start_times)
        self.max_end = max(end_times) 
        
        # Add some padding
        self.total_duration = self.max_end - self.min_offset
        if self.total_duration <= 0:
            self.total_duration = 1000.0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        width = self.width()
        height = self.height()
        
        # Draw background
        painter.fillRect(self.rect(), QColor("#1e1e1e"))
        
        if not self.tracks:
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No waveform data available")
            return

        # Track height
        track_h = height / len(self.tracks)
        
        colors = [QColor("#4CAF50"), QColor("#2196F3"), QColor("#FFC107"), QColor("#E91E63"), QColor("#9C27B0")]
        
        for i, track in enumerate(self.tracks):
            y_base = i * track_h
            
            # Draw track background (alternating)
            bg_color = QColor("#252525") if i % 2 == 0 else QColor("#2a2a2a")
            painter.fillRect(QRectF(0, y_base, width, track_h), bg_color)
            
            # Draw label
            painter.setPen(QColor("#dddddd"))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.drawText(QRectF(5, y_base + 5, 200, 20), track["name"])
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(QRectF(5, y_base + 25, 200, 20), f"{track['offset_ms']:+.0f}ms")
            
            # Draw waveform
            data = track["data"]
            # Map time to x
            # x = (time_ms - global_start) / total_duration * width
            
            # Start x for this track
            # track absolute start = track['offset_ms']
            # relative to min_offset
            
            rel_start_ms = track["offset_ms"] - self.min_offset
            x_start = (rel_start_ms / self.total_duration) * width
            
            track_dur_ms = track["duration_ms"]
            track_width_px = (track_dur_ms / self.total_duration) * width
            
            if track_width_px <= 0:
                continue
                
            # Scale y: center at y_base + track_h/2, max amp = track_h/2 * 0.9
            y_center = y_base + track_h / 2
            y_scale = (track_h / 2) * 0.8
            
            # Build path
            path = QPainterPath()
            samples = len(data)
            
            # Simply draw lines
            painter.setPen(QPen(colors[i % len(colors)], 1))
            
            step_x = track_width_px / samples
            
            # Optimization: draw min/max per pixel column if dense, but here we decimated to 4000 pts
            # so drawing lineTo is fine.
            
            path.moveTo(x_start, y_center - data[0] * y_scale)
            for j in range(1, samples):
                x = x_start + (j / samples) * track_width_px
                y = y_center - data[j] * y_scale
                path.lineTo(x, y)
                
            painter.drawPath(path)
            
            # Draw start/end markers
            painter.setPen(QPen(QColor(255, 255, 255, 100), 1, Qt.PenStyle.DashLine))
            painter.drawLine(int(x_start), int(y_base), int(x_start), int(y_base + track_h))


class WaveformDialog(QDialog):
    def __init__(self, alignments: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sync Verification - Waveforms")
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        
        self.wave_view = WaveformView(alignments)
        layout.addWidget(self.wave_view)
        
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

