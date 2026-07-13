# Segurança

## Privacidade

O aplicativo processa PDFs localmente. Não possui telemetria, upload nem conexão automática. Apenas
quando o usuário clica em **Verificar atualizações**, o aplicativo consulta a API pública do GitHub e,
com nova confirmação, baixa o EXE da release. Nenhum nome, caminho ou conteúdo de PDF participa
dessas requisições. Como em qualquer conexão HTTPS, o GitHub recebe metadados normais da conexão,
como endereço IP e o identificador de versão do aplicativo.

O download é aceito somente de domínios HTTPS do GitHub, deve corresponder ao nome, tamanho e
SHA-256 publicados no manifesto e precisa ter o cabeçalho de executável Windows. O aplicativo em
execução não se modifica: a nova versão é salva separadamente e só é aberta por ação do usuário.

## Relato de vulnerabilidade

Não publique documentos confidenciais em issues. Envie apenas passos de reprodução usando arquivos
sintéticos. Antes de tornar o repositório público, substitua este parágrafo pelo endereço privado de
contato de segurança do mantenedor.

## Assinatura de releases

Releases devem ser produzidas exclusivamente pelo workflow de tag. Quando a SignPath estiver
habilitada, apenas o artefato retornado pela política `release-signing` pode ser publicado. Enquanto a
candidatura estiver pendente, a release deve ser marcada como não assinada e acompanhada de SHA-256.
