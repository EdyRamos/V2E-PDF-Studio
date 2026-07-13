from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "V2ECompressor"
LOCAL_APPDATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")).expanduser()
APP_DATA_DIR = LOCAL_APPDATA / APP_NAME
APP_LOG_DIR = APP_DATA_DIR / "logs"
SETTINGS_FILE = APP_DATA_DIR / "settings.json"


def ensure_app_dirs() -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    APP_LOG_DIR.mkdir(parents=True, exist_ok=True)
