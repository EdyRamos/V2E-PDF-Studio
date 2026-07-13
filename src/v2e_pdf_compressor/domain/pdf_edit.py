from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

A4_WIDTH_PT = 595
A4_HEIGHT_PT = 842


@dataclass(slots=True)
class PdfPageItem:
    page_id: str
    source_path: Path | None
    source_page_index: int | None
    rotation: int = 0
    blank_width: float = float(A4_WIDTH_PT)
    blank_height: float = float(A4_HEIGHT_PT)

    @classmethod
    def from_source(cls, source_path: Path, source_page_index: int) -> PdfPageItem:
        return cls(
            page_id=uuid4().hex,
            source_path=Path(source_path).resolve(),
            source_page_index=source_page_index,
        )

    @classmethod
    def blank(cls) -> PdfPageItem:
        return cls(page_id=uuid4().hex, source_path=None, source_page_index=None)

    @property
    def is_blank(self) -> bool:
        return self.source_path is None


@dataclass(slots=True)
class PdfDocumentSession:
    original_path: Path | None
    pages: list[PdfPageItem] = field(default_factory=list)
    modified: bool = False

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def title(self) -> str:
        if self.original_path:
            return self.original_path.name
        return "Documento sem nome"


@dataclass(slots=True)
class ExportOptions:
    output_path: Path
    overwrite: bool = False
    compress_after_export: bool = False


@dataclass(slots=True)
class RenderedPage:
    page_id: str
    width: int
    height: int
    png_bytes: bytes
