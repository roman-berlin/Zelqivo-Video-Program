"""Entry point for running ``multicam_editor`` as a module.

This module simply delegates to the :func:`main` function in
``multicam_editor.main``.  It allows the application to be started with
``python -m multicam_editor``.
"""

from .main import main


def _run() -> None:
    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover - manual entry point
    _run()