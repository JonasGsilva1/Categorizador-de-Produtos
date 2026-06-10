"""
Modelos Pydantic para request/response e domínio.
"""

from pydantic import BaseModel, Field


# =============================================================
# Modelos de Domínio
# =============================================================

class ProductInput(BaseModel):
    """Produto lido da planilha de entrada."""
    row_index: int = Field(description="Índice da linha na planilha original")
    descricao: str = Field(description="Descrição do produto")
    ean: str = Field(default="", description="Código EAN/GTIN")
    ncm: str = Field(default="", description="Código NCM")


class ProductOutput(BaseModel):
    """Produto processado com categorização."""
    row_index: int
    descricao: str
    ean: str = ""
    ncm: str = ""
    grupo: str = ""
    subgrupo: str = ""
    origem: str = Field(description="Origem da decisão: EAN/NCM, Busca Vetorial, LLM, LLM (Baixa Confiança)")
    status: str = Field(description="Aprovado ou Pendente de Revisão")


class LLMClassification(BaseModel):
    """Resposta estruturada do LLM."""
    grupo: str = Field(description="Grupo/categoria principal do produto")
    subgrupo: str = Field(description="Subcategoria do produto")
    grau_de_confianca: int = Field(
        ge=0, le=100,
        description="Grau de confiança da classificação (0-100%)"
    )


class VectorMatch(BaseModel):
    """Resultado de busca por similaridade vetorial."""
    id: int
    descricao: str
    grupo: str
    subgrupo: str
    similarity: float


# =============================================================
# Modelos de Response da API
# =============================================================

class HealthResponse(BaseModel):
    """Resposta do health check."""
    status: str = "ok"
    service: str = "categorizador-backend"
    version: str = "1.0.0"


class FeedbackResponse(BaseModel):
    """Resposta do endpoint de retroalimentação."""
    message: str
    inserted: int = 0
    updated: int = 0
    errors: int = 0
    total: int = 0


class ErrorResponse(BaseModel):
    """Resposta de erro padrão."""
    detail: str
