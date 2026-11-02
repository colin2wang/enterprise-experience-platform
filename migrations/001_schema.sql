-- EEP PostgreSQL 16 + pgvector schema (Phase 1).
-- Companion to src/eep/db/models.py (SQLAlchemy ORM).
-- Author: Wang, Bing <colin2wang@gmail.com>

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------- project
CREATE TABLE IF NOT EXISTS project (
  id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name       TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- ---------------------------------------------------------------- "user"
CREATE TABLE IF NOT EXISTS "user" (
  id     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name   TEXT NOT NULL,
  avatar TEXT
);

-- ---------------------------------------------------------------- meeting
CREATE TABLE IF NOT EXISTS meeting (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id       UUID NOT NULL REFERENCES project(id),
  title            TEXT NOT NULL,
  meet_date        DATE,
  participants     JSONB DEFAULT '[]'::jsonb,
  source_type      TEXT NOT NULL DEFAULT 'upload',   -- upload | transcript | api
  transcript_uri   TEXT,
  summary          TEXT,
  discussion       TEXT,
  review_status    TEXT NOT NULL DEFAULT 'pending',  -- pending | reviewed
  exp_stat_cache   JSONB DEFAULT '{}'::jsonb,
  pipeline_version TEXT NOT NULL DEFAULT 'v1',
  created_at       TIMESTAMPTZ DEFAULT now(),
  updated_at       TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_meeting_project ON meeting (project_id, meet_date DESC);
-- Idempotency: one pipeline run per (meeting, pipeline_version).
CREATE UNIQUE INDEX IF NOT EXISTS uq_meeting_pipeline
  ON meeting (id, pipeline_version);

-- ---------------------------------------------------------------- experience
CREATE TABLE IF NOT EXISTS experience (
  id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id          UUID NOT NULL REFERENCES project(id),
  code                TEXT UNIQUE,
  type                TEXT NOT NULL CHECK (type IN
                        ('question','hypothesis','experiment','decision','action')),
  title               TEXT NOT NULL,
  description         TEXT,
  status              TEXT NOT NULL DEFAULT 'pending',
  owner_id            UUID REFERENCES "user"(id),   -- NULL = unclaimed
  due_date            DATE,                          -- NULL = TBD
  acceptance_criteria TEXT,
  source_meeting_id   UUID,
  source_span         JSONB DEFAULT '{}'::jsonb,
  t_event             DATE,
  t_invalid           DATE,
  superseded_by       UUID,
  embedding           vector(1024),
  created_at          TIMESTAMPTZ DEFAULT now(),
  updated_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_exp_vec
  ON experience USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_exp_filter
  ON experience (project_id, type, status);

-- ---------------------------------------------------------------- extraction
CREATE TABLE IF NOT EXISTS extraction (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  meeting_id    UUID NOT NULL REFERENCES meeting(id),
  draft_json    JSONB DEFAULT '{}'::jsonb,
  model_ver     TEXT,
  confidence    REAL,
  review_status TEXT NOT NULL DEFAULT 'pending',     -- pending | accepted | rejected
  reviewer_id   UUID REFERENCES "user"(id),
  reviewed_at   TIMESTAMPTZ
);

-- ---------------------------------------------------------------- exp_meeting
CREATE TABLE IF NOT EXISTS exp_meeting (
  exp_id          UUID NOT NULL REFERENCES experience(id),
  meeting_id      UUID NOT NULL REFERENCES meeting(id),
  evidence_span   JSONB DEFAULT '{}'::jsonb,
  is_first_record BOOLEAN DEFAULT FALSE,
  PRIMARY KEY (exp_id, meeting_id)
);
CREATE INDEX IF NOT EXISTS idx_exp_meeting_meeting ON exp_meeting (meeting_id);

-- ---------------------------------------------------------------- relation
CREATE TABLE IF NOT EXISTS relation (
  id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  from_exp   UUID NOT NULL REFERENCES experience(id),
  to_exp     UUID NOT NULL REFERENCES experience(id),
  rel_type   TEXT NOT NULL,   -- evolves | supports | grounds | conflicts | suspected_duplicate
  origin     TEXT NOT NULL DEFAULT 'AI',  -- manual | AI
  confidence REAL,
  meeting_id UUID
);
CREATE INDEX IF NOT EXISTS idx_rel_from ON relation (from_exp);
CREATE INDEX IF NOT EXISTS idx_rel_to   ON relation (to_exp);

-- ---------------------------------------------------------------- change_log
-- Append-only audit trail: INSERT only, UPDATE/DELETE rejected by trigger.
CREATE TABLE IF NOT EXISTS change_log (
  id          BIGSERIAL PRIMARY KEY,
  entity_type TEXT NOT NULL,
  entity_id   UUID,
  field       TEXT NOT NULL,
  old_value   TEXT,
  new_value   TEXT,
  actor_id    UUID,
  at          TIMESTAMPTZ DEFAULT now(),
  source      TEXT DEFAULT 'ui'  -- ui | background-sync
);

CREATE OR REPLACE FUNCTION forbid_change_log_update() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'change_log is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_change_log_ro ON change_log;
CREATE TRIGGER trg_change_log_ro
  BEFORE UPDATE OR DELETE ON change_log
  FOR EACH ROW EXECUTE FUNCTION forbid_change_log_update();

-- ---------------------------------------------------------------- integration
CREATE TABLE IF NOT EXISTS integration (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name         TEXT NOT NULL,
  scope        TEXT,
  status       TEXT DEFAULT 'connected',
  last_sync_at TIMESTAMPTZ
);

-- ---------------------------------------------------------------- ai_provider
CREATE TABLE IF NOT EXISTS ai_provider (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name          TEXT NOT NULL UNIQUE,
  type          TEXT NOT NULL,
  base_url      TEXT NOT NULL,
  status        TEXT DEFAULT 'unknown',
  breaker_state TEXT DEFAULT 'closed',
  last_probe_at TIMESTAMPTZ
);
