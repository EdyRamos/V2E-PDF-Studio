from __future__ import annotations

from ..domain import CompressionResult, CompressionStatus, ErrorCode

ERROR_MESSAGES = {
    ErrorCode.UNKNOWN_ERROR: "Erro inesperado durante compressao.",
    ErrorCode.CANCELLED: "Operacao cancelada.",
    ErrorCode.PROCESS_FAILED: "Falha ao executar o Ghostscript.",
    ErrorCode.PROCESS_TIMEOUT: "Tempo limite excedido durante compressao.",
    ErrorCode.PDF_CORRUPTED: "PDF corrompido ou invalido.",
    ErrorCode.PDF_PASSWORD_PROTECTED: "PDF protegido por senha nao pode ser comprimido.",
    ErrorCode.GHOSTSCRIPT_RUNTIME_INVALID: "Runtime do Ghostscript incompleto no pacote.",
    ErrorCode.GHOSTSCRIPT_NOT_FOUND: "Ghostscript nao encontrado no app.",
    ErrorCode.PERMISSION_DENIED: "Permissao negada para ler/escrever arquivo.",
    ErrorCode.OUTPUT_PARENT_MISSING: "Nao foi possivel criar o diretorio de saida.",
    ErrorCode.OUTPUT_EXISTS: "Arquivo de saida ja existe. Ative sobrescrita ou altere o nome.",
    ErrorCode.SAME_INPUT_OUTPUT: "Arquivo de saida deve ser diferente do arquivo de entrada.",
    ErrorCode.INVALID_EXTENSION: "Somente arquivos PDF sao aceitos.",
    ErrorCode.INPUT_NOT_FOUND: "Arquivo de entrada nao encontrado.",
}


def result_to_user_message(result: CompressionResult) -> str:
    if result.status == CompressionStatus.SUCCESS:
        reduction = result.reduction_percent or 0
        before_mb = result.before_mb or 0
        after_mb = result.after_mb or 0
        return (
            f"Concluido: {result.input_path.name} -> {result.output_path.name} | "
            f"{before_mb} MB -> {after_mb} MB ({reduction}%)"
        )
    if result.status == CompressionStatus.CANCELLED:
        return f"Cancelado: {result.input_path.name}"

    detail = ""
    if result.error_detail:
        first_line = result.error_detail.splitlines()[0].strip()
        if first_line:
            detail = f" | Detalhe: {first_line[:180]}"
    if result.error_code:
        message = ERROR_MESSAGES.get(result.error_code, "Erro desconhecido")
        return f"Falha: {result.input_path.name} | {message}{detail}"
    return f"Falha: {result.input_path.name} | Erro nao identificado.{detail}"
