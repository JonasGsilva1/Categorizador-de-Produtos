"""
Orquestrador do Funil de 3 Camadas com Processamento em Lotes.

1. Camada 1: Validação Determinística (apenas EAN Local)
2. Camada 2: Busca Vetorial Rápida (pgvector)
3. Camada 3: Inteligência Artificial (Gemini) em Lotes (chunks de 30) + Filtro
"""

import logging
import asyncio
import asyncpg
from app.models import ProductInput, ProductOutput
from app.services.layer1_deterministic import layer1_lookup
from app.services.layer2_ai import vector_search, save_to_history
from app.services.embedding import generate_embedding
from app.services.llm import classify_products_batch
from app.services.layer3_filter import layer3_filter

logger = logging.getLogger(__name__)

class FunnelMetrics:
    def __init__(self):
        self.total: int = 0
        self.layer1_ean: int = 0
        self.layer2_vector: int = 0
        self.layer2_llm_approved: int = 0
        self.layer2_llm_pending: int = 0
        self.errors: int = 0

    def summary(self) -> dict:
        return {
            "total_processado": self.total,
            "camada1_ean": self.layer1_ean,
            "camada2_busca_vetorial": self.layer2_vector,
            "camada2_llm_aprovado": self.layer2_llm_approved,
            "camada2_llm_pendente_revisao": self.layer2_llm_pending,
            "erros": self.errors,
        }

async def process_products(
    products: list[ProductInput],
    pool: asyncpg.Pool,
    concurrency: int = 5,
) -> tuple[list[ProductOutput], dict]:
    """
    Processa a lista de produtos com otimização de lotes na Camada 3.
    """
    metrics = FunnelMetrics()
    metrics.total = len(products)
    results: list[ProductOutput] = []

    # Passo 1: Processar Camadas 1 e 2 com controle de concorrência
    pendentes_llm = []
    
    # Semáforo de conexões DB: pool max_size=10, reservamos 2 para overhead
    # Cada coroutine pode precisar de até 2 conexões (layer1 + vector_search),
    # então limitamos a 4 coroutines simultâneas = 8 conexões max
    db_semaphore = asyncio.Semaphore(4)
    
    async def process_l1_l2(product: ProductInput):
        async with db_semaphore:
            # Camada 1
            l1_result = await layer1_lookup(product, pool)
            if l1_result:
                metrics.layer1_ean += 1
                logger.info(f"[Linha {product.row_index}] Camada 1 ✓ EAN → {l1_result.grupo}/{l1_result.subgrupo}")
                return l1_result, None, None
            
            # Camada 2
            embedding = await generate_embedding(product.descricao)
            vector_match = await vector_search(embedding, pool, threshold=0.98)
            
            if vector_match:
                metrics.layer2_vector += 1
                logger.info(f"[Linha {product.row_index}] Camada 2 ✓ Busca Vetorial → {vector_match.grupo}/{vector_match.subgrupo}")
                output = ProductOutput(
                    row_index=product.row_index,
                    descricao=product.descricao,
                    ean=product.ean,
                    ncm=product.ncm,
                    grupo=vector_match.grupo,
                    subgrupo=vector_match.subgrupo,
                    origem="Busca Vetorial",
                    status="Aprovado",
                )
                return output, None, None
                
            # Adiar LLM
            return None, product, embedding

    logger.info(f"Iniciando avaliação rápida das Camadas 1 e 2 ({len(products)} itens)")
    
    # Processar em lotes seguros para evitar explosão de tasks
    l1_l2_batch_size = 50
    for batch_start in range(0, len(products), l1_l2_batch_size):
        batch = products[batch_start:batch_start + l1_l2_batch_size]
        tasks = [process_l1_l2(p) for p in batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in batch_results:
            if isinstance(result, Exception):
                logger.error(f"Erro inesperado na Camada 1/2: {result}")
                metrics.errors += 1
                continue
            output, product, embedding = result
            if output:
                results.append(output)
            elif product:
                pendentes_llm.append((product, embedding))

    # Passo 2: Processar Camada 3 em Lotes (Chunks)
    chunk_size = 30
    logger.info(f"{len(pendentes_llm)} itens enviados para a Camada 3 (LLM) em lotes de {chunk_size}")
    
    # Dividir em chunks
    for i in range(0, len(pendentes_llm), chunk_size):
        chunk = pendentes_llm[i:i + chunk_size]
        
        # Preparar payload
        payload = [
            {
                "id_linha": p[0].row_index, 
                "descricao": p[0].descricao, 
                "ncm": p[0].ncm
            } 
            for p in chunk
        ]
        
        logger.info(f"Enviando lote de {len(payload)} itens para o Gemini...")
        
        # Chamar Gemini
        resposta_lote = await classify_products_batch(payload)
        
        # Mapear e avaliar Filtro da Camada 3
        for product, embedding in chunk:
            llm_result_dict = resposta_lote.get(product.row_index, {})
            
            if not llm_result_dict:
                metrics.errors += 1
                logger.warning(f"[Linha {product.row_index}] LLM falhou no lote → Pendente de Revisão")
                output = ProductOutput(
                    row_index=product.row_index,
                    descricao=product.descricao,
                    ean=product.ean,
                    ncm=product.ncm,
                    grupo="",
                    subgrupo="",
                    origem="Erro de API",
                    status="Pendente de Revisão",
                )
                results.append(output)
                continue
                
            output = layer3_filter(product, llm_result_dict)
            
            if output.status == "Aprovado":
                metrics.layer2_llm_approved += 1
                try:
                    await save_to_history(
                        product, output.grupo, output.subgrupo,
                        embedding, "LLM", pool,
                    )
                except Exception as e:
                    logger.warning(f"[Linha {product.row_index}] Erro ao salvar no histórico: {e}")
            else:
                metrics.layer2_llm_pending += 1
                
            results.append(output)
            
        # Anti-Bloqueio (Rate Limit) após processar o chunk
        if i + chunk_size < len(pendentes_llm):
            logger.info("Aguardando 5 segundos para evitar Rate Limit da API...")
            await asyncio.sleep(5)

    results_sorted = sorted(results, key=lambda r: r.row_index)
    summary = metrics.summary()
    logger.info(f"Processamento concluído. Métricas: {summary}")

    return results_sorted, summary
