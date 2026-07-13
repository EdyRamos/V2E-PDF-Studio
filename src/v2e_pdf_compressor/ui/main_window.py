from __future__ import annotations

import logging
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import (
    QItemSelectionModel,
    QObject,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..application import (
    PdfEditError,
    PdfPasswordRequiredError,
    UpdateCheckResult,
    UpdateInfo,
    UpdateService,
    UpdateServiceError,
    build_batch_jobs,
)
from ..config import load_update_configuration
from ..domain import (
    BatchResult,
    CompressionJob,
    CompressionProfile,
    CompressionResult,
    CompressionStatus,
    ExportOptions,
)
from .messages import ERROR_MESSAGES, result_to_user_message


class DropHome(QFrame):
    open_requested = Signal()
    update_requested = Signal()
    batch_requested = Signal()
    tool_requested = Signal(str)
    file_dropped = Signal(Path)

    def __init__(self):
        """dropHome"""
        super().__init__()
        self.setObjectName("dropHome")
        self.setAcceptDrops(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(64, 54, 64, 54)
        layout.setSpacing(54)
        intro = QVBoxLayout()
        intro.setSpacing(20)
        intro.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        eyebrow = QLabel("V2E PDF Studio")
        eyebrow.setObjectName("homeEyebrow")
        title = QLabel("Escolha uma ferramenta para trabalhar no PDF.")
        title.setObjectName("homeTitle")
        title.setWordWrap(True)
        title.setMaximumWidth(560)
        made_by = QLabel("Uma ferramenta V2E desenvolvida por Eder A. Ramos")
        made_by.setObjectName("madeBy")
        made_by.setMaximumWidth(560)
        subtitle = QLabel(
            "Comece pela ação que você quer fazer. O app mostra somente as opções necessárias."
        )
        subtitle.setObjectName("homeSubtitle")
        subtitle.setWordWrap(True)
        subtitle.setMaximumWidth(560)
        quick_open = QPushButton("Abrir PDF no organizador")
        quick_open.setObjectName("primaryButton")
        quick_open.clicked.connect(self.open_requested.emit)
        self.update_button = QPushButton("Verificar atualizações")
        self.update_button.setObjectName("secondaryButton")
        self.update_button.clicked.connect(self.update_requested.emit)
        home_actions = QHBoxLayout()
        home_actions.setSpacing(10)
        home_actions.addWidget(quick_open)
        home_actions.addWidget(self.update_button)
        hint = QLabel("Ou arraste um PDF aqui para abrir direto no organizador.")
        hint.setObjectName("homeHint")
        hint.setMaximumWidth(560)
        intro.addStretch()
        intro.addWidget(eyebrow)
        intro.addWidget(title)
        intro.addWidget(made_by)
        intro.addWidget(subtitle)
        intro.addLayout(home_actions)
        intro.addWidget(hint)
        intro.addStretch()
        tool_grid = QGridLayout()
        tool_grid.setSpacing(14)
        tool_grid.addWidget(
            self._tool_button("Organizar PDF", "Editar páginas.", "organize"),
            0,
            0,
        )
        tool_grid.addWidget(
            self._tool_button("Comprimir PDF", "Reduzir um arquivo.", "compress"),
            0,
            1,
        )
        tool_grid.addWidget(
            self._tool_button("Comprimir lote", "Comprimir vários PDFs.", "batch"),
            1,
            0,
        )
        tool_grid.addWidget(
            self._tool_button("Dividir PDF", "Extrair páginas.", "split"),
            1,
            1,
        )
        layout.addLayout(intro, stretch=4)
        layout.addLayout(tool_grid, stretch=3)
        return None

    def _tool_button(self, title, description, tool_key):
        """ """
        button = QPushButton(f"""{title}\n{description}""")
        button.setObjectName("toolTile")
        button.setMinimumSize(230, 132)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda: self.tool_requested.emit(tool_key))
        return button

    def dragEnterEvent(self, event):
        """dragActive"""
        if not self._event_has_pdf(event):
            event.ignore()
            return None
        if self.property("dragActive") is not True:
            self.setProperty("dragActive", True)
            self.style().unpolish(self)
            self.style().polish(self)
        event.acceptProposedAction()
        return None

    def dragLeaveEvent(self, event):
        """dragActive"""
        self.setProperty("dragActive", False)
        self.style().unpolish(self)
        self.style().polish(self)
        event.accept()

    def dropEvent(self, event):
        """dragActive"""
        self.setProperty("dragActive", False)
        self.style().unpolish(self)
        self.style().polish(self)
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if not path.suffix.lower() == ".pdf":
                continue
            self.file_dropped.emit(path)
            event.acceptProposedAction()
            return None

    def _event_has_pdf(self, event):
        return any(
            Path(url.toLocalFile()).suffix.lower() == ".pdf" for url in event.mimeData().urls()
        )


class PageListWidget(QListWidget):
    order_changed = Signal()

    def __init__(self):
        """pageList"""
        super().__init__()
        self.setObjectName("pageList")
        self.setViewMode(QListWidget.ViewMode.ListMode)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropOverwriteMode(False)
        self.setIconSize(QSize(132, 176))
        self.setSpacing(10)
        return None

    def dropEvent(self, event):
        before = self._page_id_order()
        super().dropEvent(event)
        after = self._page_id_order()
        if before != after:
            self.order_changed.emit()
            return None
        return None

    def _page_id_order(self):
        return [self.item(index).data(Qt.ItemDataRole.UserRole) for index in range(self.count())]


class CompressionWorkerSignals(QObject):
    progress = Signal(int, int, object)
    finished = Signal(object)
    failed = Signal(str)


class ThumbnailWorkerSignals(QObject):
    rendered = Signal(int, object, bytes)


class ThumbnailWorker(QRunnable):
    """Renderiza uma miniatura fora da thread da UI."""

    def __init__(self, signals, generation, page, render_fn):
        super().__init__()
        self._signals = signals
        self._generation = generation
        self._page = page
        self._render_fn = render_fn

    def run(self):
        try:
            rendered = self._render_fn(self._page, scale=0.18)
            png_bytes = rendered.png_bytes
        except Exception:
            png_bytes = b""
        self._signals.rendered.emit(self._generation, self._page.page_id, png_bytes)


class UpdateWorkerSignals(QObject):
    check_finished = Signal(object)
    download_finished = Signal(object)
    progress = Signal(int, int)
    failed = Signal(str)


class MainWindow(QMainWindow):
    def __init__(
        self,
        edit_service,
        compression_service,
        settings_repository,
        update_service=None,
    ):
        """v2e.ui"""
        super().__init__()
        qt_app = QApplication.instance()
        if qt_app is not None:
            qt_app.setStyle("Fusion")
        self.edit_service = edit_service
        self.compression_service = compression_service
        self.settings_repository = settings_repository
        self.settings = settings_repository.load()
        if update_service is None:
            from .. import __version__

            update_service = UpdateService(load_update_configuration(), __version__)
        self.update_service = update_service
        self.logger = logging.getLogger("v2e.ui")
        self.session = None
        self.zoom = 1.1
        self._compression_thread = None
        self._compression_signals = None
        self._compression_generation = 0
        self._update_thread = None
        self._update_signals = None
        self._update_generation = 0
        self._closing = False
        self._temporary_paths: set[Path] = set()
        self._thumb_pool = QThreadPool(self)
        self._thumb_pool.setMaxThreadCount(2)
        self._thumb_generation = 0
        self._thumb_cache: dict[object, bytes] = {}
        self._thumb_signals = ThumbnailWorkerSignals()
        self._thumb_signals.rendered.connect(self._on_thumbnail_rendered)
        self._preview_cache: dict[tuple, bytes] = {}
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(120)
        self._preview_timer.timeout.connect(self._refresh_preview_now)
        self.setWindowTitle("V2E PDF Studio")
        self.resize(1360, 820)
        self.setMinimumSize(1024, 640)
        self.setAcceptDrops(True)
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.home = DropHome()
        self.home.open_requested.connect(lambda: self.start_home_tool("organize"))
        self.home.update_requested.connect(self.check_for_updates)
        self.home.batch_requested.connect(self.compress_batch)
        self.home.tool_requested.connect(self.start_home_tool)
        self.home.file_dropped.connect(self.load_pdf)
        self.editor = self._build_editor()
        self.main_stack = QStackedWidget()
        self.main_stack.addWidget(self.home)
        self.main_stack.addWidget(self.editor)
        self.setCentralWidget(self.main_stack)
        self.main_stack.setCurrentWidget(self.home)
        self._apply_style()
        self._apply_modern_control_style()
        self.set_active_tool("organize")
        self.status.showMessage("Escolha uma ferramenta para começar")
        self._set_document_actions_enabled(False)
        return None

    def _build_editor(self):
        """appShell"""
        shell = QWidget()
        shell.setObjectName("appShell")
        root = QVBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar())
        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.workspace_splitter.setObjectName("workspaceSplitter")
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.addWidget(self._build_pages_panel())
        self.workspace_splitter.addWidget(self._build_preview_panel())
        self.workspace_splitter.addWidget(self._build_tools_panel())
        self.workspace_splitter.setStretchFactor(0, 0)
        self.workspace_splitter.setStretchFactor(1, 1)
        self.workspace_splitter.setStretchFactor(2, 0)
        self.workspace_splitter.setSizes([220, 700, 340])
        root.addWidget(self.workspace_splitter, stretch=1)
        return shell

    def _build_topbar(self):
        """topbar"""
        bar = QFrame()
        bar.setObjectName("topbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(10)
        brand = QLabel("V2E PDF Studio")
        brand.setObjectName("brand")
        layout.addWidget(brand)
        self.brand_byline = QLabel("Desenvolvido por Eder A. Ramos")
        self.brand_byline.setObjectName("brandByline")
        layout.addWidget(self.brand_byline)
        layout.addStretch()
        self.update_button = self._make_button(
            "Atualizações", self.check_for_updates, "ghostButton"
        )
        self.update_button.setToolTip("Verificar manualmente se existe uma nova versão")
        self.home_button = self._make_button("Início", self.go_home, "ghostButton")
        self.open_button = self._make_button("Abrir PDF", self.open_pdf, "ghostButton")
        self.save_button = self._make_button("Salvar", self.save_document, "ghostButton")
        layout.addWidget(self.update_button)
        layout.addWidget(self.home_button)
        layout.addWidget(self.open_button)
        layout.addWidget(self.save_button)
        return bar

    def _build_pages_panel(self):
        """pagesPanel"""
        panel = QFrame()
        panel.setObjectName("pagesPanel")
        panel.setMinimumWidth(186)
        panel.setMaximumWidth(264)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 14, 18)
        layout.setSpacing(12)
        title = QLabel("Páginas")
        title.setObjectName("panelTitle")
        helper = QLabel("Arraste para reordenar. Ctrl ou Shift seleciona várias.")
        helper.setObjectName("panelHelper")
        helper.setWordWrap(True)
        self.thumbnail_list = PageListWidget()
        self.thumbnail_list.itemSelectionChanged.connect(self.refresh_preview)
        self.thumbnail_list.order_changed.connect(self.sync_session_order_from_ui)
        select_all = self._make_button("Selecionar tudo", self.select_all_pages, "flatButton")
        clear_selection = self._make_button(
            "Limpar seleção", self.clear_page_selection, "flatButton"
        )
        selection_actions = QVBoxLayout()
        selection_actions.setSpacing(8)
        selection_actions.addWidget(select_all)
        selection_actions.addWidget(clear_selection)
        layout.addWidget(title)
        layout.addWidget(helper)
        layout.addWidget(self.thumbnail_list, stretch=1)
        layout.addLayout(selection_actions)
        return panel

    def _build_preview_panel(self):
        """previewPanel"""
        panel = QFrame()
        panel.setObjectName("previewPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)
        header = QHBoxLayout()
        header.setSpacing(10)
        self.document_title = QLabel("Nenhum PDF aberto")
        self.document_title.setObjectName("documentTitle")
        header.addWidget(self.document_title, stretch=1)
        self.zoom_out_button = self._make_button("−", self.zoom_out, "zoomButton")
        self.zoom_out_button.setToolTip("Diminuir zoom")
        self.zoom_out_button.setAccessibleName("Diminuir zoom")
        self.zoom_in_button = self._make_button("+", self.zoom_in, "zoomButton")
        self.zoom_in_button.setToolTip("Aumentar zoom")
        self.zoom_in_button.setAccessibleName("Aumentar zoom")
        header.addWidget(self.zoom_out_button)
        header.addWidget(self.zoom_in_button)
        self.preview = QLabel("Abra um PDF para visualizar")
        self.preview.setObjectName("previewLabel")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_scroll.setWidget(self.preview)
        layout.addLayout(header)
        layout.addWidget(self.preview_scroll, stretch=1)
        return panel

    def _build_tools_panel(self):
        """toolsPanel"""
        panel = QFrame()
        panel.setObjectName("toolsPanel")
        panel.setMinimumWidth(296)
        panel.setMaximumWidth(384)
        shell_layout = QVBoxLayout(panel)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        self.tools_scroll = QScrollArea()
        self.tools_scroll.setObjectName("toolsScroll")
        self.tools_scroll.setWidgetResizable(True)
        self.tools_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tools_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.tools_content = QWidget()
        self.tools_content.setObjectName("toolsContent")
        layout = QVBoxLayout(self.tools_content)
        self.tools_layout = layout
        layout.setContentsMargins(20, 20, 20, 18)
        layout.setSpacing(12)
        self.tools_content.setMinimumWidth(0)
        tools_title = QLabel("Ferramentas")
        tools_title.setObjectName("panelTitle")
        layout.addWidget(tools_title)
        tool_hint = QLabel("Mostrando apenas as opções da ferramenta ativa.")
        tool_hint.setObjectName("panelHelper")
        tool_hint.setWordWrap(True)
        layout.addWidget(tool_hint)
        active_label = QLabel("Ferramenta ativa")
        active_label.setObjectName("fieldLabel")
        self.tool_combo = QComboBox()
        self.tool_combo.setObjectName("toolCombo")
        self.tool_combo.addItem("Organizar PDF", "organize")
        self.tool_combo.addItem("Comprimir PDF", "compress")
        self.tool_combo.addItem("Comprimir lote", "batch")
        self.tool_combo.addItem("Dividir", "split")
        self.tool_combo.currentIndexChanged.connect(self._on_tool_combo_changed)
        layout.addWidget(active_label)
        layout.addWidget(self.tool_combo)
        self.tool_stack = QStackedWidget()
        self.tool_stack.setObjectName("toolStack")
        self.tool_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        organize_panel = QFrame()
        organize_panel.setObjectName("toolPage")
        organize_layout = QVBoxLayout(organize_panel)
        organize_layout.setContentsMargins(14, 14, 14, 14)
        organize_layout.setSpacing(9)
        organize_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        organize_layout.addWidget(self._section_label("Organizar PDF"))
        self.organize_open_button = self._make_button(
            "Selecionar PDF para organizar", self.open_pdf, "primaryButton"
        )
        self.insert_button = self._make_button(
            "Adicionar páginas de outro PDF", self.insert_pdf, "toolButton"
        )
        self.blank_button = self._make_button(
            "Inserir página em branco", self.add_blank_page, "toolButton"
        )
        self.remove_button = self._make_button(
            "Remover páginas selecionadas", self.remove_selected_pages, "dangerButton"
        )
        organize_layout.addWidget(self.organize_open_button)
        organize_layout.addWidget(self.insert_button)
        organize_layout.addWidget(self.blank_button)
        organize_layout.addWidget(self.remove_button)
        compress_panel = QFrame()
        compress_panel.setObjectName("toolPage")
        compress_layout = QVBoxLayout(compress_panel)
        compress_layout.setContentsMargins(14, 14, 14, 14)
        compress_layout.setSpacing(9)
        compress_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        compress_layout.addWidget(self._section_label("Comprimir"))
        profile_label = QLabel("Perfil")
        profile_label.setObjectName("fieldLabel")
        self.profile_combo = QComboBox()
        self.profile_combo.setObjectName("profileCombo")
        self.profile_combo.addItem(
            "Alta compressão · arquivo menor", CompressionProfile.SCREEN.value
        )
        self.profile_combo.addItem("Equilibrado · recomendado", CompressionProfile.EBOOK.value)
        self.profile_combo.addItem("Melhor qualidade · impressão", CompressionProfile.PRINTER.value)
        self._select_profile(CompressionProfile.from_value(self.settings.default_profile))
        self.profile_combo.currentIndexChanged.connect(
            lambda index: self._on_profile_changed(self.profile_combo, index)
        )
        self.profile_description = QLabel(
            self._profile_description(CompressionProfile.from_value(self.settings.default_profile))
        )
        self.profile_description.setObjectName("fieldHelp")
        self.profile_description.setWordWrap(True)
        self.optimize_check = QCheckBox("Otimizações extras")
        self.optimize_check.setObjectName("optionCheck")
        self.optimize_check.setChecked(True)
        self.overwrite_check = QCheckBox("Permitir sobrescrever a saída")
        self.overwrite_check.setObjectName("optionCheck")
        self.overwrite_check.setChecked(self.settings.overwrite_policy == "overwrite")
        self.overwrite_check.stateChanged.connect(
            lambda _state: self._save_compression_preferences()
        )
        self.compress_import_button = self._make_button(
            "Escolher PDF para comprimir", self.open_pdf, "primaryButton"
        )
        self.compress_open_button = self._make_button(
            "Usar o PDF já aberto", self.compress_current_pdf, "toolButton"
        )
        self.cancel_button = self._make_button(
            "Cancelar processo", self.cancel_compression, "dangerButton"
        )
        self.cancel_button.setEnabled(False)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Pronto")
        self.log_output = QTextEdit()
        self.log_output.setObjectName("logOutput")
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("O resultado da compressão aparecerá aqui.")
        self.log_output.setMinimumHeight(104)
        self.log_output.setMaximumHeight(150)
        compress_layout.addWidget(profile_label)
        compress_layout.addWidget(self.profile_combo)
        compress_layout.addWidget(self.profile_description)
        compress_layout.addWidget(self.optimize_check)
        compress_layout.addWidget(self.overwrite_check)
        compress_layout.addWidget(self.compress_import_button)
        compress_layout.addWidget(self.compress_open_button)
        batch_panel = QFrame()
        batch_panel.setObjectName("toolPage")
        batch_layout = QVBoxLayout(batch_panel)
        batch_layout.setContentsMargins(14, 14, 14, 14)
        batch_layout.setSpacing(9)
        batch_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        batch_layout.addWidget(self._section_label("Comprimir lote"))
        batch_help = QLabel(
            "Selecione vários PDFs e uma pasta de saída. Cada arquivo será comprimido separadamente."
        )
        batch_help.setObjectName("panelHelper")
        batch_help.setWordWrap(True)
        batch_profile_label = QLabel("Perfil")
        batch_profile_label.setObjectName("fieldLabel")
        self.batch_profile_combo = QComboBox()
        self.batch_profile_combo.setObjectName("profileCombo")
        self.batch_profile_combo.addItem(
            "Alta compressão · arquivo menor", CompressionProfile.SCREEN.value
        )
        self.batch_profile_combo.addItem(
            "Equilibrado · recomendado", CompressionProfile.EBOOK.value
        )
        self.batch_profile_combo.addItem(
            "Melhor qualidade · impressão", CompressionProfile.PRINTER.value
        )
        for index in range(self.batch_profile_combo.count()):
            if (
                self.batch_profile_combo.itemData(index)
                != CompressionProfile.from_value(self.settings.default_profile).value
            ):
                continue
            self.batch_profile_combo.setCurrentIndex(index)
            break
        self.batch_profile_combo.currentIndexChanged.connect(
            lambda index: self._on_profile_changed(self.batch_profile_combo, index)
        )
        self.batch_profile_description = QLabel(
            self._profile_description(CompressionProfile.from_value(self.settings.default_profile))
        )
        self.batch_profile_description.setObjectName("fieldHelp")
        self.batch_profile_description.setWordWrap(True)
        self.batch_optimize_check = QCheckBox("Otimizações extras")
        self.batch_optimize_check.setObjectName("optionCheck")
        self.batch_optimize_check.setChecked(True)
        self.batch_overwrite_check = QCheckBox("Permitir sobrescrever a saída")
        self.batch_overwrite_check.setObjectName("optionCheck")
        self.batch_overwrite_check.setChecked(self.settings.overwrite_policy == "overwrite")
        self.batch_overwrite_check.stateChanged.connect(
            lambda _state: self._save_compression_preferences()
        )
        self.batch_pick_button = self._make_button(
            "Selecionar PDFs e comprimir", self.compress_batch, "primaryButton"
        )
        batch_layout.addWidget(batch_help)
        batch_layout.addWidget(batch_profile_label)
        batch_layout.addWidget(self.batch_profile_combo)
        batch_layout.addWidget(self.batch_profile_description)
        batch_layout.addWidget(self.batch_optimize_check)
        batch_layout.addWidget(self.batch_overwrite_check)
        batch_layout.addWidget(self.batch_pick_button)
        split_panel = QFrame()
        split_panel.setObjectName("toolPage")
        split_layout = QVBoxLayout(split_panel)
        split_layout.setContentsMargins(14, 14, 14, 14)
        split_layout.setSpacing(9)
        split_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        split_layout.addWidget(self._section_label("Dividir PDF"))
        split_help = QLabel(
            "Selecione páginas nas miniaturas ou informe intervalos como 1-3,5,8-10."
        )
        split_help.setObjectName("panelHelper")
        split_help.setWordWrap(True)
        self.split_import_button = self._make_button(
            "Selecionar PDF para dividir", self.open_pdf, "primaryButton"
        )
        self.split_selected_button = self._make_button(
            "Salvar páginas selecionadas", self._split_selected, "toolButton"
        )
        self.split_ranges_button = self._make_button(
            "Dividir por intervalos", self._split_ranges, "toolButton"
        )
        split_layout.addWidget(split_help)
        split_layout.addWidget(self.split_import_button)
        split_layout.addWidget(self.split_selected_button)
        split_layout.addWidget(self.split_ranges_button)
        self.tool_stack.addWidget(organize_panel)
        self.tool_stack.addWidget(compress_panel)
        self.tool_stack.addWidget(batch_panel)
        self.tool_stack.addWidget(split_panel)
        layout.addWidget(self.tool_stack)
        self.activity_panel = QFrame()
        self.activity_panel.setObjectName("activityPanel")
        activity_layout = QVBoxLayout(self.activity_panel)
        activity_layout.setContentsMargins(14, 14, 14, 14)
        activity_layout.setSpacing(9)
        activity_title = QLabel("Atividade")
        activity_title.setObjectName("activityTitle")
        activity_hint = QLabel("Acompanhe o processo atual e os resultados.")
        activity_hint.setObjectName("fieldHelp")
        activity_hint.setWordWrap(True)
        activity_layout.addWidget(activity_title)
        activity_layout.addWidget(activity_hint)
        activity_layout.addWidget(self.progress_bar)
        activity_layout.addWidget(self.cancel_button)
        activity_layout.addWidget(self.log_output)
        layout.addWidget(self.activity_panel)
        layout.addStretch(1)
        footer = QLabel("V2E | Desenvolvido por Eder A. Ramos")
        footer.setObjectName("toolsFooter")
        layout.addWidget(footer)
        self.tools_scroll.setWidget(self.tools_content)
        shell_layout.addWidget(self.tools_scroll)
        return panel

    def _make_button(self, text, callback, object_name):
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.clicked.connect(callback)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _section_label(self, text):
        """sectionLabel"""
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def start_home_tool(self, tool_key):
        self.set_active_tool(tool_key)
        self._show_editor()

    def go_home(self):
        """Escolha uma ferramenta para começar"""
        self.main_stack.setCurrentWidget(self.home)
        self.status.showMessage("Escolha uma ferramenta para começar")

    def _show_editor(self):
        self.main_stack.setCurrentWidget(self.editor)
        self._set_document_actions_enabled(self.session is not None)

    def _on_tool_combo_changed(self):
        self.set_active_tool(str(self.tool_combo.currentData()))

    def set_active_tool(self, tool_key):
        """organize"""
        mapping = {"split": 3, "batch": 2, "compress": 1, "organize": 0}
        combo_mapping = {"split": 3, "batch": 2, "compress": 1, "organize": 0}
        index = mapping.get(tool_key, 0)
        if hasattr(self, "tool_stack"):
            self.tool_stack.setCurrentIndex(index)
            self._resize_tool_stack()
        if hasattr(self, "tool_combo"):
            combo_index = combo_mapping.get(tool_key, 0)
            if self.tool_combo.currentIndex() != combo_index:
                self.tool_combo.blockSignals(True)
                self.tool_combo.setCurrentIndex(combo_index)
                self.tool_combo.blockSignals(False)
        labels = {
            "split": "Ferramenta ativa: Dividir PDF",
            "batch": "Ferramenta ativa: Comprimir lote",
            "compress": "Ferramenta ativa: Comprimir",
            "organize": "Ferramenta ativa: Organizar PDF",
        }
        if hasattr(self, "activity_panel"):
            is_busy = bool(
                self._compression_thread is not None and self._compression_thread.is_alive()
            )
            has_activity = bool(self.log_output.toPlainText().strip())
            show_compression_output = (is_busy or has_activity) and tool_key in {
                "batch",
                "compress",
            }
            self.activity_panel.setVisible(show_compression_output)
            self._refresh_tools_layout()
        self.status.showMessage(labels.get(tool_key, "Ferramenta ativa: Organizar PDF"))
        return None

    def _resize_tool_stack(self):
        current = self.tool_stack.currentWidget()
        if current is None:
            return
        for index in range(self.tool_stack.count()):
            page = self.tool_stack.widget(index)
            if page is current:
                page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
            else:
                page.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        current.updateGeometry()
        self.tool_stack.updateGeometry()

    def _refresh_tools_layout(self):
        if not hasattr(self, "tools_content"):
            return
        self.tools_content.updateGeometry()

    def open_pdf(self):
        """Abrir PDF"""
        start_dir = self.settings.last_directory or ""
        path, _ = QFileDialog.getOpenFileName(self, "Abrir PDF", start_dir, "Arquivos PDF (*.pdf)")
        if path:
            self.load_pdf(Path(path))
            return None

    def load_pdf(self, path):
        """PDF protegido por senha"""
        try:
            path = Path(path)
            session = self.edit_service.open_document(path)
            self.session = session
            self._thumb_cache.clear()
            self._preview_cache.clear()
            self._update_last_directory(path.parent)
            self._show_editor()
            self._set_document_actions_enabled(True)
            self.refresh_thumbnails(select_first=True)
            self.status.showMessage(f"{session.page_count} página(s) carregada(s)")
        except PdfPasswordRequiredError:
            self._show_error(
                "PDF protegido por senha", "Este PDF precisa de senha e não pode ser aberto."
            )
        except Exception as exc:
            self.logger.exception("Falha ao abrir PDF")
            self._show_error("Não foi possível abrir o PDF", str(exc))

    def refresh_thumbnails(self, select_first=False, selected_ids=None, current_id=None):
        if not self.session:
            return None
        self._thumb_generation += 1
        self.thumbnail_list.blockSignals(True)
        self.thumbnail_list.clear()
        for index, page in enumerate(self.session.pages, start=1):
            item = QListWidgetItem(f"Página {index}")
            item.setData(Qt.ItemDataRole.UserRole, page.page_id)
            item.setSizeHint(QSize(184, 218))
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEnabled
            )
            cached = self._thumb_cache.get(page.page_id)
            if cached:
                pixmap = QPixmap()
                pixmap.loadFromData(cached, "PNG")
                item.setIcon(QIcon(pixmap))
            else:
                self._thumb_pool.start(
                    ThumbnailWorker(
                        self._thumb_signals,
                        self._thumb_generation,
                        page,
                        self.edit_service.render_page,
                    )
                )
            self.thumbnail_list.addItem(item)
        selected_ids = selected_ids or set()
        for row in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(row)
            page_id = item.data(Qt.ItemDataRole.UserRole)
            if page_id in selected_ids:
                item.setSelected(True)
            if not current_id:
                continue
            if not page_id == current_id:
                continue
            self.thumbnail_list.setCurrentItem(item)
        if select_first and self.thumbnail_list.count():
            self.thumbnail_list.setCurrentRow(0, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        elif current_id is not None and selected_ids:
            selected_items = self.thumbnail_list.selectedItems()
            if selected_items:
                self.thumbnail_list.setCurrentItem(selected_items[0])
        self.thumbnail_list.blockSignals(False)
        self.refresh_preview()
        self._update_document_title()

    def _on_thumbnail_rendered(self, generation, page_id, png_bytes):
        if self._closing or generation != self._thumb_generation:
            return None
        if png_bytes:
            self._thumb_cache[page_id] = png_bytes
        for row in range(self.thumbnail_list.count()):
            item = self.thumbnail_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) != page_id:
                continue
            if png_bytes:
                pixmap = QPixmap()
                pixmap.loadFromData(png_bytes, "PNG")
                item.setIcon(QIcon(pixmap))
            else:
                item.setText(item.text() + "\nErro no preview")
            break
        return None

    def refresh_preview(self):
        """Agenda a atualização do preview (com debounce anti-engasgo)."""
        self._preview_timer.start()

    def _refresh_preview_now(self):
        """Nenhuma página para visualizar"""
        if not self.session or not self.session.pages:
            self.preview.setText("Nenhuma página para visualizar")
            self.preview.setPixmap(QPixmap())
            self._update_document_title()
            return None
        row = self.thumbnail_list.currentRow()
        if row < 0:
            row = 0
        item = self.thumbnail_list.item(row)
        if item is None:
            self._update_document_title()
            return None
        page_id = item.data(Qt.ItemDataRole.UserRole)
        page = next(
            (candidate for candidate in self.session.pages if candidate.page_id == page_id), None
        )
        if page is None:
            self._update_document_title()
            return None
        try:
            cache_key = (page.page_id, round(self.zoom, 2))
            png_bytes = self._preview_cache.get(cache_key)
            if png_bytes is None:
                rendered = self.edit_service.render_page(page, scale=self.zoom)
                png_bytes = rendered.png_bytes
                if len(self._preview_cache) > 24:
                    self._preview_cache.clear()
                self._preview_cache[cache_key] = png_bytes
            pixmap = QPixmap()
            pixmap.loadFromData(png_bytes, "PNG")
            self.preview.setPixmap(pixmap)
            self.preview.setText("")
            self._update_document_title()
        except Exception as exc:
            self.preview.setPixmap(QPixmap())
            self.preview.setText(f"Não foi possível renderizar a página: {exc}")

    def _refresh_page_labels(self):
        for index in range(self.thumbnail_list.count()):
            self.thumbnail_list.item(index).setText(f"Página {index + 1}")
        self._update_document_title()

    def sync_session_order_from_ui(self):
        if not self.session:
            return None
        page_ids = [
            self.thumbnail_list.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.thumbnail_list.count())
        ]
        try:
            self.edit_service.reorder_by_page_ids(self.session, page_ids)
            self._refresh_page_labels()
            self.refresh_preview()
            self.status.showMessage("Ordem das páginas atualizada")
        except PdfEditError as exc:
            self._show_error("Não foi possível reordenar", str(exc))
            self.refresh_thumbnails(select_first=True)

    def insert_pdf(self):
        if not self.session:
            return None
        path, _ = QFileDialog.getOpenFileName(
            self, "Adicionar PDF", self.settings.last_directory or "", "Arquivos PDF (*.pdf)"
        )
        if not path:
            return None
        try:
            after_page_id = self._last_selected_page_id()
            inserted_ids = self.edit_service.insert_pdf(
                self.session, Path(path), after_page_id=after_page_id
            )
            self._update_last_directory(Path(path).parent)
            self.refresh_thumbnails(
                selected_ids=set(inserted_ids),
                current_id=inserted_ids[0] if inserted_ids else None,
            )
            self.status.showMessage("PDF adicionado ao documento")
        except Exception as exc:
            self._show_error("Não foi possível adicionar PDF", str(exc))

    def add_blank_page(self):
        if not self.session:
            return None
        after_page_id = self._last_selected_page_id()
        self.edit_service.add_blank_page(self.session, after_page_id=after_page_id)
        if after_page_id:
            position = next(
                (i for i, page in enumerate(self.session.pages) if page.page_id == after_page_id),
                len(self.session.pages) - 2,
            )
            inserted_id = self.session.pages[position + 1].page_id
        else:
            inserted_id = self.session.pages[-1].page_id
        self.refresh_thumbnails(selected_ids={inserted_id}, current_id=inserted_id)
        self.status.showMessage("Página em branco adicionada")

    def remove_selected_pages(self):
        if not self.session:
            return None
        selected_ids = self._selected_page_ids()
        if not selected_ids:
            self._show_error(
                "Nenhuma página selecionada", "Selecione uma ou mais páginas para remover."
            )
            return None
        answer = QMessageBox.question(
            self, "Remover páginas", f"Remover {len(selected_ids)} página(s) selecionada(s)?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return None
        self.edit_service.remove_pages(self.session, selected_ids)
        self.refresh_thumbnails(select_first=True)
        self.status.showMessage("Página(s) removida(s)")

    def split_pdf(self):
        if not self.session:
            return None
        message = QMessageBox(self)
        message.setWindowTitle("Dividir PDF")
        message.setText("Como deseja dividir o PDF?")
        selected_button = message.addButton(
            "Páginas selecionadas", QMessageBox.ButtonRole.AcceptRole
        )
        ranges_button = message.addButton("Intervalos", QMessageBox.ButtonRole.ActionRole)
        message.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        message.exec()
        clicked = message.clickedButton()
        if clicked == selected_button:
            self._split_selected()
            return None
        if clicked == ranges_button:
            self._split_ranges()
            return None

    def _split_selected(self):
        if not self.session:
            return None
        selected_ids = self._selected_page_ids()
        if not selected_ids:
            self._show_error(
                "Nenhuma página selecionada", "Selecione as páginas que devem virar um novo PDF."
            )
            return None
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar páginas selecionadas",
            self._default_output_path("paginas_selecionadas"),
            "Arquivos PDF (*.pdf)",
        )
        if not output_path:
            return None
        try:
            self.edit_service.split_selected(
                self.session,
                selected_ids,
                self._ensure_pdf_suffix(Path(output_path)),
                overwrite=True,
            )
            self.status.showMessage("PDF dividido com páginas selecionadas")
        except Exception as exc:
            self._show_error("Falha ao dividir PDF", str(exc))

    def _split_ranges(self):
        if not self.session:
            return None
        ranges_text, ok = QInputDialog.getText(
            self, "Dividir por intervalos", "Exemplo: 1-3,5,8-10"
        )
        if not ok or not ranges_text.strip():
            return None
        output_dir = QFileDialog.getExistingDirectory(
            self, "Escolha a pasta de saída", self.settings.last_directory or ""
        )
        if not output_dir:
            return None
        base_name = self.session.original_path.stem if self.session.original_path else "documento"
        try:
            outputs = self.edit_service.split_ranges(
                self.session, ranges_text, Path(output_dir), base_name, overwrite=True
            )
            self.status.showMessage(f"{len(outputs)} arquivo(s) criado(s)")
        except Exception as exc:
            self._show_error("Falha ao dividir por intervalos", str(exc))

    def save_document(self):
        if not self.session:
            return None
        message = QMessageBox(self)
        message.setWindowTitle("Salvar PDF")
        message.setText("Como deseja salvar as alterações?")
        save_as_button = message.addButton("Salvar como novo", QMessageBox.ButtonRole.AcceptRole)
        overwrite_button = message.addButton(
            "Sobrescrever original", QMessageBox.ButtonRole.DestructiveRole
        )
        message.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        message.exec()
        clicked = message.clickedButton()
        if clicked == save_as_button:
            output_path, _ = QFileDialog.getSaveFileName(
                self,
                "Salvar como novo PDF",
                self._default_output_path("editado"),
                "Arquivos PDF (*.pdf)",
            )
            if output_path:
                self._export_to(self._ensure_pdf_suffix(Path(output_path)), overwrite=True)
                return None
            return None
        if clicked == overwrite_button:
            if not self.session.original_path:
                self._show_error(
                    "Sem arquivo original", "Use salvar como novo para este documento."
                )
                return None
            self._export_to(self.session.original_path, overwrite=True)
            return None

    def compress_current_pdf(self):
        """Nenhum PDF aberto"""
        if not self.session:
            self._show_error("Nenhum PDF aberto", "Abra um PDF ou use a compressão em lote.")
            return None
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar PDF comprimido",
            self._default_output_path("comprimido"),
            "Arquivos PDF (*.pdf)",
        )
        if not output_path:
            return None
        try:
            input_path = self._materialize_current_pdf()
            job = CompressionJob(
                input_path=input_path,
                output_path=self._ensure_pdf_suffix(Path(output_path)),
                profile=self._selected_profile(),
                overwrite=True,
                optimize=self._selected_optimize(),
            )
            self._start_compression([job], "document")
        except Exception as exc:
            self._show_error("Falha ao preparar PDF", str(exc))

    def compress_batch(self):
        """Selecionar PDFs para comprimir"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Selecionar PDFs para comprimir",
            self.settings.last_directory or "",
            "Arquivos PDF (*.pdf)",
        )
        if not files:
            return None
        output_dir = QFileDialog.getExistingDirectory(
            self, "Escolha a pasta de saída", str(Path(files[0]).parent)
        )
        if not output_dir:
            return None
        self.set_active_tool("batch")
        self._show_editor()
        input_files = [Path(file) for file in files]
        self._update_last_directory(input_files[0].parent)
        jobs = build_batch_jobs(
            input_files=input_files,
            output_dir=Path(output_dir),
            profile=self._selected_profile(),
            overwrite=self._selected_overwrite(),
            optimize=self._selected_optimize(),
        )
        self._start_compression(jobs, "batch")
        return None

    def _start_compression(self, jobs, mode):
        """Processo em andamento"""
        if self._compression_thread and self._compression_thread.is_alive():
            self._show_error("Processo em andamento", "Aguarde ou cancele a compressão atual.")
            return None
        if not jobs:
            self._show_error("Nenhum arquivo", "Não há arquivos para comprimir.")
            return None
        self.compression_service.reset_cancel()
        self._set_compression_busy(True)
        self.progress_bar.setRange(0, len(jobs))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"""0/{len(jobs)}""")
        self.log_output.clear()
        self._append_log(
            f"""Compressão iniciada: {len(jobs)} arquivo(s), perfil {self._selected_profile().value}."""
        )
        signals = CompressionWorkerSignals()
        self._compression_generation += 1
        generation = self._compression_generation
        signals.progress.connect(
            lambda done, total, result: self._dispatch_compression_progress(
                generation, done, total, result
            )
        )
        signals.finished.connect(
            lambda result: self._dispatch_compression_finished(generation, result, mode)
        )
        signals.failed.connect(
            lambda message: self._dispatch_compression_failed(generation, message)
        )
        self._compression_signals = signals

        def run():

            try:
                if len(jobs) == 1:
                    result = self.compression_service.compress(jobs[0])
                    signals.progress.emit(1, 1, result)
                    signals.finished.emit(result)
                    return None
                batch = self.compression_service.compress_many(
                    jobs,
                    progress_cb=lambda done, total, result: signals.progress.emit(
                        done, total, result
                    ),
                )
                signals.finished.emit(batch)
                return None
            except Exception as exc:
                self.logger.exception("Falha inesperada na worker de compressão")
                signals.failed.emit(str(exc))

        self._compression_thread = threading.Thread(target=run, daemon=True)
        self._compression_thread.start()

    def _dispatch_compression_progress(self, generation, done, total, result):
        if self._closing or generation != self._compression_generation:
            return
        self._on_compression_progress(done, total, result)

    def _dispatch_compression_finished(self, generation, result, mode):
        if self._closing or generation != self._compression_generation:
            return
        self._on_compression_finished(result, mode)

    def _dispatch_compression_failed(self, generation, message):
        if self._closing or generation != self._compression_generation:
            return
        self._on_compression_failed(message)

    def _on_compression_progress(self, done, total, result):
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(done)
        self.progress_bar.setFormat(f"""{done}/{total}""")
        self._append_log(result_to_user_message(result))

    def _on_compression_finished(self, result, mode):
        self._compression_thread = None
        self._set_compression_busy(False)
        self._cleanup_temporary_paths()
        if isinstance(result, BatchResult):
            summary = f"""Finalizado. Total: {result.total} | Sucesso: {result.success} | Falhas: {result.failed} | Cancelados: {result.cancelled}"""
            self._append_log(summary)
            self.status.showMessage(summary)
            return None
        if isinstance(result, CompressionResult):
            if result.status != CompressionStatus.SUCCESS:
                message = ERROR_MESSAGES.get(result.error_code, "Falha ao comprimir PDF")
                if result.error_detail:
                    message = f"""{message}\n\n{result.error_detail}"""
                self._show_error("Falha ao comprimir", message)
                return None
            self.status.showMessage("PDF comprimido com sucesso")
            return None
        self.status.showMessage(f"Compressão {mode} finalizada")

    def _on_compression_failed(self, message):
        self._compression_thread = None
        self._set_compression_busy(False)
        self._cleanup_temporary_paths()
        self._show_error("Falha na compressão", message)

    def cancel_compression(self):
        """Solicita o encerramento imediato do processo atual."""
        self.compression_service.cancel()
        self._append_log("Cancelamento solicitado. Encerrando o processo atual.")
        self.status.showMessage("Cancelamento solicitado")

    def check_for_updates(self):
        """Consulta o GitHub somente quando o usuário solicita."""
        if self._update_thread is not None and self._update_thread.is_alive():
            return None
        if not self.update_service.configuration.configured:
            detail = self.update_service.configuration.error or (
                "Este build ainda não informa o repositório oficial de atualizações."
            )
            self._show_error("Atualizações não configuradas", detail)
            return None

        self._set_update_busy(True, "Verificando...")
        self.status.showMessage("Consultando a release mais recente no GitHub")
        signals = UpdateWorkerSignals()
        self._update_generation += 1
        generation = self._update_generation
        signals.check_finished.connect(
            lambda result: self._dispatch_update_check_finished(generation, result)
        )
        signals.failed.connect(lambda message: self._dispatch_update_failed(generation, message))
        self._update_signals = signals

        def run():
            try:
                signals.check_finished.emit(self.update_service.check_for_update())
            except UpdateServiceError as exc:
                signals.failed.emit(str(exc))
            except Exception as exc:
                self.logger.exception("Falha inesperada ao verificar atualizações")
                signals.failed.emit(str(exc))

        self._update_thread = threading.Thread(target=run, daemon=True)
        self._update_thread.start()
        return None

    def _dispatch_update_check_finished(self, generation, result):
        if self._closing or generation != self._update_generation:
            return None
        self._update_thread = None
        self._set_update_busy(False)
        if not isinstance(result, UpdateCheckResult):
            self._on_update_failed("O serviço retornou uma resposta inesperada.")
            return None
        if not result.update_available or result.update is None:
            self.status.showMessage("Você já está usando a versão mais recente")
            QMessageBox.information(
                self,
                "Aplicativo atualizado",
                f"A versão {result.current_version} já é a mais recente.",
            )
            return None

        update = result.update
        size_mb = update.size_bytes / (1024 * 1024)
        notes = update.release_notes.strip()
        notes_text = f"\n\nNovidades:\n{notes[:600]}" if notes else ""
        answer = QMessageBox.question(
            self,
            "Nova versão disponível",
            (
                f"A versão {update.version} está disponível ({size_mb:.1f} MB)."
                f"{notes_text}\n\nDeseja baixar agora?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._start_update_download(update)
        else:
            self.status.showMessage("Atualização adiada")
        return None

    def _start_update_download(self, update: UpdateInfo):
        self._set_update_busy(True, "Baixando 0%")
        self.status.showMessage(f"Baixando a versão {update.version}")
        signals = UpdateWorkerSignals()
        self._update_generation += 1
        generation = self._update_generation
        signals.progress.connect(
            lambda done, total: self._dispatch_update_progress(generation, done, total)
        )
        signals.download_finished.connect(
            lambda path: self._dispatch_update_download_finished(generation, path)
        )
        signals.failed.connect(lambda message: self._dispatch_update_failed(generation, message))
        self._update_signals = signals

        def run():
            try:
                path = self.update_service.download_update(
                    update,
                    lambda done, total: signals.progress.emit(done, total),
                )
                signals.download_finished.emit(path)
            except UpdateServiceError as exc:
                signals.failed.emit(str(exc))
            except Exception as exc:
                self.logger.exception("Falha inesperada ao baixar atualização")
                signals.failed.emit(str(exc))

        self._update_thread = threading.Thread(target=run, daemon=True)
        self._update_thread.start()

    def _dispatch_update_progress(self, generation, done, total):
        if self._closing or generation != self._update_generation:
            return None
        percentage = round(done * 100 / total) if total else 0
        self.update_button.setText(f"Baixando {percentage}%")
        self.status.showMessage(f"Baixando atualização: {percentage}%")
        return None

    def _dispatch_update_download_finished(self, generation, path):
        if self._closing or generation != self._update_generation:
            return None
        self._update_thread = None
        self._set_update_busy(False)
        if not isinstance(path, Path):
            self._on_update_failed("O arquivo baixado não foi localizado.")
            return None
        self.status.showMessage("Atualização baixada e verificada")
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Atualização pronta")
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setText("A nova versão foi baixada e teve o SHA-256 verificado.")
        dialog.setInformativeText(
            "O aplicativo atual não será substituído. Abra a nova versão quando quiser."
        )
        open_button = dialog.addButton("Abrir nova versão", QMessageBox.ButtonRole.AcceptRole)
        folder_button = dialog.addButton("Abrir pasta", QMessageBox.ButtonRole.ActionRole)
        dialog.addButton("Depois", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton() is open_button:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        elif dialog.clickedButton() is folder_button:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
        return None

    def _dispatch_update_failed(self, generation, message):
        if self._closing or generation != self._update_generation:
            return None
        self._on_update_failed(message)
        return None

    def _on_update_failed(self, message):
        self._update_thread = None
        self._set_update_busy(False)
        self.status.showMessage("Não foi possível concluir a atualização")
        self._show_error("Falha na atualização", message)

    def _set_update_busy(self, busy, text="Atualizações"):
        self.update_button.setEnabled(not busy)
        self.update_button.setText(text)
        self.home.update_button.setEnabled(not busy)
        self.home.update_button.setText("Verificar atualizações" if not busy else text)

    def zoom_in(self):
        self.zoom = min(self.zoom + 0.15, 3.0)
        self.status.showMessage(f"Zoom: {round(self.zoom * 100)}%")
        self.refresh_preview()

    def zoom_out(self):
        self.zoom = max(self.zoom - 0.15, 0.35)
        self.status.showMessage(f"Zoom: {round(self.zoom * 100)}%")
        self.refresh_preview()

    def select_all_pages(self):
        self.thumbnail_list.selectAll()
        self._update_document_title()

    def clear_page_selection(self):
        self.thumbnail_list.clearSelection()
        self._update_document_title()

    def dragEnterEvent(self, event):
        if any(Path(url.toLocalFile()).suffix.lower() == ".pdf" for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        """.pdf"""
        pdfs = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if Path(url.toLocalFile()).suffix.lower() == ".pdf"
        ]
        if not pdfs:
            return None
        self.load_pdf(pdfs[0])
        event.acceptProposedAction()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "brand_byline"):
            self.brand_byline.setVisible(self.width() >= 1260)

    def closeEvent(self, event):
        """Sair"""
        if self.session and self.session.modified:
            answer = QMessageBox.question(
                self, "Sair", "Há alterações não salvas. Deseja sair mesmo assim?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return None
        self._closing = True
        self._compression_generation += 1
        self._update_generation += 1
        self.compression_service.cancel()
        self._cleanup_temporary_paths()
        event.accept()

    def _export_to(self, output_path, overwrite):
        if not self.session:
            return None
        try:
            self.edit_service.export_document(
                self.session,
                ExportOptions(output_path=output_path, overwrite=overwrite),
            )
            self.refresh_thumbnails()
            self.status.showMessage("PDF salvo")
        except Exception as exc:
            self._show_error("Não foi possível salvar", str(exc))

    def _materialize_current_pdf(self):
        """Nenhum documento aberto."""
        if not self.session:
            raise RuntimeError("Nenhum documento aberto.")
        if not self.session.modified and self.session.original_path:
            return self.session.original_path
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        self._temporary_paths.add(temp_path)
        original_path = self.session.original_path
        modified = self.session.modified
        try:
            self.edit_service.export_document(
                self.session, ExportOptions(output_path=temp_path, overwrite=True)
            )
            return temp_path
        finally:
            self.session.original_path = original_path
            self.session.modified = modified

    def _cleanup_temporary_paths(self):
        for path in tuple(self._temporary_paths):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                self.logger.warning("Não foi possível remover temporário: %s", path)
            else:
                self._temporary_paths.discard(path)

    def _path_is_source(self, output_path):
        if not self.session:
            return False
        target = output_path.resolve()
        return any(
            page.source_path and page.source_path.resolve() == target for page in self.session.pages
        )

    def _selected_page_ids(self):
        return {item.data(Qt.ItemDataRole.UserRole) for item in self.thumbnail_list.selectedItems()}

    def _current_page_id(self):
        item = self.thumbnail_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _last_selected_page_id(self):
        selected_rows = [
            self.thumbnail_list.row(item) for item in self.thumbnail_list.selectedItems()
        ]
        if not selected_rows:
            return None
        return self.thumbnail_list.item(sorted(selected_rows)[-1]).data(Qt.ItemDataRole.UserRole)

    def _default_output_path(self, suffix):
        """_"""
        if self.session and self.session.original_path:
            path = self.session.original_path
            return str(path.with_name(f"""{path.stem}_{suffix}.pdf"""))
        if self.settings.last_directory:
            return str(Path(self.settings.last_directory) / f"""documento_{suffix}.pdf""")
        return f"documento_{suffix}.pdf"

    def _ensure_pdf_suffix(self, path):
        """.pdf"""
        if path.suffix.lower() != ".pdf":
            return path.with_suffix(".pdf")
        return path

    def _selected_profile(self):
        """batch"""
        combo = (
            self.batch_profile_combo if self._active_tool_key() == "batch" else self.profile_combo
        )
        profile = combo.currentData()
        if isinstance(profile, CompressionProfile):
            return profile
        return CompressionProfile.from_value(str(profile or ""))

    def _selected_optimize(self):
        """batch"""
        if self._active_tool_key() == "batch":
            return self.batch_optimize_check.isChecked()
        return self.optimize_check.isChecked()

    def _selected_overwrite(self):
        """batch"""
        if self._active_tool_key() == "batch":
            return self.batch_overwrite_check.isChecked()
        return self.overwrite_check.isChecked()

    def _active_tool_key(self):
        """tool_combo"""
        if hasattr(self, "tool_combo"):
            value = self.tool_combo.currentData()
            if isinstance(value, str):
                return value
        return "organize"

    def _select_profile(self, profile, combo=None):
        target = combo or self.profile_combo
        for index in range(target.count()):
            value = target.itemData(index)
            if value != profile and value != profile.value:
                continue
            target.setCurrentIndex(index)
            return None

    def _on_profile_changed(self, combo, index):
        if index < 0:
            return
        profile = CompressionProfile.from_value(str(combo.itemData(index) or ""))
        description = self._profile_description(profile)
        if hasattr(self, "profile_description"):
            self.profile_description.setText(description)
        if hasattr(self, "batch_profile_description"):
            self.batch_profile_description.setText(description)
        self._save_compression_preferences(profile)

    @staticmethod
    def _profile_description(profile):
        descriptions = {
            CompressionProfile.SCREEN: "Menor arquivo para envio e visualização em tela.",
            CompressionProfile.EBOOK: "Bom equilíbrio entre tamanho e nitidez para uso geral.",
            CompressionProfile.PRINTER: "Mais detalhes para impressão, com arquivo maior.",
        }
        return descriptions[profile]

    def _save_compression_preferences(self, selected_profile=None):
        """overwrite"""
        profile = selected_profile or self._selected_profile()
        overwrite = self._selected_overwrite()
        self.settings.default_profile = profile.value
        self.settings.overwrite_policy = "overwrite" if overwrite else "rename"
        self.settings_repository.save(self.settings)
        for combo in (self.profile_combo, self.batch_profile_combo):
            combo.blockSignals(True)
            self._select_profile(profile, combo)
            combo.blockSignals(False)
        for checkbox in (self.overwrite_check, self.batch_overwrite_check):
            checkbox.blockSignals(True)
            checkbox.setChecked(overwrite)
            checkbox.blockSignals(False)
        return None

    def _append_log(self, message):
        self.log_output.append(message)
        if self._active_tool_key() in {"batch", "compress"}:
            self.activity_panel.setVisible(True)
            self._refresh_tools_layout()

    def _update_document_title(self):
        """Nenhum PDF aberto"""
        if not self.session:
            self.document_title.setText("Nenhum PDF aberto")
            return None
        selected = len(self.thumbnail_list.selectedItems())
        dirty = " *" if self.session.modified else ""
        self.document_title.setText(
            f"""{self.session.title}{dirty}  |  {self.session.page_count} página(s)  |  {selected} selecionada(s)"""
        )

    def _update_last_directory(self, directory):
        self.settings.last_directory = str(directory)
        self.settings_repository.save(self.settings)

    def _set_document_actions_enabled(self, enabled):
        for button in (
            self.save_button,
            self.compress_open_button,
            self.insert_button,
            self.blank_button,
            self.remove_button,
            self.split_selected_button,
            self.split_ranges_button,
            self.zoom_in_button,
            self.zoom_out_button,
        ):
            button.setEnabled(enabled)
        return None

    def _set_compression_busy(self, busy):
        has_activity = bool(self.log_output.toPlainText().strip())
        compression_tool = self._active_tool_key() in frozenset({"batch", "compress"})
        self.activity_panel.setVisible(compression_tool and (busy or has_activity))
        self._refresh_tools_layout()
        self.compress_open_button.setEnabled(not busy and self.session is not None)
        self.batch_pick_button.setEnabled(not busy)
        self.profile_combo.setEnabled(not busy)
        self.optimize_check.setEnabled(not busy)
        self.overwrite_check.setEnabled(not busy)
        self.batch_profile_combo.setEnabled(not busy)
        self.batch_optimize_check.setEnabled(not busy)
        self.batch_overwrite_check.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        if busy:
            self.tools_scroll.ensureWidgetVisible(self.activity_panel, 0, 12)
        return None

    def _show_error(self, title, message):
        QMessageBox.critical(self, title, message)

    def _apply_modern_control_style(self):
        self.setStyleSheet(
            self.styleSheet()
            + """
            QComboBox#profileCombo, QComboBox#toolCombo {
                padding: 7px 38px 7px 12px;
                selection-background-color: #f16f3f;
                selection-color: #ffffff;
            }
            QComboBox#profileCombo:hover, QComboBox#toolCombo:hover,
            QComboBox#profileCombo:focus, QComboBox#toolCombo:focus {
                border: 2px solid #f16f3f;
                padding-left: 11px;
            }
            QComboBox#profileCombo::drop-down, QComboBox#toolCombo::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 34px;
                background: #efe6d7;
                border: 0;
                border-left: 1px solid #d6caba;
                border-top-right-radius: 9px;
                border-bottom-right-radius: 9px;
            }
            QComboBox QAbstractItemView {
                background: #ffffff;
                color: #17211d;
                border: 1px solid #d6caba;
                padding: 5px;
                outline: 0;
                selection-background-color: #f16f3f;
                selection-color: #ffffff;
            }
            QCheckBox#optionCheck {
                spacing: 10px;
                padding: 6px 2px;
            }
            QCheckBox#optionCheck::indicator {
                width: 20px;
                height: 20px;
                background: #ffffff;
                border: 2px solid #b9ad9d;
                border-radius: 6px;
            }
            QCheckBox#optionCheck::indicator:hover {
                border-color: #f16f3f;
                background: #fff7ec;
            }
            QCheckBox#optionCheck::indicator:checked {
                background: #f16f3f;
                border-color: #f16f3f;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 12px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: #b9ad9d;
                border-radius: 5px;
                min-height: 28px;
            }
            QScrollBar::handle:vertical:hover {
                background: #f16f3f;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                height: 0;
                background: transparent;
            }
            QSplitter#workspaceSplitter::handle {
                background: #ddd5c8;
                width: 1px;
            }
            QScrollArea#toolsScroll, QWidget#toolsContent {
                background: #f7f3ec;
                border: 0;
            }
            QFrame#toolPage {
                background: #ffffff;
                border: 1px solid #e2dbd0;
                border-radius: 14px;
            }
            QFrame#activityPanel {
                background: #17211d;
                border: 0;
                border-radius: 14px;
            }
            QLabel#activityTitle {
                color: #ffffff;
                font-size: 11pt;
                font-weight: 800;
            }
            QLabel#fieldHelp {
                color: #737b75;
                font-size: 9pt;
            }
            QFrame#activityPanel QLabel#fieldHelp {
                color: #b9c2bc;
            }
            QFrame#activityPanel QTextEdit#logOutput {
                background: #0f1713;
                border: 1px solid #304039;
                border-radius: 10px;
            }
            QPushButton#primaryButton, QPushButton#toolButton,
            QPushButton#dangerButton, QPushButton#flatButton {
                min-height: 40px;
                padding: 7px 12px;
            }
            QComboBox#profileCombo, QComboBox#toolCombo {
                min-height: 38px;
            }
            QProgressBar#progressBar {
                min-height: 22px;
            }
            QPushButton#zoomButton {
                background: #eee5d6;
                color: #17211d;
                border: 1px solid #d8ccbc;
                border-radius: 10px;
                min-width: 42px;
                max-width: 42px;
                min-height: 36px;
                padding: 4px;
                font-size: 16pt;
                font-weight: 700;
            }
            QPushButton#zoomButton:hover {
                background: #fff8eb;
                border-color: #f16f3f;
            }
            """
        )

    def _apply_style(self):
        """Aplica o stylesheet base da janela (fonte única, sem duplicação)."""
        self.setStyleSheet(
            '\n            QMainWindow {\n                background: #f5f1e8;\n            }\n            QWidget {\n                color: #17211d;\n                font-family: "Segoe UI", "Aptos", sans-serif;\n                font-size: 10.5pt;\n            }\n            QLabel, QCheckBox {\n                background: transparent;\n            }\n            #appShell {\n                background: #f5f1e8;\n            }\n            #dropHome {\n                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,\n                    stop:0 #111d18, stop:0.56 #20372f, stop:1 #f16f3f);\n                border: 0;\n            }\n            #dropHome[dragActive="true"] {\n                border: 3px solid #ffd2bd;\n            }\n            #homeEyebrow {\n                color: #ffb28f;\n                font-size: 11pt;\n                font-weight: 800;\n                letter-spacing: 2px;\n                text-transform: uppercase;\n            }\n            #homeTitle {\n                color: #fff8eb;\n                font-size: 31pt;\n                font-weight: 900;\n                max-width: 760px;\n            }\n            #homeSubtitle {\n                color: #eadfd2;\n                font-size: 13pt;\n                max-width: 680px;\n                line-height: 1.45;\n            }\n            #madeBy {\n                color: #ffd4c2;\n                font-size: 11pt;\n                font-weight: 800;\n            }\n            #homeHint {\n                color: #ffc8af;\n                font-weight: 600;\n            }\n            #toolTile {\n                background: rgba(255, 248, 235, 0.94);\n                color: #17211d;\n                border: 1px solid rgba(255, 255, 255, 0.55);\n                border-radius: 18px;\n                padding: 18px;\n                font-size: 11pt;\n                font-weight: 900;\n                text-align: left;\n            }\n            #toolTile:hover {\n                background: #ffffff;\n                border: 2px solid #ff8a5f;\n            }\n            #topbar {\n                background: #101713;\n                border: 0;\n            }\n            #brand {\n                color: #fff8eb;\n                font-size: 15pt;\n                font-weight: 900;\n            }\n            #brandByline {\n                color: #aeb8b1;\n                font-size: 9.5pt;\n                font-weight: 700;\n                margin-left: 8px;\n            }\n            #pagesPanel {\n                background: #e8dfd1;\n                border-right: 1px solid #d6caba;\n            }\n            #previewPanel {\n                background: #f5f1e8;\n            }\n            #toolsPanel {\n                background: #fffaf1;\n                border-left: 1px solid #dacfc0;\n            }\n            #panelTitle {\n                font-size: 16pt;\n                font-weight: 900;\n                color: #16231e;\n            }\n            #panelHelper {\n                color: #697169;\n                font-size: 9.5pt;\n            }\n            #sectionLabel {\n                color: #f16f3f;\n                font-size: 9pt;\n                font-weight: 900;\n                letter-spacing: 1.2px;\n                text-transform: uppercase;\n                margin-top: 4px;\n            }\n            #fieldLabel {\n                color: #3b463f;\n                font-weight: 800;\n            }\n            #documentTitle {\n                font-size: 13pt;\n                font-weight: 900;\n                color: #1a2822;\n            }\n            #pageList {\n                background: transparent;\n                border: 0;\n                outline: 0;\n            }\n            QListWidget::item {\n                background: #fffaf1;\n                color: #17211d;\n                border: 1px solid #d6caba;\n                border-radius: 14px;\n                padding: 10px;\n                margin: 2px 0;\n            }\n            QListWidget::item:hover {\n                border: 1px solid #f16f3f;\n            }\n            QListWidget::item:selected {\n                background: #fff2df;\n                border: 2px solid #f16f3f;\n                color: #17211d;\n            }\n            #previewLabel {\n                background: #ded6c7;\n                border: 1px solid #d3c6b4;\n                border-radius: 20px;\n                padding: 22px;\n                color: #59645d;\n                font-weight: 700;\n            }\n            QScrollArea {\n                border: 0;\n                background: #ded6c7;\n                border-radius: 20px;\n            }\n            QPushButton {\n                min-height: 34px;\n                border-radius: 10px;\n                padding: 8px 13px;\n                font-weight: 800;\n                text-align: center;\n            }\n            #primaryButton, #primaryButtonSmall {\n                background: #f16f3f;\n                color: #ffffff;\n                border: 0;\n            }\n            #primaryButton:hover, #primaryButtonSmall:hover {\n                background: #db5c2f;\n            }\n            #primaryButtonSmall {\n                min-height: 30px;\n            }\n            #secondaryButton, #darkButton {\n                background: #fff8eb;\n                color: #16231e;\n                border: 0;\n            }\n            #secondaryButton:hover, #darkButton:hover {\n                background: #ffffff;\n            }\n            #ghostButton {\n                background: rgba(255, 248, 235, 0.10);\n                color: #fff8eb;\n                border: 1px solid rgba(255, 248, 235, 0.25);\n            }\n            #ghostButton:hover {\n                background: rgba(255, 248, 235, 0.18);\n            }\n            #lightGhostButton {\n                background: #eee5d6;\n                color: #17211d;\n                border: 1px solid #d8ccbc;\n            }\n            #lightGhostButton:hover {\n                background: #fff8eb;\n                border-color: #f16f3f;\n            }\n            #toolButton, #flatButton {\n                background: #efe6d7;\n                color: #17211d;\n                border: 1px solid #d8ccbc;\n            }\n            #toolButton:hover, #flatButton:hover {\n                background: #fff2df;\n                border-color: #f16f3f;\n            }\n            #dangerButton {\n                background: #2b1712;\n                color: #fff8eb;\n                border: 0;\n            }\n            #dangerButton:hover {\n                background: #5a2419;\n            }\n            QPushButton:disabled {\n                background: #ded7ca;\n                color: #9a9387;\n                border: 1px solid #d2c8ba;\n            }\n            #profileCombo, #toolCombo {\n                background: #ffffff;\n                color: #17211d;\n                border: 1px solid #d6caba;\n                border-radius: 10px;\n                padding: 8px;\n                min-height: 34px;\n            }\n            #toolStack, #toolPage {\n                background: transparent;\n                border: 0;\n            }\n            #optionCheck {\n                color: #26332d;\n                font-weight: 650;\n                spacing: 8px;\n            }\n            #progressBar {\n                background: #eadfd0;\n                color: #17211d;\n                border: 0;\n                border-radius: 9px;\n                min-height: 18px;\n                text-align: center;\n                font-weight: 800;\n            }\n            #progressBar::chunk {\n                background: #f16f3f;\n                border-radius: 9px;\n            }\n            #logOutput {\n                background: #171f1b;\n                color: #fff8eb;\n                border: 0;\n                border-radius: 14px;\n                padding: 10px;\n                font-family: "Cascadia Mono", "Consolas", monospace;\n                font-size: 9pt;\n            }\n            #toolsFooter {\n                color: #7b837b;\n                font-size: 8.5pt;\n                font-weight: 700;\n            }\n            QStatusBar {\n                background: #101713;\n                color: #fff8eb;\n                border: 0;\n            }\n            '
        )
