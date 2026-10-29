"""Record the bundled standalone 7-Zip executable in the release SBOM."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sbom_path = Path(sys.argv[1])
binary = Path("vendor/7zip/x64/7za.exe")
expected = "7ddf0a3bc451e166679296be630d6f0573eb386159c04184761c43020c484291"
actual = hashlib.sha256(binary.read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit("O hash do 7-Zip incorporado não corresponde à versão esperada.")
payload = json.loads(sbom_path.read_text(encoding="utf-8"))
payload.setdefault("components", []).append(
    {
        "type": "application",
        "name": "7-Zip",
        "version": "26.05",
        "purl": "pkg:generic/7-zip@26.05",
        "hashes": [{"alg": "SHA-256", "content": actual}],
    }
)
sbom_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
