# Third-Party Notices

Este projeto inclui e distribui componentes de terceiros.

## 1) Ghostscript
- Projeto: Ghostscript
- Site: https://www.ghostscript.com/
- Licenca: GNU Affero General Public License v3.0 (AGPL-3.0)
- Arquivo de licenca distribuido: `vendor/ghostscript/win64/COPYING`
- Uso neste projeto: motor de compressao PDF.

## 2) PyMuPDF
- Projeto: PyMuPDF
- Site: https://pymupdf.readthedocs.io/
- Licenca: AGPL-3.0 ou licenca comercial Artifex.
- Uso neste projeto: renderizacao, montagem, reordenacao, remocao, insercao e divisao de paginas PDF.

## 3) PySide6 / Qt for Python
- Projeto: PySide6
- Site: https://doc.qt.io/qtforpython-6/
- Licenca: LGPL-3.0/GPL-3.0/comercial, conforme distribuicao da Qt Company.
- Uso neste projeto: interface grafica Windows.

## 4) packaging
- Projeto: packaging
- Repositorio: https://github.com/pypa/packaging
- Licenca: BSD-2-Clause ou Apache-2.0
- Uso neste projeto: dependencia indireta de build/runtime.

## 5) PyInstaller
- Projeto: PyInstaller
- Site: https://pyinstaller.org/
- Licenca: GPLv2 com excecao de vinculacao.
- Uso neste projeto: empacotamento do aplicativo portavel em executavel unico.

## Observacoes de conformidade AGPL
- O codigo-fonte deste projeto deve ser disponibilizado aos usuarios do binario distribuido.
- O executavel inclui componentes AGPL, incluindo Ghostscript e PyMuPDF.
- A distribuicao deve acompanhar ou apontar claramente para:
  - `LICENSE` (licenca do projeto)
  - `THIRD_PARTY_NOTICES.md`
  - `docs/SOURCE_CODE_OFFER.md`
  - `vendor/ghostscript/win64/COPYING`
- Mantenha estes avisos de terceiros sem remover termos de licenca.
