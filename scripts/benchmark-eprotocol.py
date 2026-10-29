"""Generate a large synthetic corpus and exercise PDF and archive preparation."""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v2e_pdf_compressor.application.eprotocol import (  # noqa: E402
    ArchiveEntry,
    ArchiveRequest,
    EProtocolRequest,
    EProtocolService,
)
from v2e_pdf_compressor.application.service import PdfCompressionService  # noqa: E402
from v2e_pdf_compressor.infra.ghostscript import GhostscriptLocator  # noqa: E402


def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="v2e-scale-") as temp:
        root = Path(temp)
        inputs = root / "inputs"
        outputs = root / "outputs"
        inputs.mkdir()
        outputs.mkdir()
        files = []
        for i in range(count):
            path = inputs / f"envelope{i:02}.pdf"
            with fitz.open() as doc:
                page = doc.new_page()
                pix = fitz.Pixmap(fitz.csRGB, 4200, 4200, os.urandom(4200 * 4200 * 3), False)
                page.insert_image(page.rect, pixmap=pix)
                page.insert_text((50, 50), f"Synthetic page {i}")
                doc.save(path)
            files.append(path)
            if i % 5 == 0:
                print(f"Created {i + 1}/{count} PDFs", flush=True)
        size = sum(path.stat().st_size for path in files)
        print(
            f"Input bytes: {size}; generation seconds: {time.monotonic() - start:.1f}", flush=True
        )
        service = EProtocolService(PdfCompressionService(GhostscriptLocator()))
        start_pdf = time.monotonic()
        result = service.prepare_pdfs(
            EProtocolRequest(tuple(files), outputs, "Volumes", profile=None),
            lambda message: print(message, flush=True),
        )
        print(
            f"PDF parts: {len(result.parts)}; seconds: {time.monotonic() - start_pdf:.1f}",
            flush=True,
        )
        start_zip = time.monotonic()
        package = service.prepare_archive(
            ArchiveRequest(tuple(ArchiveEntry(p, p.name) for p in files), outputs, "Pacote"),
            lambda message: print(message, flush=True),
        )
        print(
            f"ZIP parts: {len(package.parts)}; seconds: {time.monotonic() - start_zip:.1f}",
            flush=True,
        )
        print(
            f"Output bytes: {sum(p.stat().st_size for p in result.parts + package.parts)}",
            flush=True,
        )


if __name__ == "__main__":
    main()
