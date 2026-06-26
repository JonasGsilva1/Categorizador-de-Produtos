"""
Router: POST /api/categorize, GET /api/jobs/{job_id},
        GET /api/jobs/{job_id}/results, PATCH /api/jobs/{job_id}/results,
        POST /api/jobs/{job_id}/finalize, GET /api/jobs/{job_id}/download
"""

import os
import re
import uuid
import json
import asyncio
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from app.auth import verify_supabase_token
from app.database import require_pool
from app.services.job_manager import create_job, start_job
from app.models import ProdutoSaida
from app.xlsx_io import write_results
from app.audit import log_audit_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Categorização"])

TAMANHO_MAX_ARQUIVO = 50 * 1024 * 1024

@router.post("/categorize")
async def categorize_products(
    request: Request,
    file: UploadFile = File(...),
    user_data: dict = Depends(verify_supabase_token)
):
    """Envia planilha para categorização em background."""
    id_usuario = user_data["user_id"]
    id_requisicao = getattr(request.state, 'req_id', 'unknown')
    ip_cliente = request.headers.get("X-Forwarded-For", request.client.host if request.client else "127.0.0.1").split(",")[0].strip()

    if not file.filename:
        raise HTTPException(status_code=400, detail="Arquivo inválido.")

    # 0. Sanitização de nome de arquivo (Anti Path-Traversal)
    # Mantém apenas caracteres alfanuméricos, pontos, hifens e underscores
    nome_arquivo_seguro = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', file.filename)
    if not nome_arquivo_seguro.lower().endswith(('.xlsx', '.xls')):
        log_audit_event(id_usuario, "UPLOAD", nome_arquivo_seguro, ip_cliente, id_requisicao, "failure", "Extensão inválida")
        raise HTTPException(status_code=400, detail="Apenas arquivos .xlsx são permitidos.")

    bytes_arquivo = await file.read()
    
    # 1. Validação Anti-Malware (Magic Bytes)
    # Arquivos XLSX são ZIPs sob o capô, portanto a assinatura Hexadecimal inicial deve ser 'PK' (50 4B 03 04)
    if len(bytes_arquivo) < 4 or not bytes_arquivo.startswith(b'PK\x03\x04'):
        raise HTTPException(status_code=415, detail="Arquivo corrompido ou malicioso. Apenas formatos XLSX reais são permitidos.")

    if len(bytes_arquivo) > TAMANHO_MAX_ARQUIVO:
        raise HTTPException(status_code=413, detail=f"Arquivo muito grande.")

    # 2. Cria o Job e salva arquivo temporariamente
    try:
        id_tarefa, caminho_arquivo = await create_job(id_usuario, bytes_arquivo, nome_arquivo_seguro)
    except Exception as excecao:
        log_audit_event(id_usuario, "UPLOAD", nome_arquivo_seguro, ip_cliente, id_requisicao, "failure", f"Erro de DB: {str(excecao)}")
        raise HTTPException(status_code=503, detail=f"Erro de DB: {str(excecao)}")
    
    # 3. Inicia o background task no event loop corrente.
    #    create_task() agenda no loop do Uvicorn, garantindo acesso ao pool asyncpg.
    tarefa = asyncio.get_running_loop().create_task(start_job(id_tarefa, caminho_arquivo, id_usuario))

    def _ao_concluir_tarefa(t: asyncio.Task):
        if t.cancelled():
            logger.warning(f"Background task da tarefa {id_tarefa} foi cancelada.")
        elif t.exception():
            logger.error(f"Background task da tarefa {id_tarefa} terminou com exceção: {t.exception()}")
    tarefa.add_done_callback(_ao_concluir_tarefa)
    
    # 4. Auditoria LGPD
    log_audit_event(id_usuario, "UPLOAD", nome_arquivo_seguro, ip_cliente, id_requisicao, "success", f"Job ID: {id_tarefa}")
    
    return {"job_id": id_tarefa, "message": "Processamento iniciado."}

@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, user_data: dict = Depends(verify_supabase_token)):
    """Consulta o status de um job."""
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de job_id inválido.")

    id_usuario = user_data["user_id"]
    try:
        pool_db = require_pool()
        async with pool_db.acquire() as conexao:
            linha = await conexao.fetchrow(
                """
                SELECT id, status, total_rows, processed_rows, aprovados, pendentes, erros, error_message 
                FROM processing_jobs WHERE id = $1 AND user_id = $2
                """,
                job_id, id_usuario
            )
    except Exception as excecao:
        raise HTTPException(status_code=503, detail=f"Erro de DB: {str(excecao)}")
    
    if not linha:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")

    return dict(linha)

@router.get("/jobs/{job_id}/download")
async def download_job_result(job_id: str, request: Request, user_data: dict = Depends(verify_supabase_token)):
    """Baixa o arquivo .xlsx resultante de um job concluído."""
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de job_id inválido.")

    id_usuario = user_data["user_id"]
    id_requisicao = getattr(request.state, 'req_id', 'unknown')
    ip_cliente = request.headers.get("X-Forwarded-For", request.client.host if request.client else "127.0.0.1").split(",")[0].strip()
    try:
        pool_db = require_pool()
        async with pool_db.acquire() as conexao:
            linha = await conexao.fetchrow(
                "SELECT status, result_path FROM processing_jobs WHERE id = $1 AND user_id = $2",
                job_id, id_usuario
            )
    except Exception as excecao:
        raise HTTPException(status_code=503, detail=f"Erro de DB: {str(excecao)}")
    
    if not linha:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    
    if linha["status"] != "COMPLETED" or not linha["result_path"]:
        raise HTTPException(status_code=400, detail="A tarefa ainda não foi concluída com sucesso.")

    if not os.path.exists(linha["result_path"]):
        log_audit_event(id_usuario, "DOWNLOAD", job_id, ip_cliente, id_requisicao, "failure", "Arquivo não encontrado")
        raise HTTPException(status_code=404, detail="Arquivo de resultado não encontrado no servidor.")

    log_audit_event(id_usuario, "DOWNLOAD", job_id, ip_cliente, id_requisicao, "success")

    return FileResponse(
        path=linha["result_path"],
        filename=f"resultado_categorizacao_{job_id[:8]}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ---------------------------------------------------------------------------
# Modelos para revisão
# ---------------------------------------------------------------------------

class ItemRevisao(BaseModel):
    row_index: int
    grupo: str
    subgrupo: str


class PayloadRevisao(BaseModel):
    items: list[ItemRevisao]


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}/results — retorna todos os resultados (para revisão)
# ---------------------------------------------------------------------------

@router.get("/jobs/{job_id}/results")
async def get_job_results(job_id: str, user_data: dict = Depends(verify_supabase_token)):
    """
    Retorna a lista completa de produtos categorizados do job.
    Inclui os pendentes de revisão para que o frontend possa exibi-los.
    """
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de job_id inválido.")

    id_usuario = user_data["user_id"]
    pool_db = require_pool()

    async with pool_db.acquire() as conexao:
        linha = await conexao.fetchrow(
            "SELECT status, results_json_path FROM processing_jobs WHERE id = $1 AND user_id = $2",
            job_id, id_usuario,
        )

    if not linha:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    if linha["status"] != "COMPLETED":
        raise HTTPException(status_code=400, detail="Tarefa ainda não concluída.")
    if not linha["results_json_path"] or not os.path.exists(linha["results_json_path"]):
        raise HTTPException(status_code=404, detail="Arquivo de resultados não encontrado.")

    with open(linha["results_json_path"], encoding="utf-8") as arquivo:
        resultados = json.load(arquivo)

    return {"results": resultados, "total": len(resultados)}


# ---------------------------------------------------------------------------
# PATCH /api/jobs/{job_id}/results — aplica correções do usuário
# ---------------------------------------------------------------------------

@router.patch("/jobs/{job_id}/results")
async def patch_job_results(
    job_id: str,
    payload: PayloadRevisao,
    user_data: dict = Depends(verify_supabase_token),
):
    """
    Recebe lista de correções {row_index, grupo, subgrupo} e aplica sobre o JSON
    de resultados salvo. Não regenera o XLSX ainda — isso é feito em /finalize.
    """
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de job_id inválido.")

    id_usuario = user_data["user_id"]
    pool_db = require_pool()

    async with pool_db.acquire() as conexao:
        linha = await conexao.fetchrow(
            "SELECT status, results_json_path FROM processing_jobs WHERE id = $1 AND user_id = $2",
            job_id, id_usuario,
        )

    if not linha:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    if linha["status"] != "COMPLETED":
        raise HTTPException(status_code=400, detail="Tarefa ainda não concluída.")
    if not linha["results_json_path"] or not os.path.exists(linha["results_json_path"]):
        raise HTTPException(status_code=404, detail="Arquivo de resultados não encontrado.")

    with open(linha["results_json_path"], encoding="utf-8") as arquivo:
        resultados: list[dict] = json.load(arquivo)

    # Índice por row_index para acesso O(1)
    indice = {item["row_index"]: item for item in resultados}
    aplicadas = 0

    for correcao in payload.items:
        if correcao.row_index in indice:
            indice[correcao.row_index]["grupo"] = correcao.grupo
            indice[correcao.row_index]["subgrupo"] = correcao.subgrupo
            indice[correcao.row_index]["origem"] = "Revisão Manual"
            indice[correcao.row_index]["status"] = "Aprovado"
            aplicadas += 1

    # Salvar JSON atualizado
    with open(linha["results_json_path"], "w", encoding="utf-8") as arquivo_atualizado:
        json.dump(resultados, arquivo_atualizado, ensure_ascii=False)

    # Atualizar métricas de pendentes no DB
    pendentes = sum(1 for r in resultados if r["status"] == "Pendente de Revisão")
    aprovados = sum(1 for r in resultados if r["status"] == "Aprovado")
    async with pool_db.acquire() as conexao:
        await conexao.execute(
            "UPDATE processing_jobs SET pendentes = $1, aprovados = $2 WHERE id = $3",
            pendentes, aprovados, job_id,
        )

    logger.info(f"[Tarefa {job_id[:8]}] {aplicadas} correções aplicadas. Pendentes restantes: {pendentes}")
    return {"applied": aplicadas, "pendentes_restantes": pendentes}


# ---------------------------------------------------------------------------
# POST /api/jobs/{job_id}/finalize — regenera XLSX com revisões aplicadas
# ---------------------------------------------------------------------------

@router.post("/jobs/{job_id}/finalize")
async def finalize_job(
    job_id: str,
    request: Request,
    user_data: dict = Depends(verify_supabase_token),
):
    """
    Regenera o arquivo XLSX final a partir do JSON revisado.
    Deve ser chamado após todas as correções do usuário estarem aplicadas.
    """
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de job_id inválido.")

    id_usuario = user_data["user_id"]
    id_requisicao = getattr(request.state, "req_id", "unknown")
    ip_cliente = request.headers.get("X-Forwarded-For", "127.0.0.1").split(",")[0].strip()
    pool_db = require_pool()

    async with pool_db.acquire() as conexao:
        linha = await conexao.fetchrow(
            "SELECT status, results_json_path, result_path FROM processing_jobs WHERE id = $1 AND user_id = $2",
            job_id, id_usuario,
        )

    if not linha:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    if linha["status"] != "COMPLETED":
        raise HTTPException(status_code=400, detail="Tarefa ainda não concluída.")
    if not linha["results_json_path"] or not os.path.exists(linha["results_json_path"]):
        raise HTTPException(status_code=404, detail="Arquivo de resultados não encontrado.")

    with open(linha["results_json_path"], encoding="utf-8") as arquivo:
        resultados_raw: list[dict] = json.load(arquivo)

    # Reconstruir ProdutoSaida e gerar XLSX
    produtos = [ProdutoSaida(**r) for r in resultados_raw]
    produtos_ordenados = sorted(produtos, key=lambda p: p.row_index)
    buffer_saida = write_results(produtos_ordenados)

    # Sobrescrever o XLSX existente
    caminho_resultado = linha["result_path"]
    with open(caminho_resultado, "wb") as arquivo_xlsx:
        arquivo_xlsx.write(buffer_saida.getbuffer())

    log_audit_event(id_usuario, "FINALIZE", job_id, ip_cliente, id_requisicao, "success")
    logger.info(f"[Tarefa {job_id[:8]}] XLSX finalizado com revisões.")
    return {"message": "Arquivo finalizado com sucesso.", "pronto_para_download": True}
