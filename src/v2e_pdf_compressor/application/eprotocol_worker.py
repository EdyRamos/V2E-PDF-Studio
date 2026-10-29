"""Process boundary for eProtocolo operations."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from ..domain import CompressionProfile
from ..infra.ghostscript import GhostscriptLocator
from .eprotocol import ArchiveEntry, ArchiveRequest, EProtocolRequest, EProtocolService
from .service import PdfCompressionService


def run_worker(request_path: Path, status_path: Path, cancel_path: Path) -> int:
    def report(data: dict[str, object]) -> None:
        temporary = status_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        for attempt in range(50):
            try:
                os.replace(temporary, status_path)
                break
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(0.02)

    service = EProtocolService(PdfCompressionService(GhostscriptLocator()))
    finished = threading.Event()

    def watch_cancel() -> None:
        while not finished.wait(0.2):
            if cancel_path.exists():
                service.cancel()
                break

    watcher = threading.Thread(target=watch_cancel, daemon=True)
    watcher.start()
    try:
        payload = json.loads(request_path.read_text(encoding="utf-8"))

        def progress(message: str) -> None:
            report({"status": "working", "message": message})

        if payload["mode"] == "inspect":
            progress("Analisando PDFs...")
            items = service.inspect_pdfs(tuple(Path(e["path"]) for e in payload["entries"]))
            report(
                {
                    "status": "inspected",
                    "items": [
                        {
                            "path": str(item.path),
                            "pages": item.pages,
                            "signed": item.signed,
                            "forms": item.forms,
                        }
                        for item in items
                    ],
                }
            )
            return 0
        if payload["mode"] == "archive":
            result = service.prepare_archive(
                ArchiveRequest(
                    tuple(ArchiveEntry(Path(e["path"]), e["relative"]) for e in payload["entries"]),
                    Path(payload["destination"]),
                    payload["base_name"],
                    payload["max_bytes"],
                ),
                progress,
            )
        else:
            profile = payload["profile"]
            result = service.prepare_pdfs(
                EProtocolRequest(
                    tuple(Path(e["path"]) for e in payload["entries"]),
                    Path(payload["destination"]),
                    payload["base_name"],
                    payload["max_bytes"],
                    CompressionProfile(profile) if profile else None,
                    payload.get("allow_signed", False),
                    payload.get("allow_forms", False),
                ),
                progress,
            )
        report(
            {
                "status": "success",
                "directory": str(result.directory),
                "parts": [str(p) for p in result.parts],
                "warnings": list(result.warnings),
            }
        )
        return 0
    except Exception as exc:
        report({"status": "error", "message": str(exc)})
        return 1
    finally:
        finished.set()
