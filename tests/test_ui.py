from __future__ import annotations

import logging
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from v2e_pdf_compressor.application import (
    PdfCompressionService,
    PdfEditService,
    UpdateCheckResult,
)
from v2e_pdf_compressor.config import SettingsRepository, UpdateConfiguration
from v2e_pdf_compressor.domain import CompressionProfile
from v2e_pdf_compressor.infra.ghostscript import GhostscriptLocator
from v2e_pdf_compressor.ui import MainWindow


@pytest.fixture
def window(qtbot, tmp_path: Path):
    project_root = Path(__file__).resolve().parents[1]
    widget = MainWindow(
        edit_service=PdfEditService(),
        compression_service=PdfCompressionService(
            GhostscriptLocator(search_roots=[project_root], include_default_roots=False),
            logger=logging.getLogger("test.ui"),
        ),
        settings_repository=SettingsRepository(tmp_path / "settings.json"),
    )

    def discard_test_changes(target) -> None:
        if target.session is not None:
            target.session.modified = False

    qtbot.addWidget(widget, before_close_func=discard_test_changes)
    return widget


def test_all_tool_modes_are_selectable(window) -> None:
    for key, expected_index in {"organize": 0, "compress": 1, "batch": 2, "split": 3}.items():
        window.set_active_tool(key)
        assert window.tool_stack.currentIndex() == expected_index


def test_compression_profile_selection_changes_and_persists(window) -> None:
    window.set_active_tool("compress")
    window.profile_combo.setCurrentIndex(0)

    assert window.profile_combo.currentData() == CompressionProfile.SCREEN.value
    assert window.batch_profile_combo.currentData() == CompressionProfile.SCREEN.value
    assert window.settings.default_profile == CompressionProfile.SCREEN.value
    assert window.settings_repository.load().default_profile == CompressionProfile.SCREEN.value

    window.set_active_tool("batch")
    window.batch_profile_combo.setCurrentIndex(2)

    assert window.batch_profile_combo.currentData() == CompressionProfile.PRINTER.value
    assert window.profile_combo.currentData() == CompressionProfile.PRINTER.value
    assert window.settings.default_profile == CompressionProfile.PRINTER.value


def test_modern_controls_have_explicit_styles(window) -> None:
    style = window.styleSheet()
    assert "QCheckBox#optionCheck::indicator" in style
    assert "QComboBox#profileCombo::drop-down" in style


def test_update_check_is_only_started_by_user_action(
    window, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeUpdateService:
        configuration = UpdateConfiguration(repository="example/v2e")

        def __init__(self) -> None:
            self.calls = 0

        def check_for_update(self) -> UpdateCheckResult:
            self.calls += 1
            return UpdateCheckResult("0.3.0", "0.3.0", False)

    service = FakeUpdateService()
    window.update_service = service
    messages: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, _title, message: messages.append(message),
    )

    qtbot.wait(20)
    assert service.calls == 0

    window.update_button.click()
    qtbot.waitUntil(lambda: bool(messages), timeout=2000)

    assert service.calls == 1
    assert window.update_button.isEnabled()
    assert window.update_button.text() == "Atualizações"


def test_stale_update_callbacks_are_ignored(window, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(window, "_on_update_failed", calls.append)
    window._update_generation = 4

    window._dispatch_update_failed(3, "antiga")
    window._closing = True
    window._dispatch_update_failed(4, "fechando")

    assert calls == []


def test_workspace_layout_does_not_overlap_at_supported_sizes(window, qtbot) -> None:
    window.show()
    window.set_active_tool("compress")
    window._append_log("Teste de atividade")
    for width, height in ((1120, 700), (1360, 820), (1536, 864)):
        window.resize(width, height)
        window.set_active_tool("compress")
        qtbot.wait(20)

        assert window.tools_scroll.horizontalScrollBar().maximum() == 0
        assert window.tool_stack.parentWidget() is window.activity_panel.parentWidget()
        assert window.tool_stack.geometry().bottom() < window.activity_panel.geometry().top()
        assert window.profile_combo.height() >= 38
        assert window.compress_import_button.height() >= 40

    window.resize(1120, 700)
    qtbot.wait(20)
    assert window.brand_byline.isHidden()
    window.resize(1360, 820)
    qtbot.wait(20)
    assert not window.brand_byline.isHidden()


def test_load_select_zoom_reorder_and_temp_cleanup(window, make_pdf, qtbot) -> None:
    window.load_pdf(make_pdf(pages=2))
    assert window.session is not None
    assert window.thumbnail_list.count() == 2
    qtbot.waitUntil(lambda: not window.preview.pixmap().isNull(), timeout=3000)
    assert not window.preview.pixmap().isNull()
    initial_zoom = window.zoom
    window.zoom_in()
    assert window.zoom > initial_zoom
    window.thumbnail_list.selectAll()
    assert len(window._selected_page_ids()) == 2

    moved = window.thumbnail_list.takeItem(1)
    window.thumbnail_list.insertItem(0, moved)
    window.sync_session_order_from_ui()
    assert window.session.modified

    temp_path = window._materialize_current_pdf()
    assert temp_path.exists()
    window._cleanup_temporary_paths()
    assert not temp_path.exists()


def test_thumbnail_workers_fill_icons_and_cache(window, make_pdf, qtbot) -> None:
    window.load_pdf(make_pdf(pages=2))

    qtbot.waitUntil(
        lambda: all(
            not window.thumbnail_list.item(row).icon().isNull()
            for row in range(window.thumbnail_list.count())
        ),
        timeout=3000,
    )

    assert len(window._thumb_cache) == 2


def test_preview_refresh_is_debounced(window, make_pdf, qtbot, monkeypatch) -> None:
    window.load_pdf(make_pdf(pages=1))
    qtbot.waitUntil(lambda: not window.preview.pixmap().isNull(), timeout=3000)
    window._preview_cache.clear()
    calls: list[float] = []
    original_render = window.edit_service.render_page

    def tracked_render(page, scale=1.0):
        if scale == window.zoom:
            calls.append(scale)
        return original_render(page, scale)

    monkeypatch.setattr(window.edit_service, "render_page", tracked_render)
    for _ in range(5):
        window.refresh_preview()

    qtbot.waitUntil(lambda: len(calls) == 1, timeout=3000)
    qtbot.wait(180)
    assert calls == [window.zoom]


def test_stale_worker_callbacks_are_ignored(window, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(window, "_on_compression_progress", lambda *args: calls.append(args))
    window._compression_generation = 4
    window._dispatch_compression_progress(3, 1, 1, object())
    window._closing = True
    window._dispatch_compression_progress(4, 1, 1, object())
    assert calls == []


def test_close_with_unsaved_changes_can_be_cancelled(
    window, make_pdf, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.load_pdf(make_pdf())
    assert window.session is not None
    window.session.modified = True
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.No,
    )

    assert window.close() is False
    assert window._closing is False
