# Inventário inicial de bugs

## P0 — risco de perda ou corrupção

- [x] Exportação escrevia diretamente no destino e podia deixar PDF parcial.
- [x] Sobrescrita do PDF de origem dependia de temporário em outro volume.
- [x] Configurações eram gravadas diretamente e podiam ficar truncadas.
- [x] Temporários de compressão não tinham limpeza garantida.

## P1 — falha funcional

- [x] Cancelar não encerrava o Ghostscript em execução.
- [x] Runtime incompleto do Ghostscript só era detectado após iniciar o processo.
- [x] Configuração JSON com tipo inesperado podia impedir a inicialização.
- [x] Serviço aceitava compressões concorrentes sem proteção própria.
- [x] Callbacks de worker podiam atingir uma janela em fechamento.
- [ ] Validar o executável final em VMs limpas Windows 10 e Windows 11.

## P2 — interface e manutenção

- [x] Ausência de diagnóstico de ambiente sem abrir a UI.
- [x] Remover os artefatos textuais da decompilação do código-fonte executável.
- [x] Eliminar sobreposição entre opções, progresso e log no painel de ferramentas.
- [x] Corrigir cortes de texto e hierarquia em 1120×700 e escala de 150%.
- [x] Tornar cards de ferramenta compactos e o painel lateral rolável verticalmente.
- [x] Executar revisão visual manual em escala 100%, 125% e 150%.
- [ ] Obter aprovação da SignPath Foundation para releases assinadas.

Itens dependentes de infraestrutura externa permanecem abertos até a publicação do repositório e
execução em VMs/SignPath.
