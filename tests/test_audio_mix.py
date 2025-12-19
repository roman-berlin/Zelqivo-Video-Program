"""Tests for audio mix settings (Prompt 7.1)."""

import pytest
from multicam_editor.core.project import AudioMixMode, AudioMixSettings


class TestAudioMixSettings:
    """Tests for AudioMixSettings dataclass."""

    def test_default_values(self) -> None:
        """Default settings should be Replace mode with 0dB gains."""
        settings = AudioMixSettings()
        assert settings.mode == AudioMixMode.REPLACE
        assert settings.video_gain_db == 0.0
        assert settings.external_gain_db == 0.0
        assert settings.ducking_enabled is False
        assert settings.ducking_amount_db == -12.0

    def test_replace_mode(self) -> None:
        """Replace mode enum value should be 'replace'."""
        assert AudioMixMode.REPLACE.value == "replace"

    def test_mix_mode(self) -> None:
        """Mix mode enum value should be 'mix'."""
        assert AudioMixMode.MIX.value == "mix"

    def test_custom_gains(self) -> None:
        """Settings should accept custom gain values."""
        settings = AudioMixSettings(
            mode=AudioMixMode.MIX,
            video_gain_db=-6.0,
            external_gain_db=3.0,
            ducking_enabled=True,
            ducking_amount_db=-18.0,
        )
        assert settings.mode == AudioMixMode.MIX
        assert settings.video_gain_db == -6.0
        assert settings.external_gain_db == 3.0
        assert settings.ducking_enabled is True
        assert settings.ducking_amount_db == -18.0

    def test_clamp_gains_within_range(self) -> None:
        """Gains within valid range should not be modified."""
        settings = AudioMixSettings(
            video_gain_db=-30.0,
            external_gain_db=6.0,
            ducking_amount_db=-24.0,
        )
        clamped = settings.clamp_gains()
        assert clamped.video_gain_db == -30.0
        assert clamped.external_gain_db == 6.0
        assert clamped.ducking_amount_db == -24.0

    def test_clamp_gains_too_low(self) -> None:
        """Gains below -60dB should be clamped to -60dB."""
        settings = AudioMixSettings(
            video_gain_db=-100.0,
            external_gain_db=-80.0,
        )
        clamped = settings.clamp_gains()
        assert clamped.video_gain_db == -60.0
        assert clamped.external_gain_db == -60.0

    def test_clamp_gains_too_high(self) -> None:
        """Gains above +12dB should be clamped to +12dB."""
        settings = AudioMixSettings(
            video_gain_db=20.0,
            external_gain_db=15.0,
        )
        clamped = settings.clamp_gains()
        assert clamped.video_gain_db == 12.0
        assert clamped.external_gain_db == 12.0

    def test_clamp_ducking_amount(self) -> None:
        """Ducking amount should be clamped to [-60, 0]."""
        # Too low
        settings1 = AudioMixSettings(ducking_amount_db=-100.0)
        clamped1 = settings1.clamp_gains()
        assert clamped1.ducking_amount_db == -60.0

        # Too high (positive ducking doesn't make sense)
        settings2 = AudioMixSettings(ducking_amount_db=10.0)
        clamped2 = settings2.clamp_gains()
        assert clamped2.ducking_amount_db == 0.0

    def test_clamp_preserves_mode_and_ducking_flag(self) -> None:
        """Clamping should preserve mode and ducking enabled flag."""
        settings = AudioMixSettings(
            mode=AudioMixMode.MIX,
            ducking_enabled=True,
        )
        clamped = settings.clamp_gains()
        assert clamped.mode == AudioMixMode.MIX
        assert clamped.ducking_enabled is True


class TestAudioMixModeEnum:
    """Tests for AudioMixMode enum."""

    def test_enum_values(self) -> None:
        """Enum should have exactly REPLACE and MIX."""
        modes = list(AudioMixMode)
        assert len(modes) == 2
        assert AudioMixMode.REPLACE in modes
        assert AudioMixMode.MIX in modes
