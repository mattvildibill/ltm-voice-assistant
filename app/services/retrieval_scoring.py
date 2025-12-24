from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from app.models.entry import Entry, MemoryType, SourceType
from app.services.embedding_service import (
    embed_text,
    deserialize_embedding,
    cosine_similarity,
)

# Weights for the blended scoring function
W_SIM = 0.6
W_REC = 0.15
W_IMP = 0.1
W_CONF = 0.1
W_PROJ = 0.05

# Recency half-life (days) per memory type
HALF_LIFE_DAYS = {
    MemoryType.PREFERENCE: 90,
    MemoryType.IDENTITY: 120,
    MemoryType.EVENT: 21,
    MemoryType.PROJECT: 45,
    MemoryType.REFLECTION: 60,
}
DEFAULT_HALF_LIFE = 45

# Domain keywords for lightweight intent classification
DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "jobs": ["job", "career", "work", "manager", "promotion", "resume", "interview"],
    "family": ["family", "kids", "parent", "child", "partner", "spouse"],
    "travel": ["trip", "travel", "flight", "airport", "vacation"],
    "health": ["health", "exercise", "diet", "doctor", "sleep", "workout"],
    "finance": ["budget", "money", "finance", "savings", "invest", "spend"],
    "project": ["project", "roadmap", "build", "ship", "sprint", "release"],
}

# Domain boosts/suppressions by memory_type
DOMAIN_BOOSTS: Dict[str, Dict[str, float]] = {
    "jobs": {
        MemoryType.PROJECT.value: 0.2,
        MemoryType.IDENTITY.value: 0.1,
        MemoryType.PREFERENCE.value: -0.1,
    },
    "family": {
        MemoryType.IDENTITY.value: 0.2,
        MemoryType.PREFERENCE.value: 0.1,
        MemoryType.PROJECT.value: -0.15,
    },
    "travel": {
        MemoryType.EVENT.value: 0.15,
        MemoryType.PREFERENCE.value: 0.05,
    },
    "health": {
        MemoryType.IDENTITY.value: 0.1,
        MemoryType.PREFERENCE.value: 0.05,
    },
    "finance": {
        MemoryType.PROJECT.value: 0.1,
        MemoryType.IDENTITY.value: 0.05,
    },
}

PROJECT_DOMAINS = {"jobs", "project"}


@dataclass
class ScoredEntry:
    entry: Entry
    similarity: float
    recency_boost: float
    importance: float
    confidence: float
    project_relevance: float
    domain_boost: float
    final_score: float


@dataclass
class RerankResult:
    entries: List[Entry]
    debug: Optional[List[Dict]] = None


def classify_query_domain(question: str) -> Optional[str]:
    normalized = (question or "").lower()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(word in normalized for word in keywords):
            return domain
    return None


def recency_boost(entry: Entry, now: Optional[datetime] = None) -> float:
    now = now or datetime.utcnow()
    created = getattr(entry, "created_at", None) or now
    age_days = max(0.0, (now - created).total_seconds() / 86400.0)
    mtype = getattr(entry, "memory_type", None)
    if hasattr(mtype, "value"):
        mtype = mtype.value
    half_life = HALF_LIFE_DAYS.get(mtype, DEFAULT_HALF_LIFE)
    try:
        return math.exp(-age_days / float(half_life))
    except Exception:
        return 0.0


def importance_score(entry: Entry) -> float:
    base = {
        MemoryType.PROJECT.value: 0.9,
        MemoryType.IDENTITY.value: 0.8,
        MemoryType.REFLECTION.value: 0.7,
        MemoryType.PREFERENCE.value: 0.6,
        MemoryType.EVENT.value: 0.5,
    }
    mtype = getattr(entry, "memory_type", None)
    if hasattr(mtype, "value"):
        mtype = mtype.value
    score = base.get(mtype, 0.5)
    tags = getattr(entry, "tags", None) or []
    try:
        iterable_tags = tags if isinstance(tags, list) else []
    except Exception:
        iterable_tags = []
    important_tags = {"important", "goal", "milestone", "priority"}
    if any(str(t).lower() in important_tags for t in iterable_tags):
        score += 0.1
    return min(score, 1.0)


def project_relevance(entry: Entry, domain: Optional[str]) -> float:
    mtype = getattr(entry, "memory_type", None)
    if hasattr(mtype, "value"):
        mtype = mtype.value
    if mtype == MemoryType.PROJECT.value and domain in PROJECT_DOMAINS:
        return 1.0
    return 0.0


def domain_boost(entry: Entry, domain: Optional[str]) -> float:
    if not domain:
        return 0.0
    mtype = getattr(entry, "memory_type", None)
    if hasattr(mtype, "value"):
        mtype = mtype.value
    boosts = DOMAIN_BOOSTS.get(domain, {})
    return boosts.get(mtype, 0.0)


def confidence(entry: Entry) -> float:
    try:
        val = float(getattr(entry, "confidence_score", 0.0))
    except (TypeError, ValueError):
        val = 0.0
    return max(0.0, min(1.0, val))


def compute_score(entry: Entry, similarity: float, domain: Optional[str], now: Optional[datetime] = None) -> ScoredEntry:
    rec = recency_boost(entry, now)
    imp = importance_score(entry)
    conf = confidence(entry)
    proj = project_relevance(entry, domain)
    dom = domain_boost(entry, domain)
    final = (
        W_SIM * similarity
        + W_REC * rec
        + W_IMP * imp
        + W_CONF * conf
        + W_PROJ * proj
        + dom  # domain boost is additive
    )
    return ScoredEntry(
        entry=entry,
        similarity=similarity,
        recency_boost=rec,
        importance=imp,
        confidence=conf,
        project_relevance=proj,
        domain_boost=dom,
        final_score=final,
    )


def generate_candidates(question: str, entries: Iterable[Entry], top_k: int = 50) -> List[Tuple[float, Entry]]:
    query_vec = embed_text(question)
    if not query_vec:
        return []
    scored: List[Tuple[float, Entry]] = []
    for entry in entries:
        vec = deserialize_embedding(getattr(entry, "embedding", None))
        if not vec:
            continue
        sim = cosine_similarity(query_vec, vec)
        if sim is not None:
            scored.append((sim, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]


def rerank_entries(
    question: str,
    entries: Iterable[Entry],
    top_n: int = 10,
    candidate_k: int = 50,
    debug: bool = False,
    now: Optional[datetime] = None,
) -> RerankResult:
    domain = classify_query_domain(question)
    candidates = generate_candidates(question, entries, top_k=candidate_k)
    if not candidates:
        recent = sorted(entries, key=lambda e: getattr(e, "created_at", datetime.utcnow()), reverse=True)
        trimmed = recent[:top_n]
        return RerankResult(entries=trimmed, debug=None)

    scored = [compute_score(entry, sim, domain, now=now) for sim, entry in candidates]
    scored.sort(key=lambda s: s.final_score, reverse=True)
    top = scored[:top_n]

    debug_data = None
    if debug:
        debug_data = [
            {
                "entry_id": s.entry.id,
                "similarity": s.similarity,
                "recency_boost": s.recency_boost,
                "importance": s.importance,
                "confidence": s.confidence,
                "project_relevance": s.project_relevance,
                "domain_boost": s.domain_boost,
                "final_score": s.final_score,
            }
            for s in top
        ]

    return RerankResult(entries=[s.entry for s in top], debug=debug_data)
