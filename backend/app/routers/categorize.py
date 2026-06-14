"""
Router: POST /api/categorize e GET /api/jobs/{job_id}

Agora com suporte a background jobs e autenticação.
"""

import os
import re
import uuid
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks, Request
from fastapi.responses import FileResponse
from app.auth import verify_supabase_token
from app.database import require_pool
from app.services.job_manager import create_job, start_job
from app.audit import log_audit_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Categorização"])

MAX_FILE_SIZE = 50 * 1024 * 1024

@router.post("/categorize")
async def categorize_products(
    request: Request,
    background_tasks: BackgroundTasks,
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
    
    # 3. Inicia o background task
    background_tasks.add_task(start_job, job_id, file_path, user_id)
    
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
