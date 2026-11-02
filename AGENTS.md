# EEP — Enterprise Experience Platform (AI Pipeline Service)

"Meeting → experience → decision → action" closed-loop system: Python (LangGraph) backend + Vue 3 frontend.

## Language rule

All code comments, docstrings, commit messages, and user-facing output in this project MUST be in English. This instruction file is also maintained in English.

## Common commands

- Backend tests: `uv run --extra dev pytest tests -q` (pytest-asyncio `asyncio_mode = "auto"`, no decorators needed)
- Start backend: `uv run uvicorn eep.main:app --port 8100` (SQLite default `./eep.db`, tables auto-created on startup)
- Frontend build: `powershell ./web-build.ps1` (pnpm + vue-tsc, output to `web/`, statically served by the backend at `/web`)
- Frontend dev: `powershell ./web-run.ps1` (vite 5173, `/v1` proxied to 8100 — start the backend yourself first)

## Architecture & boundaries

- `src/eep/graphs/`: four LangGraph graphs — G1 ingestion (summarize + parallel extraction), G2 review (human-in-the-loop via `interrupt()`), G3 briefing, G4 qa. Only G1 actually calls an LLM today; G3/G4/`suggest_edits` are deterministic/placeholder implementations.
- **Two-file model configuration contract**: `ai-providers.yaml` holds interface info only (endpoints, timeouts, concurrency, breakers, per-role temperature / structured-output / `extra-body`); `model-info.yml` is the single source of models (a `models` catalog + `roles` routing, model-ids like `lmstudio-local:qwen/qwen3-8b` matching LM Studio `lms ps` IDENTIFIER). Adding a role requires touching both files.
- `ModelFactory.get_chat_model(role)` resolves models by role (model-info.yml) + behavior knobs (ai-providers.yaml), with circuit breaking; `/internal/ai-config/reload` hot-reloads config.
- Dual-layer memory: AI writes only to the draft layer; the G2 human review promotes it into the formal layer (`MemoryService`, with change_log audit).
- `eep.yml` / `EEP_*` env vars are service settings; precedence env > yml > defaults.

## Gotchas

- The loaded runtime context window (CONTEXT column of `lms ps`) is NOT the model's native context; `expected-context` is the health-check baseline.
- `ai-providers.yaml` is shared with the Spring Boot backend — never break its kebab-case keys.
- Commit messages: write an English commit message into root `COMMIT.md` (gitignored); do NOT run `git commit` yourself.

## Instruction file maintenance

When project structure, build/test commands, architecture boundaries, conventions, or any other fact recorded here changes, update this file in the same change: replace stale statements with current facts, never append change history. Detailed post-mortems, experiments, etc. go into linked standalone docs, read only when relevant.
