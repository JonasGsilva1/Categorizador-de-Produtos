"""
Modelos Pydantic para request/response e domínio.
"""

from pydantic import BaseModel, Field


# =============================================================
# Modelos de Domínio
# =============================================================

class ProdutoEntrada(BaseModel):
    """Produto lido da planilha de entrada."""
    row_index: int = Field(description="Índice da linha na planilha original")
    descricao: str = Field(description="Descrição do produto")
    ean: str = Field(default="", description="Código EAN/GTIN")
    ncm: str = Field(default="", description="Código NCM")


class ProdutoSaida(BaseModel):
    """Produto processado com categorização."""
    row_index: int
    descricao: str
    ean: str = ""
    ncm: str = ""
    grupo: str = ""
    subgrupo: str = ""
    origem: str = Field(description="Origem da decisão: EAN/NCM, Busca Vetorial, LLM, LLM (Baixa Confiança)")
    status: str = Field(description="Aprovado ou Pendente de Revisão")




# =============================================================
# Modelos de Response da API
# =============================================================

class RespostaSaude(BaseModel):
    """Resposta da verificação de saúde."""
    status: str = "ok"
    service: str = "categorizador-backend"
    version: str = "1.0.0"
    database: str = "unknown"


class RespostaRetroalimentacao(BaseModel):
    """Resposta do endpoint de retroalimentação."""
    message: str
    inserted: int = 0
    updated: int = 0
    errors: int = 0
    total: int = 0


class RespostaErro(BaseModel):
    """Resposta de erro padrão."""
    detail: str
