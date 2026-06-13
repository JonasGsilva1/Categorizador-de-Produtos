"""
Gerenciador de Jobs em Background.
Salva o arquivo recebido localmente e lança a execução do funil em segundo plano,
atualizando a tabela `processing_jobs` no Supabase com o status e as métricas.
"""

import os
import uuid
import logging
import asyncio
from pathlib import Path
from app.config import get_settings
from app.database import get_pool, require_pool
from app.xlsx_io import read_products, write_results
from app.services.funnel import process_single_product, FunnelMetrics

logger = logging.getLogger(__name__)

async def start_job(job_id: str, file_path: str, user_id: str) -> None:
    """
    Função principal executada em background.
    1. Lê a planilha.
    2. Atualiza o total_rows no job.
    3. Processa produto a produto com concorrência e reporta progresso ao DB.
    4. Salva XLSX final e atualiza job para COMPLETED.
    """
    pool = get_pool()
    settings = get_settings()

    try:
        # Mudar status para PROCESSING
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE processing_jobs SET status = 'PROCESSING' WHERE id = $1",
                job_id
            )

        # 1. Ler arquivo
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        products = read_products(file_bytes)
        total_rows = len(products)

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE processing_jobs SET total_rows = $1 WHERE id = $2",
                total_rows, job_id
            )

        # 2. Processar Lotes (Chunking gerido por funnel.py)
        results, summary = await process_products(products, pool, concurrency=5)

        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE processing_jobs 
                SET processed_rows = $1, aprovados = $2, pendentes = $3, erros = $4
                WHERE id = $5
                """,
                summary["total_processado"], 
                summary["camada1_ean"] + summary["camada2_busca_vetorial"] + summary["camada2_llm_aprovado"], 
                summary["camada2_llm_pendente_revisao"], 
                summary["erros"], 
                job_id
            )

        # 3. Gerar XLSX final via Pandas (xlsx_io)
        results_sorted = sorted(results, key=lambda r: r.row_index)
        output_buffer = write_results(results_sorted)

        result_path = os.path.join(settings.temp_storage_path, f"{job_id}_result.xlsx")
        with open(result_path, "wb") as f:
            f.write(output_buffer.getbuffer())

        # 4. Finalizar job
        async with pool.acquire() as conn:
            aprovados = summary["camada1_ean"] + summary["camada2_busca_vetorial"] + summary["camada2_llm_aprovado"]
            await conn.execute(
                """
                UPDATE processing_jobs 
                SET status = 'COMPLETED', result_path = $1, processed_rows = $2, 
                    aprovados = $3, pendentes = $4, erros = $5
                WHERE id = $6
                """,
                result_path, total_rows, aprovados, summary["camada2_llm_pendente_revisao"], summary["erros"], job_id
            )

    except Exception as e:
        logger.error(f"Job {job_id} falhou: {e}", exc_info=True)
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE processing_jobs SET status = 'FAILED', error_message = $1 WHERE id = $2",
                str(e), job_id
            )
            
    finally:
        # LGPD: Deleção segura do arquivo original independentemente do sucesso ou falha
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Arquivo temporário deletado com sucesso: {file_path}")
        except OSError as e:
            logger.error(f"Falha ao deletar arquivo temporário {file_path}: {e}")

async def create_job(user_id: str, file_bytes: bytes, filename: str) -> str:
    """
    Cria um registro de job no banco e salva o arquivo fisicamente,
    pronto para o processador de background.
    """
    pool = require_pool()
    settings = get_settings()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO processing_jobs (user_id) VALUES ($1) RETURNING id",
            user_id
        )
        job_id = str(row["id"])

    # Salvar arquivo
    os.makedirs(settings.temp_storage_path, exist_ok=True)
    file_path = os.path.join(settings.temp_storage_path, f"{job_id}_{filename}")
    
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE processing_jobs SET file_path = $1 WHERE id = $2",
            file_path, job_id
        )

    return job_id, file_path
