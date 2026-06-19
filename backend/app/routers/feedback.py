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
from app.models import FeedbackResponse
from app.xlsx_io import read_feedback_products
from app.services.tfidf_matcher import load_index
from app.audit import log_audit_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Retroalimentação"])


@router.post("/feedback", response_model=FeedbackResponse)
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
    user_id = user_data["user_id"]
    req_id = getattr(request.state, "req_id", "unknown")
    client_ip = (
        request.headers.get("X-Forwarded-For", request.client.host if request.client else "127.0.0.1")
        .split(",")[0]
        .strip()
    )

    if not file.filename:
        raise HTTPException(status_code=400, detail="Arquivo inválido.")

    # --- Validação e Sanitização ---
    safe_filename = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", file.filename)
    if not safe_filename.lower().endswith((".xlsx", ".xls")):
        log_audit_event(user_id, "FEEDBACK", safe_filename, client_ip, req_id, "failure", "Extensão inválida")
        raise HTTPException(
            status_code=400,
            detail="Formato inválido. Envie um arquivo .xlsx.",
        )

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    # Validação Anti-Malware (Magic Bytes)
    if len(file_bytes) < 4 or not file_bytes.startswith(b"PK\x03\x04"):
        log_audit_event(user_id, "FEEDBACK", safe_filename, client_ip, req_id, "failure", "Falha de Magic Bytes")
        raise HTTPException(
            status_code=415,
            detail="Arquivo corrompido ou malicioso. Apenas formatos XLSX reais são permitidos.",
        )

    # --- Leitura da planilha ---
    try:
        rows = read_feedback_products(file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao ler planilha de feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="Erro ao ler o arquivo. Verifique se é um .xlsx válido com as colunas corretas.",
        )

    if not rows:
        raise HTTPException(
            status_code=400,
            detail="Nenhuma linha válida encontrada. Preencha Descrição, Grupo e Subgrupo.",
        )

    logger.info(f"Feedback recebido: '{file.filename}' com {len(rows)} linhas válidas")

    # --- Pool de DB ---
    try:
        pool = require_pool()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro de DB: {str(e)}")

    inserted = 0
    updated = 0
    errors = 0

    for row in rows:
        try:
            async with pool.acquire() as conn:
                # Upsert no product_history — embedding salvo como vetor nulo (não usado pelo TF-IDF)
                result = await conn.execute(
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
                    row["descricao"],
                    row["ean"],
                    row["ncm"],
                    row["grupo"],
                    row["subgrupo"],
                )

            if "INSERT" in result:
                inserted += 1
            else:
                updated += 1

        except Exception as e:
            logger.error(
                f"Erro ao processar feedback para '{row['descricao'][:50]}': {e}",
                exc_info=True,
            )
            errors += 1

    logger.info(
        f"Feedback processado: {inserted} inseridos, {updated} atualizados, {errors} erros"
    )

    # --- Invalidar cache TF-IDF para refletir os novos dados ---
    if inserted > 0 or updated > 0:
        try:
            await load_index(pool, force=True)
            logger.info("Índice TF-IDF recarregado após retroalimentação.")
        except Exception as e:
            # Não bloqueia a resposta — o cache expirará automaticamente pelo TTL
            logger.warning(f"Não foi possível recarregar o índice TF-IDF: {e}")

    log_audit_event(
        user_id, "FEEDBACK", safe_filename, client_ip, req_id,
        "success", f"In:{inserted} Up:{updated} Err:{errors}"
    )

    return FeedbackResponse(
        message="Retroalimentação processada com sucesso.",
        inserted=inserted,
        updated=updated,
        errors=errors,
        total=len(rows),
    )
