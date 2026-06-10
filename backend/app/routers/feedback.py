"""
Router: POST /api/feedback

Recebe a planilha corrigida manualmente pelo usuário e realimenta o banco de dados:
- Insere/atualiza embeddings no product_history
- Insere/atualiza regras em ean_rules e ncm_rules
"""

import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.auth import verify_supabase_token
from app.database import get_pool
from app.models import FeedbackResponse
from app.xlsx_io import read_feedback_products
from app.services.embedding import generate_embedding

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Retroalimentação"])


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    file: UploadFile = File(...),
    user_id: str = Depends(verify_supabase_token)
):
    """
    Endpoint de retroalimentação.
    
    Recebe um arquivo .xlsx corrigido manualmente com colunas:
    Descrição, EAN, NCM, Grupo, Subgrupo.
    
    Para cada linha com Grupo e Subgrupo preenchidos:
    1. Gera embedding da Descrição
    2. Insere/atualiza no product_history (upsert)
    3. Insere/atualiza regras de EAN (se preenchido)
    4. Insere/atualiza regras de NCM (se preenchido, usando prefixo)
    """
    # --- Validação ---
    if not file.filename or not file.filename.endswith((".xlsx", ".XLSX")):
        raise HTTPException(
            status_code=400,
            detail="Formato inválido. Envie um arquivo .xlsx.",
        )

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

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
    pool = get_pool()
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

                # 3. Upsert na ean_rules (se EAN preenchido)
                if row["ean"] and row["ean"].strip():
                    await conn.execute(
                        """
                        INSERT INTO ean_rules (ean, grupo, subgrupo)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (ean) DO UPDATE SET
                            grupo = EXCLUDED.grupo,
                            subgrupo = EXCLUDED.subgrupo,
                            updated_at = NOW()
                        """,
                        row["ean"].strip(),
                        row["grupo"],
                        row["subgrupo"],
                    )

                # 4. Upsert na ncm_rules (se NCM preenchido, usar como prefixo)
                if row["ncm"] and row["ncm"].strip():
                    clean_ncm = row["ncm"].strip().replace(".", "").replace("-", "").replace("/", "")
                    if clean_ncm:
                        await conn.execute(
                            """
                            INSERT INTO ncm_rules (ncm_prefix, grupo, subgrupo)
                            VALUES ($1, $2, $3)
                            ON CONFLICT (ncm_prefix) DO UPDATE SET
                                grupo = EXCLUDED.grupo,
                                subgrupo = EXCLUDED.subgrupo,
                                updated_at = NOW()
                            """,
                            clean_ncm,
                            row["grupo"],
                            row["subgrupo"],
                        )

        except Exception as e:
            errors += 1
            logger.error(
                f"Erro ao processar feedback para '{row['descricao'][:50]}': {e}",
                exc_info=True,
            )

    logger.info(
        f"Feedback processado: {inserted} inseridos, {updated} atualizados, {errors} erros"
    )

    return FeedbackResponse(
        message="Retroalimentação processada com sucesso.",
        inserted=inserted,
        updated=updated,
        errors=errors,
        total=len(rows),
    )
