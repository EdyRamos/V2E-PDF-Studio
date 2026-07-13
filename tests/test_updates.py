from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from urllib.request import Request

import pytest

from v2e_pdf_compressor.application.updates import (
    RELEASE_ASSET_NAME,
    RELEASE_MANIFEST_NAME,
    UpdateErrorCode,
    UpdateInfo,
    UpdateService,
    UpdateServiceError,
)
from v2e_pdf_compressor.config.updates import (
    UpdateConfiguration,
    load_update_configuration,
)


class FakeOpener:
    def __init__(self, responses: dict[str, bytes]) -> None:
        self.responses = responses
        self.requests: list[Request] = []

    def __call__(self, request: Request, timeout: float) -> io.BytesIO:
        del timeout
        self.requests.append(request)
        return io.BytesIO(self.responses[request.full_url])


def _release_payload(executable: bytes, *, version: str = "0.3.0") -> tuple[dict, dict]:
    sha256 = hashlib.sha256(executable).hexdigest().upper()
    executable_url = (
        f"https://github.com/example/v2e/releases/download/v{version}/{RELEASE_ASSET_NAME}"
    )
    manifest_url = (
        f"https://github.com/example/v2e/releases/download/v{version}/{RELEASE_MANIFEST_NAME}"
    )
    release = {
        "tag_name": f"v{version}",
        "html_url": f"https://github.com/example/v2e/releases/tag/v{version}",
        "body": "Correções e melhorias.",
        "assets": [
            {
                "name": RELEASE_ASSET_NAME,
                "browser_download_url": executable_url,
                "size": len(executable),
                "digest": f"sha256:{sha256.lower()}",
            },
            {
                "name": RELEASE_MANIFEST_NAME,
                "browser_download_url": manifest_url,
                "size": 100,
            },
        ],
    }
    manifest = {
        "version": version,
        "artifact": {
            "name": RELEASE_ASSET_NAME,
            "size": len(executable),
            "sha256": sha256,
        },
    }
    return release, manifest


def _service(
    tmp_path: Path,
    executable: bytes = b"MZportable-executable",
    *,
    version: str = "0.3.0",
) -> tuple[UpdateService, FakeOpener, dict, dict]:
    release, manifest = _release_payload(executable, version=version)
    api_url = "https://api.github.com/repos/example/v2e/releases/latest"
    manifest_url = release["assets"][1]["browser_download_url"]
    executable_url = release["assets"][0]["browser_download_url"]
    opener = FakeOpener(
        {
            api_url: json.dumps(release).encode(),
            manifest_url: json.dumps(manifest).encode(),
            executable_url: executable,
        }
    )
    service = UpdateService(
        UpdateConfiguration(repository="example/v2e"),
        "0.2.0",
        update_directory=tmp_path / "updates",
        opener=opener,
    )
    return service, opener, release, manifest


def test_load_update_configuration(tmp_path: Path) -> None:
    path = tmp_path / "update-config.json"
    path.write_text('{"provider":"github","repository":"owner/project"}', encoding="utf-8")

    configuration = load_update_configuration(path)

    assert configuration.configured
    assert configuration.latest_release_api_url.endswith("/owner/project/releases/latest")


@pytest.mark.parametrize(
    "payload",
    ["not json", "[]", '{"provider":"drive"}', '{"repository":"invalid"}'],
)
def test_invalid_update_configuration_is_safe(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "update-config.json"
    path.write_text(payload, encoding="utf-8")

    configuration = load_update_configuration(path)

    assert not configuration.configured
    assert configuration.error


def test_unconfigured_service_never_opens_network(tmp_path: Path) -> None:
    opener = FakeOpener({})
    service = UpdateService(
        UpdateConfiguration(), "0.2.0", update_directory=tmp_path, opener=opener
    )

    with pytest.raises(UpdateServiceError) as caught:
        service.check_for_update()

    assert caught.value.code is UpdateErrorCode.NOT_CONFIGURED
    assert opener.requests == []


def test_check_reports_available_update(tmp_path: Path) -> None:
    service, opener, _release, _manifest = _service(tmp_path)

    result = service.check_for_update()

    assert result.update_available
    assert result.latest_version == "0.3.0"
    assert result.update is not None
    assert (
        result.update.expected_sha256
        == hashlib.sha256(b"MZportable-executable").hexdigest().upper()
    )
    assert len(opener.requests) == 2
    assert opener.requests[0].get_header("User-agent") == "V2E-PDF-Studio/0.2.0"


@pytest.mark.parametrize("version", ["0.2.0", "0.1.9"])
def test_check_reports_no_update_for_same_or_older_release(tmp_path: Path, version: str) -> None:
    service, opener, _release, _manifest = _service(tmp_path, version=version)

    result = service.check_for_update()

    assert not result.update_available
    assert result.update is None
    assert len(opener.requests) == 1


def test_release_must_contain_executable_and_manifest(tmp_path: Path) -> None:
    service, _opener, release, _manifest = _service(tmp_path)
    release["assets"] = []
    service._opener.responses[service.configuration.latest_release_api_url] = json.dumps(  # type: ignore[attr-defined]
        release
    ).encode()

    with pytest.raises(UpdateServiceError) as caught:
        service.check_for_update()

    assert caught.value.code is UpdateErrorCode.RELEASE_INCOMPLETE


def test_manifest_must_match_github_digest(tmp_path: Path) -> None:
    service, opener, release, _manifest = _service(tmp_path)
    release["assets"][0]["digest"] = f"sha256:{'0' * 64}"
    opener.responses[service.configuration.latest_release_api_url] = json.dumps(release).encode()

    with pytest.raises(UpdateServiceError) as caught:
        service.check_for_update()

    assert caught.value.code is UpdateErrorCode.INTEGRITY_FAILED


def test_download_is_verified_and_stored_atomically(tmp_path: Path) -> None:
    executable = b"MZ" + b"portable" * 100
    service, _opener, _release, _manifest = _service(tmp_path, executable)
    result = service.check_for_update()
    progress: list[tuple[int, int]] = []

    output = service.download_update(
        result.update, lambda done, total: progress.append((done, total))
    )  # type: ignore[arg-type]

    assert output.name == "V2E-PDF-Compressor-0.3.0.exe"
    assert output.read_bytes() == executable
    assert progress[-1] == (len(executable), len(executable))
    assert list(output.parent.glob("*.download")) == []


def test_bad_download_hash_is_deleted(tmp_path: Path) -> None:
    service, opener, _release, _manifest = _service(tmp_path)
    result = service.check_for_update()
    assert result.update is not None
    opener.responses[result.update.executable_url] = b"MZ" + b"x" * (result.update.size_bytes - 2)

    with pytest.raises(UpdateServiceError) as caught:
        service.download_update(result.update)

    assert caught.value.code is UpdateErrorCode.INTEGRITY_FAILED
    assert list(service.update_directory.iterdir()) == []


def test_download_rejects_non_github_origin_before_network(tmp_path: Path) -> None:
    opener = FakeOpener({})
    service = UpdateService(
        UpdateConfiguration(repository="example/v2e"),
        "0.2.0",
        update_directory=tmp_path,
        opener=opener,
    )
    update = UpdateInfo("0.3.0", "https://evil.example/app.exe", "0" * 64, 10, "", "")

    with pytest.raises(UpdateServiceError) as caught:
        service.download_update(update)

    assert caught.value.code is UpdateErrorCode.INVALID_RESPONSE
    assert opener.requests == []
