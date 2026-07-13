from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


@dataclass(frozen=True, slots=True)
class UpdateConfiguration:
    provider: str = "github"
    repository: str = ""
    error: str | None = None

    @property
    def configured(self) -> bool:
        return (
            self.error is None
            and self.provider == "github"
            and REPOSITORY_PATTERN.fullmatch(self.repository) is not None
        )

    @property
    def latest_release_api_url(self) -> str:
        if not self.configured:
            return ""
        return f"https://api.github.com/repos/{self.repository}/releases/latest"


def default_update_config_path() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return bundle_root / "update-config.json"
    return Path(__file__).resolve().parents[3] / "build" / "update-config.json"


def load_update_configuration(path: Path | None = None) -> UpdateConfiguration:
    config_path = path or default_update_config_path()
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("A configuração de atualizações deve ser um objeto JSON.")
        provider = payload.get("provider", "github")
        repository = payload.get("repository", "")
        if provider != "github":
            raise ValueError("Provedor de atualizações não suportado.")
        if not isinstance(repository, str):
            raise ValueError("O repositório de atualizações deve ser texto.")
        repository = repository.strip()
        if repository and REPOSITORY_PATTERN.fullmatch(repository) is None:
            raise ValueError("Use o formato owner/repository.")
        return UpdateConfiguration(provider=provider, repository=repository)
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        return UpdateConfiguration(error=str(exc))
