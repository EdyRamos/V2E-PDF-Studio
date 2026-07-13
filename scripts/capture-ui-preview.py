from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PySide6.QtWidgets import QApplication  # noqa: E402

from v2e_pdf_compressor.application import (  # noqa: E402
    PdfCompressionService,
    PdfEditService,
)
from v2e_pdf_compressor.config import SettingsRepository  # noqa: E402
from v2e_pdf_compressor.infra.ghostscript import GhostscriptLocator  # noqa: E402
from v2e_pdf_compressor.ui import MainWindow  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1360)
    parser.add_argument("--height", type=int, default=820)
    parser.add_argument(
        "--tool",
        choices=("home", "organize", "compress", "batch", "split"),
        default="compress",
    )
    args = parser.parse_args()

    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as temp_dir:
        window = MainWindow(
            edit_service=PdfEditService(),
            compression_service=PdfCompressionService(
                GhostscriptLocator(search_roots=[PROJECT_ROOT], include_default_roots=False),
                logger=logging.getLogger("ui-preview"),
            ),
            settings_repository=SettingsRepository(Path(temp_dir) / "settings.json"),
        )
        if args.tool != "home":
            window.start_home_tool(args.tool)
        window.resize(args.width, args.height)
        window.show()
        app.processEvents()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(args.output), "PNG"):
            return 1
        window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
