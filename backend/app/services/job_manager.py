"""
Gerenciador de Tarefas (Jobs) em Background.
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
    1. Atualiza status para PROCESSING (PROCESSANDO).
    2. Lê a planilha.
    3. Executa o funil de categorização.
    4. Salva XLSX final e atualiza tarefa para COMPLETED (CONCLUÍDO).
    """
    logger.info(f"[Tarefa {job_id[:8]}] ▶ Tarefa em background iniciada.")
    pool_db = get_pool()
    configuracoes = get_settings()

    try:
        # Mudar status para PROCESSING
        logger.info(f"[Tarefa {job_id[:8]}] Atualizando status → PROCESSING...")
        async with pool_db.acquire(timeout=15) as conexao:
            await conexao.execute(
                "UPDATE processing_jobs SET status = 'PROCESSING' WHERE id = $1",
                job_id
            )
        logger.info(f"[Tarefa {job_id[:8]}] Status → PROCESSING ✓")

        # 1. Ler arquivo
        logger.info(f"[Tarefa {job_id[:8]}] Lendo arquivo: {file_path}")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Arquivo temporário não encontrado: {file_path}")

        with open(file_path, "rb") as arquivo:
            produtos = read_products(arquivo)
        total_linhas = len(produtos)
        logger.info(f"[Tarefa {job_id[:8]}] {total_linhas} produtos lidos.")

        async with pool_db.acquire(timeout=15) as conexao:
            await conexao.execute(
                "UPDATE processing_jobs SET total_rows = $1 WHERE id = $2",
                total_linhas, job_id
            )

        # 2. Processar via funil de 3 camadas
        logger.info(f"[Tarefa {job_id[:8]}] Iniciando funil (3 camadas)...")

        async def _reportar_progresso(processados: int, aprovados: int, pendentes: int, erros: int):
            """Grava progresso intermediário no Banco de Dados para o frontend acompanhar."""
            try:
                async with pool_db.acquire(timeout=10) as conexao:
                    await conexao.execute(
                        """
                        UPDATE processing_jobs
                        SET processed_rows = $1, aprovados = $2, pendentes = $3, erros = $4
                        WHERE id = $5
                        """,
                        processados, aprovados, pendentes, erros, job_id,
                    )
                logger.info(f"[Tarefa {job_id[:8]}] Progresso: {processados}/{total_linhas} processados.")
            except Exception as erro_progresso:
                logger.warning(f"[Tarefa {job_id[:8]}] Falha ao gravar progresso: {erro_progresso}")

        resultados, sumario = await process_products(produtos, pool_db, concorrencia=5, ao_progredir=_reportar_progresso)
        logger.info(f"[Tarefa {job_id[:8]}] Funil concluído: {sumario}")

        total_aprovados = (
            sumario["camada1_ean"]
            + sumario["camada2_busca_vetorial"]
            + sumario["camada2_llm_aprovado"]
        )

        # Pendentes = itens não classificados + itens com erro (ambos têm status "Pendente de Revisão")
        total_pendentes = sumario["camada2_llm_pendente_revisao"] + sumario["erros"]

        # 3. Ordenar e persistir resultados em JSON (para revisão no frontend)
        resultados_ordenados = sorted(resultados, key=lambda r: r.row_index)
        caminho_resultados_json = os.path.join(configuracoes.temp_storage_path, f"{job_id}_results.json")
        dados_resultados = [r.model_dump() for r in resultados_ordenados]
        with open(caminho_resultados_json, "w", encoding="utf-8") as arquivo_json:
            json.dump(dados_resultados, arquivo_json, ensure_ascii=False)
        logger.info(f"[Tarefa {job_id[:8]}] Resultados JSON salvos: {caminho_resultados_json}")

        # 4. Gerar XLSX de resultado
        logger.info(f"[Tarefa {job_id[:8]}] Gerando XLSX de resultado...")
        buffer_saida = write_results(resultados_ordenados)

        caminho_resultado = os.path.join(configuracoes.temp_storage_path, f"{job_id}_result.xlsx")
        with open(caminho_resultado, "wb") as arquivo_xlsx:
            arquivo_xlsx.write(buffer_saida.getbuffer())
        logger.info(f"[Tarefa {job_id[:8]}] XLSX salvo: {caminho_resultado}")

        # 5. Marcar como COMPLETED
        async with pool_db.acquire(timeout=15) as conexao:
            await conexao.execute(
                """
                UPDATE processing_jobs
                SET status = 'COMPLETED', result_path = $1, results_json_path = $2,
                    processed_rows = $3, aprovados = $4, pendentes = $5, erros = $6
                WHERE id = $7
                """,
                caminho_resultado,
                caminho_resultados_json,
                total_linhas,
                total_aprovados,
                total_pendentes,
                sumario["erros"],
                job_id,
            )
        logger.info(f"[Tarefa {job_id[:8]}] ✅ Concluído com sucesso.")

    except Exception as excecao:
        rastreamento = traceback.format_exc()
        detalhe_erro = f"{type(excecao).__name__}: {excecao}\n\n{rastreamento}"
        logger.error(f"[Tarefa {job_id[:8]}] ❌ Falhou:\n{detalhe_erro}")
        try:
            async with pool_db.acquire(timeout=15) as conexao:
                await conexao.execute(
                    "UPDATE processing_jobs SET status = 'FAILED', error_message = $1 WHERE id = $2",
                    detalhe_erro[:4000],
                    job_id,
                )
        except Exception as erro_db:
            logger.critical(
                f"[Tarefa {job_id[:8]}] FALHA DUPLA — original: {excecao} | DB: {erro_db}"
            )

    finally:
        # LGPD: remover arquivo temporário original
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"[Tarefa {job_id[:8]}] Arquivo temporário removido: {file_path}")
        except OSError as erro_os:
            logger.error(f"[Tarefa {job_id[:8]}] Falha ao remover arquivo temporário: {erro_os}")


from typing import BinaryIO
import shutil

async def create_job(user_id: str, file_obj: BinaryIO, filename: str) -> tuple[str, str]:
    """
    Cria um registro de tarefa (job) no banco de dados e salva o arquivo fisicamente.
    Retorna (job_id, file_path). Usa shutil para não estourar a memória RAM.
    """
    pool_db = require_pool()
    configuracoes = get_settings()

    async with pool_db.acquire() as conexao:
        linha = await conexao.fetchrow(
            "INSERT INTO processing_jobs (user_id) VALUES ($1) RETURNING id",
            user_id,
        )
        job_id = str(linha["id"])

    # Salvar arquivo temporário
    os.makedirs(configuracoes.temp_storage_path, exist_ok=True)
    caminho_arquivo = os.path.join(configuracoes.temp_storage_path, f"{job_id}_{filename}")

    with open(caminho_arquivo, "wb") as arquivo_temp:
        file_obj.seek(0)
        shutil.copyfileobj(file_obj, arquivo_temp)

    async with pool_db.acquire() as conexao:
        await conexao.execute(
            "UPDATE processing_jobs SET file_path = $1 WHERE id = $2",
            caminho_arquivo,
            job_id,
        )

    logger.info(f"[Tarefa {job_id[:8]}] Criado. Arquivo: {caminho_arquivo}")
    return job_id, caminho_arquivo
