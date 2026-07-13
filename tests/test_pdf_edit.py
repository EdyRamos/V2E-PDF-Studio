from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from v2e_pdf_compressor.application.pdf_edit import (
    PdfEditError,
    PdfEditService,
    PdfPasswordRequiredError,
)
from v2e_pdf_compressor.domain import ExportOptions


def test_open_reorder_insert_blank_remove_and_export(make_pdf, tmp_path: Path) -> None:
    service = PdfEditService()
    source = make_pdf("origem ünicode.pdf", 3)
    inserted_source = make_pdf("adicional.pdf", 1)
    session = service.open_document(source)

    original_ids = [page.page_id for page in session.pages]
    service.reorder_by_page_ids(session, list(reversed(original_ids)))
    inserted_ids = service.insert_pdf(session, inserted_source, session.pages[0].page_id)
    service.add_blank_page(session, inserted_ids[0])
    service.remove_pages(session, {session.pages[-1].page_id})

    output = tmp_path / "saída final.pdf"
    service.export_document(session, ExportOptions(output, overwrite=False))
    with fitz.open(output) as result:
        assert result.page_count == 4
    assert session.modified is False
    assert session.original_path == output.resolve()


def test_split_selected_and_ranges(make_pdf, tmp_path: Path) -> None:
    service = PdfEditService()
    session = service.open_document(make_pdf(pages=5))
    selected = {session.pages[1].page_id, session.pages[3].page_id}
    selected_output = service.split_selected(session, selected, tmp_path / "selected.pdf")
    outputs = service.split_ranges(session, "1-2,5", tmp_path, "partes")

    with fitz.open(selected_output) as document:
        assert document.page_count == 2
    page_counts = []
    for path in outputs:
        with fitz.open(path) as document:
            page_counts.append(document.page_count)
    assert page_counts == [2, 1]


def test_atomic_export_preserves_existing_file_when_validation_fails(
    make_pdf, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = PdfEditService()
    session = service.open_document(make_pdf())
    output = tmp_path / "existing.pdf"
    original = b"ORIGINAL-CONTENT"
    output.write_bytes(original)

    def fail_validation(path: Path, expected_pages: int) -> None:
        raise PdfEditError("forced validation failure")

    monkeypatch.setattr(service, "_validate_generated_pdf", fail_validation)
    with pytest.raises(PdfEditError):
        service.export_document(session, ExportOptions(output, overwrite=True))

    assert output.read_bytes() == original
    assert not list(tmp_path.glob(".*.tmp.pdf"))


def test_password_corrupt_extension_and_missing_inputs(make_pdf, tmp_path: Path) -> None:
    service = PdfEditService()
    with pytest.raises(PdfPasswordRequiredError):
        service.open_document(make_pdf("protected.pdf", password="secret"))
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"not a pdf")
    with pytest.raises(fitz.FileDataError):
        service.open_document(corrupt)
    wrong = tmp_path / "file.txt"
    wrong.write_text("x", encoding="utf-8")
    with pytest.raises(PdfEditError):
        service.open_document(wrong)
    with pytest.raises(FileNotFoundError):
        service.open_document(tmp_path / "missing.pdf")
