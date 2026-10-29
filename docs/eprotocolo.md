# Preparar documentos para eProtocolo

O modo funciona localmente e não envia arquivos ao portal. O tutorial fornecido
descreve um limite de 100M por arquivo e por envio na área de anexos; ele não
estabelece o limite da área de documentos paginados. Confirme as regras do seu
processo antes de enviar.

Escolha **PDFs independentes** para reunir PDFs em partes legíveis separadamente.
A ordem inicial é natural e pode ser alterada na lista. Documentos que não cabem
inteiros são divididos entre partes. O padrão de 90 MB decimais usa corte efetivo
de 88 MB. O perfil Equilibrado usa Ghostscript, que pode modificar características
do PDF; confira a legibilidade e o conteúdo antes de enviar. Uma página individual
acima do limite impede a conclusão. Assinaturas detectadas e formulários requerem
confirmação, pois as cópias não preservam assinaturas e os campos tornam-se estáticos.

Escolha **Pacote de anexos** para manter os bytes originais e os caminhos relativos.
Se houver várias partes, coloque todas na mesma pasta e abra a primeira (`.zip.001`)
com 7-Zip para extrair. Para anexar ao portal, envie uma parte por vez e em ordem.
Não é necessário instalar 7-Zip para criar o pacote no aplicativo.

As saídas são gravadas em uma nova pasta no destino escolhido, com um relatório e
manifesto de conferência. Os originais não são sobrescritos. A verificação de texto
não garante fidelidade visual; examine documentos importantes e assinaturas no fluxo
apropriado do órgão antes de protocolar.
