# EEP — Enterprise Experience Platform (AI Pipeline Service)

The Python AI backend + Vue 3 web frontend of the **EEP Enterprise Experience
Platform** — a "meeting → experience → decision → action" closed-loop
knowledge system.

Meetings are ingested through an AI pipeline (LangGraph), extracted into
structured experience units (question / hypothesis / experiment / decision /
action), reviewed by humans, and promoted into a traceable experience library
that supports decision retrospectives, action follow-up, and pre-meeting
briefings.

## Features

- **AI Provider layer** — role-based model routing (`extractor` / `summarizer`
  / `linker` / `memory-manager`) with circuit breaking, per-provider
  concurrency limits, and health probes. Configuration lives in a single
  `ai-providers.yaml`.
- **Four LangGraph graphs**
  - **G1 `ingestion`** — summarize → chunk → parallel extraction (`Send`) →
    dedupe/link → draft memory. AI writes *only* to the draft layer.
  - **G2 `review`** — human-in-the-loop via `interrupt()`; the review queue is
    the set of suspended threads; verdicts resume the graph with
    `Command(resume=...)`.
  - **G3 `briefing`** — pre-meeting briefing composed strictly from stored
    facts, every line carrying a source link.
  - **G4 `qa`** — experience Q&A with forced `meeting_id + span` citations.
- **Dual-layer memory** — draft layer (AI, low-confidence, reversible) is
  promoted into the formal layer (human-reviewed, audited) only after review;
  dual timeline (`t_event` / `t_invalid`) plus supersession for fact decay.
- **Audit trail** — append-only `change_log` (INSERT-only trigger), field-level
  old → new values for every edit.
- **Web UI** — Vue 3 + TypeScript single-page frontend (Vite build) served at
  `/web/`: decision overview, meetings (incl. transcript push form),
  extraction review workbench, experience library, evolution chain (five
  swimlanes), action follow-up, connected services.

## Project layout

```
ai-providers.yaml         # AI provider config (single source of truth)
eep.yml                   # Service config (database switch, host/port) — documented inline
migrations/001_schema.sql # PostgreSQL 16 + pgvector schema (sqlite auto-initializes instead)
src/eep/
  config.py               # Settings: env EEP_* > eep.yml > defaults
  ai_providers/           # ModelFactory, breaker, health probe, semaphores
  db/                     # SQLAlchemy async models (cross-dialect UUID)
  graphs/                 # G1-G4 LangGraph graphs + extraction prompt (L1-L4 ladder)
  memory/                 # MemoryService: filter -> vector -> edges -> rerank
  api/                    # REST routes (all under /v1)
  checkpoints.py          # PostgresSaver checkpointer (InMemory fallback)
  codes.py                # experience code generator (action-114 style)
  seed.py                 # demo dataset (fictional English content, fixed project UUID)
frontend/                 # Vue 3 + TypeScript SPA source (Vite)
web/                      # Frontend build output — served statically by FastAPI at /web
tests/                    # pytest suite
web-build.ps1             # pnpm build -> web/
web-run.ps1               # vite dev server (proxies /v1 to :8100)
docker-compose.yml        # postgres(pgvector) / redis / minio / ai-worker
Dockerfile
```

## Quick start

Requirements: Python 3.12+, Node 20+ with pnpm (frontend only). SQLite is the
default database — **no external services needed**.

```bash
# 1. Create venv and install
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"        # Windows
# .venv/bin/pip install -e ".[dev]"          # Linux/macOS

# 2. Run the backend (binds to 127.0.0.1 only)
.venv/Scripts/uvicorn eep.main:app --port 8100

# 3. Open
#    Web UI:    http://localhost:8100/web/
#    API docs:  http://localhost:8100/docs
#    Health:    http://localhost:8100/healthz
```

On startup with SQLite the service **auto-creates `eep.db` and all tables**.
Startup log prints the access URLs.

The backend serves whatever is currently in `web/`; build the frontend first
(see below) or run the dev server for hot reload.

### Frontend (Vue 3 + TypeScript)

Two ways to run the frontend — both expect the backend on `127.0.0.1:8100`
(start it yourself; the scripts never launch Python):

```powershell
# Production build: type-checks (vue-tsc) and outputs to web/, served at /web by the backend
./web-build.ps1

# Dev server with hot reload at http://localhost:5173/web/  (/v1 is proxied to :8100)
./web-run.ps1
```

Equivalent raw commands: `pnpm build` / `pnpm run dev` inside `frontend/`.

### Demo data (fictional, fully anonymized)

Seed the demo dataset: project **"Demo Project"** (fixed UUID
`00000000-0000-0000-0000-000000000001`, matching the frontend default), 5
reviewed meetings, 16 experiences (1 question + 2 experiments + 6 decisions +
7 actions, including the `action-114` reference sample), evidence links and
evolution-chain relations. All content is **fictional English** with
placeholder people (Alice Johnson, Brian Miller, Clara Schmidt, David
Thompson) and a knowledge-base Q&A / smart ticket routing scenario:

```bash
.venv/Scripts/python -m eep.seed          # skip if already seeded
.venv/Scripts/python -m eep.seed --force  # wipe and reseed
```

Adding content through the UI: **Meetings → Add meeting** pushes a transcript
(`POST /v1/projects/{pid}/meetings`), which triggers G1 extraction; drafts
then appear in **Extraction Review** for human verdicts.

## Configuration

### Switching the database (`eep.yml`)

Precedence: environment `EEP_*` > `eep.yml` > built-in defaults. The file is
optional and fully commented.

| Database | Value | Notes |
|---|---|---|
| SQLite (default) | `sqlite+aiosqlite:///./eep.db` | Zero setup; tables auto-created |
| PostgreSQL 16 + pgvector | `postgresql+asyncpg://eep:eep@localhost:5432/eep` | Production choice; run `psql -U eep -d eep -f migrations/001_schema.sql` once |

```yaml
# eep.yml — uncomment one line to switch
database-url: sqlite+aiosqlite:///./eep.db
# database-url: postgresql+asyncpg://eep:eep@localhost:5432/eep
```

Any value can be overridden via environment: `EEP_DATABASE_URL`, `EEP_HOST`,
`EEP_PORT`, `EEP_REDIS_URL`, ...

### AI providers (`ai-providers.yaml`)

Defines local runtimes (LM Studio `:1234`, Ollama `:11434`) and maps
*roles* → primary/fallback models. `base-url` stays bare; the Python factory
appends `/v1` automatically. Hot-reload after editing:

```bash
curl -X POST http://localhost:8100/v1/internal/ai-config/reload
```

## Docker deployment

```bash
docker compose up -d          # postgres(pgvector) + redis + minio + ai-worker
docker compose up -d postgres # DB only
```

LM Studio / Ollama / TEI run on the host; `ai-providers.yaml` is
volume-mounted into the worker.

## API overview (all under `/v1`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/projects/{pid}/overview` | Aggregated decision overview |
| GET/POST | `/projects/{pid}/meetings` | Meeting list / push transcript (triggers G1) |
| GET | `/meetings/{id}` | Transcript viewer payload |
| GET | `/projects/{pid}/experiences` | Library / action list (filters: `type,status,owner,q`) |
| GET/PATCH | `/experiences/{id}` | Detail / edit (writes change_log) |
| POST | `/experiences/{id}/claim` | Claim action |
| GET | `/experiences/{id}/chain` | Five-lane evolution chain |
| GET | `/projects/{pid}/review/queue` | Review queue (interrupted G2 threads) |
| POST | `/review/{token}/submit` | Verdict: accept / accept_edited / reject |
| POST | `/projects/{pid}/briefing` | Pre-meeting briefing (markdown) |
| GET | `/admin/ai-providers/health` | Provider health for "connected services" |
| POST | `/internal/ai-config/reload` | Hot-reload provider config |

## Tests

```bash
.venv/Scripts/python -m pytest tests -q
```

Covers config parsing, role routing + circuit breaker, the extraction JSON
repair ladder, the experience code generator, memory service, and the API
routes.

---

*Author: Wang, Bing <colin2wang@gmail.com>*
