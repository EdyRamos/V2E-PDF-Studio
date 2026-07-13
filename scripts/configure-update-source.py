from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")

parser = argparse.ArgumentParser(description="Configura a origem do atualizador no build.")
parser.add_argument("--repository", required=True, help="Repositório GitHub no formato owner/name")
parser.add_argument(
    "--output",
    type=Path,
    default=Path("build/update-config.json"),
)
args = parser.parse_args()

repository = args.repository.strip()
if REPOSITORY_PATTERN.fullmatch(repository) is None:
    parser.error("--repository deve usar o formato owner/name")

payload = {"provider": "github", "repository": repository}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
