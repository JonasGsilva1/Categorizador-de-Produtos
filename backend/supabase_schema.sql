-- Habilitar a extensão pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Tabela de Jobs Assíncronos (para controle de upload e processamento em lote)
CREATE TABLE IF NOT EXISTS processing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    status VARCHAR(50) DEFAULT 'PENDING',
    file_path TEXT,
    result_path TEXT,
    total_rows INT DEFAULT 0,
    processed_rows INT DEFAULT 0,
    aprovados INT DEFAULT 0,
    pendentes INT DEFAULT 0,
    erros INT DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabela Central do Histórico de Produtos (usada pela Camada 1: EAN e Camada 2: Vetorial)
CREATE TABLE IF NOT EXISTS product_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    descricao TEXT NOT NULL,
    ean TEXT,
    ncm TEXT,
    grupo TEXT NOT NULL,
    subgrupo TEXT NOT NULL,
    embedding vector(1536), -- Ajuste para 1536 se usar text-embedding-3-small da OpenAI
    origem TEXT, -- Ex: 'LLM', 'Retroalimentação'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Constraint para garantir que a descrição seja única de forma case-insensitive, otimizando o UPSERT
CREATE UNIQUE INDEX IF NOT EXISTS product_history_descricao_lower_idx ON product_history (LOWER(descricao));

-- Índice para busca rápida de EAN exato (Camada 1)
CREATE INDEX IF NOT EXISTS product_history_ean_idx ON product_history (ean);

-- Índice HNSW do pgvector para buscas super rápidas por similaridade de cossenos na Camada 2
-- 'vector_cosine_ops' otimiza o operador <=>
CREATE INDEX IF NOT EXISTS product_history_embedding_idx 
ON product_history 
USING hnsw (embedding vector_cosine_ops);
