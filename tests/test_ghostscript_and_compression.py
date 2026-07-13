from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import fitz
import pytest

from v2e_pdf_compressor.application.service import (
    PdfCompressionService,
    _percent_reduction,
    build_batch_jobs,
)
from v2e_pdf_compressor.domain import (
    CompressionJob,
    CompressionProfile,
    CompressionStatus,
    ErrorCode,
)
from v2e_pdf_compressor.infra.ghostscript import (
    GhostscriptLocator,
    GhostscriptRuntimeError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def embedded_locator() -> GhostscriptLocator:
    return GhostscriptLocator(search_roots=[PROJECT_ROOT], include_default_roots=False)


def test_locator_validates_embedded_runtime() -> None:
    executable = embedded_locator().resolve_executable()
    assert executable.name == "gswin64c.exe"


def test_locator_rejects_incomplete_embedded_runtime(tmp_path: Path) -> None:
    executable = tmp_path / "vendor" / "ghostscript" / "win64" / "bin" / "gswin64c.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"MZ")
    locator = GhostscriptLocator(search_roots=[tmp_path], include_default_roots=False)
    with pytest.raises(GhostscriptRuntimeError):
        locator.resolve_executable()


def test_batch_job_names_are_unique(make_pdf, tmp_path: Path) -> None:
    first = make_pdf("same.pdf", 1)
    second_dir = tmp_path / "other"
    second_dir.mkdir()
    second = second_dir / "same.pdf"
    second.write_bytes(first.read_bytes())
    outputs = tmp_path / "outputs"
    jobs = build_batch_jobs([first, second], outputs, CompressionProfile.EBOOK, False, True)
    assert jobs[0].output_path.name == "same_comprimido.pdf"
    assert jobs[1].output_path.name == "same_comprimido_2.pdf"


def test_error_mapping_and_math(tmp_path: Path) -> None:
    service = PdfCompressionService(embedded_locator())
    assert _percent_reduction(10, 4) == 60
    assert service._map_subprocess_error("password required") is ErrorCode.PDF_PASSWORD_PROTECTED
    assert service._map_subprocess_error("syntaxerror") is ErrorCode.PDF_CORRUPTED
    assert service._map_subprocess_error("access denied") is ErrorCode.PERMISSION_DENIED
    assert (
        service._map_subprocess_error("gs_init.ps missing") is ErrorCode.GHOSTSCRIPT_RUNTIME_INVALID
    )


@pytest.mark.skipif(os.name != "nt", reason="Ghostscript incorporado e exclusivo do Windows")
@pytest.mark.parametrize("profile", list(CompressionProfile))
def test_real_compression_for_all_profiles(make_pdf, tmp_path: Path, profile) -> None:
    input_path = make_pdf(f"input-{profile.value}.pdf", 2)
    output_path = tmp_path / f"output-{profile.value}.pdf"
    service = PdfCompressionService(embedded_locator(), timeout_seconds=60)
    result = service.compress(
        CompressionJob(input_path, output_path, profile, overwrite=False, optimize=True)
    )
    assert result.status is CompressionStatus.SUCCESS, result.error_detail
    with fitz.open(output_path) as document:
        assert document.page_count == 2


@pytest.mark.skipif(os.name != "nt", reason="Valida encerramento da arvore no Windows")
def test_cancel_terminates_running_process() -> None:
    service = PdfCompressionService(embedded_locator(), timeout_seconds=30)
    result_holder: list[object] = []

    def run() -> None:
        result_holder.append(
            service._run_process(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                dict(os.environ),
                creationflags=0,
            )
        )

    thread = threading.Thread(target=run)
    thread.start()
    deadline = time.monotonic() + 5
    while service._active_process is None and time.monotonic() < deadline:
        time.sleep(0.02)
    service.cancel()
    thread.join(timeout=8)
    assert not thread.is_alive()
    assert result_holder == [None]
