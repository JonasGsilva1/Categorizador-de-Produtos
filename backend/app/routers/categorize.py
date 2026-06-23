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
from app.models import ProductOutput
from app.xlsx_io import write_results
from app.audit import log_audit_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Categorização"])

MAX_FILE_SIZE = 50 * 1024 * 1024

@router.post("/categorize")
async def categorize_products(
    request: Request,
    file: UploadFile = File(...),
    user_data: dict = Depends(verify_supabase_token)
):
    """Envia planilha para categorização em background."""
    user_id = user_data["user_id"]
    req_id = getattr(request.state, 'req_id', 'unknown')
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "127.0.0.1").split(",")[0].strip()

    if not file.filename:
        raise HTTPException(status_code=400, detail="Arquivo inválido.")

    # 0. Sanitização de nome de arquivo (Anti Path-Traversal)
    # Mantém apenas caracteres alfanuméricos, pontos, hifens e underscores
    safe_filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', file.filename)
    if not safe_filename.lower().endswith(('.xlsx', '.xls')):
        log_audit_event(user_id, "UPLOAD", safe_filename, client_ip, req_id, "failure", "Extensão inválida")
        raise HTTPException(status_code=400, detail="Apenas arquivos .xlsx são permitidos.")

    file_bytes = await file.read()
    
    # 1. Validação Anti-Malware (Magic Bytes)
    # Arquivos XLSX são ZIPs sob o capô, portanto a assinatura Hexadecimal inicial deve ser 'PK' (50 4B 03 04)
    if len(file_bytes) < 4 or not file_bytes.startswith(b'PK\x03\x04'):
        raise HTTPException(status_code=415, detail="Arquivo corrompido ou malicioso. Apenas formatos XLSX reais são permitidos.")

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"Arquivo muito grande.")

    # 2. Cria o Job e salva arquivo temporariamente
    try:
        job_id, file_path = await create_job(user_id, file_bytes, safe_filename)
    except Exception as e:
        log_audit_event(user_id, "UPLOAD", safe_filename, client_ip, req_id, "failure", f"DB Error: {str(e)}")
        raise HTTPException(status_code=503, detail=f"Erro de DB: {str(e)}")
    
    # 3. Inicia o background task no event loop corrente.
    #    create_task() agenda no loop do Uvicorn, garantindo acesso ao pool asyncpg.
    task = asyncio.get_running_loop().create_task(start_job(job_id, file_path, user_id))

    def _on_task_done(t: asyncio.Task):
        if t.cancelled():
            logger.warning(f"Background task do job {job_id} foi cancelada.")
        elif t.exception():
            logger.error(f"Background task do job {job_id} terminou com exceção: {t.exception()}")
    task.add_done_callback(_on_task_done)
    
    # 4. Auditoria LGPD
    log_audit_event(user_id, "UPLOAD", safe_filename, client_ip, req_id, "success", f"Job ID: {job_id}")
    
    return {"job_id": job_id, "message": "Processamento iniciado."}

@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, user_data: dict = Depends(verify_supabase_token)):
    """Consulta o status de um job."""
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de job_id inválido.")

    user_id = user_data["user_id"]
    try:
        pool = require_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, status, total_rows, processed_rows, aprovados, pendentes, erros, error_message 
                FROM processing_jobs WHERE id = $1 AND user_id = $2
                """,
                job_id, user_id
            )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro de DB: {str(e)}")
    
    if not row:
        raise HTTPException(status_code=404, detail="Job não encontrado.")

    return dict(row)

@router.get("/jobs/{job_id}/download")
async def download_job_result(job_id: str, request: Request, user_data: dict = Depends(verify_supabase_token)):
    """Baixa o arquivo .xlsx resultante de um job concluído."""
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de job_id inválido.")

    user_id = user_data["user_id"]
    req_id = getattr(request.state, 'req_id', 'unknown')
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "127.0.0.1").split(",")[0].strip()
    try:
        pool = require_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status, result_path FROM processing_jobs WHERE id = $1 AND user_id = $2",
                job_id, user_id
            )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro de DB: {str(e)}")
    
    if not row:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    
    if row["status"] != "COMPLETED" or not row["result_path"]:
        raise HTTPException(status_code=400, detail="O Job ainda não foi concluído com sucesso.")

    if not os.path.exists(row["result_path"]):
        log_audit_event(user_id, "DOWNLOAD", job_id, client_ip, req_id, "failure", "Arquivo não encontrado")
        raise HTTPException(status_code=404, detail="Arquivo de resultado não encontrado no servidor.")

    log_audit_event(user_id, "DOWNLOAD", job_id, client_ip, req_id, "success")

    return FileResponse(
        path=row["result_path"],
        filename=f"resultado_categorizacao_{job_id[:8]}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ---------------------------------------------------------------------------
# Modelos para revisão
# ---------------------------------------------------------------------------

class ReviewItem(BaseModel):
    row_index: int
    grupo: str
    subgrupo: str


class ReviewPayload(BaseModel):
    items: list[ReviewItem]


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

    user_id = user_data["user_id"]
    pool = require_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, results_json_path FROM processing_jobs WHERE id = $1 AND user_id = $2",
            job_id, user_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    if row["status"] != "COMPLETED":
        raise HTTPException(status_code=400, detail="Job ainda não concluído.")
    if not row["results_json_path"] or not os.path.exists(row["results_json_path"]):
        raise HTTPException(status_code=404, detail="Arquivo de resultados não encontrado.")

    with open(row["results_json_path"], encoding="utf-8") as f:
        results = json.load(f)

    return {"results": results, "total": len(results)}


# ---------------------------------------------------------------------------
# PATCH /api/jobs/{job_id}/results — aplica correções do usuário
# ---------------------------------------------------------------------------

@router.patch("/jobs/{job_id}/results")
async def patch_job_results(
    job_id: str,
    payload: ReviewPayload,
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

    user_id = user_data["user_id"]
    pool = require_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, results_json_path FROM processing_jobs WHERE id = $1 AND user_id = $2",
            job_id, user_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    if row["status"] != "COMPLETED":
        raise HTTPException(status_code=400, detail="Job ainda não concluído.")
    if not row["results_json_path"] or not os.path.exists(row["results_json_path"]):
        raise HTTPException(status_code=404, detail="Arquivo de resultados não encontrado.")

    with open(row["results_json_path"], encoding="utf-8") as f:
        results: list[dict] = json.load(f)

    # Índice por row_index para acesso O(1)
    index = {item["row_index"]: item for item in results}
    applied = 0

    for correction in payload.items:
        if correction.row_index in index:
            index[correction.row_index]["grupo"] = correction.grupo
            index[correction.row_index]["subgrupo"] = correction.subgrupo
            index[correction.row_index]["origem"] = "Revisão Manual"
            index[correction.row_index]["status"] = "Aprovado"
            applied += 1

    # Salvar JSON atualizado
    with open(row["results_json_path"], "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False)

    # Atualizar métricas de pendentes no DB
    pendentes = sum(1 for r in results if r["status"] == "Pendente de Revisão")
    aprovados = sum(1 for r in results if r["status"] == "Aprovado")
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE processing_jobs SET pendentes = $1, aprovados = $2 WHERE id = $3",
            pendentes, aprovados, job_id,
        )

    logger.info(f"[Job {job_id[:8]}] {applied} correções aplicadas. Pendentes restantes: {pendentes}")
    return {"applied": applied, "pendentes_restantes": pendentes}


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

    user_id = user_data["user_id"]
    req_id = getattr(request.state, "req_id", "unknown")
    client_ip = request.headers.get("X-Forwarded-For", "127.0.0.1").split(",")[0].strip()
    pool = require_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, results_json_path, result_path FROM processing_jobs WHERE id = $1 AND user_id = $2",
            job_id, user_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    if row["status"] != "COMPLETED":
        raise HTTPException(status_code=400, detail="Job ainda não concluído.")
    if not row["results_json_path"] or not os.path.exists(row["results_json_path"]):
        raise HTTPException(status_code=404, detail="Arquivo de resultados não encontrado.")

    with open(row["results_json_path"], encoding="utf-8") as f:
        results_raw: list[dict] = json.load(f)

    # Reconstruir ProductOutput e gerar XLSX
    products = [ProductOutput(**r) for r in results_raw]
    products_sorted = sorted(products, key=lambda p: p.row_index)
    output_buffer = write_results(products_sorted)

    # Sobrescrever o XLSX existente
    result_path = row["result_path"]
    with open(result_path, "wb") as f:
        f.write(output_buffer.getbuffer())

    log_audit_event(user_id, "FINALIZE", job_id, client_ip, req_id, "success")
    logger.info(f"[Job {job_id[:8]}] XLSX finalizado com revisões.")
    return {"message": "Arquivo finalizado com sucesso.", "pronto_para_download": True}
