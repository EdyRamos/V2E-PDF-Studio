# Troubleshooting

## O aplicativo demora para abrir
Sintoma:
- O primeiro clique no `V2E-PDF-Compressor.exe` demora alguns segundos.

Causa:
- O executavel `onefile` extrai internamente o runtime antes de abrir a janela.

Correcao:
- Aguarde a primeira abertura.
- Se o antivirus estiver verificando o arquivo, adicione o executavel a lista confiavel conforme a politica de TI do cliente.

## Ghostscript nao encontrado
Sintoma:
- Mensagem `Ghostscript nao encontrado no app`.

Causa:
- Runtime do Ghostscript ausente ou incompleto no executavel gerado.

Correcao:
- Refaca o build com `scripts/build-portable.ps1`.
- Verifique antes do build se estes caminhos existem no projeto:
  - `vendor/ghostscript/win64/bin/gswin64c.exe`
  - `vendor/ghostscript/win64/Resource/Init/gs_init.ps`
  - `vendor/ghostscript/win64/Resource/`
  - `vendor/ghostscript/win64/COPYING`

## Falha por permissao
Sintoma:
- Mensagem `Permissao negada para ler/escrever arquivo`.

Correcao:
- Escolha uma pasta onde o usuario atual tenha permissao de escrita.
- Evite salvar por cima de arquivos abertos em outro programa.
- Evite pastas protegidas como `C:\\Windows` ou locais gerenciados por politicas restritivas.

## PDF protegido por senha
Sintoma:
- O app informa que o PDF precisa de senha.

Correcao:
- Remova a senha do PDF em ferramenta apropriada e tente novamente.

## PDF corrompido ou invalido
Sintoma:
- O app nao abre, nao renderiza ou nao comprime um PDF especifico.

Correcao:
- Abra o PDF em um leitor comum para validar integridade.
- Gere novamente o PDF na origem.
- Se outros PDFs funcionam, o problema provavelmente esta no arquivo.

## Reordenacao nao salva
Sintoma:
- O usuario arrasta paginas, fecha o app e perde a mudanca.

Causa:
- Reordenar altera apenas a sessao aberta ate clicar em `Salvar`.

Correcao:
- Clique em `Salvar` e escolha `Salvar como novo` ou `Sobrescrever original`.

## Logs
- Logs tecnicos ficam em `%LOCALAPPDATA%\\V2ECompressor\\logs\\app.log`.
- Use esse arquivo para diagnosticar falhas de Ghostscript, permissao ou PDF invalido.
