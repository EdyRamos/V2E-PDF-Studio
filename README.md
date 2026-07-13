# V2E PDF Studio

Aplicativo desktop portátil e offline para Windows 10/11 x64. Organiza, gira,
remove, insere, divide e comprime PDFs individualmente ou em lote. O código foi
recuperado do executável original, auditado e preparado para manutenção pública
sob a AGPL-3.0-or-later.

## Privacidade

- O processamento ocorre localmente.
- O aplicativo não possui telemetria nem faz conexões em segundo plano.
- O GitHub só é consultado quando o usuário clica em **Verificar atualizações**.
- Nomes, caminhos e conteúdo dos PDFs não são enviados a terceiros.
- As configurações guardam apenas o último diretório, perfil e política de
  sobrescrita.

## Desenvolvimento

Requer Windows x64 e Python 3.14:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python app.py
```

Validação completa:

```powershell
python -m pytest
python -m ruff check .
python -m mypy
python app.py --diagnostics
```

O diagnóstico mostra versões, permissões, caminhos do aplicativo, logs e estado
do Ghostscript e do atualizador, sem listar PDFs do usuário.

## Build portátil

```powershell
.\scripts\build-portable.ps1
```

Para um build local com atualizações apontando ao repositório oficial:

```powershell
.\scripts\build-portable.ps1 -Repository "usuario/repositorio"
```

O build versionado usa `V2E-PDF-Compressor.spec`, inclui o runtime completo do
Ghostscript e gera `dist\V2E-PDF-Compressor.exe`. Releases oficiais são criadas
somente pelo workflow Windows a partir de uma tag `v*`, com testes, smoke-test,
SHA-256, manifesto e SBOM.

## Atualizações sob demanda

O botão **Verificar atualizações** consulta a release pública mais recente no GitHub. Se houver uma
versão nova, o aplicativo baixa `V2E-PDF-Compressor.exe`, compara tamanho e SHA-256 com
`release-manifest.json` e salva uma cópia versionada em `%LOCALAPPDATA%\V2ECompressor\updates`.
O executável aberto nunca é alterado e a nova versão só é executada por escolha explícita do usuário.

O workflow oficial injeta automaticamente o próprio `owner/repository` no build. Por isso, releases
oficiais não dependem de URL ou token gravado no código e o repositório precisa ser público.

## Segurança da saída

Exportações são gravadas em arquivo temporário no mesmo volume, validadas como
PDF e substituídas atomicamente. Cancelamento encerra a árvore do Ghostscript e
remove saídas parciais. Arquivos existentes nunca são substituídos sem a política
de sobrescrita correspondente.

## Assinatura do EXE

A automação aceita assinatura SignPath opcional. Enquanto não houver assinatura,
a release deve ser identificada como não assinada e acompanhada do código-fonte,
SHA-256 e SBOM. Detalhes estão em `docs/RELEASING.md`.

## Estrutura

- `src/v2e_pdf_compressor/`: código da aplicação.
- `tests/`: testes unitários, integração e UI.
- `vendor/ghostscript/win64/`: runtime incorporado.
- `.github/workflows/`: CI e release protegida.
- `analysis/disassembly/`: referência do bytecode recuperado.
- `baseline/original-executable.json`: hash da referência original.
- `BUG_INVENTORY.md`: inventário e estado dos riscos.
- `RECOVERY_REPORT.md`: relatório técnico da recuperação.
