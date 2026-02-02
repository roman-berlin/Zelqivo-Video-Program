"""Active speaker diarization with pluggable backends."""

from __future__ import annotations

import logging
import struct
import tempfile
import time
import wave
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Protocol, runtime_checkable, Tuple

logger = logging.getLogger(__name__)

import warnings
# Suppress torchcodec/torchaudio warnings on Windows
warnings.filterwarnings("ignore", message=".*torchcodec.*")
warnings.filterwarnings("ignore", message=".*torchaudio._backend.*")


class DiarizationMode(Enum):
    """Diarization backend mode selection."""
    OFF = "off"          # No diarization, single camera
    STUB = "stub"        # Dev-only stub (EnergyVADBackend)
    ENERGY = "energy"    # CPU-only RMS energy-based switching (default for V1)
    REAL = "real"        # Real pyannote.audio backend
    LIPS = "lips"        # Visual lip movement detection
    HYBRID = "hybrid"    # LIPS + Audio VAD (recommended)



@dataclass(frozen=True)
class SpeakerSegment:
    """A single speaker segment."""
    start_ms: int
    end_ms: int
    speaker_id: int

    def __post_init__(self) -> None:
        if self.start_ms < 0:
            raise ValueError("start_ms must be >= 0")
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be > start_ms")
        if self.speaker_id < 0:
            raise ValueError("speaker_id must be >= 0")


@runtime_checkable
class DiarizationBackend(Protocol):
    """Protocol for diarization backends."""

    def diarize(self, audio_path: str, num_channels: int = 2) -> List[SpeakerSegment]:
        """Return non-overlapping speaker segments sorted by start_ms."""
        ...


class NullBackend:
    """No-op backend for OFF mode - returns empty segments."""

    def diarize(self, audio_path: str, num_channels: int = 2) -> List[SpeakerSegment]:
        logger.debug("NullBackend: diarization disabled, returning empty")
        return []


class EnergyVADBackend:
    """
    Stub backend: energy-based VAD with channel gating.

    Simulates detection by creating mock segments based on channel count.
    In production, this would analyze actual audio energy levels.
    """

    def __init__(self, min_segment_ms: int = 500, silence_threshold: float = 0.01) -> None:
        self.min_segment_ms = min_segment_ms
        self.silence_threshold = silence_threshold

    def diarize(self, audio_path: str, num_channels: int = 2) -> List[SpeakerSegment]:
        """
        Stub implementation returning mock segments.

        Creates alternating speaker segments (one per channel) for demonstration.
        Real implementation would analyze audio energy per channel.
        """
        logger.debug("EnergyVADBackend.diarize called: %s, channels=%d", audio_path, num_channels)

        if num_channels < 1:
            return []

        # Stub: create 3 alternating segments per channel (6 total for stereo)
        segments: List[SpeakerSegment] = []
        segment_duration_ms = 2000
        current_ms = 0

        for i in range(min(num_channels * 3, 10)):  # cap at 10 segments
            speaker_id = i % num_channels
            segments.append(SpeakerSegment(
                start_ms=current_ms,
                end_ms=current_ms + segment_duration_ms,
                speaker_id=speaker_id,
            ))
            current_ms += segment_duration_ms

        return segments


class RealEnergyVADBackend:
    """
    CPU-only energy-based speaker detection for multicam switching.

    Robust switching logic to avoid jumping on noise spikes:
    1. Adaptive noise floor per camera: estimated from p20 of energy distribution.
       Frames below noise_floor * gate_factor are treated as non-speech.
    2. Hysteresis: candidate must beat current camera by margin (ratio >= hysteresis_ratio,
       ~3 dB) to trigger a switch consideration.
    3. Consecutive-windows requirement: candidate must win N consecutive windows
       (default 3 x 200ms = 600ms) to actually switch.
    4. Min hold time: after a switch, stay on camera for at least hold_time_ms (2s default).
    5. When uncertain (all cameras below threshold or no clear winner): stay on current camera.

    Thresholds rationale:
    - noise_percentile=20: p20 captures ambient noise floor ignoring speech peaks.
    - gate_factor=2.0: speech typically 6-10 dB above noise; factor of 2 (~6 dB) is conservative.
    - hysteresis_ratio=1.6: ~4 dB margin prevents ping-pong on similar levels.
    - consecutive_wins=3: 600ms sustained speech prevents short noise bursts.
    - hold_time_ms=2000: 2 seconds prevents rapid switching during natural pauses.

    This is the default V1 backend - works without pyannote or HuggingFace setup.
    """

    # Default parameters
    DEFAULT_WINDOW_MS = 200
    DEFAULT_SILENCE_THRESHOLD = 0.01  # RMS below this = absolute silence
    DEFAULT_MIN_SEGMENT_MS = 200  # Minimum segment length

    # Robustness parameters
    DEFAULT_NOISE_PERCENTILE = 20  # Use p20 of energy distribution as noise floor
    DEFAULT_GATE_FACTOR = 2.0  # Speech must be gate_factor * noise_floor
    DEFAULT_HYSTERESIS_RATIO = 1.6  # Candidate must beat current by this ratio (~4 dB)
    DEFAULT_CONSECUTIVE_WINS = 3  # Must win N consecutive windows to switch
    DEFAULT_HOLD_TIME_MS = 2000  # Minimum time to stay on a camera after switching

    def __init__(
        self,
        window_ms: int = DEFAULT_WINDOW_MS,
        silence_threshold: float = DEFAULT_SILENCE_THRESHOLD,
        min_segment_ms: int = DEFAULT_MIN_SEGMENT_MS,
        noise_percentile: int = DEFAULT_NOISE_PERCENTILE,
        gate_factor: float = DEFAULT_GATE_FACTOR,
        hysteresis_ratio: float = DEFAULT_HYSTERESIS_RATIO,
        consecutive_wins: int = DEFAULT_CONSECUTIVE_WINS,
        hold_time_ms: int = DEFAULT_HOLD_TIME_MS,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> None:
        self.window_ms = window_ms
        self.silence_threshold = silence_threshold
        self.min_segment_ms = min_segment_ms
        self.noise_percentile = noise_percentile
        self.gate_factor = gate_factor
        self.hysteresis_ratio = hysteresis_ratio
        self.consecutive_wins = consecutive_wins
        self.hold_time_ms = hold_time_ms
        self.cancel_callback = cancel_callback
        # Paths to camera audio WAV files (set before diarize)
        self._camera_audio_paths: List[str] = []

    def set_camera_audio_paths(self, paths: List[str]) -> None:
        """Set paths to extracted WAV audio for each camera."""
        self._camera_audio_paths = list(paths)
        logger.debug("RealEnergyVADBackend: set %d camera audio paths", len(paths))

    def diarize(self, audio_path: str, num_channels: int = 2) -> List[SpeakerSegment]:
        """
        Analyze energy across camera audio files and return speaker segments.

        If camera_audio_paths are set, uses those. Otherwise falls back to stub.
        speaker_id maps directly to camera_id (cam0, cam1, etc.).

        Returns empty list (safe fallback) if audio is missing or processing fails.
        """
        if not self._camera_audio_paths:
            logger.warning("RealEnergyVADBackend: no camera audio paths set, using stub")
            return EnergyVADBackend().diarize(audio_path, num_channels)

        num_cameras = len(self._camera_audio_paths)
        logger.info("DIARIZE: analyzing %d cameras, window=%dms, hold=%dms, consecutive=%d",
                   num_cameras, self.window_ms, self.hold_time_ms, self.consecutive_wins)

        try:
            # Load audio data from each camera
            camera_samples: List[List[float]] = []
            sample_rate = 16000  # Expected from ffmpeg extraction

            for i, wav_path in enumerate(self._camera_audio_paths):
                if self.cancel_callback and self.cancel_callback():
                    logger.info("RealEnergyVADBackend: cancelled during audio loading")
                    return []
                samples, sr = self._load_wav_samples(wav_path)
                if sr != sample_rate and sr > 0:
                    logger.warning("Camera %d sample rate %d != expected %d", i, sr, sample_rate)
                    sample_rate = sr
                camera_samples.append(samples)
                logger.debug("Camera %d: loaded %d samples from %s", i, len(samples), wav_path)

            if not camera_samples or all(len(s) == 0 for s in camera_samples):
                logger.error("DIARIZE: No audio samples loaded from any camera - fallback to cam0")
                return []

            # Find max duration across cameras
            max_samples = max(len(s) for s in camera_samples)
            total_duration_ms = int(max_samples * 1000 / sample_rate)
            logger.info("DIARIZE: total duration=%dms, sample_rate=%d", total_duration_ms, sample_rate)

            # Compute RMS energy per window for each camera
            window_samples = int(self.window_ms * sample_rate / 1000)
            num_windows = max(1, max_samples // window_samples)

            # energy_matrix[camera][window] = RMS energy
            energy_matrix: List[List[float]] = []
            for cam_idx, samples in enumerate(camera_samples):
                cam_energy = []
                for w in range(num_windows):
                    start = w * window_samples
                    end = min(start + window_samples, len(samples))
                    if start >= len(samples):
                        cam_energy.append(0.0)
                    else:
                        rms = self._compute_rms(samples[start:end])
                        cam_energy.append(rms)
                energy_matrix.append(cam_energy)
                if self.cancel_callback and self.cancel_callback():
                    logger.info("RealEnergyVADBackend: cancelled during energy calculation")
                    return []

            # Estimate adaptive noise floor per camera (p20 of energy distribution)
            noise_floors = self._estimate_noise_floors(energy_matrix)
            for cam_idx, nf in enumerate(noise_floors):
                avg_rms = sum(energy_matrix[cam_idx]) / len(energy_matrix[cam_idx]) if energy_matrix[cam_idx] else 0
                logger.info("Camera %d: noise_floor=%.4f, avg_rms=%.4f, gate_thresh=%.4f",
                           cam_idx, nf, avg_rms, nf * self.gate_factor)

            # Compute speech-gated energy: zero out frames below adaptive threshold
            gated_energy = self._apply_speech_gating(energy_matrix, noise_floors)

            # Determine window winners with hysteresis, consecutive wins, and hold time
            window_winners = self._determine_winners_robust(
                gated_energy, num_cameras, num_windows
            )

            # Merge consecutive windows with same winner into segments
            segments = self._merge_windows_to_segments(
                window_winners, self.window_ms, total_duration_ms
            )

            logger.info("DIARIZE: created %d segments from %d windows",
                       len(segments), num_windows)
            return segments

        except Exception as e:
            logger.error("DIARIZE error: %s - returning empty segments", e, exc_info=True)
            return []

    def _estimate_noise_floors(self, energy_matrix: List[List[float]]) -> List[float]:
        """
        Estimate adaptive noise floor per camera using percentile of energy distribution.

        Uses noise_percentile (default p20) to capture ambient noise level,
        ignoring speech peaks. Returns at least silence_threshold to avoid div-by-zero.
        """
        noise_floors: List[float] = []
        for cam_idx, cam_energy in enumerate(energy_matrix):
            if not cam_energy:
                noise_floors.append(self.silence_threshold)
                continue

            # Sort energies and take percentile
            sorted_energy = sorted(cam_energy)
            idx = max(0, min(len(sorted_energy) - 1,
                           int(len(sorted_energy) * self.noise_percentile / 100)))
            noise_floor = sorted_energy[idx]

            # Ensure minimum threshold
            noise_floor = max(noise_floor, self.silence_threshold)
            noise_floors.append(noise_floor)

        return noise_floors

    def _apply_speech_gating(
        self,
        energy_matrix: List[List[float]],
        noise_floors: List[float],
    ) -> List[List[float]]:
        """
        Apply speech gating: set energy to 0 if below noise_floor * gate_factor.

        This filters out low-level noise and only considers frames likely to contain speech.
        """
        gated: List[List[float]] = []
        for cam_idx, cam_energy in enumerate(energy_matrix):
            threshold = noise_floors[cam_idx] * self.gate_factor
            gated_cam = [
                e if e >= threshold else 0.0
                for e in cam_energy
            ]
            gated.append(gated_cam)
        return gated

    def _determine_winners_robust(
        self,
        gated_energy: List[List[float]],
        num_cameras: int,
        num_windows: int,
    ) -> List[int]:
        """
        Determine window winners with robust switching logic.

        Implements:
        - Hysteresis: candidate must beat current by ratio >= hysteresis_ratio
        - Consecutive wins: candidate must win N consecutive windows
        - Hold time: after switch, stay on camera for hold_time_ms
        - When uncertain: stay on current camera (never guess)
        """
        if num_windows == 0:
            return []

        hold_windows = max(1, self.hold_time_ms // self.window_ms)
        window_winners: List[int] = []
        current_camera = 0  # Start on cam0
        windows_since_switch = hold_windows  # Allow immediate switch at start
        consecutive_candidate = -1  # Camera currently building consecutive wins
        consecutive_count = 0  # How many consecutive windows candidate has won

        for w in range(num_windows):
            # Get energy for each camera at this window
            energies = [
                gated_energy[cam][w] if w < len(gated_energy[cam]) else 0.0
                for cam in range(num_cameras)
            ]

            current_energy = energies[current_camera]

            # Find best candidate (highest energy, excluding current)
            best_candidate = -1
            best_energy = 0.0
            for cam_idx, energy in enumerate(energies):
                if cam_idx != current_camera and energy > best_energy:
                    best_energy = energy
                    best_candidate = cam_idx

            # Check if we should consider switching
            should_consider_switch = False

            if best_candidate >= 0 and best_energy > 0:
                # Apply hysteresis: candidate must beat current by margin
                if current_energy > 0:
                    ratio = best_energy / current_energy
                    should_consider_switch = ratio >= self.hysteresis_ratio
                else:
                    # Current is silent, any speech wins
                    should_consider_switch = True

            # Track consecutive wins for the candidate
            if should_consider_switch:
                if best_candidate == consecutive_candidate:
                    consecutive_count += 1
                else:
                    # New candidate, reset counter
                    consecutive_candidate = best_candidate
                    consecutive_count = 1
            else:
                # No clear winner this window, reset
                consecutive_candidate = -1
                consecutive_count = 0

            # Decide if we actually switch
            actual_switch = False
            if (consecutive_count >= self.consecutive_wins and
                windows_since_switch >= hold_windows and
                consecutive_candidate >= 0):
                # Switch to new camera
                current_camera = consecutive_candidate
                actual_switch = True
                windows_since_switch = 0
                consecutive_candidate = -1
                consecutive_count = 0
                logger.debug("DIARIZE: switch to cam%d at window %d (%.1fs)",
                           current_camera, w, w * self.window_ms / 1000)

            window_winners.append(current_camera)
            if not actual_switch:
                windows_since_switch += 1

        return window_winners

    @staticmethod
    def _load_wav_samples(wav_path: str) -> tuple[List[float], int]:
        """Load WAV file and return normalized samples (-1.0 to 1.0) and sample rate."""
        if not Path(wav_path).exists():
            logger.error("WAV file not found: %s", wav_path)
            return [], 0

        try:
            with wave.open(wav_path, 'rb') as wf:
                n_channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                sample_rate = wf.getframerate()
                n_frames = wf.getnframes()

                raw_data = wf.readframes(n_frames)

            # Convert to float samples
            if sample_width == 2:  # 16-bit
                fmt = f"<{n_frames * n_channels}h"
                samples = struct.unpack(fmt, raw_data)
                max_val = 32768.0
            elif sample_width == 1:  # 8-bit
                samples = list(raw_data)
                max_val = 128.0
            else:
                logger.warning("Unsupported sample width: %d", sample_width)
                return [], sample_rate

            # Normalize and convert to mono if stereo
            float_samples: List[float] = []
            for i in range(0, len(samples), n_channels):
                # Average channels for mono
                val = sum(samples[i:i + n_channels]) / n_channels
                float_samples.append(val / max_val)

            return float_samples, sample_rate

        except Exception as e:
            logger.error("Failed to load WAV %s: %s", wav_path, e)
            return [], 0

    @staticmethod
    def _compute_rms(samples: List[float]) -> float:
        """Compute RMS (root mean square) energy of samples."""
        if not samples:
            return 0.0
        sum_sq = sum(s * s for s in samples)
        return (sum_sq / len(samples)) ** 0.5

    def _merge_windows_to_segments(
        self,
        window_winners: List[int],
        window_ms: int,
        total_duration_ms: int,
    ) -> List[SpeakerSegment]:
        """Merge consecutive windows with same speaker into segments."""
        if not window_winners:
            return []

        segments: List[SpeakerSegment] = []
        current_speaker = window_winners[0]
        segment_start_ms = 0

        for i, speaker in enumerate(window_winners[1:], start=1):
            if speaker != current_speaker:
                # Close current segment
                end_ms = i * window_ms
                if end_ms - segment_start_ms >= self.min_segment_ms:
                    segments.append(SpeakerSegment(
                        start_ms=segment_start_ms,
                        end_ms=end_ms,
                        speaker_id=current_speaker,
                    ))
                else:
                    # Too short, merge with previous if exists
                    if segments:
                        # Extend previous segment
                        prev = segments[-1]
                        segments[-1] = SpeakerSegment(
                            start_ms=prev.start_ms,
                            end_ms=end_ms,
                            speaker_id=prev.speaker_id,
                        )
                    else:
                        # First segment too short, still add it
                        segments.append(SpeakerSegment(
                            start_ms=segment_start_ms,
                            end_ms=end_ms,
                            speaker_id=current_speaker,
                        ))
                segment_start_ms = end_ms
                current_speaker = speaker

        # Close final segment
        end_ms = total_duration_ms
        if end_ms > segment_start_ms:
            segments.append(SpeakerSegment(
                start_ms=segment_start_ms,
                end_ms=end_ms,
                speaker_id=current_speaker,
            ))

        return segments


def compute_speaker_camera_mapping(
    segments: List[SpeakerSegment],
    camera_audio_paths: List[str],
    sample_rate: int = 16000,
) -> dict[int, int]:
    """
    Automatically map pyannote speakers to cameras based on audio energy.

    For each speaker in segments, analyzes which camera had the highest
    energy during that speaker's speech. Uses greedy assignment with
    conflict resolution.

    Args:
        segments: Speaker segments from pyannote (speaker_id is arbitrary)
        camera_audio_paths: Paths to extracted WAV audio for each camera
        sample_rate: Expected sample rate of audio files

    Returns:
        Dict mapping speaker_id -> camera_id
    """
    if not segments or not camera_audio_paths:
        logger.warning("compute_speaker_camera_mapping: no segments or audio paths")
        return {}

    num_cameras = len(camera_audio_paths)
    unique_speakers = sorted(set(s.speaker_id for s in segments))
    
    if not unique_speakers:
        return {}

    logger.info("Computing speaker-camera mapping for %d speakers, %d cameras",
               len(unique_speakers), num_cameras)

    # Load audio samples from each camera
    camera_samples: List[List[float]] = []
    actual_sample_rate = sample_rate
    
    for i, wav_path in enumerate(camera_audio_paths):
        if not wav_path:
            camera_samples.append([])
            continue
        samples, sr = RealEnergyVADBackend._load_wav_samples(wav_path)
        if sr > 0:
            actual_sample_rate = sr
        camera_samples.append(samples)
        logger.debug("Loaded %d samples from camera %d", len(samples), i)

    if all(len(s) == 0 for s in camera_samples):
        logger.error("No audio loaded from any camera")
        return {spk: spk % num_cameras for spk in unique_speakers}

    # Compute energy matrix: energy_matrix[speaker_id][camera_id] = total energy
    energy_matrix: dict[int, List[float]] = {spk: [0.0] * num_cameras for spk in unique_speakers}

    for seg in segments:
        speaker_id = seg.speaker_id
        start_sample = int(seg.start_ms * actual_sample_rate / 1000)
        end_sample = int(seg.end_ms * actual_sample_rate / 1000)

        for cam_idx, samples in enumerate(camera_samples):
            if not samples:
                continue
            # Clamp to valid range
            start_idx = max(0, min(start_sample, len(samples) - 1))
            end_idx = max(start_idx + 1, min(end_sample, len(samples)))
            
            segment_samples = samples[start_idx:end_idx]
            if segment_samples:
                rms = RealEnergyVADBackend._compute_rms(segment_samples)
                duration_ms = seg.end_ms - seg.start_ms
                # Weight by duration to handle varying segment lengths
                energy_matrix[speaker_id][cam_idx] += rms * duration_ms

    # Log energy matrix for debugging
    for spk in unique_speakers:
        energies = [f"cam{i}={e:.4f}" for i, e in enumerate(energy_matrix[spk])]
        logger.debug("Speaker %d energy: %s", spk, ", ".join(energies))

    # Greedy assignment: sort speakers by max energy (most confident first)
    speaker_max_energy = [
        (spk, max(energy_matrix[spk]), energy_matrix[spk].index(max(energy_matrix[spk])))
        for spk in unique_speakers
    ]
    # Sort by max energy descending
    speaker_max_energy.sort(key=lambda x: x[1], reverse=True)

    speaker_to_camera: dict[int, int] = {}
    assigned_cameras: set[int] = set()

    for spk, max_e, preferred_cam in speaker_max_energy:
        if preferred_cam not in assigned_cameras:
            # Assign to preferred camera
            speaker_to_camera[spk] = preferred_cam
            assigned_cameras.add(preferred_cam)
        else:
            # Preferred camera taken, find next best available
            cam_energies = list(enumerate(energy_matrix[spk]))
            cam_energies.sort(key=lambda x: x[1], reverse=True)
            
            assigned = False
            for cam_idx, _ in cam_energies:
                if cam_idx not in assigned_cameras:
                    speaker_to_camera[spk] = cam_idx
                    assigned_cameras.add(cam_idx)
                    assigned = True
                    break
            
            if not assigned:
                # All cameras taken, assign to preferred anyway
                speaker_to_camera[spk] = preferred_cam
                logger.warning("Speaker %d conflict: all cameras taken, using cam %d",
                              spk, preferred_cam)

    logger.info("Speaker-camera mapping result: %s", speaker_to_camera)
    return speaker_to_camera


def assign_cameras_by_energy(
    segments: List[SpeakerSegment],
    camera_audio_paths: List[str],
    sample_rate: int = 16000,
) -> List[SpeakerSegment]:
    """
    Hybrid approach: Use pyannote segment timing, pick camera by NORMALIZED energy.

    For each speech segment from pyannote, determines which camera has
    the highest RELATIVE energy spike (compared to its own baseline).
    This allows cameras with different mic levels to all be used fairly.

    Args:
        segments: Speech segments from pyannote (timing is used, speaker_id ignored)
        camera_audio_paths: Paths to extracted WAV audio for each camera
        sample_rate: Expected sample rate of audio files

    Returns:
        New list of SpeakerSegment with speaker_id set to the loudest camera
    """
    if not segments or not camera_audio_paths:
        logger.warning("assign_cameras_by_energy: no segments or audio paths")
        return segments

    num_cameras = len(camera_audio_paths)
    logger.info("Hybrid mode: assigning %d segments to %d cameras by normalized energy",
               len(segments), num_cameras)

    # Load audio samples from each camera
    camera_samples: List[List[float]] = []
    actual_sample_rate = sample_rate
    
    for i, wav_path in enumerate(camera_audio_paths):
        if not wav_path:
            camera_samples.append([])
            continue
        samples, sr = RealEnergyVADBackend._load_wav_samples(wav_path)
        if sr > 0:
            actual_sample_rate = sr
        camera_samples.append(samples)
        logger.debug("Loaded %d samples from camera %d", len(samples), i)

    if all(len(s) == 0 for s in camera_samples):
        logger.error("No audio loaded from any camera - returning original segments")
        return segments

    # Compute baseline (average) RMS energy per camera across all speech segments
    camera_baselines: List[float] = []
    for cam_idx, samples in enumerate(camera_samples):
        if not samples:
            camera_baselines.append(0.001)  # Avoid div by zero
            continue
        
        total_energy = 0.0
        total_samples = 0
        for seg in segments:
            start_sample = int(seg.start_ms * actual_sample_rate / 1000)
            end_sample = int(seg.end_ms * actual_sample_rate / 1000)
            start_idx = max(0, min(start_sample, len(samples) - 1))
            end_idx = max(start_idx + 1, min(end_sample, len(samples)))
            segment_samples = samples[start_idx:end_idx]
            if segment_samples:
                total_energy += sum(s * s for s in segment_samples)
                total_samples += len(segment_samples)
        
        if total_samples > 0:
            baseline = (total_energy / total_samples) ** 0.5
            camera_baselines.append(max(baseline, 0.001))  # Avoid div by zero
        else:
            camera_baselines.append(0.001)
    
    # Log baselines
    for cam_idx, baseline in enumerate(camera_baselines):
        logger.info("Camera %d baseline RMS: %.6f", cam_idx, baseline)

    # For each segment, find the camera with highest NORMALIZED energy
    result_segments: List[SpeakerSegment] = []
    camera_usage_count = [0] * num_cameras

    for seg in segments:
        start_sample = int(seg.start_ms * actual_sample_rate / 1000)
        end_sample = int(seg.end_ms * actual_sample_rate / 1000)

        # Compute normalized energy for each camera during this segment
        cam_normalized_energies = []
        for cam_idx, samples in enumerate(camera_samples):
            if not samples:
                cam_normalized_energies.append(0.0)
                continue
            # Clamp to valid range
            start_idx = max(0, min(start_sample, len(samples) - 1))
            end_idx = max(start_idx + 1, min(end_sample, len(samples)))
            
            segment_samples = samples[start_idx:end_idx]
            if segment_samples:
                rms = RealEnergyVADBackend._compute_rms(segment_samples)
                # Normalize: how much above baseline is this segment?
                normalized = rms / camera_baselines[cam_idx]
                cam_normalized_energies.append(normalized)
            else:
                cam_normalized_energies.append(0.0)

        # Pick camera with highest normalized energy
        if sum(cam_normalized_energies) > 0:
            best_cam = cam_normalized_energies.index(max(cam_normalized_energies))
        else:
            best_cam = 0  # Fallback to camera 0

        result_segments.append(SpeakerSegment(
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            speaker_id=best_cam,  # speaker_id now represents camera_id
        ))
        camera_usage_count[best_cam] += 1

    # Log camera usage statistics
    for cam_idx, count in enumerate(camera_usage_count):
        logger.info("Camera %d: %d segments (%.1f%%)",
                   cam_idx, count, 100 * count / len(result_segments) if result_segments else 0)

    logger.info("Hybrid assignment complete: %d segments across %d cameras",
               len(result_segments), sum(1 for c in camera_usage_count if c > 0))
    return result_segments


def assign_cameras_hybrid(
    segments: List[SpeakerSegment],
    camera_audio_paths: List[str],
    speaker_to_cameras: Dict[int, List[int]],
    sample_rate: int = 16000,
) -> List[SpeakerSegment]:
    """
    Hybrid approach: Use pyannote speaker IDs + user's camera groups + energy within groups.

    For each speech segment:
    1. Look up which cameras are assigned to this speaker (from user mapping)
    2. Use energy detection to pick the best camera within that group
    3. If speaker has only one camera, use that camera
    4. If speaker has no mapping, fall back to energy across all cameras

    Args:
        segments: Speech segments from pyannote with speaker_id
        camera_audio_paths: Paths to extracted WAV audio for each camera
        speaker_to_cameras: User's mapping {speaker_id: [camera_ids]}
        sample_rate: Expected sample rate of audio files

    Returns:
        New list of SpeakerSegment with speaker_id set to the chosen camera_id
    """
    if not segments or not camera_audio_paths:
        logger.warning("assign_cameras_hybrid: no segments or audio paths")
        return segments

    num_cameras = len(camera_audio_paths)
    logger.info("Hybrid mode with groups: %d segments, %d cameras, %d speaker groups",
               len(segments), num_cameras, len(speaker_to_cameras))

    # Log the speaker groups
    for speaker_id, cameras in speaker_to_cameras.items():
        logger.info("Speaker %d -> Cameras %s", speaker_id + 1, cameras)

    # Load audio samples from each camera
    camera_samples: List[List[float]] = []
    actual_sample_rate = sample_rate
    
    for i, wav_path in enumerate(camera_audio_paths):
        if not wav_path:
            camera_samples.append([])
            continue
        samples, sr = RealEnergyVADBackend._load_wav_samples(wav_path)
        if sr > 0:
            actual_sample_rate = sr
        camera_samples.append(samples)
        logger.debug("Loaded %d samples from camera %d", len(samples), i)

    if all(len(s) == 0 for s in camera_samples):
        logger.error("No audio loaded from any camera - returning original segments")
        return segments

    # For each segment, find the best camera within the speaker's camera group
    result_segments: List[SpeakerSegment] = []
    camera_usage_count = [0] * num_cameras

    for seg in segments:
        speaker_id = seg.speaker_id
        camera_group = speaker_to_cameras.get(speaker_id, [])
        
        # If no cameras assigned to this speaker, use ALL cameras (full energy detection)
        if not camera_group:
            camera_group = list(range(num_cameras))
            logger.debug("Speaker %d has no mapping, using all cameras", speaker_id)
        
        # If only one camera in group, use it directly
        if len(camera_group) == 1:
            best_cam = camera_group[0]
        else:
            # Multiple cameras - use energy to pick best one
            start_sample = int(seg.start_ms * actual_sample_rate / 1000)
            end_sample = int(seg.end_ms * actual_sample_rate / 1000)

            best_cam = camera_group[0]  # Default
            best_energy = 0.0

            for cam_idx in camera_group:
                if cam_idx >= len(camera_samples) or not camera_samples[cam_idx]:
                    continue
                samples = camera_samples[cam_idx]
                start_idx = max(0, min(start_sample, len(samples) - 1))
                end_idx = max(start_idx + 1, min(end_sample, len(samples)))
                
                segment_samples = samples[start_idx:end_idx]
                if segment_samples:
                    rms = RealEnergyVADBackend._compute_rms(segment_samples)
                    if rms > best_energy:
                        best_energy = rms
                        best_cam = cam_idx

        result_segments.append(SpeakerSegment(
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            speaker_id=best_cam,  # speaker_id now represents camera_id
        ))
        camera_usage_count[best_cam] += 1

    # Log camera usage statistics
    for cam_idx, count in enumerate(camera_usage_count):
        logger.info("Camera %d: %d segments (%.1f%%)",
                   cam_idx, count, 100 * count / len(result_segments) if result_segments else 0)

    logger.info("Hybrid with groups: %d segments across %d cameras",
               len(result_segments), sum(1 for c in camera_usage_count if c > 0))
    return result_segments


class PyannoteBackend:
    """
    Real diarization backend using pyannote.audio.

    Models are downloaded on first use to ~/.cache/torch/pyannote/.
    Requires HuggingFace token for some models (see pyannote docs).
    """

    # Embedded token for packaged app (fallback when user hasn't logged in)
    # Replace with your own token from https://huggingface.co/settings/tokens
    _EMBEDDED_TOKEN: Optional[str] = None  # Set your token here: "hf_xxxxxxxxxxxx"

    _pipeline: Optional["Pipeline"] = None  # type: ignore[name-defined]
    _load_error: Optional[str] = None

    def __init__(self, use_auth_token: Optional[str] = None) -> None:
        self.use_auth_token = use_auth_token
        self._ensure_loaded()

    @classmethod
    def _ensure_loaded(cls) -> None:
        """Lazy-load the pyannote pipeline (singleton)."""
        if cls._pipeline is not None or cls._load_error is not None:
            return

        try:
            logger.info("Loading pyannote.audio diarization pipeline...")
            start = time.time()

            from pyannote.audio import Pipeline
            
            # Get token: try cached login, env var, or embedded fallback
            token = None
            try:
                from huggingface_hub import get_token
                token = get_token()
                if token:
                    logger.debug("Using HuggingFace token from cached login")
            except Exception as e:
                logger.debug("Could not get HF token from login: %s", e)
            
            # Fallback to environment variable
            if not token:
                import os
                token = os.environ.get("HF_TOKEN")
                if token:
                    logger.debug("Using HuggingFace token from HF_TOKEN env var")
            
            # Fallback to embedded token (for packaged exe)
            if not token and cls._EMBEDDED_TOKEN:
                token = cls._EMBEDDED_TOKEN
                logger.debug("Using embedded HuggingFace token")

            # Use pretrained pipeline - models auto-download on first run
            # pyannote 3.x uses HuggingFace Hub token from environment or login
            # Try different model versions with different auth approaches
            model_ids = [
                "pyannote/speaker-diarization-3.1",
                "pyannote/speaker-diarization@2.1",
            ]

            for model_id in model_ids:
                try:
                    # Pass token explicitly if available (newer API uses 'token', not 'use_auth_token')
                    if token:
                        cls._pipeline = Pipeline.from_pretrained(model_id, token=token)
                    else:
                        cls._pipeline = Pipeline.from_pretrained(model_id)
                    logger.info("Loaded model: %s", model_id)
                    break
                except Exception as e:
                    logger.debug("Model %s failed: %s", model_id, e)
                    continue

            if cls._pipeline is None:
                raise RuntimeError(
                    "Could not load any pyannote model. "
                    "Please run 'huggingface-cli login' or set HF_TOKEN environment variable."
                )

            elapsed = time.time() - start
            logger.info("Pyannote pipeline loaded in %.2fs", elapsed)

        except ImportError as e:
            cls._load_error = f"pyannote.audio not installed: {e}"
            logger.error(cls._load_error)
        except Exception as e:
            cls._load_error = f"Failed to load pyannote model: {e}"
            logger.error(cls._load_error, exc_info=True)

    @classmethod
    def check_install(cls) -> Tuple[bool, Optional[str]]:
        """
        Fast check if pyannote is installed and configured.
        
        Returns:
            (available, error_message)
            Does NOT load the model (which is slow).
        """
        try:
            import pyannote.audio
            import torch
        except ImportError as e:
            return False, f"Import error: {e}"
            
        # Check for token
        try:
            from huggingface_hub import get_token
            token = get_token()
            if not token:
                import os
                if not os.environ.get("HF_TOKEN"):
                    return False, "Missing HuggingFace token (run huggingface-cli login)"
        except ImportError:
             # If huggingface_hub missing, we can't authenticate easily
             pass
        except Exception:
            pass
            
        return True, None

    @classmethod
    def is_available(cls) -> bool:
        """Check if pyannote backend is usable."""
        if cls._pipeline is not None:
            return True
        # Use fast check to avoid blocking UI
        available, _ = cls.check_install()
        return available

    @classmethod
    def get_error(cls) -> Optional[str]:
        """Get error message if backend failed to load."""
        if cls._load_error:
            return cls._load_error
        available, error = cls.check_install()
        return error

    def diarize(self, audio_path: str, num_channels: int = 2) -> List[SpeakerSegment]:
        """
        Run pyannote diarization on audio file.

        Returns non-overlapping segments sorted by start_ms.
        """
        if not Path(audio_path).exists():
            logger.error("Audio file not found: %s", audio_path)
            return []

        if self._pipeline is None:
            logger.error("Pyannote pipeline not loaded: %s", self._load_error)
            return []

        logger.info("Starting diarization: %s", audio_path)
        start = time.time()

        try:
            # Pre-load audio with torchaudio since torchcodec doesn't work on Windows
            # pyannote accepts {"waveform": tensor, "sample_rate": int} format
            import torchaudio
            waveform, sample_rate = torchaudio.load(audio_path)
            
            # Run diarization with pre-loaded audio
            audio_input = {"waveform": waveform, "sample_rate": sample_rate}
            diarization = self._pipeline(audio_input)

            # Convert pyannote output to SpeakerSegments
            segments: List[SpeakerSegment] = []
            speaker_map: dict[str, int] = {}
            total_speech_ms = 0

            # Handle different pyannote return types (Annotation vs DiarizeOutput)
            # Access the annotation object if wrapped in DiarizeOutput
            annotation = diarization
            if hasattr(diarization, 'speaker_diarization'):
                # DiarizeOutput from newer pyannote API
                annotation = diarization.speaker_diarization
                logger.debug("Using speaker_diarization attribute from DiarizeOutput")
            elif hasattr(diarization, 'annotation'):
                annotation = diarization.annotation
            elif hasattr(diarization, 'get_timeline'):
                # Already an Annotation object
                pass
            
            # Now iterate over tracks
            if hasattr(annotation, 'itertracks'):
                for turn, _, speaker in annotation.itertracks(yield_label=True):
                    # Map speaker labels to integer IDs
                    if speaker not in speaker_map:
                        speaker_map[speaker] = len(speaker_map)
                    speaker_id = speaker_map[speaker]

                    start_ms = int(turn.start * 1000)
                    end_ms = int(turn.end * 1000)

                    # Skip invalid/tiny segments
                    if end_ms <= start_ms:
                        continue

                    segments.append(SpeakerSegment(
                        start_ms=start_ms,
                        end_ms=end_ms,
                        speaker_id=speaker_id,
                    ))
                    total_speech_ms += (end_ms - start_ms)
            else:
                # Log available attributes for debugging
                logger.error("Diarization output has no itertracks. Type: %s, attrs: %s", 
                           type(diarization).__name__, 
                           [a for a in dir(diarization) if not a.startswith('_')][:20])

            # Sort by start time (should already be sorted, but ensure)
            segments.sort(key=lambda s: s.start_ms)

            # Merge overlapping segments (pyannote can produce overlaps)
            segments = self._merge_overlaps(segments)

            elapsed = time.time() - start
            logger.info(
                "Diarization complete: %.2fs, %d speakers, %d segments, %.1fs total speech",
                elapsed,
                len(speaker_map),
                len(segments),
                total_speech_ms / 1000,
            )

            return segments

        except Exception as e:
            logger.error("Diarization failed: %s", e, exc_info=True)
            return []

    @staticmethod
    def _merge_overlaps(segments: List[SpeakerSegment]) -> List[SpeakerSegment]:
        """Merge overlapping segments, keeping the longer/earlier one."""
        if not segments:
            return []

        merged: List[SpeakerSegment] = [segments[0]]
        for seg in segments[1:]:
            prev = merged[-1]
            if seg.start_ms < prev.end_ms:
                # Overlap: extend previous if same speaker, else truncate current
                if seg.speaker_id == prev.speaker_id:
                    merged[-1] = SpeakerSegment(
                        prev.start_ms, max(prev.end_ms, seg.end_ms), prev.speaker_id
                    )
                else:
                    # Start current segment after previous ends
                    if seg.end_ms > prev.end_ms:
                        merged.append(SpeakerSegment(
                            prev.end_ms, seg.end_ms, seg.speaker_id
                        ))
            else:
                merged.append(seg)
        return merged


def create_backend(
    mode: DiarizationMode,
    fallback_on_error: bool = True,
) -> tuple[DiarizationBackend, Optional[str]]:
    """
    Factory to create diarization backend based on mode.

    Args:
        mode: Which backend to use
        fallback_on_error: If True and REAL backend fails, fall back to ENERGY

    Returns:
        (backend, error_message) - error_message is None if OK
    """
    if mode == DiarizationMode.OFF:
        return NullBackend(), None

    if mode == DiarizationMode.STUB:
        return EnergyVADBackend(), None

    if mode == DiarizationMode.ENERGY:
        return RealEnergyVADBackend(), None

    if mode == DiarizationMode.REAL:
        if PyannoteBackend.is_available():
            return PyannoteBackend(), None
        else:
            error = PyannoteBackend.get_error() or "Unknown error loading pyannote"
            if fallback_on_error:
                logger.warning("Falling back to ENERGY backend: %s", error)
                return RealEnergyVADBackend(), error
            else:
                return NullBackend(), error

    # Unknown mode, default to ENERGY
    return RealEnergyVADBackend(), f"Unknown mode: {mode}"


class ActiveSpeakerDetector:
    """Main detector with pluggable backend."""

    def __init__(self, backend: DiarizationBackend | None = None) -> None:
        self._backend = backend or EnergyVADBackend()

    @property
    def backend(self) -> DiarizationBackend:
        return self._backend

    @backend.setter
    def backend(self, value: DiarizationBackend) -> None:
        self._backend = value

    def detect(self, audio_path: str, num_channels: int = 2) -> List[SpeakerSegment]:
        """
        Run diarization and validate output.

        Returns sorted, non-overlapping segments.
        """
        segments = self._backend.diarize(audio_path, num_channels)
        self._validate_segments(segments)
        return segments

    @staticmethod
    def _validate_segments(segments: List[SpeakerSegment]) -> None:
        """Ensure segments are sorted and non-overlapping."""
        for i, seg in enumerate(segments):
            if i > 0:
                prev = segments[i - 1]
                if seg.start_ms < prev.start_ms:
                    raise ValueError(f"Segments not sorted at index {i}")
                if seg.start_ms < prev.end_ms:
                    raise ValueError(f"Overlapping segments at index {i}")


class LipMovementBackend:
    """
    Visual-based speaker detection using lip movement analysis.
    
    Uses MediaPipe Face Mesh to detect face landmarks and track mouth/lip
    movement to determine who is actively speaking.
    """
    
    # MediaPipe Face Mesh mouth landmarks for lip aperture calculation
    # Upper lip: 13 (center top), 14 (center top inner)
    # Lower lip: 14 (center bottom inner), 17 (center bottom)
    # Lip corners: 78 (left), 308 (right)
    UPPER_LIP_TOP = 13
    UPPER_LIP_BOTTOM = 14
    LOWER_LIP_TOP = 14
    LOWER_LIP_BOTTOM = 17  
    LEFT_CORNER = 78
    RIGHT_CORNER = 308
    
    def __init__(
        self,
        sample_interval_ms: int = 100,
        min_segment_ms: int = 500,
        movement_threshold: float = 0.02,
    ):
        """
        Initialize lip movement detector.
        
        Args:
            sample_interval_ms: Check frames every N milliseconds (default 100ms = 10 fps)
            min_segment_ms: Minimum segment duration to avoid flicker (default 500ms)
            movement_threshold: Minimum lip aperture ratio to count as speaking
        """
        self.sample_interval_ms = sample_interval_ms
        self.min_segment_ms = min_segment_ms
        self.movement_threshold = movement_threshold
        self._face_cascade = None
        self._mouth_cascade = None
        self._initialized = False
    
    def _ensure_detector(self):
        """Lazy-load face and mouth detectors using OpenCV Haar cascades."""
        if self._initialized:
            return
        
        try:
            import cv2
            
            # Try to load Haar cascades for face and mouth detection
            # These come bundled with OpenCV
            face_cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            mouth_cascade_path = cv2.data.haarcascades + 'haarcascade_smile.xml'
            
            self._face_cascade = cv2.CascadeClassifier(face_cascade_path)
            self._mouth_cascade = cv2.CascadeClassifier(mouth_cascade_path)
            
            if self._face_cascade.empty():
                logger.warning("Could not load face cascade, using motion detection fallback")
                self._face_cascade = None
            
            self._initialized = True
            logger.info("OpenCV face/mouth detection initialized")
            
        except Exception as e:
            logger.warning("OpenCV detection init failed: %s, using motion fallback", e)
            self._initialized = True
    
    def _analyze_mouth_region(self, frame, prev_frame) -> float:
        """
        Analyze mouth region activity in a frame.
        
        Uses face detection to locate mouth area, then measures
        pixel change in that region between frames.
        
        Returns activity score 0.0-1.0 (higher = more movement).
        """
        import cv2
        
        if frame is None:
            return 0.0
        
        # Convert to grayscale for detection
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        
        # If we have a previous frame, calculate motion in the frame
        if prev_frame is not None:
            prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_RGB2GRAY)
            
            # Calculate frame difference
            diff = cv2.absdiff(gray, prev_gray)
            
            # Try to detect face and focus on lower third (mouth region)
            if self._face_cascade is not None and not self._face_cascade.empty():
                faces = self._face_cascade.detectMultiScale(gray, 1.1, 4)
                
                if len(faces) > 0:
                    # Focus on the largest face
                    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                    
                    # Mouth region is lower third of face
                    mouth_y = y + int(h * 0.6)
                    mouth_h = int(h * 0.4)
                    
                    # Get motion in mouth region
                    mouth_diff = diff[mouth_y:mouth_y+mouth_h, x:x+w]
                    if mouth_diff.size > 0:
                        motion = mouth_diff.mean() / 255.0
                        return motion * 5.0  # Scale up for sensitivity
            
            # Fallback: use overall frame motion (less accurate)
            # Focus on center-lower region where face likely is
            h, w = diff.shape
            center_region = diff[h//3:, w//4:3*w//4]
            if center_region.size > 0:
                return center_region.mean() / 255.0 * 3.0
        
        return 0.0
    
    def _calculate_lip_aperture(self, landmarks) -> float:

        """
        Calculate lip aperture ratio (how open is the mouth).
        
        Returns ratio of vertical opening to horizontal width.
        Higher ratio = mouth more open = likely speaking.
        """
        if landmarks is None:
            return 0.0
        
        try:
            # Get lip landmarks
            upper_lip = landmarks.landmark[self.UPPER_LIP_TOP]
            lower_lip = landmarks.landmark[self.LOWER_LIP_BOTTOM]
            left_corner = landmarks.landmark[self.LEFT_CORNER]
            right_corner = landmarks.landmark[self.RIGHT_CORNER]
            
            # Calculate vertical and horizontal distances
            vertical = abs(lower_lip.y - upper_lip.y)
            horizontal = abs(right_corner.x - left_corner.x)
            
            if horizontal < 0.001:  # Avoid division by zero
                return 0.0
            
            # Return ratio - higher means mouth more open
            return vertical / horizontal
        except (IndexError, AttributeError):
            return 0.0
    
    def _get_frame_at_ms(self, video_path: str, time_ms: int):
        """Extract a single frame from video at specified time."""
        import cv2
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.warning("Cannot open video: %s", video_path)
            return None
        
        # Seek to time
        cap.set(cv2.CAP_PROP_POS_MSEC, time_ms)
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return None
        
        # Convert BGR to RGB for MediaPipe
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    def detect_speakers(
        self,
        video_paths: List[str],
        duration_ms: int,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> List[SpeakerSegment]:
        """
        Analyze videos to detect active speaker at each time window.
        
        Uses OpenCV face detection and motion analysis to detect
        which camera has the most mouth/face movement.
        
        Args:
            video_paths: List of camera video file paths
            duration_ms: Total duration in milliseconds
            
        Returns:
            List of SpeakerSegment with speaker_id = camera_id of active speaker
        """
        self._ensure_detector()
        
        num_cameras = len(video_paths)
        if num_cameras == 0:
            logger.warning("No video paths provided")
            return []
        
        logger.info("Lip detection: analyzing %d cameras, %dms duration, sampling every %dms",
                   num_cameras, duration_ms, self.sample_interval_ms)
        
        # Sample frames at regular intervals
        time_points = list(range(0, duration_ms, self.sample_interval_ms))
        
        # Track previous frames for each camera (for motion detection)
        prev_frames: List = [None] * num_cameras
        
        # For each time point, determine which camera has the most movement
        raw_decisions: List[tuple[int, int, int]] = []  # (start_ms, end_ms, camera_id)
        
        for i, time_ms in enumerate(time_points):
            if i % 50 == 0:  # Log progress every 5 seconds
                logger.debug("Lip detection progress: %d/%d time points", i, len(time_points))
                if progress_callback:
                    # Report progress 0-100%
                    percent = int(i * 100 / len(time_points))
                    progress_callback(percent)
            
            # Check motion for each camera
            motions = []
            for cam_idx, video_path in enumerate(video_paths):
                frame = self._get_frame_at_ms(video_path, time_ms)
                
                # Calculate motion score compared to previous frame
                motion = self._analyze_mouth_region(frame, prev_frames[cam_idx])
                motions.append(motion)
                
                # Store this frame for next comparison
                prev_frames[cam_idx] = frame
            
            # Pick camera with highest motion (if above threshold)
            max_motion = max(motions) if motions else 0.0
            if max_motion >= self.movement_threshold:
                best_cam = motions.index(max_motion)
            else:
                # No one speaking, use previous or default to camera 0
                best_cam = raw_decisions[-1][2] if raw_decisions else 0
            
            # Create segment for this time window
            end_ms = min(time_ms + self.sample_interval_ms, duration_ms)
            raw_decisions.append((time_ms, end_ms, best_cam))
        
        # Merge adjacent segments with same camera
        if not raw_decisions:
            return [SpeakerSegment(0, duration_ms, 0)]
        
        merged_segments: List[SpeakerSegment] = []
        current_start = raw_decisions[0][0]
        current_cam = raw_decisions[0][2]
        
        for start_ms, end_ms, cam_id in raw_decisions[1:]:
            if cam_id == current_cam:
                # Extend current segment
                continue
            else:
                # Different camera - close current segment
                merged_segments.append(SpeakerSegment(
                    start_ms=current_start,
                    end_ms=start_ms,
                    speaker_id=current_cam,
                ))
                current_start = start_ms
                current_cam = cam_id
        
        # Add final segment
        merged_segments.append(SpeakerSegment(
            start_ms=current_start,
            end_ms=raw_decisions[-1][1],
            speaker_id=current_cam,
        ))
        
        # Apply minimum segment duration (merge short segments)
        final_segments = self._apply_min_duration(merged_segments)
        
        # Log statistics
        camera_counts = [0] * num_cameras
        for seg in final_segments:
            camera_counts[seg.speaker_id] += 1
        
        for cam_idx, count in enumerate(camera_counts):
            pct = 100 * count / len(final_segments) if final_segments else 0
            logger.info("Camera %d: %d segments (%.1f%%)", cam_idx, count, pct)
        
        logger.info("Lip detection complete: %d segments from %d time points",
                   len(final_segments), len(time_points))
        
        return final_segments
    
    def _apply_min_duration(
        self,
        segments: List[SpeakerSegment],
    ) -> List[SpeakerSegment]:
        """Merge segments shorter than min_segment_ms with neighbors."""
        if not segments or len(segments) <= 1:
            return segments
        
        result = [segments[0]]
        
        for seg in segments[1:]:
            prev = result[-1]
            duration = seg.end_ms - seg.start_ms
            
            if duration < self.min_segment_ms:
                # Extend previous segment instead
                result[-1] = SpeakerSegment(
                    start_ms=prev.start_ms,
                    end_ms=seg.end_ms,
                    speaker_id=prev.speaker_id,
                )
            else:
                # Long enough, keep as separate segment
                result.append(seg)
        
        return result


class HybridBackend:
    """
    Hybrid speaker detection combining Audio VAD with visual lip movement.
    
    Uses Pyannote/audio analysis to detect WHEN speech occurs, then uses
    LipMovementBackend to determine WHO is speaking during those periods.
    
    This is faster than pure LIPS mode (only analyzes speech regions)
    and more accurate than audio-only (uses visual confirmation).
    """
    
    def __init__(
        self,
        sample_interval_ms: int = 200,  # Faster sampling than pure LIPS
        min_segment_ms: int = 500,
        speech_threshold: float = 0.02,  # RMS threshold for speech detection
    ):
        self.sample_interval_ms = sample_interval_ms
        self.min_segment_ms = min_segment_ms
        self.speech_threshold = speech_threshold
        self._lip_backend: Optional[LipMovementBackend] = None
    
    def _ensure_backends(self):
        """Initialize sub-backends lazily."""
        if self._lip_backend is None:
            self._lip_backend = LipMovementBackend(
                sample_interval_ms=self.sample_interval_ms,
                min_segment_ms=self.min_segment_ms,
            )
    
    def _detect_speech_regions(
        self,
        audio_path: str,
        duration_ms: int,
    ) -> List[tuple[int, int]]:
        """
        Detect regions of speech in audio using RMS energy.
        
        Returns list of (start_ms, end_ms) tuples where speech occurs.
        Uses numpy for memory-efficient processing.
        """
        import wave
        import numpy as np
        
        try:
            with wave.open(audio_path, 'rb') as wf:
                sample_rate = wf.getframerate()
                n_frames = wf.getnframes()
                n_channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                
                # Check for empty file
                if n_frames == 0:
                    logger.warning("Audio file empty: %s", audio_path)
                    return [(0, duration_ms)]

                # Read all audio data
                raw_data = wf.readframes(n_frames)
        except Exception as e:
            logger.warning("Could not read audio for VAD: %s, using full duration", e)
            return [(0, duration_ms)]
        
        # Use numpy for efficient memory handling
        try:
            if sample_width == 2:
                # 16-bit audio (standard)
                samples = np.frombuffer(raw_data, dtype=np.int16)
            elif sample_width == 4:
                # 32-bit float or int
                samples = np.frombuffer(raw_data, dtype=np.int32) 
            else:
                logger.warning("Unsupported sample width %d, using full duration", sample_width)
                return [(0, duration_ms)]
                
            # Convert to float32 (smaller than default float64) and normalize
            samples = samples.astype(np.float32) / 32768.0
            
            # If stereo, use first channel only
            if n_channels > 1:
                samples = samples[::n_channels]
                
            # Calculate window size in samples
            window_samples = int(sample_rate * self.sample_interval_ms / 1000)
            if window_samples <= 0:
                 window_samples = 1000 # Fallback
            
            # Truncate to full windows for reshaped calculation (fastest)
            num_windows = len(samples) // window_samples
            if num_windows == 0:
                 return [(0, duration_ms)]
                 
            truncated_len = num_windows * window_samples
            
            # Reshape to (num_windows, window_samples) to calculate RMS for all windows at once
            windows = samples[:truncated_len].reshape(num_windows, window_samples)
            
            # RMS = sqrt(mean(square(samples)))
            means_sq = np.mean(windows**2, axis=1)
            rms_values = np.sqrt(means_sq)
            
            # Identify speech windows
            is_speech = rms_values >= self.speech_threshold
            
            # Convert boolean array to start/end times
            speech_regions: List[tuple[int, int]] = []
            in_speech = False
            speech_start = 0
            
            for i, speech_detected in enumerate(is_speech):
                time_ms = int(i * self.sample_interval_ms)
                
                if speech_detected:
                    if not in_speech:
                        speech_start = time_ms
                        in_speech = True
                else:
                    if in_speech:
                        speech_regions.append((speech_start, time_ms))
                        in_speech = False
            
            # Close final region
            if in_speech:
                speech_regions.append((speech_start, duration_ms))
                
            # Merge close regions (within 500ms)
            merged: List[tuple[int, int]] = []
            for start, end in speech_regions:
                if merged and start - merged[-1][1] < 500:
                    # Extend previous region
                    merged[-1] = (merged[-1][0], end)
                else:
                    merged.append((start, end))
                    
            logger.info("HYBRID: Found %d speech regions covering %.1f%% of audio",
                       len(merged),
                       100 * sum(e - s for s, e in merged) / duration_ms if duration_ms > 0 else 0)
            
            return merged if merged else [(0, duration_ms)]

        except Exception as e:
            logger.error("VAD processing failed: %s, using full duration", e, exc_info=True)
            return [(0, duration_ms)]
    
    def detect_speakers(
        self,
        video_paths: List[str],
        audio_path: str,
        duration_ms: int,
        cancel_callback: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> List[SpeakerSegment]:
        """
        Detect speakers using hybrid audio+visual approach.
        
        Args:
            video_paths: List of camera video file paths
            audio_path: Path to audio file for VAD (from any camera)
            duration_ms: Total duration in milliseconds
            cancel_callback: Optional function returning True if cancelled
            
        Returns:
            List of SpeakerSegment with speaker_id = camera_id
        """
        self._ensure_backends()
        
        num_cameras = len(video_paths)
        if num_cameras == 0:
            logger.warning("No video paths provided")
            return []
        
        logger.info("HYBRID mode: %d cameras, %dms duration", num_cameras, duration_ms)
        
        # Step 1: Detect speech regions using audio VAD
        speech_regions = self._detect_speech_regions(audio_path, duration_ms)
        
        # Step 2: For each speech region, use LIPS to determine speaker
        all_segments: List[SpeakerSegment] = []
        
        for i, (region_start, region_end) in enumerate(speech_regions):
            # Update progress
            if progress_callback and i % 5 == 0:
                percent = int(i * 100 / len(speech_regions))
                progress_callback(percent)

            # Check for cancellation
            if cancel_callback and cancel_callback():
                logger.info("HYBRID: Cancelled during detection")
                return []
            
            # Get LIPS decision for this region
            region_duration = region_end - region_start
            
            if region_duration < self.min_segment_ms:
                # Too short, skip
                continue
            
            # Sample middle of region for LIPS analysis
            # (analyze fewer frames for speed)
            mid_point = (region_start + region_end) // 2
            
            # Get frames from each camera at this time
            import cv2
            motions = []
            prev_frames = [None] * num_cameras
            
            # Analyze a few frames around the midpoint
            for sample_time in [mid_point - 100, mid_point, mid_point + 100]:
                if sample_time < region_start or sample_time > region_end:
                    continue
                    
                for cam_idx, video_path in enumerate(video_paths):
                    frame = self._lip_backend._get_frame_at_ms(video_path, sample_time)
                    motion = self._lip_backend._analyze_mouth_region(frame, prev_frames[cam_idx])
                    
                    if len(motions) <= cam_idx:
                        motions.append(motion)
                    else:
                        motions[cam_idx] = max(motions[cam_idx], motion)
                    
                    prev_frames[cam_idx] = frame
            
            # Pick camera with most motion
            if motions:
                best_cam = motions.index(max(motions))
            else:
                best_cam = 0
            
            all_segments.append(SpeakerSegment(
                start_ms=region_start,
                end_ms=region_end,
                speaker_id=best_cam,
            ))
        
        # If no segments, return default
        if not all_segments:
            return [SpeakerSegment(0, duration_ms, 0)]
        
        # Merge adjacent segments with same camera
        merged: List[SpeakerSegment] = [all_segments[0]]
        for seg in all_segments[1:]:
            if seg.speaker_id == merged[-1].speaker_id:
                # Extend previous
                merged[-1] = SpeakerSegment(
                    merged[-1].start_ms,
                    seg.end_ms,
                    seg.speaker_id,
                )
            else:
                merged.append(seg)
        
        logger.info("HYBRID complete: %d segments", len(merged))
        return merged


# Legacy API compatibility
def detect_active_speakers(audio_path: str, num_channels: int = 2) -> List[dict]:
    """
    Legacy function for backward compatibility.

    Returns list of dicts: [{"start_ms": int, "end_ms": int, "speaker_id": int}, ...]
    """
    detector = ActiveSpeakerDetector()
    segments = detector.detect(audio_path, num_channels)
    return [
        {"start_ms": s.start_ms, "end_ms": s.end_ms, "speaker_id": s.speaker_id}
        for s in segments
    ]
