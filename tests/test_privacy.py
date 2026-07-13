from __future__ import annotations

import ast
from pathlib import Path

NETWORK_MODULES = {"aiohttp", "http", "httpx", "requests", "socket", "urllib"}


def test_network_code_is_isolated_to_manual_updater() -> None:
    project_root = Path(__file__).resolve().parents[1]
    sources = [project_root / "app.py", *project_root.joinpath("src").rglob("*.py")]
    violations: list[str] = []

    for source in sources:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module]
            for module in imported:
                is_manual_updater = source.as_posix().endswith(
                    "v2e_pdf_compressor/application/updates.py"
                )
                if module.split(".", 1)[0] in NETWORK_MODULES and not is_manual_updater:
                    violations.append(f"{source}:{node.lineno}: {module}")

    assert violations == []


def test_settings_schema_does_not_persist_pdf_paths() -> None:
    settings_source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "v2e_pdf_compressor"
        / "config"
        / "settings.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(settings_source)
    app_settings = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "AppSettings"
    )
    persisted_fields = {
        node.target.id
        for node in app_settings.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert persisted_fields == {
        "schema_version",
        "last_directory",
        "default_profile",
        "overwrite_policy",
    }
