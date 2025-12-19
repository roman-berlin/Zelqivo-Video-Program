"""External audio synchronisation module using cross-correlation."""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import librosa
import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

# Target sample rate for cross-correlation (lower for faster processing)
_SYNC_SR = 16000


@dataclass
class SyncResult:
    """Result of audio synchronisation."""

    output_path: str
    offset_ms: float
    status: str  # "ok", "trimmed", "padded", "failed"
    message: str


def _load_audio_mono(path: str, sr: int = _SYNC_SR) -> tuple[np.ndarray, int]:
    """Load audio file as mono at specified sample rate."""
    audio, sr_out = librosa.load(path, sr=sr, mono=True)
    return audio, sr_out


def _cross_correlate_offset(ref: np.ndarray, ext: np.ndarray, sr: int) -> float:
    """Compute time offset (in ms) of ext relative to ref via cross-correlation.

    A positive offset means ext starts *after* ref (ext is delayed).
    A negative offset means ext starts *before* ref (ext is early).
    """
    # Use only first 30 seconds for faster correlation
    max_samples = sr * 30
    ref_seg = ref[:max_samples]
    ext_seg = ext[:max_samples]

    # Normalise to prevent numerical issues
    ref_seg = ref_seg / (np.max(np.abs(ref_seg)) + 1e-10)
    ext_seg = ext_seg / (np.max(np.abs(ext_seg)) + 1e-10)

    # Full cross-correlation
    correlation = np.correlate(ref_seg, ext_seg, mode="full")
    # Peak index relative to center
    peak_idx = np.argmax(correlation)
    # Offset in samples: positive = ext delayed, negative = ext early
    # Formula: when ext is delayed (zeros at start), peak shifts left -> negative peak_idx offset
    # We negate to get positive offset for delayed ext
    offset_samples = (len(ext_seg) - 1) - peak_idx
    offset_ms = (offset_samples / sr) * 1000.0
    return offset_ms


def _apply_offset(
    audio: np.ndarray, offset_ms: float, sr: int
) -> tuple[np.ndarray, str, str]:
    """Apply offset to audio by trimming or padding.

    Returns (adjusted_audio, status, message).
    """
    offset_samples = int((offset_ms / 1000.0) * sr)

    if offset_samples > 0:
        # ext is delayed -> trim start of ext (skip first offset_samples)
        if offset_samples >= len(audio):
            return np.zeros(1024, dtype=audio.dtype), "failed", "Offset exceeds audio length"
        trimmed = audio[offset_samples:]
        return trimmed, "trimmed", f"Trimmed {offset_ms:.1f}ms from start"
    elif offset_samples < 0:
        # ext is early -> pad start of ext
        pad_samples = abs(offset_samples)
        padded = np.concatenate([np.zeros(pad_samples, dtype=audio.dtype), audio])
        return padded, "padded", f"Padded {-offset_ms:.1f}ms to start"
    else:
        return audio, "ok", "No offset adjustment needed"


def sync_external_audio(
    external_audio: str,
    reference_audio: str,
    output_dir: Optional[str] = None,
) -> Optional[SyncResult]:
    """Synchronise external audio to reference audio via cross-correlation.

    Args:
        external_audio: Path to external audio file to sync.
        reference_audio: Path to reference audio (e.g., from video).
        output_dir: Directory for output WAV. Uses temp dir if None.

    Returns:
        SyncResult with output path, offset, and status, or None on failure.
    """
    try:
        ext_path = Path(external_audio)
        if not ext_path.exists():
            logger.error("External audio not found: %s", external_audio)
            return SyncResult("", 0.0, "failed", f"File not found: {external_audio}")

        ref_path = Path(reference_audio)
        if not ref_path.exists():
            logger.error("Reference audio not found: %s", reference_audio)
            return SyncResult("", 0.0, "failed", f"File not found: {reference_audio}")

        # Load at sync sample rate for correlation
        logger.info("Loading audio for sync: ext=%s, ref=%s", ext_path.name, ref_path.name)
        ext_audio, sr = _load_audio_mono(external_audio, _SYNC_SR)
        ref_audio, _ = _load_audio_mono(reference_audio, _SYNC_SR)

        # Check minimum length (at least 0.5 second)
        min_samples = int(sr * 0.5)
        if len(ext_audio) < min_samples or len(ref_audio) < min_samples:
            msg = "Audio too short for sync (min 0.5s required)"
            logger.warning(msg)
            return SyncResult("", 0.0, "failed", msg)

        # Cross-correlate to find offset
        offset_ms = _cross_correlate_offset(ref_audio, ext_audio, sr)
        logger.info("Detected offset: %.1f ms", offset_ms)

        # Reload at original quality for output
        ext_full, sr_full = librosa.load(external_audio, sr=None, mono=False)
        if ext_full.ndim == 1:
            ext_full = ext_full.reshape(1, -1)

        # Apply offset to all channels
        adjusted_channels = []
        status = "ok"
        message = "No offset adjustment needed"
        for ch in ext_full:
            adj_ch, status, message = _apply_offset(ch, offset_ms, sr_full)
            adjusted_channels.append(adj_ch)

        # Stack channels back
        if len(adjusted_channels) == 1:
            adjusted = adjusted_channels[0]
        else:
            min_len = min(len(ch) for ch in adjusted_channels)
            adjusted = np.stack([ch[:min_len] for ch in adjusted_channels])

        # Write output
        if output_dir is None:
            output_dir = tempfile.gettempdir()
        out_path = Path(output_dir) / f"{ext_path.stem}_synced.wav"
        sf.write(str(out_path), adjusted.T if adjusted.ndim > 1 else adjusted, sr_full)

        logger.info("Synced audio saved: %s (offset=%.1fms, status=%s)", out_path, offset_ms, status)
        return SyncResult(str(out_path), offset_ms, status, message)

    except Exception as e:
        logger.error("Audio sync failed: %s", e, exc_info=True)
        return SyncResult("", 0.0, "failed", str(e))


def align_audio_offset(
    external_audio: str, reference_audio: str
) -> tuple[float, str]:
    """Compute alignment offset without producing output file.

    Returns (offset_ms, status_message).
    """
    try:
        ext_audio, sr = _load_audio_mono(external_audio, _SYNC_SR)
        ref_audio, _ = _load_audio_mono(reference_audio, _SYNC_SR)

        min_samples = int(sr * 0.5)
        if len(ext_audio) < min_samples or len(ref_audio) < min_samples:
            return 0.0, "Audio too short for sync"

        offset_ms = _cross_correlate_offset(ref_audio, ext_audio, sr)
        return offset_ms, "ok"
    except Exception as e:
        logger.error("Offset calculation failed: %s", e, exc_info=True)
        return 0.0, str(e)
