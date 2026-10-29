"""Local eProtocolo preparation primitives.

This module does not upload documents. Outputs are staged before publication.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import fitz

from ..domain import CompressionJob, CompressionProfile, CompressionStatus
from .service import PdfCompressionService


class EProtocolError(RuntimeError):
    """The operation cannot safely produce a complete result."""


class EProtocolCancelled(EProtocolError):
    pass


@dataclass(frozen=True, slots=True)
class PdfInput:
    path: Path
    pages: int
    signed: bool
    forms: bool
    sha256: str


@dataclass(frozen=True, slots=True)
class EProtocolRequest:
    inputs: tuple[Path, ...]
    destination: Path
    base_name: str
    max_bytes: int = 90_000_000
    profile: CompressionProfile | None = CompressionProfile.EBOOK
    allow_signed: bool = False
    allow_forms: bool = False


@dataclass(frozen=True, slots=True)
class ArchiveEntry:
    path: Path
    relative_path: str


@dataclass(frozen=True, slots=True)
class ArchiveRequest:
    entries: tuple[ArchiveEntry, ...]
    destination: Path
    base_name: str
    max_bytes: int = 90_000_000


@dataclass(frozen=True, slots=True)
class EProtocolResult:
    directory: Path
    parts: tuple[Path, ...]
    warnings: tuple[str, ...]


def natural_key(path: Path) -> tuple[tuple[int, str | int], ...]:
    tokens = tuple(
        (1, int(part)) if part.isdigit() else (0, part.casefold())
        for part in re.split(r"(\d+)", str(path))
    )
    return (*tokens, (0, str(path).casefold()), (0, str(path)))


def is_link_path(path: Path) -> bool:
    return any(
        item.is_symlink() or bool(getattr(item, "is_junction", lambda: False)())
        for item in (path, *path.parents)
    )


def sha256_file(path: Path, check: Callable[[], None] | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            if check is not None:
                check()
            digest.update(block)
    return digest.hexdigest()


def write_report(directory: Path, parts: list[Path], warnings: list[str]) -> None:
    rows = "".join(
        f"<li>{html.escape(part.name)} — {part.stat().st_size / 1_000_000:.2f} MB</li>"
        for part in parts
    )
    notices = "".join(f"<li>{html.escape(warning)}</li>" for warning in warnings)
    (directory / "relatorio.html").write_text(
        '<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
        "<title>Resultado eProtocolo</title><body><h1>Documentos preparados</h1>"
        "<p>Envie uma parte por vez, em ordem. Confirme as regras do processo no portal.</p>"
        f"<ol>{rows}</ol><h2>Avisos</h2><ul>{notices}</ul></body></html>",
        encoding="utf-8",
    )


class EProtocolService:
    def __init__(self, compressor: PdfCompressionService) -> None:
        self.compressor = compressor
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()
        self.compressor.cancel()

    def _check_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise EProtocolCancelled("Operação cancelada.")

    def prepare_archive(
        self, request: ArchiveRequest, progress: Callable[[str], None] | None = None
    ) -> EProtocolResult:
        """Archive exact originals, verify a full extraction, then publish the set."""
        self._cancelled.clear()
        notify = progress or (lambda _message: None)
        if not request.entries or not 5_000_000 <= request.max_bytes <= 90_000_000:
            raise EProtocolError("Selecione arquivos e um limite entre 5 e 90 MB.")
        if (
            not request.base_name.strip()
            or request.base_name in {".", ".."}
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', request.base_name)
            or request.base_name.endswith((" ", "."))
        ):
            raise EProtocolError("Nome base inválido para Windows.")
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
        executable = root / "vendor" / "7zip" / "x64" / "7za.exe"
        if not executable.is_file():
            raise EProtocolError("O compactador 7-Zip incorporado não foi encontrado.")
        destination = request.destination.resolve(strict=True)
        required = sum(entry.path.stat().st_size for entry in request.entries) * 3 + 64_000_000
        if shutil.disk_usage(destination).free < required:
            raise EProtocolError("Espaço livre insuficiente para criar e verificar o pacote.")
        stage = Path(tempfile.mkdtemp(prefix=".v2e-eprotocolo-", dir=destination))
        inputs = stage / "inputs"
        verified = stage / "verified"
        outputs = stage / "result"
        inputs.mkdir()
        outputs.mkdir()
        expected: dict[str, str] = {}
        try:
            for entry in request.entries:
                self._check_cancelled()
                relative = Path(entry.relative_path)
                if (
                    relative.is_absolute()
                    or not relative.parts
                    or ".." in relative.parts
                    or any(part in {"", "."} or ":" in part for part in relative.parts)
                ):
                    raise EProtocolError("Caminho de arquivo inválido no pacote.")
                key = relative.as_posix().casefold()
                if key in expected:
                    raise EProtocolError(f"Nomes duplicados no pacote: {relative}")
                source = entry.path.resolve(strict=True)
                if not source.is_file() or is_link_path(entry.path):
                    raise EProtocolError(f"Arquivo inválido ou link: {entry.path.name}")
                notify(f"Preparando {entry.path.name}...")
                target = inputs / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = sha256_file(source, self._check_cancelled)
                with source.open("rb") as source_stream, target.open("wb") as target_stream:
                    while block := source_stream.read(1024 * 1024):
                        self._check_cancelled()
                        target_stream.write(block)
                if (
                    sha256_file(target, self._check_cancelled) != digest
                    or sha256_file(source, self._check_cancelled) != digest
                ):
                    raise EProtocolError(f"Arquivo alterado durante leitura: {source.name}")
                expected[key] = digest
            archive = outputs / f"{request.base_name}.zip"

            def run(command: list[str], cwd: Path) -> None:
                process = subprocess.Popen(
                    command,
                    cwd=cwd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                while process.poll() is None:
                    if self._cancelled.wait(0.2):
                        process.kill()
                        process.wait()
                        raise EProtocolCancelled("Operação cancelada.")
                if process.returncode:
                    raise EProtocolError(f"Falha no compactador (código {process.returncode}).")

            notify("Criando pacote dividido...")
            run(
                [
                    str(executable),
                    "a",
                    "-tzip",
                    "-mm=Deflate",
                    "-mx=5",
                    f"-v{request.max_bytes}b",
                    "-y",
                    str(archive),
                    ".",
                ],
                inputs,
            )
            parts = sorted(
                (p for p in outputs.iterdir() if p.name.startswith(f"{request.base_name}.zip.")),
                key=lambda p: int(p.suffix[1:]),
            )
            if len(parts) == 1:
                parts[0].rename(archive)
                parts = [archive]
            if not parts or any(p.stat().st_size > request.max_bytes for p in parts):
                raise EProtocolError("Pacote ausente ou parte acima do limite.")
            notify("Validando conteúdo do pacote...")
            run([str(executable), "t", str(parts[0]), "-y"], outputs)
            verified.mkdir()
            run([str(executable), "x", str(parts[0]), f"-o{verified}", "-y"], outputs)
            found = {
                p.relative_to(verified).as_posix().casefold(): sha256_file(p, self._check_cancelled)
                for p in verified.rglob("*")
                if p.is_file()
            }
            if found != expected:
                raise EProtocolError("Os arquivos extraídos diferem dos originais.")
            self._check_cancelled()
            for entry in request.entries:
                if (
                    sha256_file(entry.path, self._check_cancelled)
                    != expected[Path(entry.relative_path).as_posix().casefold()]
                ):
                    raise EProtocolError(f"Arquivo de entrada alterado: {entry.path.name}")
            (outputs / "manifesto.json").write_text(
                json.dumps(
                    {
                        "inputs": [
                            {
                                "name": e.relative_path,
                                "sha256": expected[Path(e.relative_path).as_posix().casefold()],
                            }
                            for e in request.entries
                        ],
                        "parts": [
                            {"name": p.name, "size": p.stat().st_size, "sha256": sha256_file(p)}
                            for p in parts
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (outputs / "LEIA-ME.txt").write_text(
                "Envie uma parte por vez, em ordem. Para extrair, reúna todas na mesma pasta e abra a primeira parte com 7-Zip.\n",
                encoding="utf-8",
            )
            write_report(outputs, parts, [])
            suffix = 1
            while True:
                final = destination / (
                    request.base_name if suffix == 1 else f"{request.base_name}_{suffix}"
                )
                try:
                    outputs.rename(final)
                    break
                except FileExistsError:
                    suffix += 1
            return EProtocolResult(final, tuple(final / part.name for part in parts), ())
        finally:
            shutil.rmtree(stage)

    def inspect_pdfs(self, paths: tuple[Path, ...]) -> tuple[PdfInput, ...]:
        if not paths:
            raise EProtocolError("Selecione ao menos um PDF.")
        result = []
        seen: set[Path] = set()
        for path in paths:
            self._check_cancelled()
            if is_link_path(path):
                raise EProtocolError(f"O caminho contém link ou junção: {path.name}")
            path = path.resolve(strict=True)
            if path in seen or path.suffix.lower() != ".pdf":
                raise EProtocolError(f"Arquivo duplicado ou não é PDF: {path.name}")
            seen.add(path)
            try:
                with fitz.open(path) as document:
                    if not document.is_pdf or document.needs_pass or not document.page_count:
                        raise EProtocolError(f"PDF vazio, inválido ou protegido: {path.name}")
                    if document.embfile_count():
                        raise EProtocolError(
                            f"PDF contém anexos: {path.name}. Use pacote de anexos."
                        )
                    signed = document.get_sigflags() > 0
                    forms = False
                    for page in document:
                        for annotation in page.annots() or ():
                            if annotation.type[0] == fitz.PDF_ANNOT_FILE_ATTACHMENT:
                                raise EProtocolError(
                                    f"PDF contém anexos: {path.name}. Use pacote de anexos."
                                )
                        for widget in page.widgets() or ():
                            if widget.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                                # Treat even an empty signature field conservatively.
                                signed = True
                            else:
                                forms = True
                    result.append(
                        PdfInput(
                            path,
                            document.page_count,
                            signed,
                            forms,
                            sha256_file(path, self._check_cancelled),
                        )
                    )
            except EProtocolError:
                raise
            except (OSError, RuntimeError, ValueError) as exc:
                raise EProtocolError(f"Não foi possível ler {path.name}: {exc}") from exc
        return tuple(result)

    def prepare_pdfs(
        self,
        request: EProtocolRequest,
        progress: Callable[[str], None] | None = None,
    ) -> EProtocolResult:
        """Build and validate a set of ordered, independently readable PDFs."""
        self._cancelled.clear()
        self.compressor.reset_cancel()
        notify = progress or (lambda _message: None)
        if not 5_000_000 <= request.max_bytes <= 90_000_000:
            raise EProtocolError("O limite deve estar entre 5 e 90 MB.")
        if (
            not request.base_name.strip()
            or request.base_name in {".", ".."}
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', request.base_name)
            or request.base_name.endswith((" ", "."))
        ):
            raise EProtocolError("Nome base inválido para Windows.")
        inventory = self.inspect_pdfs(request.inputs)
        if any(item.signed for item in inventory) and not request.allow_signed:
            raise EProtocolError("PDF com assinatura detectada; confirme a geração de cópias.")
        if any(item.forms for item in inventory) and not request.allow_forms:
            raise EProtocolError("PDF com formulário: confirme a geração de cópias estáticas.")
        destination = request.destination.resolve(strict=True)
        if not destination.is_dir():
            raise EProtocolError("A pasta de destino é inválida.")
        required = sum(item.path.stat().st_size for item in inventory) * 2 + 64_000_000
        if shutil.disk_usage(destination).free < required:
            raise EProtocolError("Espaço livre insuficiente para preparar e verificar os PDFs.")
        limit = request.max_bytes * 88 // 90
        warnings: list[str] = []
        parts: list[str] = []
        references: list[dict[str, object]] = []
        baselines: dict[int, Path] = {}
        stage = Path(tempfile.mkdtemp(prefix=".v2e-eprotocolo-", dir=destination))
        current = fitz.open()
        toc: list[list[object]] = []
        try:

            def save_candidate(document: fitz.Document, markers: list[list[object]]) -> Path:
                self._check_cancelled()
                path = stage / "candidate.tmp.pdf"
                path.unlink(missing_ok=True)
                document.set_toc(markers)
                document.save(path, garbage=4, deflate=True)
                return path

            def finish() -> None:
                nonlocal current, toc
                if not current.page_count:
                    return
                candidate = save_candidate(current, toc)
                if candidate.stat().st_size > limit:
                    raise EProtocolError("Parte gerada excede o limite.")
                name = f"{request.base_name}_Parte{len(parts) + 1:02d}.pdf"
                with fitz.open(candidate) as check:
                    if check.page_count != current.page_count:
                        raise EProtocolError("Número de páginas inválido no volume.")
                candidate.rename(stage / name)
                parts.append(name)
                current.close()
                current = fitz.open()
                toc = []

            for index, item in enumerate(inventory, 1):
                self._check_cancelled()
                baseline = item.path
                if item.forms:
                    baseline = stage / f"form-{index}.tmp.pdf"
                    with fitz.open(item.path) as form_document:
                        form_document.bake(annots=False, widgets=True)
                        form_document.save(baseline, garbage=4, deflate=True)
                    warnings.append(f"{item.path.name}: formulário convertido em cópia estática.")
                baselines[index - 1] = baseline
                source_path = baseline
                verb = "Otimizando" if request.profile is not None else "Preparando"
                notify(f"{verb} envelope {index} de {len(inventory)}...")
                if request.profile is not None:
                    optimized = stage / f"source-{index}.tmp.pdf"
                    result = self.compressor.compress(
                        CompressionJob(
                            baseline, optimized, request.profile, overwrite=False, optimize=True
                        )
                    )
                    if result.status == CompressionStatus.CANCELLED:
                        raise EProtocolCancelled("Operação cancelada.")
                    if result.status != CompressionStatus.SUCCESS:
                        raise EProtocolError(
                            f"Falha ao otimizar {item.path.name}: {result.error_detail}"
                        )
                    with fitz.open(baseline) as original, fitz.open(optimized) as compressed:
                        same_text = original.page_count == compressed.page_count and all(
                            " ".join(original[p].get_text().split())
                            == " ".join(compressed[p].get_text().split())
                            and original[p].rotation == compressed[p].rotation
                            for p in range(original.page_count)
                        )
                    if same_text and optimized.stat().st_size <= baseline.stat().st_size:
                        source_path = optimized
                    else:
                        warnings.append(
                            f"{item.path.name}: original usado; otimização alterou texto ou aumentou tamanho."
                        )
                with fitz.open(source_path) as source:
                    page = 0
                    while page < source.page_count:
                        self._check_cancelled()
                        notify(f"Gerando {request.base_name}_Parte{len(parts) + 1:02d}.pdf...")
                        # Try the whole remaining document first; halve until a candidate fits.
                        count = source.page_count - page
                        if current.page_count:
                            probe = fitz.open()
                            try:
                                probe.insert_pdf(current)
                                probe.insert_pdf(
                                    source, from_page=page, to_page=source.page_count - 1
                                )
                                candidate_toc = [*toc, [1, item.path.name, current.page_count + 1]]
                                if save_candidate(probe, candidate_toc).stat().st_size > limit:
                                    finish()
                                    continue
                            finally:
                                probe.close()
                        while True:
                            probe = fitz.open()
                            try:
                                if current.page_count:
                                    probe.insert_pdf(current)
                                probe.insert_pdf(source, from_page=page, to_page=page + count - 1)
                                title = item.path.name + (" (continuação)" if page else "")
                                marker = [1, title, current.page_count + 1]
                                candidate_toc = [*toc, marker]
                                if save_candidate(probe, candidate_toc).stat().st_size <= limit:
                                    current.close()
                                    current = probe
                                    probe = None
                                    toc = candidate_toc
                                    references.append(
                                        {
                                            "file": item.path.name,
                                            "input_index": index,
                                            "part": len(parts) + 1,
                                            "from_page": page + 1,
                                            "to_page": page + count,
                                        }
                                    )
                                    page += count
                                    break
                            finally:
                                if probe is not None:
                                    probe.close()
                            if count == 1:
                                raise EProtocolError(
                                    f"Página {page + 1} de {item.path.name} excede o limite."
                                )
                            count = max(1, count // 2)
                        if page < source.page_count:
                            finish()
                if request.profile is not None:
                    optimized.unlink(missing_ok=True)
            finish()
            self._check_cancelled()
            for part_number, name in enumerate(parts, 1):
                position = 0
                with fitz.open(stage / name) as output:
                    for reference in references:
                        if reference["part"] != part_number:
                            continue
                        input_index = int(str(reference["input_index"])) - 1
                        start = int(str(reference["from_page"])) - 1
                        end = int(str(reference["to_page"]))
                        with fitz.open(baselines[input_index]) as original:
                            for page_number in range(start, end):
                                self._check_cancelled()
                                a = original[page_number]
                                b = output[position]
                                if (
                                    " ".join(a.get_text().split()) != " ".join(b.get_text().split())
                                    or a.rotation != b.rotation
                                ):
                                    raise EProtocolError(
                                        f"Conteúdo ou rotação divergente: {inventory[input_index].path.name}, página {page_number + 1}."
                                    )
                                position += 1
                    if position != output.page_count:
                        raise EProtocolError("A sequência de páginas do volume está incompleta.")
            for item in inventory:
                if sha256_file(item.path, self._check_cancelled) != item.sha256:
                    raise EProtocolError(f"Arquivo de entrada alterado: {item.path.name}")
            for baseline_path in baselines.values():
                if baseline_path.parent == stage:
                    baseline_path.unlink(missing_ok=True)
            (stage / "manifesto.json").write_text(
                json.dumps(
                    {
                        "parts": [
                            {
                                "name": name,
                                "size": (stage / name).stat().st_size,
                                "sha256": sha256_file(stage / name),
                            }
                            for name in parts
                        ],
                        "inputs": [
                            {"name": i.path.name, "sha256": i.sha256, "pages": i.pages}
                            for i in inventory
                        ],
                        "pages": references,
                        "warnings": warnings,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (stage / "candidate.tmp.pdf").unlink(missing_ok=True)
            write_report(stage, [stage / name for name in parts], warnings)
            suffix = 1
            while True:
                final = destination / (
                    request.base_name if suffix == 1 else f"{request.base_name}_{suffix}"
                )
                try:
                    stage.rename(final)
                    break
                except FileExistsError:
                    suffix += 1
            return EProtocolResult(final, tuple(final / p for p in parts), tuple(warnings))
        finally:
            current.close()
            if stage.exists():
                shutil.rmtree(stage)
