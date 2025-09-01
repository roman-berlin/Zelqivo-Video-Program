"""Sanity tests for importing the package.

We deliberately avoid importing GUI modules here because PyQt6 may not be
available in the test environment.  Instead we import the top‑level
package and a core submodule to verify that basic imports succeed.
"""

def test_import_package() -> None:
    import importlib

    # Import the package itself.  This should not raise.
    import multicam_editor  # type: ignore[import-not-found]

    # Import a specific module from the package.  Project.MIN_SEGMENT_MS should
    # be defined and greater than zero.
    mod = importlib.import_module("multicam_editor.core.project")
    assert getattr(mod, "Project").MIN_SEGMENT_MS > 0