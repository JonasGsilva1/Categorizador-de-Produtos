-- =============================================================
-- CATEGORIZADOR INTELIGENTE DE PRODUTOS
-- Schema SQL para Supabase (PostgreSQL + pgvector)
-- =============================================================

-- 1. Habilitar extensão pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================
-- TABELAS DE REGRAS DETERMINÍSTICAS (Camada 1)
-- =============================================================

-- Tabela de regras por EAN (código de barras)
CREATE TABLE IF NOT EXISTS ean_rules (
    id          BIGSERIAL PRIMARY KEY,
    ean         VARCHAR(14) NOT NULL,
    grupo       TEXT NOT NULL,
    subgrupo    TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT uq_ean UNIQUE (ean)
);

-- Índice para busca rápida por EAN
CREATE INDEX IF NOT EXISTS idx_ean_rules_ean ON ean_rules (ean);

-- Tabela de regras por prefixo NCM
CREATE TABLE IF NOT EXISTS ncm_rules (
    id          BIGSERIAL PRIMARY KEY,
    ncm_prefix  VARCHAR(10) NOT NULL,
    grupo       TEXT NOT NULL,
    subgrupo    TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_ncm_prefix UNIQUE (ncm_prefix)
);

-- Índice para busca por prefixo NCM (usado com LIKE 'prefix%')
CREATE INDEX IF NOT EXISTS idx_ncm_rules_prefix ON ncm_rules (ncm_prefix);

-- =============================================================
-- TABELA DE HISTÓRICO DE PRODUTOS COM EMBEDDINGS (Camada 2)
-- =============================================================

CREATE TABLE IF NOT EXISTS product_history (
    id          BIGSERIAL PRIMARY KEY,
    descricao   TEXT NOT NULL,
    ean         VARCHAR(14),
    ncm         VARCHAR(10),
    grupo       TEXT NOT NULL,
    subgrupo    TEXT NOT NULL,
    embedding   VECTOR(1536) NOT NULL,
    origem      TEXT NOT NULL DEFAULT 'Manual',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Índice HNSW para busca por similaridade de cosseno (otimizado)
-- m=16: bom equilíbrio entre memória e recall
-- ef_construction=200: alta qualidade do índice (construção mais lenta, busca melhor)
CREATE INDEX IF NOT EXISTS idx_product_history_embedding 
    ON product_history 
    USING hnsw (embedding vector_cosine_ops) 
    WITH (m = 16, ef_construction = 200);

-- Índice para evitar duplicatas por descrição normalizada
CREATE INDEX IF NOT EXISTS idx_product_history_descricao 
    ON product_history USING btree (LOWER(descricao));

-- =============================================================
-- FUNÇÃO RPC: Busca por Similaridade de Cosseno
-- =============================================================

CREATE OR REPLACE FUNCTION match_products(
    query_embedding VECTOR(1536),
    match_threshold FLOAT DEFAULT 0.98,
    match_count INT DEFAULT 1
)
RETURNS TABLE (
    id          BIGINT,
    descricao   TEXT,
    grupo       TEXT,
    subgrupo    TEXT,
    similarity  FLOAT
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT
        ph.id,
        ph.descricao,
        ph.grupo,
        ph.subgrupo,
        (1 - (ph.embedding <=> query_embedding))::FLOAT AS similarity
    FROM product_history ph
    WHERE (1 - (ph.embedding <=> query_embedding)) >= match_threshold
    ORDER BY ph.embedding <=> query_embedding ASC
    LIMIT match_count;
END;
$$;

-- =============================================================
-- FUNÇÃO RPC: Busca NCM por prefixo decrescente
-- Tenta match com o prefixo mais longo primeiro (8 → 6 → 4 → 2 dígitos)
-- =============================================================

CREATE OR REPLACE FUNCTION match_ncm_rule(
    input_ncm VARCHAR
)
RETURNS TABLE (
    grupo    TEXT,
    subgrupo TEXT
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT nr.grupo, nr.subgrupo
    FROM ncm_rules nr
    WHERE input_ncm LIKE nr.ncm_prefix || '%'
    ORDER BY LENGTH(nr.ncm_prefix) DESC
    LIMIT 1;
END;
$$;

-- =============================================================
-- TRIGGERS: Auto-update de updated_at
-- =============================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_ean_rules_updated_at
    BEFORE UPDATE ON ean_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_ncm_rules_updated_at
    BEFORE UPDATE ON ncm_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_product_history_updated_at
    BEFORE UPDATE ON product_history
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================
-- PERMISSÕES (para uso via Supabase service_role ou anon)
-- =============================================================

-- Habilitar RLS (Row Level Security) - desabilitado para uso via service_role
ALTER TABLE ean_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE ncm_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE product_history ENABLE ROW LEVEL SECURITY;

-- Políticas permissivas para service_role (backend)
-- Se usar via service_role key, RLS é ignorado automaticamente.
-- Caso queira acesso via anon, crie políticas específicas.

-- Policy para permitir leitura pública (se necessário via anon)
CREATE POLICY "Allow read access" ON ean_rules FOR SELECT USING (true);
CREATE POLICY "Allow read access" ON ncm_rules FOR SELECT USING (true);
CREATE POLICY "Allow read access" ON product_history FOR SELECT USING (true);

-- Policy para permitir inserção via service_role (fallback)
CREATE POLICY "Allow insert access" ON ean_rules FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow insert access" ON ncm_rules FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow insert access" ON product_history FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow update access" ON ean_rules FOR UPDATE USING (true);
CREATE POLICY "Allow update access" ON ncm_rules FOR UPDATE USING (true);
CREATE POLICY "Allow update access" ON product_history FOR UPDATE USING (true);

-- =============================================================
-- JOBS (Processamento Ass�ncrono)
-- =============================================================

CREATE TABLE IF NOT EXISTS processing_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL, -- referenciar auth.users via RLS ou externalmente
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- PENDING, PROCESSING, COMPLETED, FAILED
    total_rows      INT DEFAULT 0,
    processed_rows  INT DEFAULT 0,
    aprovados       INT DEFAULT 0,
    pendentes       INT DEFAULT 0,
    erros           INT DEFAULT 0,
    file_path       TEXT,
    result_path     TEXT,
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TRIGGER trigger_processing_jobs_updated_at
    BEFORE UPDATE ON processing_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- =============================================================
-- ROW LEVEL SECURITY (RLS) - CYBERSECURITY & LGPD
-- =============================================================

ALTER TABLE processing_jobs ENABLE ROW LEVEL SECURITY;

-- Pol�tica restrita: O usu�rio s� pode ver e alterar os seus pr�prios jobs
CREATE POLICY "Isolamento de Tenant: Ver apenas pr�prios jobs" ON processing_jobs
FOR SELECT USING (user_id = auth.uid());

CREATE POLICY "Isolamento de Tenant: Modificar apenas pr�prios jobs" ON processing_jobs
FOR UPDATE USING (user_id = auth.uid());

CREATE POLICY "Isolamento de Tenant: Inserir pr�prios jobs" ON processing_jobs
FOR INSERT WITH CHECK (user_id = auth.uid());

