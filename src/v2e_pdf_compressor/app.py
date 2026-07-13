from __future__ import annotations

import argparse
import importlib.metadata
import json
import logging
import os
import platform
import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from . import __version__
from .application import PdfCompressionService, PdfEditService
from .config import (
    APP_DATA_DIR,
    APP_LOG_DIR,
    SettingsRepository,
    ensure_app_dirs,
    load_update_configuration,
)
from .domain import (
    CompressionJob,
    CompressionProfile,
    CompressionStatus,
    ExportOptions,
)
from .infra import configure_logging
from .infra.ghostscript import GhostscriptLocator
from .ui import MainWindow


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="v2e-pdf-compressor")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Executa verificacoes de ambiente e finaliza sem abrir UI.",
    )
    parser.add_argument(
        "--full-smoke-test",
        action="store_true",
        help="Valida UI offscreen, edicao PDF e compressao Ghostscript sem abrir janela.",
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Mostra ambiente, dependencias e caminhos sem acessar documentos PDF.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser.parse_args(argv)


def _run_smoke_test(logger: logging.Logger) -> int:
    settings_repo = SettingsRepository()
    settings = settings_repo.load()
    locator = GhostscriptLocator()
    payload = {
        "overwrite_policy": settings.overwrite_policy,
        "default_profile": settings.default_profile,
        "settings_file": str(settings_repo.settings_file),
    }
    try:
        payload["ghostscript_executable"] = str(locator.resolve_executable())
        payload["ghostscript_available"] = True
    except FileNotFoundError as exc:
        logger.warning("Ghostscript nao encontrado no smoke-test: %s", exc)
        payload["ghostscript_available"] = False
        payload["ghostscript_error"] = str(exc)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def _run_diagnostics() -> int:
    ensure_app_dirs()
    probe = APP_DATA_DIR / ".write-probe"
    writable = False
    try:
        probe.write_text("ok", encoding="utf-8")
        writable = True
    except OSError:
        pass
    finally:
        probe.unlink(missing_ok=True)

    locator = GhostscriptLocator()
    ghostscript_path: str | None = None
    ghostscript_error: str | None = None
    try:
        ghostscript_path = str(locator.resolve_executable())
    except (FileNotFoundError, RuntimeError) as exc:
        ghostscript_error = str(exc)
    update_configuration = load_update_configuration()
    payload = {
        "app_version": __version__,
        "python": platform.python_version(),
        "python_executable": sys.executable,
        "windows": platform.platform(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "packages": {
            "PySide6": _package_version("PySide6"),
            "PyMuPDF": _package_version("PyMuPDF"),
            "PyInstaller": _package_version("PyInstaller"),
        },
        "app_data_dir": str(APP_DATA_DIR),
        "log_dir": str(APP_LOG_DIR),
        "app_data_writable": writable,
        "ghostscript_executable": ghostscript_path,
        "ghostscript_error": ghostscript_error,
        "network": {
            "automatic": False,
            "manual_update_check": update_configuration.configured,
            "provider": update_configuration.provider,
            "repository": update_configuration.repository,
            "configuration_error": update_configuration.error,
        },
        "telemetry": False,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if writable and ghostscript_path else 1


def _run_full_smoke_test(logger: logging.Logger) -> int:
    import fitz

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    locator = GhostscriptLocator()
    edit_service = PdfEditService()
    compression_service = PdfCompressionService(
        locator=locator, logger=logging.getLogger("v2e.service")
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        source_path = temp_root / "full_smoke_source.pdf"
        edited_path = temp_root / "full_smoke_edited.pdf"
        compressed_path = temp_root / "full_smoke_compressed.pdf"

        document = fitz.open()
        for page_number in range(2):
            page = document.new_page(width=300, height=300)
            page.insert_text((40, 120), f"V2E full smoke {page_number + 1}")
        document.save(source_path)
        document.close()

        qt_app = QApplication.instance() or QApplication([])
        window = MainWindow(
            edit_service=edit_service,
            compression_service=compression_service,
            settings_repository=SettingsRepository(),
        )
        window.load_pdf(source_path)
        if window.session is None or window.thumbnail_list.count() != 2:
            raise RuntimeError("UI nao carregou miniatura do PDF de smoke-test.")
        if window.preview.pixmap().isNull():
            raise RuntimeError("UI nao renderizou preview do PDF de smoke-test.")

        original_order = [page.page_id for page in window.session.pages]
        moved_item = window.thumbnail_list.takeItem(1)
        window.thumbnail_list.insertItem(0, moved_item)
        window.thumbnail_list.setCurrentRow(0)
        window.sync_session_order_from_ui()
        reordered = [page.page_id for page in window.session.pages]
        if reordered != [original_order[1], original_order[0]]:
            raise RuntimeError("Reordenacao de paginas falhou no smoke-test.")

        edit_service.add_blank_page(window.session)
        edit_service.export_document(
            window.session, ExportOptions(output_path=edited_path, overwrite=True)
        )
        job = CompressionJob(
            input_path=edited_path,
            output_path=compressed_path,
            profile=CompressionProfile.EBOOK,
            overwrite=True,
            optimize=True,
        )
        result = compression_service.compress(job)
        if result.status != CompressionStatus.SUCCESS:
            raise RuntimeError(
                f"Compressao falhou no smoke-test: {result.error_code} {result.error_detail}"
            )

        payload = {
            "ghostscript_executable": str(locator.resolve_executable()),
            "compression_status": result.status.value,
            "edited_pdf_exists": edited_path.exists(),
            "session_page_count": window.session.page_count,
            "page_reorder_ok": True,
            "thumbnail_count": window.thumbnail_list.count(),
            "ui_loaded": True,
        }
        print(json.dumps(payload, ensure_ascii=False))
        qt_app.processEvents()

    logger.info("Full smoke-test concluido com sucesso.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    configure_logging()
    logger = logging.getLogger("v2e")
    if args.smoke_test:
        return _run_smoke_test(logger)
    if args.full_smoke_test:
        return _run_full_smoke_test(logger)
    if args.diagnostics:
        return _run_diagnostics()

    settings_repo = SettingsRepository()
    locator = GhostscriptLocator()
    service = PdfCompressionService(locator=locator, logger=logging.getLogger("v2e.service"))
    qt_app = QApplication.instance() or QApplication([])
    window = MainWindow(
        edit_service=PdfEditService(),
        compression_service=service,
        settings_repository=settings_repo,
    )
    window.show()
    qt_app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
