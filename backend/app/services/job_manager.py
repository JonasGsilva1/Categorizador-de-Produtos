"""
Gerenciador de Jobs em Background.
Salva o arquivo recebido localmente e lança a execução do funil em segundo plano,
atualizando a tabela `processing_jobs` no Supabase com o status e as métricas.
"""

import os
import json
import logging
import traceback
from app.config import get_settings
from app.database import get_pool, require_pool
from app.xlsx_io import read_products, write_results
from app.services.funnel import process_products

logger = logging.getLogger(__name__)


async def start_job(job_id: str, file_path: str, user_id: str) -> None:
    """
    Função principal executada em background via asyncio.create_task().
    1. Atualiza status para PROCESSING.
    2. Lê a planilha.
    3. Executa o funil de categorização.
    4. Salva XLSX final e atualiza job para COMPLETED.
    """
    logger.info(f"[Job {job_id[:8]}] ▶ Background task iniciada.")
    pool = get_pool()
    settings = get_settings()

    try:
        # Mudar status para PROCESSING
        logger.info(f"[Job {job_id[:8]}] Atualizando status → PROCESSING...")
        async with pool.acquire(timeout=15) as conn:
            await conn.execute(
                "UPDATE processing_jobs SET status = 'PROCESSING' WHERE id = $1",
                job_id
            )
        logger.info(f"[Job {job_id[:8]}] Status → PROCESSING ✓")

        # 1. Ler arquivo
        logger.info(f"[Job {job_id[:8]}] Lendo arquivo: {file_path}")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Arquivo temporário não encontrado: {file_path}")

        with open(file_path, "rb") as f:
            file_bytes = f.read()

        products = read_products(file_bytes)
        total_rows = len(products)
        logger.info(f"[Job {job_id[:8]}] {total_rows} produtos lidos.")

        async with pool.acquire(timeout=15) as conn:
            await conn.execute(
                "UPDATE processing_jobs SET total_rows = $1 WHERE id = $2",
                total_rows, job_id
            )

        # 2. Processar via funil de 3 camadas
        logger.info(f"[Job {job_id[:8]}] Iniciando funil (3 camadas)...")

        async def _report_progress(processed: int, aprovados: int, pendentes: int, erros: int):
            """Grava progresso intermediário no DB para o frontend acompanhar."""
            try:
                async with pool.acquire(timeout=10) as conn:
                    await conn.execute(
                        """
                        UPDATE processing_jobs
                        SET processed_rows = $1, aprovados = $2, pendentes = $3, erros = $4
                        WHERE id = $5
                        """,
                        processed, aprovados, pendentes, erros, job_id,
                    )
                logger.info(f"[Job {job_id[:8]}] Progresso: {processed}/{total_rows} processados.")
            except Exception as e:
                logger.warning(f"[Job {job_id[:8]}] Falha ao gravar progresso: {e}")

        results, summary = await process_products(products, pool, concurrency=5, on_progress=_report_progress)
        logger.info(f"[Job {job_id[:8]}] Funil concluído: {summary}")

        aprovados = (
            summary["camada1_ean"]
            + summary["camada2_busca_vetorial"]
            + summary["camada2_llm_aprovado"]
        )

        # 3. Ordenar e persistir resultados em JSON (para revisão no frontend)
        results_sorted = sorted(results, key=lambda r: r.row_index)
        results_path_json = os.path.join(settings.temp_storage_path, f"{job_id}_results.json")
        results_data = [r.model_dump() for r in results_sorted]
        with open(results_path_json, "w", encoding="utf-8") as f:
            json.dump(results_data, f, ensure_ascii=False)
        logger.info(f"[Job {job_id[:8]}] Resultados JSON salvos: {results_path_json}")

        # 4. Gerar XLSX de resultado
        logger.info(f"[Job {job_id[:8]}] Gerando XLSX de resultado...")
        output_buffer = write_results(results_sorted)

        result_path = os.path.join(settings.temp_storage_path, f"{job_id}_result.xlsx")
        with open(result_path, "wb") as f:
            f.write(output_buffer.getbuffer())
        logger.info(f"[Job {job_id[:8]}] XLSX salvo: {result_path}")

        # 5. Marcar como COMPLETED
        async with pool.acquire(timeout=15) as conn:
            await conn.execute(
                """
                UPDATE processing_jobs
                SET status = 'COMPLETED', result_path = $1, results_json_path = $2,
                    processed_rows = $3, aprovados = $4, pendentes = $5, erros = $6
                WHERE id = $7
                """,
                result_path,
                results_path_json,
                total_rows,
                aprovados,
                summary["camada2_llm_pendente_revisao"],
                summary["erros"],
                job_id,
            )
        logger.info(f"[Job {job_id[:8]}] ✅ Concluído com sucesso.")

    except Exception as e:
        tb = traceback.format_exc()
        error_detail = f"{type(e).__name__}: {e}\n\n{tb}"
        logger.error(f"[Job {job_id[:8]}] ❌ Falhou:\n{error_detail}")
        try:
            async with pool.acquire(timeout=15) as conn:
                await conn.execute(
                    "UPDATE processing_jobs SET status = 'FAILED', error_message = $1 WHERE id = $2",
                    error_detail[:4000],
                    job_id,
                )
        except Exception as db_err:
            logger.critical(
                f"[Job {job_id[:8]}] FALHA DUPLA — original: {e} | DB: {db_err}"
            )

    finally:
        # LGPD: remover arquivo temporário original
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"[Job {job_id[:8]}] Arquivo temporário removido: {file_path}")
        except OSError as e:
            logger.error(f"[Job {job_id[:8]}] Falha ao remover arquivo temporário: {e}")


async def create_job(user_id: str, file_bytes: bytes, filename: str) -> tuple[str, str]:
    """
    Cria um registro de job no banco e salva o arquivo fisicamente.
    Retorna (job_id, file_path).
    """
    pool = require_pool()
    settings = get_settings()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO processing_jobs (user_id) VALUES ($1) RETURNING id",
            user_id,
        )
        job_id = str(row["id"])

    # Salvar arquivo temporário
    os.makedirs(settings.temp_storage_path, exist_ok=True)
    file_path = os.path.join(settings.temp_storage_path, f"{job_id}_{filename}")

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE processing_jobs SET file_path = $1 WHERE id = $2",
            file_path,
            job_id,
        )

    logger.info(f"[Job {job_id[:8]}] Criado. Arquivo: {file_path}")
    return job_id, file_path
