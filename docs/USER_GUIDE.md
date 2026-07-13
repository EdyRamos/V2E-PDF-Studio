# Guia de Uso

## 1. Abrir o aplicativo
- Execute `V2E-PDF-Compressor.exe`.
- Nao e necessario instalar Python, Ghostscript ou dependencias externas.
- A tela inicial identifica o app como uma ferramenta V2E desenvolvida por Eder A. Ramos.

## 2. Escolher uma ferramenta
- Na tela inicial, escolha uma das ferramentas:
  - `Organizar PDF`
  - `Comprimir PDF`
  - `Comprimir lote`
  - `Dividir PDF`
- A tela da ferramenta mostra somente as opcoes daquela acao.
- Voce tambem pode arrastar um PDF para abrir direto no organizador.

## 3. Visualizar paginas
- As miniaturas aparecem na coluna da esquerda.
- Clique em uma miniatura para ver a pagina maior no painel da direita.
- Use `Mais zoom` e `Menos zoom` para ajustar a visualizacao.

## 4. Reordenar paginas
- Escolha `Organizar PDF`.
- Clique em `Selecionar PDF para organizar` se ainda nao houver documento aberto.
- Arraste as miniaturas para mudar a ordem das paginas.
- O asterisco no titulo indica que existem alteracoes nao salvas.

## 5. Adicionar paginas
- Clique em `Adicionar PDF` para inserir paginas de outro PDF.
- As paginas entram depois da ultima pagina selecionada.
- Clique em `Pagina em branco` para inserir uma pagina A4 vazia.

## 6. Remover paginas
- Selecione uma ou mais miniaturas.
- Clique em `Remover paginas`.
- Confirme a remocao.

## 7. Dividir PDF
- Escolha `Dividir PDF`.
- Clique em `Selecionar PDF para dividir` se ainda nao houver documento aberto.
- Use `Salvar paginas selecionadas` para gerar um novo PDF somente com as paginas marcadas.
- Use `Dividir por intervalos` para informar algo como `1-3,5,8-10`.

## 8. Salvar alteracoes
- Clique em `Salvar`.
- Escolha `Salvar como novo` para criar outro arquivo.
- Escolha `Sobrescrever original` somente quando tiver certeza de que quer substituir o PDF aberto.

## 9. Comprimir PDF
- Escolha `Comprimir PDF`.
- Clique em `Selecionar PDF para comprimir` se ainda nao houver documento aberto.
- No painel `Ferramentas`, escolha o perfil:
  - `Alta compressao - screen`: menor arquivo, menor qualidade.
  - `Equilibrado - ebook`: tamanho e qualidade balanceados.
  - `Melhor qualidade - printer`: menor reducao, melhor fidelidade.
- Marque ou desmarque `Otimizacoes extras`.
- Marque `Sobrescrever saidas existentes` somente se quiser substituir arquivos com o mesmo nome.
- Clique em `Comprimir PDF aberto`.
- Escolha onde salvar o PDF comprimido.
- Se o documento tiver alteracoes nao salvas, o app comprime uma copia temporaria dessas alteracoes sem modificar o original.

## 10. Comprimir lote
- Escolha `Comprimir lote`.
- Configure perfil, otimizacoes e sobrescrita.
- Clique em `Selecionar PDFs e comprimir`.
- Selecione varios PDFs.
- Escolha a pasta de saida.
- Cada PDF gera um arquivo proprio com sufixo `_comprimido`; os PDFs nao sao juntados.
- Acompanhe progresso e resultado no log do painel direito.

## 11. Logs e configuracoes locais
- Configuracoes: `%LOCALAPPDATA%\\V2ECompressor\\settings.json`
- Logs: `%LOCALAPPDATA%\\V2ECompressor\\logs\\app.log`
