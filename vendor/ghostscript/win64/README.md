# Ghostscript Binario Embutido (Windows x64)

Coloque nesta pasta os arquivos necessarios para distribuicao:
- `bin/` (incluindo `gswin64c.exe` e DLLs)
- `lib/`
- `Resource/`
- `Resource/Init/gs_init.ps`
- `iccprofiles/` (quando disponivel)
- `COPYING` (licenca oficial do Ghostscript)

Estrutura esperada:
```text
vendor/ghostscript/win64/
  bin/
  lib/
  Resource/
  iccprofiles/
  COPYING
  README.md
```

O script `scripts/build-portable.ps1` tenta copiar automaticamente:
- runtime completo de `bin/lib/Resource/iccprofiles` a partir da instalacao do sistema
- `COPYING` do diretorio `doc` da instalacao do Ghostscript

Se a copia automatica falhar, inclua os arquivos manualmente antes do build.
