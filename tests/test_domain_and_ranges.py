from __future__ import annotations

import pytest

from v2e_pdf_compressor.application.pdf_edit import PdfEditError, parse_page_ranges
from v2e_pdf_compressor.domain import CompressionProfile


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("screen", CompressionProfile.SCREEN),
        (" EBOOK ", CompressionProfile.EBOOK),
        ("printer", CompressionProfile.PRINTER),
        ("unknown", CompressionProfile.EBOOK),
        ("", CompressionProfile.EBOOK),
    ],
)
def test_compression_profile_normalization(value: str, expected: CompressionProfile) -> None:
    assert CompressionProfile.from_value(value) is expected


def test_parse_page_ranges() -> None:
    assert parse_page_ranges("1-3, 5, 8-10", 10) == [
        [0, 1, 2],
        [4],
        [7, 8, 9],
    ]


@pytest.mark.parametrize("value", ["", "0", "3-2", "1-9", "x", "1--2"])
def test_parse_page_ranges_rejects_invalid_input(value: str) -> None:
    with pytest.raises(PdfEditError):
        parse_page_ranges(value, 5)
