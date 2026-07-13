from __future__ import annotations

import json
from pathlib import Path

from v2e_pdf_compressor.config.settings import (
    SETTINGS_SCHEMA_VERSION,
    AppSettings,
    SettingsRepository,
)


def test_settings_round_trip_and_validation(tmp_path: Path) -> None:
    settings_file = tmp_path / "nested" / "settings.json"
    repository = SettingsRepository(settings_file)
    repository.save(
        AppSettings(
            last_directory=str(tmp_path),
            default_profile="screen",
            overwrite_policy="overwrite",
        )
    )

    loaded = repository.load()
    assert loaded.schema_version == SETTINGS_SCHEMA_VERSION
    assert loaded.last_directory == str(tmp_path)
    assert loaded.default_profile == "screen"
    assert loaded.overwrite_policy == "overwrite"
    assert not list(settings_file.parent.glob("*.tmp"))


def test_invalid_json_is_preserved_and_replaced(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{invalid", encoding="utf-8")
    repository = SettingsRepository(settings_file)

    loaded = repository.load()

    assert loaded == AppSettings()
    assert json.loads(settings_file.read_text(encoding="utf-8"))["schema_version"] == 1
    assert len(list(tmp_path.glob("settings.json.invalid-*"))) == 1


def test_settings_reject_unknown_values_and_missing_directory(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "last_directory": str(tmp_path / "missing"),
                "default_profile": "not-a-profile",
                "overwrite_policy": "dangerous",
                "recent_documents": ["secret.pdf"],
            }
        ),
        encoding="utf-8",
    )
    loaded = SettingsRepository(settings_file).load()
    assert loaded.last_directory is None
    assert loaded.default_profile == "ebook"
    assert loaded.overwrite_policy == "rename"
