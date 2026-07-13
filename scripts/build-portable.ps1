param(
    [string]$Repository = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Ambiente virtual ausente. Crie com: py -3.14 -m venv .venv"
}

$ghostscript = Join-Path $projectRoot "vendor\ghostscript\win64"
if (-not (Test-Path -LiteralPath (Join-Path $ghostscript "bin\gswin64c.exe"))) {
    throw "Ghostscript incorporado não encontrado em vendor\ghostscript\win64"
}

Push-Location $projectRoot
try {
    if ($Repository) {
        & $python scripts/configure-update-source.py --repository $Repository
        if ($LASTEXITCODE -ne 0) { throw "Origem de atualizações inválida." }
    }
    & $python -m pytest
    if ($LASTEXITCODE -ne 0) { throw "Testes falharam." }
    & $python -m ruff check src tests
    if ($LASTEXITCODE -ne 0) { throw "Lint falhou." }
    & $python -m mypy
    if ($LASTEXITCODE -ne 0) { throw "Analise de tipos falhou." }
    & $python -m PyInstaller --noconfirm --clean "V2E-PDF-Compressor.spec"
    if ($LASTEXITCODE -ne 0) { throw "Build PyInstaller falhou." }
}
finally {
    Pop-Location
}
