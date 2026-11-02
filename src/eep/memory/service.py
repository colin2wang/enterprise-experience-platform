"""MemoryService: unified read/write facade over the dual-layer memory.

Read pipeline (5.5):
  query -> 1) hard filter (project/type/status, formal layer only)
        -> 2) pgvector recall top-50 (BGE-M3)
        -> 3) 1-hop edge expansion (related experiences)
        -> 4) bge-reranker refine to top-8
        -> 5) assemble context, every item carries {meeting_id, span}

Write: drafts to the draft namespace; promotion moves to the formal layer
inside a transaction with change_log.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eep.config import Settings
from eep.db.models import ChangeLog, ExpMeeting, Experience, Relation

logger = logging.getLogger(__name__)


class MemoryService:
    """Facade over Postgres (formal layer + edge table) and the vector index."""

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or Settings()

    # ------------------------------------------------------------------ #
    # Read pipeline
    # ------------------------------------------------------------------ #
    async def retrieve(
        self,
        project_id: str | UUID,
        query: str,
        *,
        exp_type: str | None = None,
        status: str | None = None,
        top_k: int | None = None,
        expand_edges: bool = True,
    ) -> list[dict[str, Any]]:
        """Full retrieval pipeline; formal layer only.

        Returns up to ``rerank_top_k`` items, each with
        ``{id, title, type, status, source_meeting_id, source_span, ...}``.
        """
        query_embedding = await self.embed_query(query)
        rows = await self._vector_recall(
            project_id, query_embedding, exp_type=exp_type, status=status
        )
        if expand_edges and rows:
            rows = await self._expand_one_hop(rows)
        hits = [self._to_hit(r) for r in rows]
        hits = await self._rerank(query, hits)
        return hits[: top_k or self.settings.rerank_top_k]

    async def _vector_recall(
        self,
        project_id: str | UUID,
        embedding: list[float] | None,
        *,
        exp_type: str | None,
        status: str | None,
    ) -> list[Experience]:
        """Step 1+2: hard filter + pgvector cosine recall.

        Falls back to recency ordering when the embedding service is
        unavailable or the pgvector extension is missing (dev setups).
        """
        stmt = select(Experience).where(
            Experience.project_id == project_id,
            Experience.t_invalid.is_(None),  # formal layer, not superseded
        )
        if exp_type:
            stmt = stmt.where(Experience.type == exp_type)
        if status:
            stmt = stmt.where(Experience.status == status)
        if embedding is not None:
            try:
                stmt = stmt.order_by(Experience.embedding.cosine_distance(embedding)).limit(
                    self.settings.vector_top_k
                )
                return list((await self.session.execute(stmt)).scalars())
            except Exception as exc:  # noqa: BLE001 - graceful degradation
                logger.warning("Vector recall failed, falling back to recency: %s", exc)
        stmt = stmt.order_by(Experience.updated_at.desc()).limit(self.settings.vector_top_k)
        return list((await self.session.execute(stmt)).scalars())

    async def _expand_one_hop(self, rows: list[Experience]) -> list[Experience]:
        """Step 3: include 1-hop neighbors along relation edges."""
        ids = [r.id for r in rows]
        if not ids:
            return rows
        known = set(ids)
        edge_stmt = select(Relation).where(
            (Relation.from_exp.in_(ids)) | (Relation.to_exp.in_(ids))
        )
        edges = (await self.session.execute(edge_stmt)).scalars().all()
        neighbor_ids: set[UUID] = set()
        for e in edges:
            for nid in (e.from_exp, e.to_exp):
                if nid not in known:
                    neighbor_ids.add(nid)
        if not neighbor_ids:
            return rows
        nb_stmt = select(Experience).where(Experience.id.in_(neighbor_ids))
        neighbors = (await self.session.execute(nb_stmt)).scalars().all()
        return rows + list(neighbors)

    async def _rerank(self, query: str, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Step 4: refine hit order via TEI bge-reranker; keeps order on failure."""
        from eep.config import load_ai_config

        if len(hits) <= 1:
            return hits
        try:
            cfg = load_ai_config()
            rr = cfg.rerank
            if rr is None:
                return hits
            url = f"{rr.base_url.rstrip('/')}/rerank"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    url,
                    json={
                        "model": rr.model,
                        "query": query,
                        "texts": [h.get("title", "") + " " + (h.get("description") or "") for h in hits],
                    },
                )
                resp.raise_for_status()
                results = resp.json().get("results", [])
                ordered: list[dict[str, Any]] = []
                for r in sorted(results, key=lambda r: -r.get("score", 0.0)):
                    idx = r.get("index")
                    if isinstance(idx, int) and 0 <= idx < len(hits):
                        ordered.append(hits[idx])
                return ordered or hits
        except Exception as exc:  # noqa: BLE001 - rerank is best-effort
            logger.warning("Rerank endpoint unavailable, keeping recall order: %s", exc)
            return hits

    @staticmethod
    def _to_hit(row: Experience) -> dict[str, Any]:
        """Step 5 shape: every hit carries its meeting citation."""
        return {
            "id": str(row.id),
            "code": row.code,
            "type": row.type,
            "title": row.title,
            "description": row.description,
            "status": row.status,
            "owner_id": str(row.owner_id) if row.owner_id else None,
            "due_date": row.due_date.isoformat() if row.due_date else None,
            "source_meeting_id": str(row.source_meeting_id) if row.source_meeting_id else None,
            "source_span": row.source_span or {},
            "t_event": row.t_event.isoformat() if row.t_event else None,
        }

    # ------------------------------------------------------------------ #
    # Embedding
    # ------------------------------------------------------------------ #
    async def embed_query(self, text: str) -> list[float] | None:
        """Embed via the configured provider's OpenAI-compatible endpoint."""
        from eep.config import load_ai_config

        try:
            cfg = load_ai_config()
            emb = cfg.embeddings
            if emb is None:
                return None
            provider = cfg.provider_map()[emb.provider]
            url = f"{provider.base_url.rstrip('/')}/v1/embeddings"
            async with httpx.AsyncClient(timeout=provider.connect_timeout_seconds) as client:
                resp = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {provider.api_key}"},
                    json={"model": emb.model, "input": text},
                )
                resp.raise_for_status()
                return resp.json()["data"][0]["embedding"]
        except Exception as exc:  # noqa: BLE001 - retrieval degrades gracefully
            logger.warning("Embedding failed, recall will use recency order: %s", exc)
            return None

    # ------------------------------------------------------------------ #
    # Write path
    # ------------------------------------------------------------------ #
    async def promote_draft(
        self,
        project_id: str | UUID,
        draft: dict[str, Any],
        meeting_id: str | UUID | None,
        actor_id: str | UUID | None = None,
        *,
        code: str | None = None,
    ) -> Experience:
        """Promote one reviewed draft into the formal layer.

        Writes: experience row + exp_meeting evidence + change_log entry,
        inside the caller's transaction. confidence becomes 1 (human-verified).
        """
        span = draft.get("source", {}).get("span", {})
        exp = Experience(
            project_id=project_id,
            code=code,
            type=draft["type"],
            title=draft.get("edited_title") or draft.get("title", ""),
            description=draft.get("description"),
            status=draft.get("status", "pending"),
            acceptance_criteria=draft.get("acceptance_criteria"),
            source_meeting_id=meeting_id,
            source_span=span,
            t_event=draft.get("t_event"),
        )
        self.session.add(exp)
        await self.session.flush()  # assign exp.id

        if meeting_id:
            self.session.add(
                ExpMeeting(
                    exp_id=exp.id,
                    meeting_id=meeting_id,
                    evidence_span=span,
                    is_first_record=True,
                )
            )
        self.session.add(
            ChangeLog(
                entity_type="experience",
                entity_id=exp.id,
                field="created",
                old_value=None,
                new_value=exp.title,
                actor_id=actor_id,
                source="ui",
            )
        )
        return exp

    async def patch_experience(
        self,
        exp_id: str | UUID,
        changes: dict[str, Any],
        actor_id: str | UUID | None = None,
    ) -> Experience | None:
        """Apply field edits and write one change_log row per changed field."""
        exp = await self.session.get(Experience, exp_id)
        if exp is None:
            return None
        for field, new_value in changes.items():
            if new_value is None or not hasattr(exp, field):
                continue
            old_value = getattr(exp, field)
            if old_value == new_value:
                continue
            setattr(exp, field, new_value)
            self.session.add(
                ChangeLog(
                    entity_type="experience",
                    entity_id=exp.id,
                    field=field,
                    old_value=str(old_value) if old_value is not None else None,
                    new_value=str(new_value),
                    actor_id=actor_id,
                    source="ui",
                )
            )
        await self.session.flush()
        return exp

    async def expire_fact(self, exp_id: str | UUID, superseded_by: str | UUID) -> None:
        """Fact invalidation: new decision supersedes an old one (dual timeline)."""
        exp = await self.session.get(Experience, exp_id)
        if exp is not None:
            exp.t_invalid = datetime.now(UTC).date()
            exp.superseded_by = superseded_by
            await self.session.flush()
