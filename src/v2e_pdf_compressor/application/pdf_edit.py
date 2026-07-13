from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import fitz

from ..domain import ExportOptions, PdfDocumentSession, PdfPageItem, RenderedPage


class PdfEditError(Exception):
    pass


class PdfPasswordRequiredError(PdfEditError):
    pass


class PdfEditService:
    def open_document(self, path: Path) -> PdfDocumentSession:
        path = path.resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        if path.suffix.lower() != ".pdf":
            raise PdfEditError("Somente arquivos PDF sao aceitos.")
        with fitz.open(path) as document:
            if document.needs_pass:
                raise PdfPasswordRequiredError("PDF protegido por senha.")
            pages = [PdfPageItem.from_source(path, index) for index in range(document.page_count)]
        return PdfDocumentSession(original_path=path, pages=pages, modified=False)

    def render_page(self, page: PdfPageItem, scale: float = 1.0) -> RenderedPage:
        if page.is_blank:
            doc = fitz.open()
            doc.new_page(width=page.blank_width, height=page.blank_height)
            try:
                pixmap = doc[0].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                return RenderedPage(
                    page.page_id,
                    pixmap.width,
                    pixmap.height,
                    pixmap.tobytes("png"),
                )
            finally:
                doc.close()

        if page.source_path is None or page.source_page_index is None:
            raise PdfEditError("Pagina sem origem valida.")
        with fitz.open(page.source_path) as document:
            source_page = document.load_page(page.source_page_index)
            matrix = fitz.Matrix(scale, scale).prerotate(page.rotation)
            pixmap = source_page.get_pixmap(matrix=matrix, alpha=False)
            return RenderedPage(
                page.page_id,
                pixmap.width,
                pixmap.height,
                pixmap.tobytes("png"),
            )

    def reorder_by_page_ids(self, session: PdfDocumentSession, page_ids: list[str]) -> None:
        by_id = {page.page_id: page for page in session.pages}
        if set(by_id) != set(page_ids):
            raise PdfEditError("Ordem de paginas invalida.")
        session.pages = [by_id[page_id] for page_id in page_ids]
        session.modified = True

    def remove_pages(self, session: PdfDocumentSession, page_ids: set[str]) -> None:
        session.pages = [page for page in session.pages if page.page_id not in page_ids]
        session.modified = True

    def insert_pdf(
        self,
        session: PdfDocumentSession,
        source_path: Path,
        after_page_id: str | None = None,
    ) -> list[str]:
        inserted = self.open_document(source_path).pages
        insert_at = len(session.pages)
        if after_page_id:
            for index, page in enumerate(session.pages):
                if page.page_id == after_page_id:
                    insert_at = index + 1
                    break
        session.pages[insert_at:insert_at] = inserted
        session.modified = True
        return [page.page_id for page in inserted]

    def add_blank_page(self, session: PdfDocumentSession, after_page_id: str | None = None) -> None:
        insert_at = len(session.pages)
        if after_page_id:
            for index, page in enumerate(session.pages):
                if page.page_id == after_page_id:
                    insert_at = index + 1
                    break
        session.pages.insert(insert_at, PdfPageItem.blank())
        session.modified = True

    def export_document(self, session: PdfDocumentSession, options: ExportOptions) -> Path:
        output_path = options.output_path.resolve()
        if output_path.suffix.lower() != ".pdf":
            output_path = output_path.with_suffix(".pdf")
        if output_path.exists() and not options.overwrite:
            raise FileExistsError(output_path)
        document = self._build_document(session.pages)
        try:
            self._save_document_atomically(document, output_path, options.overwrite)
        finally:
            document.close()
        session.modified = False
        session.original_path = output_path
        return output_path

    def split_selected(
        self,
        session: PdfDocumentSession,
        page_ids: set[str],
        output_path: Path,
        overwrite: bool = False,
    ) -> Path:
        selected_pages = [page for page in session.pages if page.page_id in page_ids]
        if not selected_pages:
            raise PdfEditError("Nenhuma pagina selecionada para dividir.")
        return self._export_pages(selected_pages, output_path, overwrite)

    def split_ranges(
        self,
        session: PdfDocumentSession,
        ranges_text: str,
        output_dir: Path,
        base_name: str,
        overwrite: bool = False,
    ) -> list[Path]:
        ranges = parse_page_ranges(ranges_text, session.page_count)
        output_dir.mkdir(parents=True, exist_ok=True)
        outputs: list[Path] = []
        for index, page_indexes in enumerate(ranges, start=1):
            pages = [session.pages[page_index] for page_index in page_indexes]
            output_path = output_dir / f"{base_name}_parte_{index}.pdf"
            outputs.append(self._export_pages(pages, output_path, overwrite))
        return outputs

    def _export_pages(self, pages: list[PdfPageItem], output_path: Path, overwrite: bool) -> Path:
        output_path = output_path.resolve()
        if output_path.suffix.lower() != ".pdf":
            output_path = output_path.with_suffix(".pdf")
        if output_path.exists() and not overwrite:
            raise FileExistsError(output_path)
        document = self._build_document(pages)
        try:
            self._save_document_atomically(document, output_path, overwrite)
        finally:
            document.close()
        return output_path

    def _build_document(self, pages: list[PdfPageItem]) -> fitz.Document:
        output = fitz.open()
        source_cache: dict[Path, fitz.Document] = {}
        try:
            for page in pages:
                if page.is_blank:
                    output.new_page(width=page.blank_width, height=page.blank_height)
                    continue
                if page.source_path is None or page.source_page_index is None:
                    raise PdfEditError("Pagina sem origem valida.")
                source = source_cache.get(page.source_path)
                if source is None:
                    source = fitz.open(page.source_path)
                    source_cache[page.source_path] = source
                output.insert_pdf(
                    source,
                    from_page=page.source_page_index,
                    to_page=page.source_page_index,
                    rotate=page.rotation,
                )
            for source in source_cache.values():
                source.close()
            return output
        except Exception:
            output.close()
            for source in source_cache.values():
                source.close()
            raise

    def _save_document_atomically(
        self,
        document: fitz.Document,
        output_path: Path,
        overwrite: bool,
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists() and not overwrite:
            raise FileExistsError(output_path)

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=f".{output_path.stem}.",
                suffix=".tmp.pdf",
                dir=output_path.parent,
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
            document.save(temp_path, garbage=4, deflate=True)
            self._validate_generated_pdf(temp_path, len(document))
            os.replace(temp_path, output_path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    @staticmethod
    def _validate_generated_pdf(path: Path, expected_pages: int) -> None:
        if not path.is_file() or path.stat().st_size == 0:
            raise PdfEditError("O PDF gerado esta vazio.")
        try:
            with fitz.open(path) as generated:
                if generated.needs_pass:
                    raise PdfEditError("O PDF gerado exige senha inesperadamente.")
                if generated.page_count != expected_pages:
                    raise PdfEditError(
                        "A validacao do PDF gerado encontrou quantidade de paginas diferente."
                    )
        except PdfEditError:
            raise
        except Exception as exc:
            raise PdfEditError("O arquivo gerado nao e um PDF valido.") from exc


def parse_page_ranges(ranges_text: str, page_count: int) -> list[list[int]]:
    if page_count <= 0:
        raise PdfEditError("Documento sem paginas.")
    tokens = [token.strip() for token in ranges_text.split(",") if token.strip()]
    if not tokens:
        raise PdfEditError("Informe ao menos um intervalo.")

    ranges: list[list[int]] = []
    for token in tokens:
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", token)
        if not match:
            raise PdfEditError(f"Intervalo invalido: {token}")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start < 1 or end < 1 or start > page_count or end > page_count or start > end:
            raise PdfEditError(f"Intervalo fora do documento: {token}")
        ranges.append(list(range(start - 1, end)))
    return ranges
