"""Tests for QA artifacts export."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from multicam_editor.logic.active_speaker import SpeakerSegment
from multicam_editor.logic.qa_artifacts import (
    CutPlanEntry,
    _sanitize_path,
    export_cut_plan,
    export_diarization,
    export_processing_summary,
    QAArtifactExporter,
)


class TestSanitizePath:
    """Tests for the _sanitize_path helper."""

    def test_strips_directory(self):
        assert _sanitize_path("/some/dir/video.mp4") == "video.mp4"

    def test_windows_path(self):
        assert _sanitize_path(r"C:\Users\me\video.mp4") == "video.mp4"

    def test_filename_only(self):
        assert _sanitize_path("video.mp4") == "video.mp4"


class TestExportDiarization:
    """Tests for export_diarization."""

    def test_writes_valid_json(self, tmp_path):
        segments = [
            SpeakerSegment(start_ms=0, end_ms=1000, speaker_id=0),
            SpeakerSegment(start_ms=1000, end_ms=2000, speaker_id=1),
            SpeakerSegment(start_ms=2000, end_ms=3000, speaker_id=0),
        ]
        export_diarization(tmp_path, segments)

        out_file = tmp_path / "diarization.json"
        assert out_file.exists()
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert "speakers" in data
        assert "segments" in data
        assert len(data["segments"]) == 3
        assert data["segments"][0]["start_ms"] == 0
        assert data["segments"][0]["speaker_id"] == 0

    def test_unique_speakers_listed(self, tmp_path):
        segments = [
            SpeakerSegment(start_ms=0, end_ms=1000, speaker_id=0),
            SpeakerSegment(start_ms=1000, end_ms=2000, speaker_id=1),
        ]
        export_diarization(tmp_path, segments)

        data = json.loads((tmp_path / "diarization.json").read_text(encoding="utf-8"))
        speaker_ids = [s["id"] for s in data["speakers"]]
        assert speaker_ids == [0, 1]


class TestExportCutPlan:
    """Tests for export_cut_plan."""

    def test_writes_valid_json(self, tmp_path):
        cuts = [
            CutPlanEntry(start_ms=0, end_ms=5000, chosen_camera_index=0, speaker_id=0, reason="threshold"),
            CutPlanEntry(start_ms=5000, end_ms=10000, chosen_camera_index=1, speaker_id=1, reason="forced"),
        ]
        export_cut_plan(tmp_path, cuts)

        out_file = tmp_path / "cut_plan.json"
        assert out_file.exists()
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert len(data["cuts"]) == 2
        assert data["cuts"][0]["reason"] == "threshold"
        assert data["cuts"][1]["chosen_camera_index"] == 1


class TestExportProcessingSummary:
    """Tests for export_processing_summary."""

    def test_writes_valid_json(self, tmp_path):
        thresholds = {"min_switch_interval_ms": 2000, "min_speech_ms": 500}
        export_processing_summary(
            tmp_path,
            num_speakers=2,
            num_segments=10,
            num_cuts=5,
            total_duration_ms=60000,
            thresholds=thresholds,
        )
        out_file = tmp_path / "processing_summary.json"
        assert out_file.exists()
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert data["counts"]["num_speakers"] == 2
        assert data["counts"]["total_duration_ms"] == 60000
        assert data["thresholds"]["min_switch_interval_ms"] == 2000
        assert data["external_audio_sync"] == {"used": False}

    def test_includes_sync_info(self, tmp_path):
        sync_info = {"used": True, "offset_ms": 150.0, "success": True}
        export_processing_summary(
            tmp_path,
            num_speakers=1,
            num_segments=5,
            num_cuts=3,
            total_duration_ms=30000,
            thresholds={},
            sync_info=sync_info,
        )
        data = json.loads((tmp_path / "processing_summary.json").read_text(encoding="utf-8"))
        assert data["external_audio_sync"]["offset_ms"] == 150.0

    def test_includes_camera_alignments(self, tmp_path):
        alignments = [
            {"camera_index": 0, "offset_ms": 0.0},
            {"camera_index": 1, "offset_ms": -50.0},
        ]
        export_processing_summary(
            tmp_path,
            num_speakers=2,
            num_segments=5,
            num_cuts=3,
            total_duration_ms=30000,
            thresholds={},
            camera_alignments=alignments,
        )
        data = json.loads((tmp_path / "processing_summary.json").read_text(encoding="utf-8"))
        assert len(data["camera_alignments"]) == 2


class TestCutPlanEntry:
    """Tests for CutPlanEntry dataclass."""

    def test_create(self):
        entry = CutPlanEntry(
            start_ms=0, end_ms=5000, chosen_camera_index=0,
            speaker_id=1, reason="threshold",
        )
        assert entry.start_ms == 0
        assert entry.end_ms == 5000
        assert entry.reason == "threshold"


class TestQAArtifactExporter:
    """Tests for the QAArtifactExporter class."""

    @pytest.fixture
    def exporter(self):
        return QAArtifactExporter()

    def test_init_defaults(self, exporter):
        assert exporter.run_folder is None
        assert exporter._segments == []
        assert exporter._cuts == []

    @patch("multicam_editor.logic.qa_artifacts.create_run_folder")
    def test_start_run_creates_folder(self, mock_create, exporter, tmp_path):
        mock_create.return_value = tmp_path
        result = exporter.start_run()
        assert result == tmp_path
        assert exporter.run_folder == tmp_path

    def test_set_diarization(self, exporter):
        segments = [SpeakerSegment(start_ms=0, end_ms=1000, speaker_id=0)]
        exporter.set_diarization(segments)
        assert len(exporter._segments) == 1

    def test_set_thresholds(self, exporter):
        exporter.set_thresholds(min_switch_interval_ms=2000, min_speech_ms=500, bg_short_remark_ms=800)
        assert exporter._thresholds["min_switch_interval_ms"] == 2000
        assert exporter._thresholds["min_speech_ms"] == 500

    def test_add_cut(self, exporter):
        exporter.add_cut(start_ms=0, end_ms=5000, camera_index=0, speaker_id=1, reason="threshold")
        assert len(exporter._cuts) == 1
        assert exporter._cuts[0].reason == "threshold"

    def test_set_sync_info(self, exporter):
        exporter.set_sync_info(offset_ms=100.0, success=True, message="OK")
        assert exporter._sync_info["offset_ms"] == 100.0
        assert exporter._sync_info["success"] is True

    def test_set_camera_alignments(self, exporter):
        alignments = [{"camera_index": 0, "offset_ms": 0.0}]
        exporter.set_camera_alignments(alignments)
        assert len(exporter._camera_alignments) == 1

    def test_set_external_audio_alignment(self, exporter):
        info = {"external_audio_path": "ext.wav", "offset_ms": 50.0, "status": "ok"}
        exporter.set_external_audio_alignment(info)
        assert exporter._external_audio_alignment["offset_ms"] == 50.0

    @patch("multicam_editor.logic.qa_artifacts.create_run_folder")
    def test_finalize_writes_all_artifacts(self, mock_create, exporter, tmp_path):
        mock_create.return_value = tmp_path
        exporter.start_run()
        exporter.set_diarization([SpeakerSegment(start_ms=0, end_ms=1000, speaker_id=0)])
        exporter.add_cut(start_ms=0, end_ms=1000, camera_index=0, speaker_id=0, reason="default")
        exporter.set_thresholds(min_switch_interval_ms=2000, min_speech_ms=500, bg_short_remark_ms=800)
        exporter.set_total_duration(10000)
        exporter.finalize()

        assert (tmp_path / "diarization.json").exists()
        assert (tmp_path / "cut_plan.json").exists()
        assert (tmp_path / "processing_summary.json").exists()

    def test_finalize_without_run_folder_is_noop(self, exporter):
        """Finalize without start_run should not crash."""
        exporter.finalize()  # Should just log a warning

    @patch("multicam_editor.logic.qa_artifacts.create_run_folder")
    def test_finalize_with_external_audio(self, mock_create, exporter, tmp_path):
        mock_create.return_value = tmp_path
        exporter.start_run()
        exporter.set_external_audio_alignment({"path": "ext.wav", "offset_ms": 25.0})
        exporter.finalize()

        ext_file = tmp_path / "external_audio_alignment.json"
        assert ext_file.exists()
        data = json.loads(ext_file.read_text(encoding="utf-8"))
        assert data["offset_ms"] == 25.0
