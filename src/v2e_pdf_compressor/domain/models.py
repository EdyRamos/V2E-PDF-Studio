from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class CompressionProfile(str, Enum):
    SCREEN = "screen"
    EBOOK = "ebook"
    PRINTER = "printer"

    @classmethod
    def from_value(cls, value: str) -> CompressionProfile:
        if not value:
            return cls.EBOOK
        normalized = str(value).strip().lower()
        for option in cls:
            if option.value == normalized:
                return option
        return cls.EBOOK


class CompressionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorCode(str, Enum):
    INPUT_NOT_FOUND = "INPUT_NOT_FOUND"
    INVALID_EXTENSION = "INVALID_EXTENSION"
    SAME_INPUT_OUTPUT = "SAME_INPUT_OUTPUT"
    OUTPUT_EXISTS = "OUTPUT_EXISTS"
    OUTPUT_PARENT_MISSING = "OUTPUT_PARENT_MISSING"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    GHOSTSCRIPT_NOT_FOUND = "GHOSTSCRIPT_NOT_FOUND"
    GHOSTSCRIPT_RUNTIME_INVALID = "GHOSTSCRIPT_RUNTIME_INVALID"
    PDF_PASSWORD_PROTECTED = "PDF_PASSWORD_PROTECTED"
    PDF_CORRUPTED = "PDF_CORRUPTED"
    PROCESS_TIMEOUT = "PROCESS_TIMEOUT"
    PROCESS_FAILED = "PROCESS_FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass(slots=True)
class CompressionJob:
    input_path: Path
    output_path: Path
    profile: CompressionProfile = CompressionProfile.EBOOK
    overwrite: bool = False
    optimize: bool = True


@dataclass(slots=True)
class CompressionResult:
    input_path: Path
    output_path: Path
    status: CompressionStatus
    error_code: ErrorCode | None
    before_mb: float | None
    after_mb: float | None
    reduction_percent: float | None
    elapsed_ms: int
    error_detail: str | None = None


@dataclass(slots=True)
class BatchResult:
    total: int
    success: int
    failed: int
    cancelled: int
    items: list[CompressionResult] = field(default_factory=list)
