"""Shared pytest fixtures. Isolate storage + DB per test."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db.sqlite"))
    # force a fresh Settings + db connection
    from brainrotstudy import config, db

    config.get_settings.cache_clear()
    db._reset_for_tests()
    yield tmp_path
    db._reset_for_tests()
    config.get_settings.cache_clear()
