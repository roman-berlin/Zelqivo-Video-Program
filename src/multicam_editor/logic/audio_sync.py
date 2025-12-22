"""External audio synchronisation module using cross-correlation."""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

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


@dataclass
class CameraAlignment:
    """Alignment result for a single camera."""

    camera_index: int
    video_path: str
    offset_ms: float
    status: str  # "ok", "no_audio", "failed"
    message: str


def _load_audio_mono(path: str, sr: int = _SYNC_SR) -> tuple[np.ndarray, int]:
    """Load audio file as mono at specified sample rate."""
    audio, sr_out = librosa.load(path, sr=sr, mono=True)
    return audio, sr_out


def _cross_correlate_offset(ref: np.ndarray, ext: np.ndarray, sr: int) -> tuple[float, float, float]:
    """Compute time offset (in ms) of ext relative to ref via cross-correlation.

    A positive offset means ext starts *after* ref (ext is delayed).
    A negative offset means ext starts *before* ref (ext is early).

    Returns:
        (offset_ms, correlation_score, sample_window_sec)
    """
    # Use only first 30 seconds for faster correlation
    sample_window_sec = 30.0
    max_samples = int(sr * sample_window_sec)
    ref_seg = ref[:max_samples]
    ext_seg = ext[:max_samples]
    actual_window_sec = len(ref_seg) / sr

    # Normalise to prevent numerical issues
    ref_seg = ref_seg / (np.max(np.abs(ref_seg)) + 1e-10)
    ext_seg = ext_seg / (np.max(np.abs(ext_seg)) + 1e-10)

    # Full cross-correlation
    correlation = np.correlate(ref_seg, ext_seg, mode="full")
    # Peak index relative to center
    peak_idx = np.argmax(correlation)
    peak_value = correlation[peak_idx]

    # Normalize correlation score to 0-1 range
    correlation_score = float(peak_value / (len(ref_seg) + 1e-10))

    # Offset in samples: positive = ext delayed, negative = ext early
    offset_samples = (len(ext_seg) - 1) - peak_idx
    offset_ms = (offset_samples / sr) * 1000.0

    # QA logging
    logger.info(
        "[QA] Audio sync: offset_ms=%.1f, correlation_score=%.4f, sample_window=%.1fs",
        offset_ms, correlation_score, actual_window_sec
    )

    return offset_ms, correlation_score, actual_window_sec


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

        # Cross-correlate to find offset (returns tuple with QA metrics)
        offset_ms, corr_score, window_sec = _cross_correlate_offset(ref_audio, ext_audio, sr)
        logger.info("Detected offset: %.1f ms (correlation=%.4f)", offset_ms, corr_score)

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

        offset_ms, _, _ = _cross_correlate_offset(ref_audio, ext_audio, sr)
        return offset_ms, "ok"
    except Exception as e:
        logger.error("Offset calculation failed: %s", e, exc_info=True)
        return 0.0, str(e)


def align_cameras(
    video_paths: List[str],
    on_progress: Optional[callable] = None,
) -> List[CameraAlignment]:
    """Align multiple cameras using audio cross-correlation.

    First camera (index 0) is the primary reference with offset_ms=0.
    All other cameras are aligned relative to the primary.

    Args:
        video_paths: List of video file paths (at least 2).
        on_progress: Optional callback(camera_index, total) for progress.

    Returns:
        List of CameraAlignment results for each camera.
    """
    from ..utils.ffmpeg import extract_audio_to_wav
    from ..utils.ffprobe import has_audio_stream

    if len(video_paths) < 2:
        logger.warning("align_cameras requires at least 2 videos")
        return [CameraAlignment(0, video_paths[0], 0.0, "ok", "Single camera")]

    results: List[CameraAlignment] = []
    temp_wavs: List[str] = []

    try:
        # Primary camera (index 0) always has offset 0
        primary_path = video_paths[0]
        results.append(CameraAlignment(
            camera_index=0,
            video_path=primary_path,
            offset_ms=0.0,
            status="ok",
            message="Primary camera (reference)"
        ))

        if on_progress:
            on_progress(0, len(video_paths))

        # Check if primary has audio
        if not has_audio_stream(primary_path):
            logger.warning("Primary camera has no audio stream: %s", os.path.basename(primary_path))
            # All cameras get offset 0 since we can't correlate
            for i, path in enumerate(video_paths[1:], start=1):
                results.append(CameraAlignment(
                    camera_index=i,
                    video_path=path,
                    offset_ms=0.0,
                    status="no_audio",
                    message="Cannot align: primary has no audio"
                ))
                if on_progress:
                    on_progress(i, len(video_paths))
            return results

        # Extract primary audio
        logger.info("Extracting audio from primary camera: %s", os.path.basename(primary_path))
        primary_result = extract_audio_to_wav(primary_path, sample_rate=_SYNC_SR, mono=True)
        if not primary_result.success or not primary_result.output_path:
            logger.error("Failed to extract primary audio: %s", primary_result.error)
            # All cameras get offset 0
            for i, path in enumerate(video_paths[1:], start=1):
                results.append(CameraAlignment(
                    camera_index=i,
                    video_path=path,
                    offset_ms=0.0,
                    status="failed",
                    message=f"Primary audio extraction failed: {primary_result.error}"
                ))
                if on_progress:
                    on_progress(i, len(video_paths))
            return results

        primary_wav = primary_result.output_path
        temp_wavs.append(primary_wav)

        # Load primary audio once
        try:
            primary_audio, sr = _load_audio_mono(primary_wav, _SYNC_SR)
        except Exception as e:
            logger.error("Failed to load primary audio: %s", e)
            for i, path in enumerate(video_paths[1:], start=1):
                results.append(CameraAlignment(i, path, 0.0, "failed", str(e)))
                if on_progress:
                    on_progress(i, len(video_paths))
            return results

        min_samples = int(sr * 0.5)
        if len(primary_audio) < min_samples:
            logger.warning("Primary audio too short for alignment")
            for i, path in enumerate(video_paths[1:], start=1):
                results.append(CameraAlignment(i, path, 0.0, "failed", "Primary audio too short"))
                if on_progress:
                    on_progress(i, len(video_paths))
            return results

        # Process each secondary camera
        for i, path in enumerate(video_paths[1:], start=1):
            logger.info("Aligning camera %d: %s", i, os.path.basename(path))

            # Check for audio stream
            if not has_audio_stream(path):
                logger.warning("Camera %d has no audio stream, using offset=0", i)
                results.append(CameraAlignment(
                    camera_index=i,
                    video_path=path,
                    offset_ms=0.0,
                    status="no_audio",
                    message="No audio stream in video"
                ))
                if on_progress:
                    on_progress(i, len(video_paths))
                continue

            # Extract audio
            extract_result = extract_audio_to_wav(path, sample_rate=_SYNC_SR, mono=True)
            if not extract_result.success or not extract_result.output_path:
                logger.error("Failed to extract audio from camera %d: %s", i, extract_result.error)
                results.append(CameraAlignment(
                    camera_index=i,
                    video_path=path,
                    offset_ms=0.0,
                    status="failed",
                    message=f"Audio extraction failed: {extract_result.error}"
                ))
                if on_progress:
                    on_progress(i, len(video_paths))
                continue

            secondary_wav = extract_result.output_path
            temp_wavs.append(secondary_wav)

            # Cross-correlate
            try:
                secondary_audio, _ = _load_audio_mono(secondary_wav, _SYNC_SR)

                if len(secondary_audio) < min_samples:
                    logger.warning("Camera %d audio too short for alignment", i)
                    results.append(CameraAlignment(
                        camera_index=i,
                        video_path=path,
                        offset_ms=0.0,
                        status="failed",
                        message="Audio too short for correlation"
                    ))
                    if on_progress:
                        on_progress(i, len(video_paths))
                    continue

                offset_ms, corr_score, _ = _cross_correlate_offset(primary_audio, secondary_audio, sr)
                logger.info("Camera %d offset: %.1f ms (correlation=%.4f)", i, offset_ms, corr_score)

                results.append(CameraAlignment(
                    camera_index=i,
                    video_path=path,
                    offset_ms=offset_ms,
                    status="ok",
                    message=f"Aligned (correlation={corr_score:.3f})"
                ))

            except Exception as e:
                logger.error("Correlation failed for camera %d: %s", i, e, exc_info=True)
                results.append(CameraAlignment(
                    camera_index=i,
                    video_path=path,
                    offset_ms=0.0,
                    status="failed",
                    message=f"Correlation failed: {e}"
                ))

            if on_progress:
                on_progress(i, len(video_paths))

    finally:
        # Cleanup temp WAV files
        for wav_path in temp_wavs:
            try:
                if os.path.isfile(wav_path):
                    os.remove(wav_path)
                    logger.debug("Cleaned up temp WAV: %s", os.path.basename(wav_path))
            except Exception as e:
                logger.debug("Failed to cleanup %s: %s", wav_path, e)

    return results
