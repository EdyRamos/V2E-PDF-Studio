from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from ..domain import (
    BatchResult,
    CompressionJob,
    CompressionProfile,
    CompressionResult,
    CompressionStatus,
    ErrorCode,
)
from ..infra.ghostscript import GhostscriptLocator, GhostscriptRuntimeError

ProgressCallback = Callable[[int, int, CompressionResult], None]


def _to_mb(size_in_bytes: int) -> float:
    return size_in_bytes / 1_048_576


def _percent_reduction(before_mb: float, after_mb: float) -> float:
    if before_mb <= 0:
        return 0.0
    return ((before_mb - after_mb) / before_mb) * 100.0


def _unique_output_path(base_output: Path, reserved: set[Path]) -> Path:
    candidate = base_output
    suffix = base_output.suffix
    stem = base_output.stem
    index = 2
    while candidate.exists() or candidate.resolve() in reserved:
        candidate = base_output.with_name(f"{stem}_{index}{suffix}")
        index += 1
    return candidate


def build_batch_jobs(
    input_files: list[Path],
    output_dir: Path,
    profile: CompressionProfile,
    overwrite: bool,
    optimize: bool,
) -> list[CompressionJob]:
    jobs: list[CompressionJob] = []
    reserved: set[Path] = set()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for input_file in input_files:
        base_output = output_dir / f"{input_file.stem}_comprimido.pdf"
        target_output = base_output if overwrite else _unique_output_path(base_output, reserved)
        reserved.add(target_output.resolve())
        jobs.append(
            CompressionJob(
                input_path=input_file.resolve(),
                output_path=target_output.resolve(),
                profile=profile,
                overwrite=overwrite,
                optimize=optimize,
            )
        )
    return jobs


class PdfCompressionService:
    def __init__(
        self,
        locator: GhostscriptLocator,
        timeout_seconds: int = 600,
        logger: logging.Logger | None = None,
    ) -> None:
        self.locator = locator
        self.timeout_seconds = timeout_seconds
        self.logger = logger or logging.getLogger("v2e.service")
        self._cancel_event = threading.Event()
        self._compression_lock = threading.Lock()
        self._process_lock = threading.Lock()
        self._active_process: subprocess.Popen[str] | None = None

    def reset_cancel(self) -> None:
        self._cancel_event.clear()

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._process_lock:
            process = self._active_process
        if process is not None:
            self._terminate_process(process)

    def compress(self, job: CompressionJob) -> CompressionResult:
        started = time.perf_counter()
        if not self._compression_lock.acquire(blocking=False):
            return self._error_result(
                job,
                ErrorCode.PROCESS_FAILED,
                started,
                detail="Ja existe uma compressao em andamento.",
            )
        try:
            return self._compress_job(job)
        finally:
            self._compression_lock.release()

    def _compress_job(self, job: CompressionJob) -> CompressionResult:
        started = time.perf_counter()
        try:
            validation_error = self._validate_job(job)
            if validation_error:
                return self._error_result(job, validation_error, started)
            if self._cancel_event.is_set():
                return self._cancelled_result(job, started)

            gs_executable = self.locator.resolve_executable()
            before_mb = _to_mb(job.input_path.stat().st_size)
            command = self._build_command(gs_executable, job)
            process_env = self._build_process_env(gs_executable)
            self.logger.info("Executando Ghostscript: %s", command)

            creationflags = (
                subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            )
            completed = self._run_process(command, process_env, creationflags=creationflags)
            if completed is None:
                job.output_path.unlink(missing_ok=True)
                return self._cancelled_result(job, started)
            if completed.returncode != 0:
                error_code = self._map_subprocess_error(completed.stderr)
                self.logger.error(
                    "Falha Ghostscript returncode=%s stderr=%s",
                    completed.returncode,
                    (completed.stderr or "").strip(),
                )
                return self._error_result(
                    job,
                    error_code,
                    started,
                    detail=(completed.stderr or "").strip() or None,
                )
            if not job.output_path.exists():
                return self._error_result(
                    job,
                    ErrorCode.PROCESS_FAILED,
                    started,
                    detail="Ghostscript finalizou sem gerar arquivo de saida.",
                )

            after_mb = _to_mb(job.output_path.stat().st_size)
            reduction_percent = _percent_reduction(before_mb, after_mb)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return CompressionResult(
                input_path=job.input_path,
                output_path=job.output_path,
                status=CompressionStatus.SUCCESS,
                error_code=None,
                before_mb=before_mb,
                after_mb=after_mb,
                reduction_percent=reduction_percent,
                elapsed_ms=elapsed_ms,
            )
        except FileNotFoundError as exc:
            return self._error_result(
                job, ErrorCode.GHOSTSCRIPT_NOT_FOUND, started, detail=str(exc)
            )
        except subprocess.TimeoutExpired as exc:
            return self._error_result(job, ErrorCode.PROCESS_TIMEOUT, started, detail=str(exc))
        except PermissionError as exc:
            return self._error_result(job, ErrorCode.PERMISSION_DENIED, started, detail=str(exc))
        except GhostscriptRuntimeError as exc:
            return self._error_result(
                job,
                ErrorCode.GHOSTSCRIPT_RUNTIME_INVALID,
                started,
                detail=str(exc),
            )
        except Exception as exc:
            self.logger.exception("Erro inesperado na compressao")
            return self._error_result(job, ErrorCode.UNKNOWN_ERROR, started, detail=str(exc))

    def compress_many(
        self,
        jobs: list[CompressionJob],
        progress_cb: ProgressCallback | None = None,
    ) -> BatchResult:
        results: list[CompressionResult] = []
        total = len(jobs)
        success = failed = cancelled = 0

        for index, job in enumerate(jobs, start=1):
            if self._cancel_event.is_set():
                for remaining in jobs[index - 1 :]:
                    result = self._cancelled_result(remaining, time.perf_counter())
                    results.append(result)
                    cancelled += 1
                    if progress_cb:
                        progress_cb(len(results), total, result)
                break

            result = self.compress(job)
            results.append(result)
            if result.status == CompressionStatus.SUCCESS:
                success += 1
            elif result.status == CompressionStatus.CANCELLED:
                cancelled += 1
            else:
                failed += 1
            if progress_cb:
                progress_cb(len(results), total, result)

        return BatchResult(
            total=total,
            success=success,
            failed=failed,
            cancelled=cancelled,
            items=results,
        )

    def _build_command(self, gs_executable: Path, job: CompressionJob) -> list[str]:
        command = [
            str(gs_executable),
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            f"-dPDFSETTINGS=/{job.profile.value}",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
        ]
        if job.optimize:
            command.extend(
                [
                    "-dDetectDuplicateImages=true",
                    "-dCompressFonts=true",
                    "-dSubsetFonts=true",
                ]
            )
        command.extend([f"-sOutputFile={job.output_path}", str(job.input_path)])
        return command

    def _build_process_env(self, gs_executable: Path) -> dict[str, str]:
        env = dict(os.environ)
        gs_bin = gs_executable.parent
        gs_root = gs_bin.parent
        path_entries = [str(gs_bin)]
        existing_path = env.get("PATH", "")
        if existing_path:
            path_entries.append(existing_path)
        env["PATH"] = ";".join(path_entries)

        lib_entries: list[str] = []
        lib_dir = gs_root / "lib"
        resource_dir = gs_root / "Resource"
        resource_init = resource_dir / "Init"
        resource_font = resource_dir / "Font"
        for candidate in (lib_dir, resource_init, resource_font, resource_dir):
            if candidate.exists():
                lib_entries.append(str(candidate))
        existing_gs_lib = env.get("GS_LIB", "")
        if existing_gs_lib:
            lib_entries.append(existing_gs_lib)
        if lib_entries:
            env["GS_LIB"] = ";".join(lib_entries)
        return env

    def _run_process(
        self,
        command: list[str],
        env: dict[str, str],
        *,
        creationflags: int,
    ) -> subprocess.CompletedProcess[str] | None:
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=creationflags,
            env=env,
        )
        with self._process_lock:
            self._active_process = process
        deadline = time.monotonic() + self.timeout_seconds
        try:
            while True:
                if self._cancel_event.is_set():
                    self._terminate_process(process)
                    self._drain_process(process)
                    return None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._terminate_process(process)
                    stdout, stderr = self._drain_process(process)
                    raise subprocess.TimeoutExpired(
                        command,
                        self.timeout_seconds,
                        output=stdout,
                        stderr=stderr,
                    )
                try:
                    stdout, stderr = process.communicate(timeout=min(0.2, remaining))
                    if self._cancel_event.is_set():
                        return None
                    return subprocess.CompletedProcess(
                        command,
                        process.returncode,
                        stdout=stdout,
                        stderr=stderr,
                    )
                except subprocess.TimeoutExpired:
                    continue
        finally:
            with self._process_lock:
                if self._active_process is process:
                    self._active_process = None

    def _terminate_process(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                check=False,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                ),
            )
        else:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    @staticmethod
    def _drain_process(process: subprocess.Popen[str]) -> tuple[str, str]:
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
        return stdout or "", stderr or ""

    def _validate_job(self, job: CompressionJob) -> ErrorCode | None:
        if not job.input_path.exists():
            return ErrorCode.INPUT_NOT_FOUND
        if job.input_path.suffix.lower() != ".pdf":
            return ErrorCode.INVALID_EXTENSION
        if job.input_path.resolve() == job.output_path.resolve():
            return ErrorCode.SAME_INPUT_OUTPUT
        if job.output_path.exists() and not job.overwrite:
            return ErrorCode.OUTPUT_EXISTS
        try:
            job.output_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            return ErrorCode.PERMISSION_DENIED
        except OSError:
            return ErrorCode.OUTPUT_PARENT_MISSING
        return None

    def _map_subprocess_error(self, stderr: str) -> ErrorCode:
        output = (stderr or "").lower()
        if (
            "gs_init.ps" in output
            or "can't find initialization file" in output
            or "unable to open the initial device" in output
        ):
            return ErrorCode.GHOSTSCRIPT_RUNTIME_INVALID
        if "password" in output:
            return ErrorCode.PDF_PASSWORD_PROTECTED
        if "undefined" in output or "syntaxerror" in output or "corrupt" in output:
            return ErrorCode.PDF_CORRUPTED
        if "permission" in output or "access denied" in output:
            return ErrorCode.PERMISSION_DENIED
        return ErrorCode.PROCESS_FAILED

    def _error_result(
        self,
        job: CompressionJob,
        error_code: ErrorCode,
        started: float,
        detail: str | None = None,
    ) -> CompressionResult:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return CompressionResult(
            input_path=job.input_path,
            output_path=job.output_path,
            status=CompressionStatus.FAILED,
            error_code=error_code,
            before_mb=None,
            after_mb=None,
            reduction_percent=None,
            elapsed_ms=elapsed_ms,
            error_detail=detail,
        )

    def _cancelled_result(self, job: CompressionJob, started: float) -> CompressionResult:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return CompressionResult(
            input_path=job.input_path,
            output_path=job.output_path,
            status=CompressionStatus.CANCELLED,
            error_code=ErrorCode.CANCELLED,
            before_mb=None,
            after_mb=None,
            reduction_percent=None,
            elapsed_ms=elapsed_ms,
            error_detail="Cancelado pelo usuario.",
        )
