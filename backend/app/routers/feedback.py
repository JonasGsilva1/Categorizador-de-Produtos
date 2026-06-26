"""
Router: POST /api/feedback

Recebe a planilha corrigida manualmente pelo usuário e realimenta o banco de dados:
- Insere/atualiza entradas em product_history (sem gerar embeddings — TF-IDF usa texto)
- Insere/atualiza regras em ean_rules e ncm_rules quando EAN/NCM estiver preenchido
- Após o upsert, invalida o cache TF-IDF para que a próxima busca use os novos dados
"""

import re
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request
from app.auth import verify_supabase_token
from app.database import require_pool
from app.models import RespostaRetroalimentacao
from app.xlsx_io import read_feedback_products
from app.services.tfidf_matcher import load_index
from app.audit import log_audit_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Retroalimentação"])


@router.post("/feedback", response_model=RespostaRetroalimentacao)
async def submit_feedback(
    request: Request,
    file: UploadFile = File(...),
    user_data: dict = Depends(verify_supabase_token)
):
    """
    Endpoint de retroalimentação.

    Recebe um arquivo .xlsx corrigido manualmente com colunas:
    Descrição, EAN, NCM, Grupo, Subgrupo.

    Após persistir os dados, força a recarga do índice TF-IDF em memória
    para que as próximas categorizações reflitam imediatamente os novos registros.
    """
    id_usuario = user_data["user_id"]
    id_requisicao = getattr(request.state, "req_id", "unknown")
    ip_cliente = (
        request.headers.get("X-Forwarded-For", request.client.host if request.client else "127.0.0.1")
        .split(",")[0]
        .strip()
    )

    if not file.filename:
        raise HTTPException(status_code=400, detail="Arquivo inválido.")

    # --- Validação e Sanitização ---
    nome_arquivo_seguro = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", file.filename)
    if not nome_arquivo_seguro.lower().endswith((".xlsx", ".xls")):
        log_audit_event(id_usuario, "FEEDBACK", nome_arquivo_seguro, ip_cliente, id_requisicao, "failure", "Extensão inválida")
        raise HTTPException(
            status_code=400,
            detail="Formato inválido. Envie um arquivo .xlsx.",
        )

    # Validação Anti-Malware (Magic Bytes) sem carregar o arquivo inteiro
    assinatura = file.file.read(4)
    file.file.seek(0)
    if len(assinatura) < 4 or not assinatura.startswith(b"PK\x03\x04"):
        log_audit_event(id_usuario, "FEEDBACK", nome_arquivo_seguro, ip_cliente, id_requisicao, "failure", "Falha de Magic Bytes")
        raise HTTPException(
            status_code=415,
            detail="Arquivo corrompido ou malicioso. Apenas formatos XLSX reais são permitidos.",
        )

    # --- Leitura da planilha em ThreadPool ---
    import asyncio
    try:
        # Pandas é síncrono e CPU-bound, então o rodamos em uma thread separada passando o objeto file.file
        linhas = await asyncio.to_thread(read_feedback_products, file.file)
    except ValueError as erro_valor:
        raise HTTPException(status_code=400, detail=str(erro_valor))
    except Exception as excecao:
        logger.error(f"Erro ao ler planilha de feedback: {excecao}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="Erro ao ler o arquivo. Verifique se é um .xlsx válido com as colunas corretas.",
        )

    if not linhas:
        raise HTTPException(
            status_code=400,
            detail="Nenhuma linha válida encontrada. Preencha Descrição, Grupo e Subgrupo.",
        )

    logger.info(f"Feedback recebido: '{file.filename}' com {len(linhas)} linhas válidas")

    # --- Pool de DB ---
    try:
        pool_db = require_pool()
    except HTTPException:
        raise
    except Exception as excecao:
        raise HTTPException(status_code=503, detail=f"Erro de DB: {str(excecao)}")

    inseridos = 0
    atualizados = 0
    erros = 0

    for linha in linhas:
        try:
            async with pool_db.acquire() as conexao:
                # Upsert no product_history — embedding salvo como vetor nulo (não usado pelo TF-IDF)
                resultado = await conexao.execute(
                    """
                    INSERT INTO product_history (descricao, ean, ncm, grupo, subgrupo, origem)
                    VALUES ($1, $2, $3, $4, $5, 'Retroalimentação')
                    ON CONFLICT ((LOWER(descricao)))
                    DO UPDATE SET
                        grupo     = EXCLUDED.grupo,
                        subgrupo  = EXCLUDED.subgrupo,
                        ean       = EXCLUDED.ean,
                        ncm       = EXCLUDED.ncm,
                        origem    = 'Retroalimentação',
                        updated_at = NOW()
                    """,
                    linha["descricao"],
                    linha["ean"],
                    linha["ncm"],
                    linha["grupo"],
                    linha["subgrupo"],
                )

            if "INSERT" in resultado:
                inseridos += 1
            else:
                atualizados += 1

        except Exception as excecao:
            logger.error(
                f"Erro ao processar feedback para '{linha['descricao'][:50]}': {excecao}",
                exc_info=True,
            )
            erros += 1

    logger.info(
        f"Feedback processado: {inseridos} inseridos, {atualizados} atualizados, {erros} erros"
    )

    # --- Invalidar cache TF-IDF para refletir os novos dados ---
    if inseridos > 0 or atualizados > 0:
        try:
            await load_index(pool_db, forcar=True)
            logger.info("Índice TF-IDF recarregado após retroalimentação.")
        except Exception as excecao:
            # Não bloqueia a resposta — o cache expirará automaticamente pelo TTL
            logger.warning(f"Não foi possível recarregar o índice TF-IDF: {excecao}")

    log_audit_event(
        id_usuario, "FEEDBACK", nome_arquivo_seguro, ip_cliente, id_requisicao,
        "success", f"In:{inseridos} Up:{atualizados} Err:{erros}"
    )

    return RespostaRetroalimentacao(
        message="Retroalimentação processada com sucesso.",
        inserted=inseridos,
        updated=atualizados,
        errors=erros,
        total=len(linhas),
    )
