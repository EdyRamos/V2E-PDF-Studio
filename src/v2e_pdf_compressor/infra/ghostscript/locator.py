from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


class GhostscriptRuntimeError(RuntimeError):
    pass


class GhostscriptLocator:
    def __init__(
        self,
        embedded_rel_path: Path | None = None,
        allow_path_fallback: bool | None = None,
        search_roots: list[Path] | None = None,
        include_default_roots: bool = True,
    ) -> None:
        self.embedded_rel_path = embedded_rel_path or Path(
            "vendor/ghostscript/win64/bin/gswin64c.exe"
        )
        if allow_path_fallback is None:
            allow_path_fallback = bool(
                os.environ.get("V2E_ALLOW_PATH_FALLBACK") == "1"
                or not getattr(sys, "frozen", False)
            )
        self.allow_path_fallback = allow_path_fallback
        self.search_roots = search_roots or []
        self.include_default_roots = include_default_roots

    def resolve_executable(self) -> Path:
        embedded = self._find_embedded_executable()
        if embedded:
            self.validate_runtime(embedded)
            return embedded
        if self.allow_path_fallback:
            path_exec = self._find_in_path()
            if path_exec:
                return path_exec
        raise FileNotFoundError(
            "Ghostscript nao encontrado. Esperado em "
            "vendor/ghostscript/win64/bin/gswin64c.exe ou no PATH quando "
            "fallback estiver habilitado."
        )

    def validate_runtime(self, executable: Path) -> None:
        executable = executable.resolve()
        expected_embedded = "vendor/ghostscript" in executable.as_posix().lower()
        if not expected_embedded:
            return
        root = executable.parent.parent
        required = (
            root / "bin" / "gsdll64.dll",
            root / "Resource" / "Init" / "gs_init.ps",
            root / "Resource",
            root / "lib",
        )
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise GhostscriptRuntimeError(
                "Runtime do Ghostscript incompleto. Ausente: " + ", ".join(missing)
            )

    def _find_embedded_executable(self) -> Path | None:
        for base in self._candidate_roots():
            candidate = (base / self.embedded_rel_path).resolve()
            if candidate.is_file():
                return candidate
        return None

    def _candidate_roots(self) -> list[Path]:
        roots: list[Path] = []
        roots.extend(self.search_roots)
        if self.include_default_roots:
            if getattr(sys, "frozen", False):
                roots.append(Path(sys.executable).resolve().parent)
                meipass = getattr(sys, "_MEIPASS", None)
                if meipass:
                    roots.append(Path(meipass))
            source_root = Path(__file__).resolve().parents[4]
            roots.extend([source_root, Path.cwd()])

        deduped: list[Path] = []
        seen: set[Path] = set()
        for root in roots:
            resolved = root.resolve()
            if resolved in seen:
                continue
            deduped.append(resolved)
            seen.add(resolved)
        return deduped

    def _find_in_path(self) -> Path | None:
        for name in ("gswin64c.exe", "gswin64c", "gswin32c.exe", "gswin32c"):
            found = shutil.which(name)
            if found:
                return Path(found).resolve()
        return None
