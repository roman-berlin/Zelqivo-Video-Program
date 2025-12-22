"""CLI entry point for headless QA processing.

Usage:
  python -m multicam_editor.cli \
    --videos cam1.mp4 cam2.mp4 \
    --external-audio podcast.wav \
    --enable-speaker-switching true \
    --mapping cam1:speaker_0 cam2:speaker_1 \
    --preset 1080p \
    --out output.mp4 \
    --export-artifacts true

Returns non-zero exit code on failure.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

from multicam_editor.logging_setup import configure_logging
from multicam_editor.utils.signals import ProcessingSignals
from multicam_editor.logic.processing_pipeline import ProcessingPipeline, PipelineProgress
from multicam_editor.logic.qa_artifacts import get_last_run_folder

logger = logging.getLogger(__name__)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="multicam_editor.cli",
        description="Headless multicam processing for QA and automation.",
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="Run health check and exit (verify ffmpeg, backends)",
    )
    parser.add_argument(
        "--videos",
        nargs="+",
        required=False,  # Not required when --health is used
        help="Input video files (at least 2)",
    )
    parser.add_argument(
        "--external-audio",
        dest="external_audio",
        help="Optional external audio file to sync",
    )
    parser.add_argument(
        "--enable-speaker-switching",
        dest="enable_speaker_switching",
        type=lambda x: x.lower() in ("true", "1", "yes"),
        default=True,
        help="Enable speaker-based camera switching (default: true)",
    )
    parser.add_argument(
        "--mapping",
        nargs="*",
        help="Camera to speaker mapping (e.g. cam1:speaker_0 cam2:speaker_1). Reserved for future use.",
    )
    parser.add_argument(
        "--preset",
        default="1080p",
        choices=["1080p", "720p", "480p"],
        help="Output resolution preset (default: 1080p)",
    )
    parser.add_argument(
        "--out",
        required=False,  # Not required when --health is used
        help="Output file path",
    )
    parser.add_argument(
        "--export-artifacts",
        dest="export_artifacts",
        type=lambda x: x.lower() in ("true", "1", "yes"),
        default=True,
        help="Export QA artifacts (default: true)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args(argv)


def validate_inputs(args: argparse.Namespace) -> bool:
    """Validate input files exist."""
    for video in args.videos:
        if not Path(video).is_file():
            logger.error("Video file not found: %s", video)
            return False

    if args.external_audio and not Path(args.external_audio).is_file():
        logger.error("External audio file not found: %s", args.external_audio)
        return False

    if len(args.videos) < 2:
        logger.error("At least 2 video files required")
        return False

    return True


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point.

    Returns:
        0 on success, non-zero on failure.
    """
    args = parse_args(argv)

    # Setup logging
    configure_logging()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Handle --health flag
    if args.health:
        from multicam_editor.utils.backends import print_health_check
        ready = print_health_check()
        return 0 if ready else 1

    # Validate required arguments for processing
    if not args.videos:
        logger.error("--videos is required for processing (use --health to check system)")
        return 1
    if not args.out:
        logger.error("--out is required for processing")
        return 1

    logger.info("MultiCam CLI starting...")
    logger.info("Videos: %s", args.videos)
    logger.info("Output: %s", args.out)

    # Validate inputs
    if not validate_inputs(args):
        return 1

    # Create signals for pipeline (we won't connect to UI, but pipeline needs them)
    signals = ProcessingSignals()

    # Track errors
    error_message = None

    def on_error(msg: str) -> None:
        nonlocal error_message
        error_message = msg
        logger.error("Pipeline error: %s", msg)

    def on_progress(progress: PipelineProgress) -> None:
        logger.info(
            "[%s] %d%% - %s",
            progress.stage_name,
            progress.overall_percent,
            progress.message,
        )

    signals.error.connect(on_error)

    try:
        # Create and run pipeline
        pipeline = ProcessingPipeline(
            input_files=args.videos,
            signals=signals,
            progress_callback=on_progress,
        )

        result = pipeline.run(
            external_audio=args.external_audio,
            resolution=args.preset,
            output_path=args.out,
        )

        if result.success:
            logger.info("SUCCESS: Output written to %s", result.output_path)

            # Print artifacts folder if export was enabled
            if args.export_artifacts:
                artifacts_folder = get_last_run_folder()
                if artifacts_folder:
                    print(f"Artifacts: {artifacts_folder}")
                    logger.info("QA artifacts: %s", artifacts_folder)

            return 0
        else:
            logger.error("FAILED: %s", result.error or error_message or "Unknown error")
            return 1

    except ValueError as e:
        logger.error("Invalid input: %s", e)
        return 1
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
