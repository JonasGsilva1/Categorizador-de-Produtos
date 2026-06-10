"""
Router: POST /api/categorize e GET /api/jobs/{job_id}

Agora com suporte a background jobs e autenticação.
"""

import os
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse
from app.auth import verify_supabase_token
from app.database import get_pool
from app.services.job_manager import create_job, start_job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Categorização"])

MAX_FILE_SIZE = 50 * 1024 * 1024

@router.post("/categorize")
async def categorize_products(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Depends(verify_supabase_token)
):
    """Envia planilha para categorização em background."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Arquivo inválido.")

    file_bytes = await file.read()
    
    # 1. Validação Anti-Malware (Magic Bytes)
    # Arquivos XLSX são ZIPs sob o capô, portanto a assinatura Hexadecimal inicial deve ser 'PK' (50 4B 03 04)
    if len(file_bytes) < 4 or not file_bytes.startswith(b'PK\x03\x04'):
        raise HTTPException(status_code=415, detail="Arquivo corrompido ou malicioso. Apenas formatos XLSX reais são permitidos.")

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"Arquivo muito grande.")

    # 2. Cria o Job e salva arquivo temporariamente
    job_id, file_path = await create_job(user_id, file_bytes, file.filename)
    
    # 2. Inicia o background task
    background_tasks.add_task(start_job, job_id, file_path, user_id)
    
    return {"job_id": job_id, "message": "Processamento iniciado."}

@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, user_id: str = Depends(verify_supabase_token)):
    """Consulta o status de um job."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, status, total_rows, processed_rows, aprovados, pendentes, erros, error_message 
            FROM processing_jobs WHERE id = $1 AND user_id = $2
            """,
            job_id, user_id
        )
    
    if not row:
        raise HTTPException(status_code=404, detail="Job não encontrado.")

    return dict(row)

@router.get("/jobs/{job_id}/download")
async def download_job_result(job_id: str, user_id: str = Depends(verify_supabase_token)):
    """Baixa o arquivo .xlsx resultante de um job concluído."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, result_path FROM processing_jobs WHERE id = $1 AND user_id = $2",
            job_id, user_id
        )
    
    if not row:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    
    if row["status"] != "COMPLETED" or not row["result_path"]:
        raise HTTPException(status_code=400, detail="O Job ainda não foi concluído com sucesso.")

    if not os.path.exists(row["result_path"]):
        raise HTTPException(status_code=404, detail="Arquivo de resultado não encontrado no servidor.")

    return FileResponse(
        path=row["result_path"],
        filename=f"resultado_categorizacao_{job_id[:8]}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
