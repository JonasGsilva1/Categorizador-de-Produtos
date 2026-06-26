"""
Logger Estruturado para Auditoria (LGPD Art. 37 - Relatório de Impacto).
Registra ações em dados potencialmente pessoais sem registrar os dados em si.
"""

import logging
import json
from datetime import datetime, timezone

logger = logging.getLogger("lgpd_audit")

# Para o Railway, usaremos o logger padrão (stdout) mas com formatação JSON para
# facilitar extração posterior, caso necessário.
manipulador = logging.StreamHandler()
manipulador.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(manipulador)
logger.setLevel(logging.INFO)
# Impede que os logs sejam duplicados no root logger
logger.propagate = False

def log_audit_event(
    id_usuario: str,
    acao: str,
    recurso: str,
    endereco_ip: str = "unknown",
    id_requisicao: str = "unknown",
    status: str = "success",
    detalhes: str = ""
):
    """
    Registra um evento de auditoria conforme exigências da LGPD.
    - id_usuario: ID do usuário (Supabase Auth)
    - acao: 'UPLOAD', 'DOWNLOAD', 'FEEDBACK'
    - recurso: Nome do arquivo ou ID do job
    - endereco_ip: IP do cliente
    - id_requisicao: ID único da requisição
    - status: 'success', 'failure'
    - detalhes: Mensagem de erro se falha, ou metadados de sucesso
    """
    evento = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "audit": True,
        "req_id": id_requisicao,
        "user_id": id_usuario,
        "action": acao,
        "resource": recurso,
        "ip_address": endereco_ip,
        "status": status,
        "details": detalhes
    }
    
    logger.info(json.dumps(evento))
