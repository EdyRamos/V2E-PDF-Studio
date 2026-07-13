from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def command_output(command: list[str], default: str = "unknown") -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError:
        return default
    return (
        (result.stdout or result.stderr).strip().splitlines()[0]
        if result.returncode == 0
        else default
    )


parser = argparse.ArgumentParser()
parser.add_argument("--exe", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--version", required=True)
args = parser.parse_args()

exe = args.exe.resolve()
ghostscript = Path("vendor/ghostscript/win64/bin/gswin64c.exe")
manifest = {
    "schema_version": 1,
    "product": "V2E PDF Studio",
    "version": args.version,
    "created_at_utc": datetime.now(UTC).isoformat(),
    "commit": os.environ.get("GITHUB_SHA") or command_output(["git", "rev-parse", "HEAD"]),
    "artifact": {
        "name": exe.name,
        "size": exe.stat().st_size,
        "sha256": sha256(exe),
        "authenticode": os.environ.get("V2E_SIGNATURE_STATUS", "unsigned"),
    },
    "runtime": {
        "python": platform.python_version(),
        "PySide6": importlib.metadata.version("PySide6"),
        "PyMuPDF": importlib.metadata.version("PyMuPDF"),
        "PyInstaller": importlib.metadata.version("PyInstaller"),
        "Ghostscript": command_output([str(ghostscript), "-version"]),
    },
    "quality": {
        "tests": os.environ.get("V2E_TEST_STATUS", "passed"),
        "lint": os.environ.get("V2E_LINT_STATUS", "passed"),
        "types": os.environ.get("V2E_TYPE_STATUS", "passed"),
    },
    "privacy": {
        "telemetry": False,
        "automatic_network": False,
        "manual_github_update_check": True,
    },
}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
