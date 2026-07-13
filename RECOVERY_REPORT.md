# Relatório de recuperação

## Identificação

- Produto: **V2E PDF Compressor**
- Autor mostrado no guia: **Eder A. Ramos**
- Executável localizado: `C:\Users\edy_1\Downloads\V2E-PDF-Compressor.exe`
- Data do arquivo: 09/07/2026 12:15:08
- Tamanho: 94.787.062 bytes
- SHA-256: `A1D54B47975A7B1A81517A2BA99054E29D3FF44257239029417877E6BB9A0668`
- Empacotamento: PyInstaller `onefile`
- Runtime: Python 3.14 (`python314.dll`)
- Interface: PySide6/Qt 6
- Manipulação de PDF: PyMuPDF (`fitz`)
- Compressão: Ghostscript x64 incorporado

## Funcionalidades confirmadas

- Organizar e reordenar páginas.
- Adicionar páginas de outro PDF.
- Inserir página A4 em branco.
- Remover páginas.
- Dividir por seleção ou por intervalos.
- Comprimir um PDF com perfis `screen`, `ebook` e `printer`.
- Comprimir vários PDFs em lote.
- Visualizar miniaturas e página ampliada.
- Salvar como novo arquivo ou sobrescrever o original.
- Manter configurações e logs em `%LOCALAPPDATA%\V2ECompressor`.

## Arquitetura original recuperada

```text
v2e_pdf_compressor
├── app
├── application
│   ├── pdf_edit
│   └── service
├── config
│   ├── paths
│   └── settings
├── domain
│   ├── models
│   └── pdf_edit
├── infra
│   ├── ghostscript
│   │   └── locator
│   └── logging_config
└── ui
    ├── main_window
    └── messages
```

## Conversa antiga

O índice e os arquivos de sessão desta instalação do Codex foram pesquisados. Somente a conversa atual estava disponível. Portanto, a conversa antiga não pôde ser restaurada deste computador; ela pode estar em outra conta, instalação ou equipamento. O projeto foi recuperado diretamente do executável local.

## Nível de recuperação

- Binário funcional original: preservado em `Downloads`.
- Recursos e documentação: recuperados integralmente.
- Estrutura e bytecode da aplicação: recuperados integralmente.
- Código-fonte textual: 18 módulos reconstruídos e validados. Comentários e formatação eliminados durante a compilação original não são recuperáveis literalmente.
- Scripts de build: reconstruídos a partir do conteúdo e das referências internas do pacote.

## Validação do código reconstruído

- Todos os módulos passam em `compileall`.
- O smoke-test localiza configurações e Ghostscript.
- O full smoke-test carrega a interface em modo offscreen, renderiza miniaturas e preview, reordena páginas, insere uma página em branco, exporta o PDF e executa compressão real com sucesso.
