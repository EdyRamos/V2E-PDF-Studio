import os
from pathlib import Path

import fitz
import pytest

from v2e_pdf_compressor.application.eprotocol import (
    ArchiveEntry,
    ArchiveRequest,
    EProtocolError,
    EProtocolRequest,
    EProtocolService,
    natural_key,
)
from v2e_pdf_compressor.application.service import PdfCompressionService
from v2e_pdf_compressor.infra.ghostscript import GhostscriptLocator
from v2e_pdf_compressor.ui.eprotocol_dialog import EProtocolDialog


def test_natural_sort() -> None:
    assert sorted([Path("Envelope10.pdf"), Path("Envelope2.pdf")], key=natural_key) == [
        Path("Envelope2.pdf"),
        Path("Envelope10.pdf"),
    ]


def test_prepares_ordered_pdfs_without_modifying_sources(make_pdf, tmp_path: Path) -> None:
    first = make_pdf("first.pdf", 2)
    second = make_pdf("second.pdf", 1)
    before = [first.read_bytes(), second.read_bytes()]
    output = tmp_path / "output"
    output.mkdir()
    service = EProtocolService(PdfCompressionService(GhostscriptLocator()))
    result = service.prepare_pdfs(
        EProtocolRequest((first, second), output, "Processo", profile=None)
    )
    assert len(result.parts) == 1
    with fitz.open(result.parts[0]) as document:
        assert document.page_count == 3
        assert len(document.get_toc()) == 2
    assert [first.read_bytes(), second.read_bytes()] == before
    assert (result.directory / "manifesto.json").exists()


@pytest.mark.skipif(os.name != "nt", reason="Ghostscript incorporado somente para Windows")
def test_pdf_preparation_uses_real_ghostscript(make_pdf, tmp_path: Path) -> None:
    source = make_pdf("texto.pdf", 2)
    output = tmp_path / "output"
    output.mkdir()
    project = Path(__file__).resolve().parents[1]
    service = EProtocolService(
        PdfCompressionService(
            GhostscriptLocator(search_roots=[project], include_default_roots=False)
        )
    )
    result = service.prepare_pdfs(EProtocolRequest((source,), output, "Processo"))
    with fitz.open(result.parts[0]) as document:
        assert document.page_count == 2
        assert "V2E page 1" in document[0].get_text()
    assert (result.directory / "relatorio.html").is_file()
    assert not list(result.directory.glob("*.tmp.pdf"))


@pytest.mark.skipif(os.name != "nt", reason="Ghostscript incorporado somente para Windows")
def test_existing_ocr_text_remains_searchable_after_preparation(tmp_path: Path) -> None:
    source = tmp_path / "ocr.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.draw_rect(fitz.Rect(40, 40, 400, 200), color=(0, 0, 0), fill=(0.9, 0.9, 0.9))
        page.insert_text((50, 80), "SCANNED CONTENT", fontsize=15)
        page.insert_text((50, 120), "OCR hidden text 123", render_mode=3)
        document.save(source)
    output = tmp_path / "output"
    output.mkdir()
    project = Path(__file__).resolve().parents[1]
    service = EProtocolService(
        PdfCompressionService(
            GhostscriptLocator(search_roots=[project], include_default_roots=False)
        )
    )
    result = service.prepare_pdfs(EProtocolRequest((source,), output, "Processo"))
    with fitz.open(result.parts[0]) as document:
        assert "OCR hidden text 123" in document[0].get_text()


def test_bad_pdf_does_not_publish_partial_set(make_pdf, tmp_path: Path) -> None:
    valid = make_pdf("valid.pdf")
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    output = tmp_path / "output"
    output.mkdir()
    service = EProtocolService(PdfCompressionService(GhostscriptLocator()))
    with pytest.raises(EProtocolError):
        service.prepare_pdfs(EProtocolRequest((valid, bad), output, "Processo", profile=None))
    assert list(output.iterdir()) == []


def test_form_needs_consent_and_is_flattened(tmp_path: Path) -> None:
    source = tmp_path / "form.pdf"
    with fitz.open() as document:
        page = document.new_page()
        widget = fitz.Widget()
        widget.field_name = "name"
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.field_value = "Exemplo"
        widget.rect = fitz.Rect(40, 40, 200, 70)
        page.add_widget(widget)
        document.save(source)
    output = tmp_path / "output"
    output.mkdir()
    service = EProtocolService(PdfCompressionService(GhostscriptLocator()))
    with pytest.raises(EProtocolError, match="formulário"):
        service.prepare_pdfs(EProtocolRequest((source,), output, "Processo", profile=None))
    result = service.prepare_pdfs(
        EProtocolRequest((source,), output, "Processo", profile=None, allow_forms=True)
    )
    with fitz.open(result.parts[0]) as document:
        assert list(document[0].widgets() or []) == []
        assert "Exemplo" in document[0].get_text()
    assert not list(result.directory.glob("*.tmp.pdf"))


def test_large_document_is_split_using_actual_output_size(tmp_path: Path) -> None:
    source = tmp_path / "large.pdf"
    with fitz.open() as document:
        for index in range(2):
            page = document.new_page()
            image = fitz.Pixmap(fitz.csRGB, 1050, 1050, os.urandom(1050 * 1050 * 3), False)
            page.insert_image(page.rect, pixmap=image)
            page.insert_text((50, 50), f"Page {index + 1}")
        document.save(source)
    output = tmp_path / "output"
    output.mkdir()
    service = EProtocolService(PdfCompressionService(GhostscriptLocator()))
    result = service.prepare_pdfs(
        EProtocolRequest((source,), output, "Processo", max_bytes=5_000_000, profile=None)
    )
    assert len(result.parts) == 2
    assert all(part.stat().st_size <= 5_000_000 * 88 // 90 for part in result.parts)
    for index, part in enumerate(result.parts):
        with fitz.open(part) as document:
            assert document.page_count == 1
            assert f"Page {index + 1}" in document[0].get_text()


def test_single_oversized_page_fails_without_publishing(tmp_path: Path) -> None:
    source = tmp_path / "oversized.pdf"
    with fitz.open() as document:
        page = document.new_page()
        image = fitz.Pixmap(fitz.csRGB, 1350, 1350, os.urandom(1350 * 1350 * 3), False)
        page.insert_image(page.rect, pixmap=image)
        document.save(source)
    output = tmp_path / "output"
    output.mkdir()
    service = EProtocolService(PdfCompressionService(GhostscriptLocator()))
    with pytest.raises(EProtocolError, match="Página 1"):
        service.prepare_pdfs(
            EProtocolRequest((source,), output, "Processo", max_bytes=5_000_000, profile=None)
        )
    assert list(output.iterdir()) == []


def test_cancel_cleans_staging_and_preserves_input(make_pdf, tmp_path: Path) -> None:
    source = make_pdf("cancel.pdf", 2)
    original = source.read_bytes()
    output = tmp_path / "output"
    output.mkdir()
    service = EProtocolService(PdfCompressionService(GhostscriptLocator()))

    def cancel_on_progress(_message: str) -> None:
        service.cancel()

    with pytest.raises(EProtocolError, match="cancelada"):
        service.prepare_pdfs(
            EProtocolRequest((source,), output, "Processo", profile=None), cancel_on_progress
        )
    assert list(output.iterdir()) == []
    assert source.read_bytes() == original


def test_archive_round_trip_with_split_parts(tmp_path: Path) -> None:
    source = tmp_path / "original.bin"
    source.write_bytes(os.urandom(5_500_000))
    output = tmp_path / "output"
    output.mkdir()
    service = EProtocolService(PdfCompressionService(GhostscriptLocator()))
    result = service.prepare_archive(
        ArchiveRequest((ArchiveEntry(source, "pasta/original.bin"),), output, "Processo", 5_000_000)
    )
    assert len(result.parts) == 2
    assert all(part.stat().st_size <= 5_000_000 for part in result.parts)
    assert result.parts[0].name == "Processo.zip.001"
    assert (result.directory / "manifesto.json").exists()


def test_archive_rejects_collisions_without_partial_output(tmp_path: Path) -> None:
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    service = EProtocolService(PdfCompressionService(GhostscriptLocator()))
    with pytest.raises(EProtocolError, match="duplicados"):
        service.prepare_archive(
            ArchiveRequest(
                (ArchiveEntry(first, "Doc.txt"), ArchiveEntry(second, "doc.txt")),
                output,
                "Processo",
            )
        )
    assert list(output.iterdir()) == []


def test_archive_rejects_linked_input(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "arquivo.txt"
    source.write_text("content", encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    service = EProtocolService(PdfCompressionService(GhostscriptLocator()))
    monkeypatch.setattr("v2e_pdf_compressor.application.eprotocol.is_link_path", lambda _p: True)
    with pytest.raises(EProtocolError, match="link"):
        service.prepare_archive(ArchiveRequest((ArchiveEntry(source, source.name),), output, "X"))
    assert list(output.iterdir()) == []


def test_small_archive_is_a_single_valid_zip(tmp_path: Path) -> None:
    source = tmp_path / "arquivo.txt"
    source.write_text("conteúdo preservado", encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    service = EProtocolService(PdfCompressionService(GhostscriptLocator()))
    result = service.prepare_archive(
        ArchiveRequest((ArchiveEntry(source, "arquivo.txt"),), output, "Processo")
    )
    assert [part.name for part in result.parts] == ["Processo.zip"]


def test_archive_preserves_empty_folder(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    service = EProtocolService(PdfCompressionService(GhostscriptLocator()))
    result = service.prepare_archive(
        ArchiveRequest((ArchiveEntry(empty, "folder/empty"),), output, "Processo")
    )
    import zipfile

    with zipfile.ZipFile(result.parts[0]) as archive:
        assert "folder/empty/" in archive.namelist()


def test_archive_cancel_leaves_no_result(tmp_path: Path) -> None:
    source = tmp_path / "original.bin"
    source.write_bytes(os.urandom(1_000_000))
    output = tmp_path / "output"
    output.mkdir()
    service = EProtocolService(PdfCompressionService(GhostscriptLocator()))

    def stop_when_packaging(message: str) -> None:
        if message.startswith("Criando pacote"):
            service.cancel()

    with pytest.raises(EProtocolError, match="cancelada"):
        service.prepare_archive(
            ArchiveRequest((ArchiveEntry(source, source.name),), output, "Processo"),
            stop_when_packaging,
        )
    assert list(output.iterdir()) == []


def test_ui_runs_worker_in_separate_process(make_pdf, tmp_path: Path, qtbot, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    source = make_pdf("source.pdf", 2)
    output = tmp_path / "output"
    output.mkdir()
    dialog = EProtocolDialog()
    qtbot.addWidget(dialog)
    dialog.add_paths([source])
    dialog.destination = str(output)
    dialog.profile.setCurrentIndex(2)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    dialog.start()
    qtbot.waitUntil(lambda: dialog.session is None, timeout=30000)
    assert dialog.open_button.isEnabled(), dialog.state.text()
    assert list(Path(dialog.result_dir).glob("*.pdf"))


def test_ui_skips_non_pdf_and_reports_it(make_pdf, tmp_path: Path, qtbot, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    source = make_pdf("source.pdf", 1)
    ignored = tmp_path / "notes.txt"
    ignored.write_text("not a PDF", encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    dialog = EProtocolDialog()
    qtbot.addWidget(dialog)
    dialog.add_paths([ignored, source])
    dialog.destination = str(output)
    dialog.profile.setCurrentIndex(2)
    monkeypatch.setattr(QMessageBox, "information", lambda *args: QMessageBox.StandardButton.Ok)
    dialog.start()
    qtbot.waitUntil(lambda: dialog.session is None, timeout=30000)
    assert dialog.open_button.isEnabled(), dialog.state.text()
    assert "notes.txt" in dialog.state.text()
