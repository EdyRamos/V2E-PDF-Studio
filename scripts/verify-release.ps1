param(
    [Parameter(Mandatory = $true)][string]$Executable,
    [Parameter(Mandatory = $true)][string]$Manifest,
    [switch]$AllowUnsigned
)

$ErrorActionPreference = "Stop"
$manifestData = Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json
$actualHash = (Get-FileHash -LiteralPath $Executable -Algorithm SHA256).Hash
if ($actualHash -ne $manifestData.artifact.sha256) {
    throw "SHA-256 do executavel nao corresponde ao manifesto."
}

$signature = Get-AuthenticodeSignature -LiteralPath $Executable
if ($signature.Status -eq "NotSigned") {
    if (-not $AllowUnsigned) { throw "Executavel sem assinatura Authenticode." }
    Write-Warning "Release sem assinatura: o Windows exibira editor desconhecido."
    exit 0
}
if ($signature.Status -ne "Valid") {
    throw "Assinatura Authenticode invalida: $($signature.Status) $($signature.StatusMessage)"
}

$signTool = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin" -Filter signtool.exe -Recurse |
    Where-Object FullName -Match '\\x64\\' | Sort-Object FullName -Descending | Select-Object -First 1
if ($signTool) {
    & $signTool.FullName verify /pa /all /v $Executable
    if ($LASTEXITCODE -ne 0) { throw "SignTool rejeitou a assinatura." }
}
