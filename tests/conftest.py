from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def make_pdf(tmp_path: Path):
    def factory(
        name: str = "sample.pdf",
        pages: int = 3,
        *,
        password: str | None = None,
    ) -> Path:
        path = tmp_path / name
        document = fitz.open()
        for index in range(pages):
            page = document.new_page(width=300, height=300)
            page.insert_text((30, 80), f"V2E page {index + 1}")
        save_args: dict[str, object] = {}
        if password:
            save_args = {
                "encryption": fitz.PDF_ENCRYPT_AES_256,
                "owner_pw": password,
                "user_pw": password,
            }
        document.save(path, **save_args)
        document.close()
        return path

    return factory
