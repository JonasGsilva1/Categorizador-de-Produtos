"""
Router: POST /api/feedback

Recebe a planilha corrigida manualmente pelo usuário e realimenta o banco de dados:
- Insere/atualiza embeddings no product_history
- Insere/atualiza regras em ean_rules e ncm_rules
"""

import re
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request
from app.auth import verify_supabase_token
from app.database import require_pool
from app.models import FeedbackResponse
from app.xlsx_io import read_feedback_products
from app.services.embedding import generate_embedding
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
    """
    user_id = user_data["user_id"]
    req_id = getattr(request.state, 'req_id', 'unknown')
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "127.0.0.1").split(",")[0].strip()
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="Arquivo inválido.")

    # --- Validação e Sanitização ---
    safe_filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', file.filename)
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
    if len(file_bytes) < 4 or not file_bytes.startswith(b'PK\x03\x04'):
        log_audit_event(user_id, "FEEDBACK", safe_filename, client_ip, req_id, "failure", "Falha de Magic Bytes")
        raise HTTPException(status_code=415, detail="Arquivo corrompido ou malicioso. Apenas formatos XLSX reais são permitidos.")

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

    # --- Processamento ---
    try:
        pool = require_pool()
    except HTTPException:
        raise  # Já é 503 do require_pool
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro de DB: {str(e)}")
    
    inserted = 0
    updated = 0
    errors = 0

    for row in rows:
        try:
            # 1. Gerar embedding da descrição
            embedding = await generate_embedding(row["descricao"])
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            async with pool.acquire() as conn:
                # 2. Upsert no product_history
                result = await conn.execute(
                    """
                    INSERT INTO product_history (descricao, ean, ncm, grupo, subgrupo, embedding, origem)
                    VALUES ($1, $2, $3, $4, $5, $6::vector, 'Retroalimentação')
                    ON CONFLICT ((LOWER(descricao)))
                    DO UPDATE SET
                        grupo = EXCLUDED.grupo,
                        subgrupo = EXCLUDED.subgrupo,
                        embedding = EXCLUDED.embedding,
                        ean = EXCLUDED.ean,
                        ncm = EXCLUDED.ncm,
                        origem = 'Retroalimentação',
                        updated_at = NOW()
                    """,
                    row["descricao"],
                    row["ean"],
                    row["ncm"],
                    row["grupo"],
                    row["subgrupo"],
                    embedding_str,
                )

                # Verificar se foi INSERT ou UPDATE
                if "INSERT" in result:
                    inserted += 1
                else:
                    updated += 1

        except Exception as e:
            logger.error(
                f"Erro ao processar feedback para '{row['descricao'][:50]}': {e}",
                exc_info=True,
            )
            raise HTTPException(status_code=503, detail=f"Erro de DB: {str(e)}")

    logger.info(
        f"Feedback processado: {inserted} inseridos, {updated} atualizados, {errors} erros"
    )

    log_audit_event(user_id, "FEEDBACK", safe_filename, client_ip, req_id, "success", f"In:{inserted} Up:{updated} Err:{errors}")

    return FeedbackResponse(
        message="Retroalimentação processada com sucesso.",
        inserted=inserted,
        updated=updated,
        errors=errors,
        total=len(rows),
    )
