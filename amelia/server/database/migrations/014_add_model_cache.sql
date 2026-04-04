CREATE TABLE IF NOT EXISTS model_cache (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT NOT NULL,
    context_length INTEGER,
    max_output_tokens INTEGER,
    input_cost_per_m DOUBLE PRECISION,
    output_cost_per_m DOUBLE PRECISION,
    capabilities JSONB NOT NULL,
    modalities JSONB NOT NULL,
    raw_response JSONB,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_model_cache_provider ON model_cache(provider);
CREATE INDEX IF NOT EXISTS idx_model_cache_fetched_at ON model_cache(fetched_at DESC);
