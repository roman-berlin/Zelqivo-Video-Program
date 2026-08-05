"""Prove PySide6 ``QSettings.value(key, default, type=...)`` coercion.

All 61 ``QSettings.value(..., type=X)`` call sites in ``src/`` rely on the
``type=`` keyword coercing INI strings ("false" -> False) and returning the
typed default for missing keys. This guards a future PySide6 bump from
silently breaking settings persistence.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings


def _ini(tmp_path, name="settings.ini"):
    return QSettings(str(tmp_path / name), QSettings.Format.IniFormat)


@pytest.mark.parametrize(
    "value, typ",
    [
        (True, bool),
        (False, bool),
        (42, int),
        (-7, int),
        (3.5, float),
        (0.0, float),
        ("hello world", str),
        ("", str),
        ("path with spaces/and:colons\\backslash", str),
    ],
)
def test_roundtrip_through_ini(tmp_path, value, typ):
    writer = _ini(tmp_path)
    writer.setValue("key", value)
    writer.sync()
    # Fresh QSettings forces a re-read of the INI text, not the in-memory cache.
    reader = _ini(tmp_path)
    got = reader.value("key", None, type=typ)
    assert got == value
    assert isinstance(got, typ)


@pytest.mark.parametrize(
    "default, typ",
    [
        (True, bool),
        (False, bool),
        (7, int),
        (1.5, float),
        ("fallback", str),
    ],
)
def test_missing_key_returns_typed_default(tmp_path, default, typ):
    settings = _ini(tmp_path)
    got = settings.value("does-not-exist", default, type=typ)
    assert got == default
    assert isinstance(got, typ)


def test_raw_ini_strings_coerce(tmp_path):
    # Simulate an INI written by an older app version: everything is a string.
    ini = tmp_path / "legacy.ini"
    ini.write_text("[General]\nflag=false\nenabled=true\ncount=5\nratio=2.5\n")
    settings = QSettings(str(ini), QSettings.Format.IniFormat)
    assert settings.value("flag", True, type=bool) is False
    assert settings.value("enabled", False, type=bool) is True
    assert settings.value("count", 0, type=int) == 5
    assert settings.value("ratio", 0.0, type=float) == 2.5
