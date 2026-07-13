from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import BinaryIO, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from ..config import APP_DATA_DIR, UpdateConfiguration

RELEASE_ASSET_NAME = "V2E-PDF-Compressor.exe"
RELEASE_MANIFEST_NAME = "release-manifest.json"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_EXECUTABLE_BYTES = 1024 * 1024 * 1024
SHA256_PATTERN = re.compile(r"[A-Fa-f0-9]{64}")
VERSION_PATTERN = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
ProgressCallback = Callable[[int, int], None]


class UpdateErrorCode(str, Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NETWORK_ERROR = "NETWORK_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    RELEASE_INCOMPLETE = "RELEASE_INCOMPLETE"
    INTEGRITY_FAILED = "INTEGRITY_FAILED"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"


class UpdateServiceError(RuntimeError):
    def __init__(self, code: UpdateErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class UpdateInfo:
    version: str
    executable_url: str
    expected_sha256: str
    size_bytes: int
    release_url: str
    release_notes: str


@dataclass(frozen=True, slots=True)
class UpdateCheckResult:
    current_version: str
    latest_version: str
    update_available: bool
    update: UpdateInfo | None = None


class UrlOpener(Protocol):
    def __call__(self, request: Request, timeout: float) -> AbstractContextManager[BinaryIO]: ...


def _default_url_opener(request: Request, timeout: float) -> AbstractContextManager[BinaryIO]:
    return cast(AbstractContextManager[BinaryIO], urlopen(request, timeout=timeout))


class UpdateService:
    def __init__(
        self,
        configuration: UpdateConfiguration,
        current_version: str,
        *,
        update_directory: Path | None = None,
        timeout_seconds: float = 20,
        opener: UrlOpener | None = None,
    ) -> None:
        self.configuration = configuration
        self.current_version = current_version
        self.update_directory = update_directory or APP_DATA_DIR / "updates"
        self.timeout_seconds = timeout_seconds
        self._opener = opener or _default_url_opener

    def check_for_update(self) -> UpdateCheckResult:
        if not self.configuration.configured:
            detail = self.configuration.error or "Repositório GitHub não configurado no build."
            raise UpdateServiceError(UpdateErrorCode.NOT_CONFIGURED, detail)

        release = self._read_json(self.configuration.latest_release_api_url)
        tag_name = release.get("tag_name")
        if not isinstance(tag_name, str):
            raise UpdateServiceError(
                UpdateErrorCode.INVALID_RESPONSE,
                "A release mais recente não informa uma versão válida.",
            )
        latest_version = self._normalize_version(tag_name)
        if self._version_tuple(latest_version) <= self._version_tuple(self.current_version):
            return UpdateCheckResult(
                current_version=self.current_version,
                latest_version=latest_version,
                update_available=False,
            )

        assets = release.get("assets")
        if not isinstance(assets, list):
            raise UpdateServiceError(
                UpdateErrorCode.RELEASE_INCOMPLETE,
                "A release não contém a lista de arquivos.",
            )
        executable_asset = self._find_asset(assets, RELEASE_ASSET_NAME)
        manifest_asset = self._find_asset(assets, RELEASE_MANIFEST_NAME)
        manifest = self._read_json(self._asset_url(manifest_asset))
        artifact = manifest.get("artifact")
        if not isinstance(artifact, dict):
            raise UpdateServiceError(
                UpdateErrorCode.INVALID_RESPONSE,
                "O manifesto da release não contém os dados do executável.",
            )

        manifest_version = manifest.get("version")
        if (
            not isinstance(manifest_version, str)
            or self._normalize_version(manifest_version) != latest_version
        ):
            raise UpdateServiceError(
                UpdateErrorCode.INTEGRITY_FAILED,
                "A versão do manifesto não corresponde à release.",
            )
        if artifact.get("name") != RELEASE_ASSET_NAME:
            raise UpdateServiceError(
                UpdateErrorCode.INTEGRITY_FAILED,
                "O manifesto aponta para um executável inesperado.",
            )

        sha256 = artifact.get("sha256")
        size = artifact.get("size")
        if not isinstance(sha256, str) or SHA256_PATTERN.fullmatch(sha256) is None:
            raise UpdateServiceError(
                UpdateErrorCode.INVALID_RESPONSE,
                "O manifesto não contém um SHA-256 válido.",
            )
        if not isinstance(size, int) or not 0 < size <= MAX_EXECUTABLE_BYTES:
            raise UpdateServiceError(
                UpdateErrorCode.INVALID_RESPONSE,
                "O manifesto contém um tamanho de executável inválido.",
            )
        asset_size = executable_asset.get("size")
        if isinstance(asset_size, int) and asset_size != size:
            raise UpdateServiceError(
                UpdateErrorCode.INTEGRITY_FAILED,
                "O tamanho publicado não corresponde ao manifesto.",
            )
        asset_digest = executable_asset.get("digest")
        if isinstance(asset_digest, str) and asset_digest.startswith("sha256:"):
            if asset_digest.removeprefix("sha256:").upper() != sha256.upper():
                raise UpdateServiceError(
                    UpdateErrorCode.INTEGRITY_FAILED,
                    "O digest do GitHub não corresponde ao manifesto.",
                )

        release_url = release.get("html_url", "")
        notes = release.get("body", "")
        return UpdateCheckResult(
            current_version=self.current_version,
            latest_version=latest_version,
            update_available=True,
            update=UpdateInfo(
                version=latest_version,
                executable_url=self._asset_url(executable_asset),
                expected_sha256=sha256.upper(),
                size_bytes=size,
                release_url=release_url if isinstance(release_url, str) else "",
                release_notes=notes[:2000] if isinstance(notes, str) else "",
            ),
        )

    def download_update(
        self,
        update: UpdateInfo,
        progress_callback: ProgressCallback | None = None,
    ) -> Path:
        self._validate_github_url(update.executable_url)
        if update.size_bytes > MAX_EXECUTABLE_BYTES:
            raise UpdateServiceError(
                UpdateErrorCode.DOWNLOAD_FAILED, "O arquivo excede o limite permitido."
            )
        self.update_directory.mkdir(parents=True, exist_ok=True)
        output_path = self.update_directory / f"V2E-PDF-Compressor-{update.version}.exe"
        if output_path.is_file() and self._sha256(output_path) == update.expected_sha256:
            return output_path

        temp_path: Path | None = None
        digest = hashlib.sha256()
        downloaded = 0
        download_complete = False
        try:
            request = self._request(update.executable_url, accept="application/octet-stream")
            with self._opener(request, self.timeout_seconds) as response:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    prefix=f".{output_path.stem}.",
                    suffix=".download",
                    dir=self.update_directory,
                    delete=False,
                ) as handle:
                    temp_path = Path(handle.name)
                    while chunk := response.read(1024 * 1024):
                        downloaded += len(chunk)
                        if downloaded > update.size_bytes or downloaded > MAX_EXECUTABLE_BYTES:
                            raise UpdateServiceError(
                                UpdateErrorCode.DOWNLOAD_FAILED,
                                "O download ultrapassou o tamanho publicado.",
                            )
                        digest.update(chunk)
                        handle.write(chunk)
                        if progress_callback:
                            progress_callback(downloaded, update.size_bytes)
                    handle.flush()
                    os.fsync(handle.fileno())
            download_complete = True
        except UpdateServiceError:
            raise
        except (HTTPError, URLError, OSError, TimeoutError) as exc:
            raise UpdateServiceError(
                UpdateErrorCode.NETWORK_ERROR,
                f"Não foi possível baixar a atualização: {exc}",
            ) from exc
        finally:
            if temp_path is not None and not download_complete:
                temp_path.unlink(missing_ok=True)

        if temp_path is None or downloaded != update.size_bytes:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise UpdateServiceError(
                UpdateErrorCode.DOWNLOAD_FAILED,
                "O download terminou com tamanho diferente do publicado.",
            )
        if digest.hexdigest().upper() != update.expected_sha256:
            temp_path.unlink(missing_ok=True)
            raise UpdateServiceError(
                UpdateErrorCode.INTEGRITY_FAILED,
                "O SHA-256 do download não corresponde ao manifesto.",
            )
        with temp_path.open("rb") as handle:
            if handle.read(2) != b"MZ":
                temp_path.unlink(missing_ok=True)
                raise UpdateServiceError(
                    UpdateErrorCode.INTEGRITY_FAILED,
                    "O arquivo baixado não é um executável Windows válido.",
                )
        os.replace(temp_path, output_path)
        return output_path

    def _read_json(self, url: str) -> dict[str, object]:
        self._validate_github_url(url)
        try:
            request = self._request(url, accept="application/vnd.github+json")
            with self._opener(request, self.timeout_seconds) as response:
                payload = response.read(MAX_JSON_BYTES + 1)
        except (HTTPError, URLError, OSError, TimeoutError) as exc:
            raise UpdateServiceError(
                UpdateErrorCode.NETWORK_ERROR,
                f"Não foi possível consultar o GitHub: {exc}",
            ) from exc
        if len(payload) > MAX_JSON_BYTES:
            raise UpdateServiceError(
                UpdateErrorCode.INVALID_RESPONSE, "A resposta do GitHub excedeu o limite."
            )
        try:
            parsed = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UpdateServiceError(
                UpdateErrorCode.INVALID_RESPONSE, "O GitHub retornou JSON inválido."
            ) from exc
        if not isinstance(parsed, dict):
            raise UpdateServiceError(
                UpdateErrorCode.INVALID_RESPONSE, "O GitHub retornou um formato inesperado."
            )
        return cast(dict[str, object], parsed)

    def _request(self, url: str, *, accept: str) -> Request:
        return Request(
            url,
            headers={
                "Accept": accept,
                "User-Agent": f"V2E-PDF-Studio/{self.current_version}",
                "X-GitHub-Api-Version": "2026-03-10",
            },
            method="GET",
        )

    @staticmethod
    def _find_asset(assets: list[object], name: str) -> dict[str, object]:
        for asset in assets:
            if isinstance(asset, dict) and asset.get("name") == name:
                return cast(dict[str, object], asset)
        raise UpdateServiceError(
            UpdateErrorCode.RELEASE_INCOMPLETE,
            f"A release não contém o arquivo obrigatório: {name}",
        )

    @staticmethod
    def _asset_url(asset: dict[str, object]) -> str:
        url = asset.get("browser_download_url")
        if not isinstance(url, str):
            raise UpdateServiceError(
                UpdateErrorCode.INVALID_RESPONSE, "A release contém uma URL inválida."
            )
        UpdateService._validate_github_url(url)
        return url

    @staticmethod
    def _normalize_version(value: str) -> str:
        match = VERSION_PATTERN.fullmatch(value.strip())
        if match is None:
            raise UpdateServiceError(UpdateErrorCode.INVALID_RESPONSE, f"Versão inválida: {value}")
        return ".".join(match.groups())

    @staticmethod
    def _version_tuple(value: str) -> tuple[int, int, int]:
        normalized = UpdateService._normalize_version(value)
        major, minor, patch = normalized.split(".")
        return int(major), int(minor), int(patch)

    @staticmethod
    def _validate_github_url(url: str) -> None:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").lower()
        allowed = hostname in {"api.github.com", "github.com"} or hostname.endswith(
            ".githubusercontent.com"
        )
        if parsed.scheme != "https" or not allowed or parsed.username or parsed.password:
            raise UpdateServiceError(
                UpdateErrorCode.INVALID_RESPONSE,
                "A atualização apontou para uma origem não autorizada.",
            )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest().upper()
