from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..application.eprotocol import natural_key


class EProtocolDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preparar documentos para eProtocolo")
        self.resize(950, 720)
        self.setMinimumSize(680, 420)
        self.setStyleSheet("""
            QDialog { background: #f5f1e8; }
            QWidget { color: #17211d; font-family: 'Segoe UI'; font-size: 10pt; }
            QPushButton { background: #ffffff; border: 1px solid #d6caba;
                border-radius: 7px; padding: 8px 12px; font-weight: 600; }
            QPushButton:hover { background: #fff7ec; border-color: #f16f3f; }
            QPushButton:disabled { color: #969b96; background: #eee9df; }
            QPushButton#eprotocolPrimary { background: #d9552a; color: white; border: 0; font-weight: 700; }
            QPushButton#eprotocolPrimary:hover { background: #bc4620; }
            QPushButton#eprotocolPrimary:disabled { background: #c9c0b5; color: #ece8e1; }
            QLabel#eprotocolTitle { font-size: 19pt; font-weight: 700; color: #17211d; }
            QLabel#eprotocolSection { font-size: 11pt; font-weight: 700; color: #304039; }
            QListWidget, QLineEdit, QComboBox, QSpinBox { background: white;
                border: 1px solid #d6caba; border-radius: 7px; padding: 7px; }
            QListWidget::item { padding: 6px; }
            QListWidget::item:selected { background: #f16f3f; color: white; }
            QProgressBar { background: #eadfd0; border: 0; border-radius: 6px; }
            QProgressBar::chunk { background: #f16f3f; border-radius: 6px; }
        """)
        self.setAcceptDrops(True)
        self.entries: dict[str, str] = {}
        self.session = None
        self.process = QProcess(self)
        self.process.finished.connect(self.worker_finished)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.destination = ""
        self.result_dir = ""
        self.ignored_files = []
        self.edit_controls = []
        self.close_after_cancel = False
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        title = QLabel("Preparar para eProtocolo")
        title.setObjectName("eprotocolTitle")
        layout.addWidget(title)
        layout.addWidget(
            QLabel("Organize documentos em partes para envio, com processamento local.")
        )
        section = QLabel("1. Escolha o formato")
        section.setObjectName("eprotocolSection")
        layout.addWidget(section)
        self.mode = QComboBox()
        self.mode.addItem("PDFs independentes", "pdf")
        self.mode.addItem("Pacote de anexos (ZIP dividido)", "archive")
        layout.addWidget(self.mode)
        help_text = QLabel(
            "O tutorial informa 100M por arquivo e por envio de anexos. "
            "Envie uma parte por vez; confirme as regras do processo no portal."
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        section = QLabel("2. Selecione e organize os arquivos")
        section.setObjectName("eprotocolSection")
        layout.addWidget(section)
        row = QHBoxLayout()
        for label, action in (
            ("Adicionar arquivos", self.add_files),
            ("Adicionar pasta", self.add_folder),
            ("Remover", self.remove_selected),
            ("Ordem inicial", self.sort_entries),
        ):
            button = QPushButton(label)
            button.clicked.connect(action)
            row.addWidget(button)
            self.edit_controls.append(button)
        layout.addLayout(row)
        self.recursive = QCheckBox("Incluir subpastas ao selecionar pasta")
        layout.addWidget(self.recursive)
        self.mode.currentIndexChanged.connect(self.change_mode)
        self.queue = QListWidget()
        self.queue.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.queue.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        layout.addWidget(self.queue, 1)
        move = QHBoxLayout()
        for label, direction in (("Mover para cima", -1), ("Mover para baixo", 1)):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, n=direction: self.move_row(n))
            move.addWidget(button)
            self.edit_controls.append(button)
        layout.addLayout(move)
        section = QLabel("3. Defina o nome e o destino")
        section.setObjectName("eprotocolSection")
        layout.addWidget(section)
        self.base = QLineEdit("Processo")
        self.base.setPlaceholderText("Nome base dos arquivos")
        layout.addWidget(self.base)
        options = QHBoxLayout()
        options.addWidget(QLabel("Máximo por parte (MB decimal):"))
        self.max_size = QSpinBox()
        self.max_size.setRange(5, 90)
        self.max_size.setValue(90)
        options.addWidget(self.max_size)
        options.addWidget(QLabel("Qualidade PDF:"))
        self.profile = QComboBox()
        self.profile.addItem("Equilibrado", "ebook")
        self.profile.addItem("Alta qualidade", "printer")
        self.profile.addItem("Sem otimização", "")
        options.addWidget(self.profile)
        options.addStretch()
        layout.addLayout(options)
        self.destination_button = QPushButton("Escolher pasta de destino")
        self.destination_button.clicked.connect(self.choose_destination)
        layout.addWidget(self.destination_button)
        self.edit_controls.extend(
            [self.recursive, self.base, self.max_size, self.profile, self.destination_button]
        )
        self.state = QLabel("Selecione os documentos. A lista pode ser reordenada.")
        self.state.setWordWrap(True)
        layout.addWidget(self.state)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        actions = QHBoxLayout()
        self.start_button = QPushButton("Preparar documentos")
        self.start_button.setObjectName("eprotocolPrimary")
        self.start_button.clicked.connect(self.start)
        self.cancel_button = QPushButton("Cancelar processamento")
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.setEnabled(False)
        self.open_button = QPushButton("Abrir pasta de resultado")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.result_dir))
        )
        self.report_button = QPushButton("Abrir relatório")
        self.report_button.setEnabled(False)
        self.report_button.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(Path(self.result_dir) / "relatorio.html"))
            )
        )
        for button in (self.start_button, self.cancel_button, self.open_button, self.report_button):
            actions.addWidget(button)
        layout.addLayout(actions)

    def change_mode(self):
        self.recursive.setChecked(self.mode.currentData() == "archive")
        self.profile.setEnabled(self.mode.currentData() == "pdf")

    def add_files(self):
        names, _ = QFileDialog.getOpenFileNames(self, "Selecionar arquivos")
        self.add_paths([Path(name) for name in names])

    def add_folder(self):
        selected = QFileDialog.getExistingDirectory(self, "Selecionar pasta")
        if selected:
            self.add_paths([Path(selected)])

    def add_paths(self, paths):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        candidates = []
        for path in paths:
            if path.is_symlink():
                continue
            if path.is_dir():
                iterator = path.rglob("*") if self.recursive.isChecked() else path.iterdir()
                for item in iterator:
                    if item.is_file() and not any(
                        p.is_symlink() for p in [item, *item.parents] if p != path.parent
                    ):
                        candidates.append((item, str(item.relative_to(path))))
            elif path.is_file():
                candidates.append((path, path.name))
        for path, relative in sorted(candidates, key=lambda value: natural_key(Path(value[1]))):
            key = str(path.resolve())
            if key in self.entries:
                continue
            self.entries[key] = relative
            item = QListWidgetItem(f"{relative} — {path.stat().st_size / 1_000_000:.2f} MB")
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.queue.addItem(item)

    def remove_selected(self):
        for item in self.queue.selectedItems():
            self.entries.pop(item.data(Qt.ItemDataRole.UserRole), None)
            self.queue.takeItem(self.queue.row(item))

    def sort_entries(self):
        items = [self.queue.takeItem(0) for _ in range(self.queue.count())]
        for item in sorted(
            items, key=lambda it: natural_key(Path(self.entries[it.data(Qt.ItemDataRole.UserRole)]))
        ):
            self.queue.addItem(item)

    def move_row(self, direction):
        row = self.queue.currentRow()
        target = row + direction
        if row >= 0 and 0 <= target < self.queue.count():
            item = self.queue.takeItem(row)
            self.queue.insertItem(target, item)
            self.queue.setCurrentRow(target)

    def choose_destination(self):
        selected = QFileDialog.getExistingDirectory(self, "Pasta de destino")
        if selected:
            self.destination = selected
            self.destination_button.setText(f"Destino: {selected}")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_paths(
            [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        )
        event.acceptProposedAction()

    def start(self):
        if not self.destination or not self.queue.count():
            QMessageBox.warning(self, "Documentos", "Selecione documentos e a pasta de destino.")
            return
        entries = [
            {
                "path": self.queue.item(i).data(Qt.ItemDataRole.UserRole),
                "relative": self.entries[self.queue.item(i).data(Qt.ItemDataRole.UserRole)],
            }
            for i in range(self.queue.count())
        ]
        if self.mode.currentData() == "pdf":
            ignored = [e["relative"] for e in entries if Path(e["path"]).suffix.lower() != ".pdf"]
            if ignored:
                QMessageBox.information(
                    self,
                    "Arquivos ignorados",
                    "Os arquivos abaixo não são PDFs e não serão incluídos:\n" + "\n".join(ignored),
                )
                entries = [e for e in entries if Path(e["path"]).suffix.lower() == ".pdf"]
            if not entries:
                QMessageBox.warning(self, "Documentos", "A lista não contém PDFs.")
                return
            self.ignored_files = ignored
        else:
            self.ignored_files = []
        self.session = tempfile.TemporaryDirectory(prefix="v2e-worker-")
        root = Path(self.session.name)
        self.status_path, self.cancel_path = root / "status.json", root / "cancel"
        request = root / "request.json"
        self.worker_request = {
            "mode": "inspect" if self.mode.currentData() == "pdf" else "archive",
            "entries": entries,
            "destination": self.destination,
            "base_name": self.base.text(),
            "max_bytes": self.max_size.value() * 1_000_000,
            "profile": self.profile.currentData(),
            "allow_signed": False,
        }
        request.write_text(json.dumps(self.worker_request, ensure_ascii=False), encoding="utf-8")
        self.request_path = request
        if not self.launch_worker():
            self.state.setText("Não foi possível iniciar o processamento.")
            self.session.cleanup()
            self.session = None
            return
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.open_button.setEnabled(False)
        self.report_button.setEnabled(False)
        self.queue.setEnabled(False)
        self.mode.setEnabled(False)
        for control in self.edit_controls:
            control.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.timer.start(300)

    def launch_worker(self):
        arguments = (
            []
            if getattr(sys, "frozen", False)
            else [str(Path(__file__).resolve().parents[3] / "app.py")]
        )
        arguments += [
            "--eprotocol-worker",
            str(self.request_path),
            str(self.status_path),
            str(self.cancel_path),
        ]
        self.process.start(sys.executable, arguments)
        return self.process.waitForStarted(5000)

    def poll(self):
        try:
            payload = json.loads(self.status_path.read_text(encoding="utf-8"))
            if payload.get("status") == "working":
                self.state.setText(payload.get("message", "Processando..."))
        except (OSError, ValueError):
            pass

    def cancel(self):
        if self.session:
            self.cancel_path.touch()
            self.state.setText("Cancelando e removendo temporários...")
            self.cancel_button.setEnabled(False)

    def worker_finished(self, _code, _status):
        self.timer.stop()
        try:
            payload = json.loads(self.status_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {"status": "error", "message": "O processo terminou sem resultado."}
        if payload.get("status") == "inspected" and not self.cancel_path.exists():
            signed = [Path(item["path"]).name for item in payload["items"] if item["signed"]]
            forms = [Path(item["path"]).name for item in payload["items"] if item["forms"]]
            for item in payload["items"]:
                for index in range(self.queue.count()):
                    entry = self.queue.item(index)
                    if Path(entry.data(Qt.ItemDataRole.UserRole)) == Path(item["path"]):
                        entry.setText(
                            f"{self.entries[entry.data(Qt.ItemDataRole.UserRole)]} — {item['pages']} páginas"
                        )
                        break
            if forms:
                allow_forms = (
                    QMessageBox.question(
                        self,
                        "Formulários detectados",
                        "Os campos preenchidos serão convertidos em cópias estáticas nos arquivos:\n"
                        + "\n".join(forms)
                        + "\n\nContinuar?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    == QMessageBox.StandardButton.Yes
                )
            else:
                allow_forms = True
            if allow_forms:
                approved = (
                    not signed
                    or QMessageBox.question(
                        self,
                        "Assinaturas digitais detectadas",
                        "As cópias não preservarão a validade das assinaturas destes arquivos:\n"
                        + "\n".join(signed)
                        + "\n\nContinuar?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    == QMessageBox.StandardButton.Yes
                )
                if approved:
                    self.worker_request["mode"] = "pdf"
                    self.worker_request["allow_signed"] = bool(signed)
                    self.worker_request["allow_forms"] = bool(forms)
                    self.request_path.write_text(
                        json.dumps(self.worker_request, ensure_ascii=False), encoding="utf-8"
                    )
                    self.status_path.unlink(missing_ok=True)
                    if self.launch_worker():
                        self.timer.start(300)
                        return
                    payload = {"status": "error", "message": "Falha ao iniciar geração dos PDFs."}
                else:
                    payload = {"status": "error", "message": "Operação cancelada pelo usuário."}
            else:
                payload = {"status": "error", "message": "Operação cancelada pelo usuário."}
        if payload.get("status") == "success":
            self.result_dir = payload["directory"]
            self.open_button.setEnabled(True)
            self.report_button.setEnabled(True)
            self.state.setText(
                f"Concluído: {len(payload['parts'])} parte(s). Envie uma por vez, em ordem. "
                + " ".join(payload.get("warnings", []))
                + (" Ignorados: " + ", ".join(self.ignored_files) if self.ignored_files else "")
            )
        else:
            self.state.setText(payload.get("message", "Falha no processamento."))
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.queue.setEnabled(True)
        self.mode.setEnabled(True)
        for control in self.edit_controls:
            control.setEnabled(True)
        self.change_mode_profile()
        self.progress.setVisible(False)
        if self.session:
            self.session.cleanup()
            self.session = None
        if self.close_after_cancel:
            self.accept()

    def change_mode_profile(self):
        self.profile.setEnabled(self.mode.currentData() == "pdf")

    def closeEvent(self, event):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            answer = QMessageBox.question(
                self,
                "Processamento em andamento",
                "Cancelar processamento e fechar quando terminar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.close_after_cancel = True
                self.cancel()
            event.ignore()
            return
        event.accept()

    def reject(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.close()
            return
        super().reject()
