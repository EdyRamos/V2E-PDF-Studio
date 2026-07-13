from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..domain import CompressionProfile
from .paths import SETTINGS_FILE, ensure_app_dirs

SETTINGS_SCHEMA_VERSION = 1


@dataclass(slots=True)
class AppSettings:
    last_directory: str | None = None
    default_profile: str = CompressionProfile.EBOOK.value
    overwrite_policy: str = "rename"
    schema_version: int = field(default=SETTINGS_SCHEMA_VERSION, init=False)


class SettingsRepository:
    def __init__(self, settings_file: Path | None = None) -> None:
        self.settings_file = settings_file or SETTINGS_FILE

    def load(self) -> AppSettings:
        self._ensure_parent()
        if not self.settings_file.exists():
            defaults = AppSettings()
            self.save(defaults)
            return defaults
        try:
            payload = json.loads(self.settings_file.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("O arquivo de configuracao deve conter um objeto JSON.")
            last_directory = payload.get("last_directory")
            if not isinstance(last_directory, str) or not Path(last_directory).is_dir():
                last_directory = None
            settings = AppSettings(
                last_directory=last_directory,
                default_profile=CompressionProfile.from_value(
                    payload.get("default_profile", CompressionProfile.EBOOK.value)
                ).value,
                overwrite_policy=payload.get("overwrite_policy", "rename"),
            )
            if settings.overwrite_policy not in {"rename", "overwrite"}:
                settings.overwrite_policy = "rename"
            return settings
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            self._preserve_invalid_file()
            defaults = AppSettings()
            try:
                self.save(defaults)
            except OSError:
                pass
            return defaults

    def save(self, settings: AppSettings) -> None:
        self._ensure_parent()
        settings.schema_version = SETTINGS_SCHEMA_VERSION
        if settings.overwrite_policy not in {"rename", "overwrite"}:
            settings.overwrite_policy = "rename"
        settings.default_profile = CompressionProfile.from_value(settings.default_profile).value
        if settings.last_directory and not Path(settings.last_directory).is_dir():
            settings.last_directory = None
        payload = asdict(settings)
        serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=f".{self.settings_file.name}.",
                suffix=".tmp",
                dir=self.settings_file.parent,
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.settings_file)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def _ensure_parent(self) -> None:
        ensure_app_dirs()
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)

    def _preserve_invalid_file(self) -> None:
        if not self.settings_file.exists():
            return
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = self.settings_file.with_name(f"{self.settings_file.name}.invalid-{timestamp}")
        try:
            os.replace(self.settings_file, backup)
        except OSError:
            pass
