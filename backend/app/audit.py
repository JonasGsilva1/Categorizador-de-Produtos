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
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(handler)
logger.setLevel(logging.INFO)
# Impede que os logs sejam duplicados no root logger
logger.propagate = False

def log_audit_event(
    user_id: str,
    action: str,
    resource: str,
    ip_address: str = "unknown",
    req_id: str = "unknown",
    status: str = "success",
    details: str = ""
):
    """
    Registra um evento de auditoria conforme exigências da LGPD.
    - user_id: ID do usuário (Supabase Auth)
    - action: 'UPLOAD', 'DOWNLOAD', 'FEEDBACK'
    - resource: Nome do arquivo ou ID do job
    - ip_address: IP do cliente
    - req_id: ID único da requisição
    - status: 'success', 'failure'
    - details: Mensagem de erro se falha, ou metadados de sucesso
    """
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "audit": True,
        "req_id": req_id,
        "user_id": user_id,
        "action": action,
        "resource": resource,
        "ip_address": ip_address,
        "status": status,
        "details": details
    }
    
    logger.info(json.dumps(event))
