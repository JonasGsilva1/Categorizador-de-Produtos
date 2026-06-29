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
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
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
    background_tasks: BackgroundTasks,
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

    # 1. Validação Anti-Malware (Magic Bytes) sem carregar o arquivo inteiro na RAM
    assinatura = file.file.read(4)
    file.file.seek(0)
    
    # Arquivos XLSX são ZIPs sob o capô, portanto a assinatura Hexadecimal inicial deve ser 'PK' (50 4B 03 04)
    if len(assinatura) < 4 or not assinatura.startswith(b'PK\x03\x04'):
        raise HTTPException(status_code=415, detail="Arquivo corrompido ou malicioso. Apenas formatos XLSX reais são permitidos.")

    # 2. Cria o Job e salva arquivo temporariamente em chunks
    try:
        id_tarefa, caminho_arquivo = await create_job(id_usuario, file.file, nome_arquivo_seguro)
    except Exception as excecao:
        log_audit_event(id_usuario, "UPLOAD", nome_arquivo_seguro, ip_cliente, id_requisicao, "failure", f"Erro de DB: {str(excecao)}")
        raise HTTPException(status_code=503, detail=f"Erro de DB: {str(excecao)}")
    
    # 3. Inicia o background task via FastAPI de forma segura
    background_tasks.add_task(start_job, id_tarefa, caminho_arquivo, id_usuario)
    
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
# POST /api/jobs/{job_id}/categorize_ai — Categorização on-demand (OpenRouter)
# ---------------------------------------------------------------------------

@router.post("/jobs/{job_id}/categorize_ai")
async def categorize_ai_on_demand(
    job_id: str,
    payload: PayloadRevisao,
    user_data: dict = Depends(verify_supabase_token),
):
    """
    Categoriza itens pendentes via IA (OpenRouter) com streaming SSE.
    Retorna Server-Sent Events com progresso em tempo real.
    
    Eventos SSE enviados:
    - {"type": "progress", "sublote": N, "total_sublotes": M, "classificados": X, "total_acumulado": Y, "total_itens": Z}
    - {"type": "result", "suggested": [...]}  (evento final com todos os resultados)
    - {"type": "error", "message": "..."}  (em caso de falha)
    """
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de job_id inválido.")

    if not payload.items:
        return StreamingResponse(
            _sse_single_event("result", {"suggested": []}),
            media_type="text/event-stream",
        )

    from app.services.openrouter_ai import classify_batch_openrouter

    id_usuario = user_data["user_id"]
    pool_db = require_pool()

    async with pool_db.acquire() as conexao:
        linha = await conexao.fetchrow(
            "SELECT status, results_json_path FROM processing_jobs WHERE id = $1 AND user_id = $2",
            job_id, id_usuario,
        )

    if not linha or not linha["results_json_path"] or not os.path.exists(linha["results_json_path"]):
        raise HTTPException(status_code=404, detail="Arquivo de resultados não encontrado.")

    with open(linha["results_json_path"], encoding="utf-8") as arquivo:
        resultados_raw: list[dict] = json.load(arquivo)
        
    indice_resultados = {r["row_index"]: r for r in resultados_raw}
    
    lote_para_ia = []
    for item in payload.items:
        original = indice_resultados.get(item.row_index)
        if original:
            lote_para_ia.append({
                "id_linha": item.row_index,
                "descricao": original["descricao"],
                "ncm": original.get("ncm", "")
            })
            
    if not lote_para_ia:
        return StreamingResponse(
            _sse_single_event("result", {"suggested": []}),
            media_type="text/event-stream",
        )

    async def gerar_eventos_sse():
        """Generator async que produz eventos SSE conforme cada sub-lote é processado."""
        TAMANHO_LOTE_IA = 20
        total_sublotes = (len(lote_para_ia) - 1) // TAMANHO_LOTE_IA + 1
        
        logger.info(
            f"[Tarefa {job_id[:8]}] SSE: categorização IA para "
            f"{len(lote_para_ia)} itens ({total_sublotes} sub-lotes)."
        )

        # Evento inicial: informar o frontend sobre o tamanho do trabalho
        yield _formatar_sse("start", {
            "total_itens": len(lote_para_ia),
            "total_sublotes": total_sublotes,
            "tamanho_lote": TAMANHO_LOTE_IA,
        })
        
        lote_para_processar = list(lote_para_ia)
        mapeamento_ia = {}
        pausa_entre_lotes = 12
        num_sublote = 0
        
        while lote_para_processar:
            num_sublote += 1
            lote_atual = lote_para_processar[:TAMANHO_LOTE_IA]
            
            logger.info(
                f"Enviando sub-lote {num_sublote} ({len(lote_atual)} itens, "
                f"restam {len(lote_para_processar)} na fila geral)..."
            )
            
            resultado_parcial = await classify_batch_openrouter(lote_atual)
            mapeamento_ia.update(resultado_parcial)
            classificados_neste_lote = len(resultado_parcial)
            
            if classificados_neste_lote > 0:
                logger.info(
                    f"Sub-lote {num_sublote}: {classificados_neste_lote}/{len(lote_atual)} classificados. "
                    f"Total acumulado: {len(mapeamento_ia)}."
                )
                # Sucesso (total ou parcial): remove apenas os classificados.
                # Itens ignorados por JSON truncado continuam na fila para tentar no próximo lote.
                itens_sucesso = set(resultado_parcial.keys())
                lote_para_processar = [
                    item for item in lote_para_processar if item["id_linha"] not in itens_sucesso
                ]
            else:
                logger.warning(
                    f"Sub-lote {num_sublote}: nenhum resultado retornado (0/{len(lote_atual)}). "
                    f"Descartando estes {len(lote_atual)} itens para evitar loop infinito."
                )
                # Falha total: remove o lote inteiro da fila
                lote_para_processar = lote_para_processar[TAMANHO_LOTE_IA:]
                pausa_entre_lotes = min(pausa_entre_lotes + 10, 60)
            
            # Recalcular total_sublotes estimado para a UI
            sublotes_restantes = (len(lote_para_processar) - 1) // TAMANHO_LOTE_IA + 1 if lote_para_processar else 0
            
            sugestoes_parciais = []
            for id_linha, cat in resultado_parcial.items():
                sugestoes_parciais.append({
                    "row_index": id_linha,
                    "grupo": cat.grupo,
                    "subgrupo": cat.subgrupo,
                    "confianca": cat.grau_de_confianca
                })
            
            # Enviar evento de progresso ao frontend
            yield _formatar_sse("progress", {
                "sublote": num_sublote,
                "total_sublotes": num_sublote + sublotes_restantes,
                "classificados_neste_lote": classificados_neste_lote,
                "total_acumulado": len(mapeamento_ia),
                "total_itens": len(lote_para_ia),
                "new_items": sugestoes_parciais,
            })
            
            # Pausa adaptativa entre lotes
            if lote_para_processar:
                logger.info(f"Aguardando {pausa_entre_lotes}s antes do próximo sub-lote...")
                await asyncio.sleep(pausa_entre_lotes)

        # Preparar resultado final
        sugestoes = []
        for id_linha, cat in mapeamento_ia.items():
            sugestoes.append({
                "row_index": id_linha,
                "grupo": cat.grupo,
                "subgrupo": cat.subgrupo,
                "confianca": cat.grau_de_confianca
            })

        logger.info(f"IA finalizada. {len(sugestoes)} sugestões via SSE.")
        
        # Evento final com todos os resultados
        yield _formatar_sse("result", {"suggested": sugestoes})

    return StreamingResponse(
        gerar_eventos_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Desabilita buffering no nginx/proxy
        },
    )


def _formatar_sse(tipo_evento: str, dados: dict) -> str:
    """Formata um evento SSE com tipo e dados JSON."""
    payload = json.dumps(dados, ensure_ascii=False)
    return f"event: {tipo_evento}\ndata: {payload}\n\n"


async def _sse_single_event(tipo: str, dados: dict):
    """Generator para um único evento SSE (caso trivial)."""
    yield _formatar_sse(tipo, dados)


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
