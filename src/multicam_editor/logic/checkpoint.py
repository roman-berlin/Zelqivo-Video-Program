"""Pipeline checkpoint system for crash recovery.

Saves pipeline state after each stage completes, enabling resumption
of partially completed jobs after crashes or interruptions.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Optional, Dict, Any

from PySide6.QtCore import QStandardPaths

logger = logging.getLogger(__name__)


@dataclass
class PipelineCheckpoint:
    """Persistent state for pipeline recovery.
    
    Saved after each stage completes to enable resume.
    """
    run_id: str
    current_stage: str  # Stage name string
    completed_stages: List[str] = field(default_factory=list)
    input_files: List[str] = field(default_factory=list)
    rendered_segments: List[str] = field(default_factory=list)
    camera_offsets: Dict[int, float] = field(default_factory=dict)
    cut_plan_json: str = ""  # Serialized cut plan
    output_path: str = ""
    timestamp: str = ""
    version: str = "1.0"


def get_checkpoint_dir() -> Path:
    """Return the directory for checkpoint files.
    
    Uses AppData/Local on Windows, ~/.local/share on Linux.
    """
    app_data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    if not app_data:
        app_data = os.path.expanduser("~")
    base = Path(app_data) / "MultiCamEditor" / "checkpoints"
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_checkpoint_path(run_id: str) -> Path:
    """Get path for a specific run's checkpoint file."""
    return get_checkpoint_dir() / f"checkpoint_{run_id}.json"


def save_checkpoint(checkpoint: PipelineCheckpoint) -> bool:
    """Save checkpoint to disk.
    
    Args:
        checkpoint: Checkpoint to save
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        checkpoint.timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        path = get_checkpoint_path(checkpoint.run_id)
        
        # Convert to dict for JSON serialization
        data = asdict(checkpoint)
        # Convert int keys to strings for JSON
        data["camera_offsets"] = {str(k): v for k, v in checkpoint.camera_offsets.items()}
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        logger.debug("Checkpoint saved: %s (stage: %s)", path.name, checkpoint.current_stage)
        return True
        
    except Exception as e:
        logger.error("Failed to save checkpoint: %s", e)
        return False


def load_checkpoint(run_id: str) -> Optional[PipelineCheckpoint]:
    """Load checkpoint from disk.
    
    Args:
        run_id: ID of the run to load
        
    Returns:
        PipelineCheckpoint if found and valid, None otherwise
    """
    try:
        path = get_checkpoint_path(run_id)
        if not path.exists():
            return None
            
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Convert string keys back to ints for camera_offsets
        if "camera_offsets" in data:
            data["camera_offsets"] = {int(k): v for k, v in data["camera_offsets"].items()}
        
        return PipelineCheckpoint(**data)
        
    except Exception as e:
        logger.error("Failed to load checkpoint %s: %s", run_id, e)
        return None


def find_incomplete_checkpoints() -> List[PipelineCheckpoint]:
    """Find all incomplete checkpoints that can be resumed.
    
    Returns:
        List of checkpoints where current_stage != "DONE"
    """
    checkpoints: List[PipelineCheckpoint] = []
    
    try:
        checkpoint_dir = get_checkpoint_dir()
        for path in checkpoint_dir.glob("checkpoint_*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                if "camera_offsets" in data:
                    data["camera_offsets"] = {int(k): v for k, v in data["camera_offsets"].items()}
                
                checkpoint = PipelineCheckpoint(**data)
                
                # Only include incomplete runs
                if checkpoint.current_stage != "DONE":
                    checkpoints.append(checkpoint)
                    
            except Exception as e:
                logger.debug("Skipping invalid checkpoint %s: %s", path.name, e)
                
    except Exception as e:
        logger.error("Error scanning checkpoints: %s", e)
    
    # Sort by timestamp (newest first)
    checkpoints.sort(key=lambda c: c.timestamp, reverse=True)
    return checkpoints


def delete_checkpoint(run_id: str) -> bool:
    """Delete a checkpoint file after successful completion.
    
    Args:
        run_id: ID of the run to delete
        
    Returns:
        True if deleted, False otherwise
    """
    try:
        path = get_checkpoint_path(run_id)
        if path.exists():
            path.unlink()
            logger.debug("Deleted checkpoint: %s", path.name)
        return True
    except Exception as e:
        logger.warning("Failed to delete checkpoint: %s", e)
        return False


def cleanup_old_checkpoints(max_age_days: int = 7) -> int:
    """Remove checkpoints older than max_age_days.
    
    Args:
        max_age_days: Maximum age in days
        
    Returns:
        Number of checkpoints deleted
    """
    deleted = 0
    cutoff = time.time() - (max_age_days * 24 * 60 * 60)
    
    try:
        checkpoint_dir = get_checkpoint_dir()
        for path in checkpoint_dir.glob("checkpoint_*.json"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    deleted += 1
                    logger.debug("Deleted old checkpoint: %s", path.name)
            except Exception:
                pass
                
    except Exception as e:
        logger.error("Error cleaning checkpoints: %s", e)
    
    if deleted > 0:
        logger.info("Cleaned up %d old checkpoints", deleted)
    
    return deleted
