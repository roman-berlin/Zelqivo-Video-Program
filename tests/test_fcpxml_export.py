import os
import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch
import pytest
from multicam_editor.logic.fcpxml_export import (
    generate_fcpxml, 
    TimelineCut, 
    _ms_to_frames, 
    _ms_to_rational,
    cuts_from_speaker_segments
)

@pytest.fixture
def sample_cuts():
    return [
        TimelineCut(camera_index=0, start_ms=0, end_ms=1000, source_path="/path/to/cam1.mp4"),
        TimelineCut(camera_index=1, start_ms=1000, end_ms=2500, source_path="/path/to/cam2.mp4"),
    ]

@pytest.fixture
def sample_sources():
    return ["/path/to/cam1.mp4", "/path/to/cam2.mp4"]

def test_time_conversion_utilities():
    # 30 fps
    assert _ms_to_frames(1000, 30.0) == 30
    assert _ms_to_rational(1000, 30.0) == "30/30s"
    
    # NTSC 29.97
    assert _ms_to_rational(1000, 29.97) == "29029/30000s" # 29 frames * 1001
    # Actually checking logic: int(1000/1000 * 29.97) -> 29. 29*1001 = 29029. 
    # Wait, 1000ms is 1 second. 29.97 frames.
    # The function implements:
    # frames = int(ms / 1000.0 * fps)
    
    # Let's test specific logic in function:
    # if fps in (29.97...): return f"{frames * 1001}/30000s"
    
    frames_2997 = int(1.0 * 29.97) # 29
    assert _ms_to_rational(1000, 29.97) == f"{frames_2997 * 1001}/30000s"

def test_generate_fcpxml_structure(tmp_path, sample_cuts, sample_sources):
    output_file = tmp_path / "test.fcpxml"
    
    success = generate_fcpxml(
        cuts=sample_cuts,
        source_paths=sample_sources,
        output_path=str(output_file),
        project_name="Test Project",
        fps=30.0
    )
    
    assert success
    assert output_file.exists()
    
    # Parse the generated XML to verify structure
    tree = ET.parse(output_file)
    root = tree.getroot()
    
    assert root.tag == "fcpxml"
    assert root.attrib["version"] == "1.11"
    
    # Check resources
    resources = root.find("resources")
    assert resources is not None
    assets = resources.findall("asset")
    assert len(assets) == 2
    
    # Check library/event/project
    library = root.find("library")
    assert library is not None
    event = library.find("event")
    assert event is not None
    assert event.attrib["name"] == "Test Project"
    project = event.find("project")
    assert project is not None
    sequence = project.find("sequence")
    assert sequence is not None
    
    # Check clips in spine
    spine = sequence.find("spine")
    clips = spine.findall("asset-clip")
    assert len(clips) == 2
    
    # Verify clip details
    assert clips[0].attrib["name"] == "Cam1"
    assert clips[1].attrib["name"] == "Cam2"
    
def test_cuts_from_speaker_segments():
    # Mocking segments as simple objects
    Seg = Mock
    segments = [
        Mock(speaker_id="speaker_0", start_ms=0, end_ms=1000),
        Mock(speaker_id="cam1", start_ms=1000, end_ms=2000),
        Mock(speaker_id="2", start_ms=2000, end_ms=3000), # should be cam 2
        Mock(speaker_id="unknown", start_ms=3000, end_ms=4000), # should default to 0
    ]
    
    sources = ["path0", "path1", "path2"]
    
    cuts = cuts_from_speaker_segments(segments, sources)
    
    assert len(cuts) == 4
    assert cuts[0].camera_index == 0
    assert cuts[1].camera_index == 1
    assert cuts[2].camera_index == 2
    assert cuts[3].camera_index == 0 # unknown -> 0
