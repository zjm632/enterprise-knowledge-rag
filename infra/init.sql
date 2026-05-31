CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO schema_migrations(version)
VALUES ('001_enable_pgvector')
ON CONFLICT (version) DO NOTHING;

ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS category VARCHAR(32) DEFAULT 'policy';
UPDATE knowledge_bases SET category = 'policy' WHERE category IS NULL OR category = '';
CREATE INDEX IF NOT EXISTS ix_knowledge_bases_category ON knowledge_bases(category);

INSERT INTO schema_migrations(version)
VALUES ('002_kb_category_rbac')
ON CONFLICT (version) DO NOTHING;
