"""FCPXML export module for timeline cuts.

Generates FCPXML 1.11 compatible files for import into:
- Adobe Premiere Pro
- DaVinci Resolve
- Final Cut Pro
"""

import logging
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional
from xml.dom import minidom

logger = logging.getLogger(__name__)

# FCPXML version (1.11 is widely supported)
FCPXML_VERSION = "1.11"


@dataclass
class TimelineCut:
    """Represents a single cut in the timeline."""
    camera_index: int
    start_ms: float
    end_ms: float
    source_path: str


def _ms_to_frames(ms: float, fps: float = 30.0) -> int:
    """Convert milliseconds to frame count."""
    return int(ms / 1000.0 * fps)


def _ms_to_rational(ms: float, fps: float = 30.0) -> str:
    """Convert milliseconds to FCPXML rational time format (frames/fps*1000s)."""
    frames = int(ms / 1000.0 * fps)
    # Use 1001 for NTSC drop-frame compatibility
    if fps in (29.97, 23.976, 59.94):
        return f"{frames * 1001}/30000s"
    return f"{frames}/{ int(fps)}s"


def _duration_rational(duration_ms: float, fps: float = 30.0) -> str:
    """Convert duration in ms to FCPXML rational format."""
    frames = max(1, int(duration_ms / 1000.0 * fps))
    if fps in (29.97, 23.976, 59.94):
        return f"{frames * 1001}/30000s"
    return f"{frames}/{int(fps)}s"


def generate_fcpxml(
    cuts: List[TimelineCut],
    source_paths: List[str],
    output_path: str,
    project_name: str = "Multicam Edit",
    fps: float = 30.0,
    resolution: tuple = (1920, 1080),
) -> bool:
    """Generate FCPXML file from timeline cuts.
    
    Args:
        cuts: List of TimelineCut objects representing the edit decisions
        source_paths: List of source video file paths (camera order)
        output_path: Where to save the .fcpxml file
        project_name: Name for the project/sequence
        fps: Frame rate (default 30)
        resolution: Video resolution tuple (width, height)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Create root FCPXML element
        fcpxml = ET.Element("fcpxml", version=FCPXML_VERSION)
        
        # Resources section - define all media assets
        resources = ET.SubElement(fcpxml, "resources")
        
        # Format resource (defines frame rate and resolution)
        width, height = resolution
        format_id = "r1"
        format_elem = ET.SubElement(resources, "format", 
            id=format_id,
            name=f"{width}x{height}p{int(fps)}",
            frameDuration=_duration_rational(1000/fps, fps),
            width=str(width),
            height=str(height)
        )
        
        # Asset resources for each source video
        asset_ids = {}
        for i, path in enumerate(source_paths):
            asset_id = f"asset{i+1}"
            asset_ids[path] = asset_id
            
            # Get file URL (file:// format)
            file_url = f"file:///{path.replace(os.sep, '/').replace(':', '%3A')}"
            
            asset = ET.SubElement(resources, "asset",
                id=asset_id,
                name=os.path.basename(path),
                src=file_url,
                hasVideo="1",
                hasAudio="1",
                format=format_id
            )
        
        # Library -> Event -> Project structure
        library = ET.SubElement(fcpxml, "library")
        event = ET.SubElement(library, "event", name=project_name)
        project = ET.SubElement(event, "project", name=project_name)
        
        # Calculate total duration
        if cuts:
            total_duration_ms = max(c.end_ms for c in cuts)
        else:
            total_duration_ms = 0
        
        # Sequence (timeline)
        sequence = ET.SubElement(project, "sequence",
            format=format_id,
            duration=_duration_rational(total_duration_ms, fps),
            tcStart="0s",
            tcFormat="NDF"
        )
        
        # Spine (main video track)
        spine = ET.SubElement(sequence, "spine")
        
        # Add clips to timeline
        current_offset = 0
        for cut in sorted(cuts, key=lambda c: c.start_ms):
            source_path = cut.source_path
            asset_id = asset_ids.get(source_path, "asset1")
            
            clip_duration_ms = cut.end_ms - cut.start_ms
            
            # Create clip element
            clip = ET.SubElement(spine, "asset-clip",
                ref=asset_id,
                name=f"Cam{cut.camera_index + 1}",
                offset=_ms_to_rational(current_offset, fps),
                duration=_duration_rational(clip_duration_ms, fps),
                start=_ms_to_rational(cut.start_ms, fps),
                tcFormat="NDF"
            )
            
            current_offset += clip_duration_ms
        
        # Pretty print the XML
        xml_str = ET.tostring(fcpxml, encoding='unicode')
        dom = minidom.parseString(xml_str)
        pretty_xml = dom.toprettyxml(indent="  ", encoding="UTF-8")
        
        # Add XML declaration and DOCTYPE
        with open(output_path, 'wb') as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write(b'<!DOCTYPE fcpxml>\n')
            # Write the rest without the declaration (minidom adds one)
            lines = pretty_xml.decode('utf-8').split('\n')[1:]  # Skip first line (declaration)
            f.write('\n'.join(lines).encode('utf-8'))
        
        logger.info("Generated FCPXML: %s with %d cuts", output_path, len(cuts))
        return True
        
    except Exception as e:
        logger.error("Failed to generate FCPXML: %s", e, exc_info=True)
        return False


def cuts_from_speaker_segments(
    segments: list,
    source_paths: List[str],
) -> List[TimelineCut]:
    """Convert speaker segments to timeline cuts.
    
    Args:
        segments: List of SpeakerSegment objects (from diarization)
        source_paths: List of source video paths
    
    Returns:
        List of TimelineCut objects
    """
    cuts = []
    for seg in segments:
        # Extract camera index from speaker_id (e.g., "cam0" -> 0, 3 -> 3, None -> 0)
        raw_id = seg.speaker_id if hasattr(seg, 'speaker_id') else getattr(seg, 'speaker', 0)
        speaker_id = str(raw_id) if raw_id is not None else "0"
        
        if speaker_id.startswith("cam"):
            cam_idx = int(speaker_id[3:])
        elif speaker_id.startswith("speaker_"):
            cam_idx = int(speaker_id.replace("speaker_", ""))
        elif speaker_id.lstrip("-").isdigit():
            cam_idx = int(speaker_id)
        else:
            cam_idx = 0
        
        # Ensure camera index is valid
        if cam_idx >= len(source_paths):
            cam_idx = 0
        
        cuts.append(TimelineCut(
            camera_index=cam_idx,
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            source_path=source_paths[cam_idx]
        ))
    
    return cuts
