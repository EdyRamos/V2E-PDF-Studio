# Publicação de releases

## Preparação do repositório

1. Publique todo o projeto sob AGPL, incluindo `.github`, `scripts`, `vendor` e arquivos de lock.
2. Proteja `main`, exija CI aprovado e revisão para alterações nos workflows e em `.signpath`.
3. Crie no GitHub o ambiente `release` com aprovação manual obrigatória.
4. Configure um contato privado em `SECURITY.md`.

O workflow grava `${{ github.repository }}` em `build/update-config.json` antes de empacotar. O
repositório deve ser público para que o aplicativo consulte releases sem token. Builds locais podem
usar `scripts\build-portable.ps1 -Repository "owner/name"`.

## SignPath Foundation

1. Candidate o repositório em <https://signpath.org/>.
2. Instale o GitHub App da SignPath apenas no repositório do projeto.
3. Após aprovação, configure as variáveis do ambiente `release`:
   `SIGNPATH_ENABLED=true`, `SIGNPATH_ORGANIZATION_ID`, `SIGNPATH_PROJECT_SLUG`,
   `SIGNPATH_SIGNING_POLICY_SLUG` e `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG`.
4. Cadastre `SIGNPATH_API_TOKEN` como secret do ambiente, nunca como variável ou arquivo.
5. Restrinja a política de assinatura a tags `v*` provenientes do workflow de release.

Sem aprovação, mantenha `SIGNPATH_ENABLED=false`. O workflow publicará o EXE sem assinatura, o
manifesto e o SBOM, e registrará claramente `authenticode: unsigned`.

## Criar uma versão

1. Atualize a versão em `pyproject.toml`, `src/v2e_pdf_compressor/__init__.py` e
   `build/version_info.txt`.
2. Execute `pytest`, `ruff check src tests`, `mypy` e o build local.
3. Crie e envie uma tag assinada no formato `vMAJOR.MINOR.PATCH`.
4. Aprove manualmente o ambiente `release` depois de revisar testes, hash, SBOM e estado da assinatura.

A atualização manual depende de a release publicada conter exatamente estes dois assets:

- `V2E-PDF-Compressor.exe`;
- `release-manifest.json` com versão, tamanho e SHA-256 correspondentes.

Não renomeie esses arquivos no comando `gh release create`. Releases em rascunho ou prerelease não
são retornadas pelo endpoint de “latest release” usado pelo aplicativo.

Cada novo binário possui hash diferente e pode inicialmente apresentar aviso do SmartScreen mesmo
quando a assinatura Authenticode for válida.
