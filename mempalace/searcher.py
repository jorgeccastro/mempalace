#!/usr/bin/env python3
"""
searcher.py — Find anything. Exact words.

Hybrid search against the palace. Combines:
  • Vector semantic retrieval (ChromaDB cosine distance)
  • Okapi-BM25 over candidates (IDF corpus-aware)
  • Query expansion: normalized, keyword-only, quoted-phrase variants
  • Lexical boosts: keyword overlap (with fuzzy/prefix), quoted phrases,
    notable entities, temporal signals (PT+EN)
  • Closet rank boost (topic index signal, never a gate)
  • Drawer-grep expansion for closet-boosted sources (±1 neighbor)

Signals are additive to the semantic floor: they can only help, never hide.
Closets and expansion degrade gracefully when absent.
"""

import logging
import math
import re
import unicodedata
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from .palace import get_closets_collection, get_collection

logger = logging.getLogger("mempalace_mcp")


# ── Config ─────────────────────────────────────────────────────────────

DEFAULT_OVERFETCH_FACTOR = 5
DEFAULT_MIN_CANDIDATES = 25

# Fork-style multiplicative signal weights (distance discounts).
DEFAULT_HYBRID_WEIGHT = 0.30
DEFAULT_QUOTED_PHRASE_WEIGHT = 0.60
DEFAULT_ENTITY_WEIGHT = 0.22
DEFAULT_TEMPORAL_WEIGHT = 0.35
DEFAULT_PREFIX_MATCH_WEIGHT = 0.92
DEFAULT_FUZZY_MATCH_WEIGHT = 0.84

# BM25 convex combo (applied after multiplicative fusion as final sort signal).
DEFAULT_VECTOR_WEIGHT = 0.70
DEFAULT_BM25_WEIGHT = 0.30

# Closet rank boosts (upstream) — applied as distance reduction.
CLOSET_RANK_BOOSTS = [0.40, 0.25, 0.15, 0.08, 0.04]
CLOSET_DISTANCE_CAP = 1.5
MAX_HYDRATION_CHARS = 10_000

# Closet pointer line format (upstream): "topic|entities|→drawer_id_a,drawer_id_b"
_CLOSET_DRAWER_REF_RE = re.compile(r"→([\w,]+)")
_TOKEN_RE = re.compile(r"\w{2,}", re.UNICODE)


STOP_WORDS = {
    "a",
    "about",
    "after",
    "again",
    "ago",
    "ai",
    "all",
    "am",
    "an",
    "and",
    "any",
    "ao",
    "aos",
    "are",
    "as",
    "at",
    "aquela",
    "aquele",
    "aquilo",
    "assim",
    "ate",
    "até",
    "be",
    "because",
    "been",
    "before",
    "by",
    "buy",
    "bought",
    "com",
    "como",
    "da",
    "das",
    "de",
    "del",
    "dela",
    "dele",
    "dessa",
    "desse",
    "did",
    "do",
    "does",
    "dos",
    "e",
    "ela",
    "ele",
    "em",
    "era",
    "essa",
    "esse",
    "esta",
    "este",
    "eu",
    "faz",
    "fazer",
    "foi",
    "for",
    "from",
    "gave",
    "get",
    "give",
    "go",
    "got",
    "had",
    "has",
    "have",
    "how",
    "i",
    "in",
    "into",
    "is",
    "isso",
    "isto",
    "it",
    "its",
    "last",
    "made",
    "make",
    "me",
    "meu",
    "minha",
    "my",
    "na",
    "nas",
    "no",
    "nos",
    "not",
    "o",
    "of",
    "on",
    "onde",
    "or",
    "os",
    "ou",
    "para",
    "pela",
    "pelas",
    "pelo",
    "pelos",
    "por",
    "porque",
    "qual",
    "quando",
    "que",
    "quem",
    "se",
    "sem",
    "ser",
    "seu",
    "sua",
    "suas",
    "seus",
    "sobre",
    "são",
    "ta",
    "tal",
    "tambem",
    "também",
    "te",
    "tem",
    "that",
    "the",
    "their",
    "there",
    "this",
    "to",
    "tu",
    "um",
    "uma",
    "umas",
    "uns",
    "use",
    "using",
    "voces",
    "vocês",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "you",
    "your",
}

NOTABLE_ENTITY_WORDS = {
    "And",
    "Ao",
    "Aos",
    "As",
    "At",
    "Can",
    "Com",
    "Como",
    "Could",
    "Da",
    "Das",
    "De",
    "Did",
    "Do",
    "Does",
    "Dos",
    "E",
    "Ela",
    "Ele",
    "Em",
    "Esta",
    "Este",
    "For",
    "From",
    "Ha",
    "How",
    "I",
    "In",
    "Is",
    "Isto",
    "It",
    "Its",
    "Just",
    "Last",
    "May",
    "Monday",
    "More",
    "My",
    "Na",
    "Nas",
    "No",
    "Nos",
    "November",
    "O",
    "October",
    "On",
    "Onde",
    "Os",
    "Our",
    "Para",
    "Pela",
    "Pelas",
    "Pelo",
    "Pelos",
    "Por",
    "Previously",
    "Qual",
    "Quando",
    "Que",
    "Quem",
    "Recently",
    "Saturday",
    "September",
    "Se",
    "Sem",
    "Should",
    "Sunday",
    "That",
    "The",
    "Their",
    "This",
    "Thursday",
    "To",
    "Tuesday",
    "Wednesday",
    "What",
    "When",
    "Where",
    "Which",
    "Who",
    "Why",
    "Will",
    "With",
    "Would",
    "You",
}


class SearchError(Exception):
    """Raised when search cannot proceed (e.g. no palace found)."""


# ── Tokenization / normalization ───────────────────────────────────────


def _first_or_empty(results: dict, key: str) -> list:
    """Return the first inner list of a ChromaDB query result, or []."""
    outer = results.get(key)
    if not outer:
        return []
    return outer[0] or []


def _tokenize(text: str) -> list:
    """Lowercase + strip to alphanumeric tokens of length ≥ 2 (BM25)."""
    return _TOKEN_RE.findall(text.lower())


def _normalize_text(text: str) -> str:
    """NFKD-normalize, strip diacritics, lowercase."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def _utc_now() -> datetime:
    return datetime.now()


def _extract_keywords(text: str, excluded_tokens: set = None) -> list:
    """Extract meaningful keyword tokens (≥3 chars, not stopwords)."""
    normalized = _normalize_text(text)
    tokens = re.findall(r"\b[a-z0-9]{3,}\b", normalized)
    seen = set()
    keywords = []
    excluded_tokens = excluded_tokens or set()
    for token in tokens:
        if token in STOP_WORDS or token in excluded_tokens or token in seen:
            continue
        seen.add(token)
        keywords.append(token)
    return keywords


def _extract_quoted_phrases(text: str) -> list:
    """Extract phrases enclosed in straight or curly quotes."""
    phrases = []
    for pattern in (
        r"'([^']{3,80})'",
        r'"([^"]{3,80})"',
        r"“([^”]{3,80})”",
        r"‘([^’]{3,80})’",
    ):
        phrases.extend(re.findall(pattern, text))

    seen = set()
    unique = []
    for phrase in phrases:
        cleaned = phrase.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            unique.append(cleaned)
    return unique


def _extract_notable_entities(text: str) -> list:
    """Extract proper-noun-like tokens (capitalized, not in stoplist)."""
    candidates = re.findall(r"\b(?:[A-Z][a-z0-9]{2,15}|[A-Z0-9]{2,15})\b", text)
    seen = set()
    entities = []
    for candidate in candidates:
        if candidate in NOTABLE_ENTITY_WORDS:
            continue
        normalized = _normalize_text(candidate)
        if len(normalized) < 3 or normalized in seen:
            continue
        seen.add(normalized)
        entities.append(candidate)
    return entities


# ── Overlap scores ─────────────────────────────────────────────────────


def _token_match_score(query_token: str, doc_token: str) -> float:
    """Exact / prefix (≥5) / fuzzy (SequenceMatcher ratio ≥ 0.90) match."""
    if query_token == doc_token:
        return 1.0

    min_len = min(len(query_token), len(doc_token))
    if min_len >= 5 and (query_token.startswith(doc_token) or doc_token.startswith(query_token)):
        return DEFAULT_PREFIX_MATCH_WEIGHT

    if min_len >= 5 and query_token[:5] == doc_token[:5]:
        return DEFAULT_PREFIX_MATCH_WEIGHT

    if min_len >= 6:
        ratio = SequenceMatcher(None, query_token, doc_token).ratio()
        if ratio >= 0.90:
            return DEFAULT_FUZZY_MATCH_WEIGHT

    return 0.0


def _keyword_overlap(query_keywords: list, doc_text: str) -> float:
    """Average best-match score per query keyword vs doc tokens."""
    if not query_keywords:
        return 0.0

    doc_tokens = set(re.findall(r"\b[a-z0-9]{3,}\b", _normalize_text(doc_text)))
    if not doc_tokens:
        return 0.0

    scores = []
    for keyword in query_keywords:
        best = 0.0
        for doc_token in doc_tokens:
            score = _token_match_score(keyword, doc_token)
            if score > best:
                best = score
                if best == 1.0:
                    break
        scores.append(best)

    return sum(scores) / len(scores)


def _quoted_phrase_overlap(phrases: list, doc_text: str) -> float:
    if not phrases:
        return 0.0
    normalized_doc = _normalize_text(doc_text)
    hits = sum(1 for phrase in phrases if _normalize_text(phrase) in normalized_doc)
    return hits / len(phrases)


def _entity_overlap(entities: list, doc_text: str) -> float:
    if not entities:
        return 0.0
    doc_tokens = set(re.findall(r"\b[a-z0-9]{3,}\b", _normalize_text(doc_text)))
    if not doc_tokens:
        return 0.0
    hits = 0
    for entity in entities:
        token = _normalize_text(entity)
        if token in doc_tokens:
            hits += 1
    return hits / len(entities)


def _distance_to_similarity(distance: float) -> float:
    """Monotonic distance→similarity mapping, bounded to [0, 1].

    Uses ``1 / (1 + d)`` so it works for either L2 (d ∈ [0, ∞)) or cosine
    (d ∈ [0, 2]) palaces. Closet boost can drive effective distance below
    zero, so we clamp to [0, 1].
    """
    d = max(distance, 0.0)
    return round(min(1.0, 1.0 / (1.0 + d)), 3)


# ── BM25 (Okapi, corpus-relative IDF over candidate set) ───────────────


def _bm25_scores(
    query: str,
    documents: list,
    k1: float = 1.5,
    b: float = 0.75,
) -> list:
    """Compute Okapi-BM25 scores for ``query`` against each document.

    IDF is computed over the provided corpus with the Lucene/BM25+ smoothed
    formula: ``log((N - df + 0.5) / (df + 0.5) + 1)``.
    """
    n_docs = len(documents)
    query_terms = set(_tokenize(query))
    if not query_terms or n_docs == 0:
        return [0.0] * n_docs

    tokenized = [_tokenize(d) for d in documents]
    doc_lens = [len(toks) for toks in tokenized]
    if not any(doc_lens):
        return [0.0] * n_docs
    avgdl = sum(doc_lens) / n_docs or 1.0

    df = {term: 0 for term in query_terms}
    for toks in tokenized:
        seen = set(toks) & query_terms
        for term in seen:
            df[term] += 1

    idf = {term: math.log((n_docs - df[term] + 0.5) / (df[term] + 0.5) + 1) for term in query_terms}

    scores = []
    for toks, dl in zip(tokenized, doc_lens):
        if dl == 0:
            scores.append(0.0)
            continue
        tf = {}
        for t in toks:
            if t in query_terms:
                tf[t] = tf.get(t, 0) + 1
        score = 0.0
        for term, freq in tf.items():
            num = freq * (k1 + 1)
            den = freq + k1 * (1 - b + b * dl / avgdl)
            score += idf[term] * num / den
        scores.append(score)
    return scores


# ── Temporal signals (PT+EN) ───────────────────────────────────────────


def _parse_metadata_datetime(metadata: dict):
    raw_date = metadata.get("date")
    if raw_date:
        try:
            return datetime.fromisoformat(str(raw_date))
        except ValueError:
            pass

    for key in ("timestamp", "filed_at"):
        value = metadata.get(key)
        if not value:
            continue
        try:
            cleaned = str(value).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(cleaned)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed
        except ValueError:
            continue

    source_mtime = metadata.get("source_mtime")
    if source_mtime not in (None, ""):
        try:
            return datetime.fromtimestamp(float(source_mtime))
        except (TypeError, ValueError, OSError):
            return None

    return None


def _extract_temporal_signal(query: str, reference_now: datetime = None):
    """Extract (target_datetime, tolerance_days) from PT+EN temporal cues."""
    now = reference_now or _utc_now()
    normalized = _normalize_text(query)

    match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", normalized)
    if match:
        try:
            return datetime.fromisoformat(match.group(1)), 1
        except ValueError:
            pass

    direct_patterns = [
        (r"\b(today|hoje)\b", (now, 1)),
        (r"\b(yesterday|ontem)\b", (now - timedelta(days=1), 1)),
        (r"\b(day before yesterday|anteontem)\b", (now - timedelta(days=2), 1)),
        (r"\b(last week|semana passada)\b", (now - timedelta(days=7), 4)),
        (r"\b(last month|mes passado)\b", (now - timedelta(days=30), 7)),
        (r"\b(last year|ano passado)\b", (now - timedelta(days=365), 30)),
        (r"\b(recently|recentemente)\b", (now - timedelta(days=14), 14)),
    ]
    for pattern, signal in direct_patterns:
        if re.search(pattern, normalized):
            return signal

    quantified_patterns = [
        (r"\b(\d+)\s+days?\s+ago\b", 1),
        (r"\bha\s+(\d+)\s+dias?\b", 1),
        (r"\b(\d+)\s+weeks?\s+ago\b", 5),
        (r"\bha\s+(\d+)\s+semanas?\b", 5),
        (r"\b(\d+)\s+months?\s+ago\b", 10),
        (r"\bha\s+(\d+)\s+mes(?:es)?\b", 10),
        (r"\b(\d+)\s+years?\s+ago\b", 30),
        (r"\bha\s+(\d+)\s+anos?\b", 30),
    ]
    for pattern, tolerance in quantified_patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        quantity = int(match.group(1))
        if "day" in pattern or "dias" in pattern:
            return now - timedelta(days=quantity), max(tolerance, min(quantity, 3))
        if "week" in pattern or "semanas" in pattern:
            return now - timedelta(days=quantity * 7), tolerance
        if "month" in pattern or "mes" in pattern:
            return now - timedelta(days=quantity * 30), tolerance
        return now - timedelta(days=quantity * 365), tolerance

    return None


def _temporal_overlap(query: str, metadata: dict) -> float:
    signal = _extract_temporal_signal(query)
    if not signal:
        return 0.0

    candidate_dt = _parse_metadata_datetime(metadata)
    if not candidate_dt:
        return 0.0

    target_dt, tolerance = signal
    delta_days = abs((candidate_dt.date() - target_dt.date()).days)
    if delta_days <= tolerance:
        return 1.0

    extended_window = max(tolerance * 3, tolerance + 2)
    if delta_days > extended_window:
        return 0.0

    return max(0.0, 1.0 - ((delta_days - tolerance) / max(extended_window - tolerance, 1)))


# ── Query expansion ────────────────────────────────────────────────────


def _build_query_variants(query: str) -> list:
    """Produce distinct query strings (original, normalized, keywords-only,
    quoted phrases) to expand recall during semantic retrieval."""
    variants = []

    def add_variant(candidate: str):
        cleaned = candidate.strip()
        if cleaned and cleaned not in variants:
            variants.append(cleaned)

    add_variant(query)

    normalized = _normalize_text(query)
    if normalized != query.strip().lower():
        add_variant(normalized)

    keywords = _extract_keywords(query)
    if keywords:
        add_variant(" ".join(keywords))

    for phrase in _extract_quoted_phrases(query):
        add_variant(phrase)

    return variants


def _build_where_filter(wing: str = None, room: str = None) -> dict:
    if wing and room:
        return {"$and": [{"wing": wing}, {"room": room}]}
    if wing:
        return {"wing": wing}
    if room:
        return {"room": room}
    return {}


def build_where_filter(wing: str = None, room: str = None) -> dict:
    """Public alias (upstream spelling)."""
    return _build_where_filter(wing=wing, room=room)


# ── Closet helpers (upstream) ──────────────────────────────────────────


def _extract_drawer_ids_from_closet(closet_doc: str) -> list:
    """Parse all `→drawer_id_a,drawer_id_b` pointers out of a closet doc."""
    seen = {}
    for match in _CLOSET_DRAWER_REF_RE.findall(closet_doc):
        for did in match.split(","):
            did = did.strip()
            if did and did not in seen:
                seen[did] = None
    return list(seen.keys())


def _expand_with_neighbors(
    drawers_col,
    matched_doc: str,
    matched_meta: dict,
    radius: int = 1,
):
    """Upstream-compatible: expand around the matched ``chunk_index`` in the
    same source_file. Used by callers that already know which chunk matched.
    """
    src = matched_meta.get("source_file")
    chunk_idx = matched_meta.get("chunk_index")
    if not src or not isinstance(chunk_idx, int):
        return {"text": matched_doc, "drawer_index": chunk_idx, "total_drawers": None}

    target_indexes = [chunk_idx + offset for offset in range(-radius, radius + 1)]
    try:
        neighbors = drawers_col.get(
            where={
                "$and": [
                    {"source_file": src},
                    {"chunk_index": {"$in": target_indexes}},
                ]
            },
            include=["documents", "metadatas"],
        )
    except Exception:
        return {"text": matched_doc, "drawer_index": chunk_idx, "total_drawers": None}

    indexed_docs = []
    for doc, meta in zip(neighbors.get("documents") or [], neighbors.get("metadatas") or []):
        ci = meta.get("chunk_index")
        if isinstance(ci, int):
            indexed_docs.append((ci, doc))
    indexed_docs.sort(key=lambda pair: pair[0])

    if not indexed_docs:
        combined_text = matched_doc
    else:
        combined_text = "\n\n".join(doc for _, doc in indexed_docs)

    total_drawers = None
    try:
        all_meta = drawers_col.get(where={"source_file": src}, include=["metadatas"])
        ids = all_meta.get("ids") or []
        total_drawers = len(ids) if ids else None
    except Exception:
        pass

    return {
        "text": combined_text,
        "drawer_index": chunk_idx,
        "total_drawers": total_drawers,
    }


def _drawer_grep_expand(
    drawers_col,
    query: str,
    matched_doc: str,
    matched_meta: dict,
    radius: int = 1,
):
    """Closet-boost companion: find the best-keyword chunk in the source_file
    and return it plus ± neighbors. Closets say *which source* is relevant;
    vector may have landed on the wrong chunk within it — grep picks the right
    one."""
    src = matched_meta.get("source_file")
    if not src:
        return {"text": matched_doc, "drawer_index": None, "total_drawers": None}

    try:
        source_drawers = drawers_col.get(
            where={"source_file": src},
            include=["documents", "metadatas"],
        )
    except Exception:
        return {"text": matched_doc, "drawer_index": None, "total_drawers": None}

    docs = source_drawers.get("documents") or []
    metas = source_drawers.get("metadatas") or []
    if len(docs) <= 1:
        return {
            "text": matched_doc,
            "drawer_index": None,
            "total_drawers": len(docs) or None,
        }

    indexed = []
    for idx, (d, m) in enumerate(zip(docs, metas)):
        ci = m.get("chunk_index", idx) if isinstance(m, dict) else idx
        if not isinstance(ci, int):
            ci = idx
        indexed.append((ci, d))
    indexed.sort(key=lambda p: p[0])
    ordered_docs = [d for _, d in indexed]

    query_terms = set(_tokenize(query))
    best_idx, best_score = 0, -1
    for idx, d in enumerate(ordered_docs):
        d_lower = d.lower()
        s = sum(1 for t in query_terms if t in d_lower)
        if s > best_score:
            best_score, best_idx = s, idx

    start = max(0, best_idx - radius)
    end = min(len(ordered_docs), best_idx + radius + 1)
    expanded = "\n\n".join(ordered_docs[start:end])
    if len(expanded) > MAX_HYDRATION_CHARS:
        expanded = (
            expanded[:MAX_HYDRATION_CHARS]
            + f"\n\n[...truncated. {len(ordered_docs)} total drawers. "
            "Use mempalace_get_drawer for full content.]"
        )

    return {
        "text": expanded,
        "drawer_index": best_idx,
        "total_drawers": len(ordered_docs),
    }


def _hybrid_rank(
    results: list,
    query: str,
    vector_weight: float = 0.6,
    bm25_weight: float = 0.4,
) -> list:
    """Upstream-compatible: rerank a list of result dicts by a convex
    combination of absolute vector similarity ``max(0, 1 - distance)`` and
    min-max-normalized BM25 over the candidate set.

    Mutates each result dict to add ``bm25_score`` and reorders the list
    in place. Returns the same list for convenience.
    """
    if not results:
        return results

    docs = [r.get("text", "") for r in results]
    bm25_raw = _bm25_scores(query, docs)
    max_bm25 = max(bm25_raw) if bm25_raw else 0.0
    bm25_norm = [s / max_bm25 for s in bm25_raw] if max_bm25 > 0 else [0.0] * len(bm25_raw)

    scored = []
    for r, raw, norm in zip(results, bm25_raw, bm25_norm):
        vec_sim = max(0.0, 1.0 - r.get("distance", 1.0))
        r["bm25_score"] = round(raw, 3)
        scored.append((vector_weight * vec_sim + bm25_weight * norm, r))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    results[:] = [r for _, r in scored]
    return results


# ── Retrieval ──────────────────────────────────────────────────────────


def _semantic_candidates(collection, query: str, where: dict, n_results: int) -> list:
    """Run multiple query variants; merge per-id with minimum distance."""
    fetch_limit = max(n_results * DEFAULT_OVERFETCH_FACTOR, DEFAULT_MIN_CANDIDATES)
    merged = {}

    for variant in _build_query_variants(query):
        kwargs = {
            "query_texts": [variant],
            "n_results": fetch_limit,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = collection.query(**kwargs)
        ids = _first_or_empty(results, "ids")
        docs = _first_or_empty(results, "documents")
        metas = _first_or_empty(results, "metadatas")
        dists = _first_or_empty(results, "distances")

        for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists)):
            doc_id = ids[i] if i < len(ids) else f"_synth_{hash(doc)}"
            current = merged.get(doc_id)
            if current is None or dist < current["distance"]:
                merged[doc_id] = {
                    "id": doc_id,
                    "text": doc,
                    "metadata": meta if isinstance(meta, dict) else {},
                    "distance": dist,
                }

    return list(merged.values())


def _rerank_candidates(
    query: str,
    candidates: list,
    closet_boost_by_source: dict,
    max_distance: float,
    n_results: int,
) -> list:
    """Rerank candidates using fork signals × BM25 × closet boost."""
    if max_distance and max_distance > 0.0:
        candidates = [c for c in candidates if c["distance"] <= max_distance]
    if not candidates:
        return []

    query_entities = _extract_notable_entities(query)
    normalized_entities = {_normalize_text(e) for e in query_entities}
    query_keywords = _extract_keywords(query, excluded_tokens=normalized_entities)
    query_phrases = _extract_quoted_phrases(query)

    docs_for_bm25 = [c["text"] for c in candidates]
    bm25_raw = _bm25_scores(query, docs_for_bm25)
    max_bm25 = max(bm25_raw) if bm25_raw else 0.0
    bm25_norm = [s / max_bm25 for s in bm25_raw] if max_bm25 > 0 else [0.0] * len(bm25_raw)

    for i, c in enumerate(candidates):
        kw = _keyword_overlap(query_keywords, c["text"])
        ph = _quoted_phrase_overlap(query_phrases, c["text"])
        en = _entity_overlap(query_entities, c["text"])
        tp = _temporal_overlap(query, c["metadata"])

        fused = c["distance"]
        if kw > 0:
            fused *= 1.0 - DEFAULT_HYBRID_WEIGHT * kw
        if ph > 0:
            fused *= 1.0 - DEFAULT_QUOTED_PHRASE_WEIGHT * ph
        if en > 0:
            fused *= 1.0 - DEFAULT_ENTITY_WEIGHT * en
        if tp > 0:
            fused *= 1.0 - DEFAULT_TEMPORAL_WEIGHT * tp

        src = c["metadata"].get("source_file", "") or ""
        closet_boost = 0.0
        matched_via = "drawer"
        closet_preview = None
        if src and src in closet_boost_by_source:
            c_rank, c_dist, c_preview = closet_boost_by_source[src]
            if c_dist <= CLOSET_DISTANCE_CAP and c_rank < len(CLOSET_RANK_BOOSTS):
                closet_boost = CLOSET_RANK_BOOSTS[c_rank]
                matched_via = "drawer+closet"
                closet_preview = c_preview
        fused -= closet_boost

        c["keyword_overlap"] = round(kw, 3)
        c["phrase_overlap"] = round(ph, 3)
        c["entity_overlap"] = round(en, 3)
        c["temporal_overlap"] = round(tp, 3)
        c["bm25_score"] = round(bm25_raw[i], 3)
        c["bm25_norm"] = bm25_norm[i]
        c["closet_boost"] = round(closet_boost, 3)
        c["matched_via"] = matched_via
        c["closet_preview"] = closet_preview
        c["fused_distance"] = fused

        vec_sim = max(0.0, 1.0 - fused)
        c["_sort_score"] = DEFAULT_VECTOR_WEIGHT * vec_sim + DEFAULT_BM25_WEIGHT * bm25_norm[i]

    candidates.sort(key=lambda c: (-c["_sort_score"], c["fused_distance"]))
    return candidates[:n_results]


# ── Public API ─────────────────────────────────────────────────────────


def _run_search(
    query: str,
    palace_path: str,
    wing: str = None,
    room: str = None,
    n_results: int = 5,
    max_distance: float = 0.0,
) -> dict:
    """Core search — returns a normalized dict shared by CLI and MCP paths."""
    try:
        drawers_col = get_collection(palace_path, create=False)
    except Exception as e:
        logger.error("No palace found at %s: %s", palace_path, e)
        return {
            "error": "No palace found",
            "hint": "Run: mempalace init <dir> && mempalace mine <dir>",
        }

    where = _build_where_filter(wing=wing, room=room)

    try:
        candidates = _semantic_candidates(
            drawers_col, query=query, where=where, n_results=n_results
        )
    except Exception as e:
        return {"error": f"Search error: {e}"}

    closet_boost_by_source = {}
    try:
        closets_col = get_closets_collection(palace_path, create=False)
        ckwargs = {
            "query_texts": [query],
            "n_results": n_results * 2,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            ckwargs["where"] = where
        closet_results = closets_col.query(**ckwargs)
        for rank, (cdoc, cmeta, cdist) in enumerate(
            zip(
                _first_or_empty(closet_results, "documents"),
                _first_or_empty(closet_results, "metadatas"),
                _first_or_empty(closet_results, "distances"),
            )
        ):
            if isinstance(cmeta, dict):
                source = cmeta.get("source_file", "")
            else:
                source = ""
            if source and source not in closet_boost_by_source:
                closet_boost_by_source[source] = (rank, cdist, cdoc[:200])
    except Exception:
        pass  # no closets yet — hybrid degrades to pure drawer search

    reranked = _rerank_candidates(
        query=query,
        candidates=candidates,
        closet_boost_by_source=closet_boost_by_source,
        max_distance=max_distance,
        n_results=n_results,
    )

    hits = []
    for c in reranked:
        meta = c["metadata"] if isinstance(c["metadata"], dict) else {}
        src_full = meta.get("source_file", "") or ""
        created_at = meta.get("filed_at", "unknown")

        hit = {
            "text": c["text"],
            "wing": meta.get("wing", "unknown"),
            "room": meta.get("room", "unknown"),
            "source_file": Path(src_full).name if src_full else "?",
            "created_at": created_at,
            "similarity": _distance_to_similarity(c["fused_distance"]),
            "distance": round(c["distance"], 4),
            "effective_distance": round(c["fused_distance"], 4),
            "closet_boost": c["closet_boost"],
            "matched_via": c["matched_via"],
            "keyword_overlap": c["keyword_overlap"],
            "phrase_overlap": c["phrase_overlap"],
            "entity_overlap": c["entity_overlap"],
            "temporal_overlap": c["temporal_overlap"],
            "bm25_score": c["bm25_score"],
        }
        if c.get("closet_preview"):
            hit["closet_preview"] = c["closet_preview"]

        if c["matched_via"] == "drawer+closet" and src_full:
            try:
                expanded = _drawer_grep_expand(drawers_col, query, c["text"], meta, radius=1)
                if expanded and expanded.get("text"):
                    hit["text"] = expanded["text"]
                    hit["drawer_index"] = expanded.get("drawer_index")
                    hit["total_drawers"] = expanded.get("total_drawers")
            except Exception:
                pass  # expansion is best-effort

        hits.append(hit)

    return {
        "query": query,
        "filters": {"wing": wing, "room": room},
        "total_before_filter": len(candidates),
        "results": hits,
    }


def search(
    query: str,
    palace_path: str,
    wing: str = None,
    room: str = None,
    n_results: int = 5,
):
    """CLI search — prints verbatim drawer content."""
    result = _run_search(query, palace_path, wing=wing, room=room, n_results=n_results)
    if "error" in result:
        print(f"\n  {result['error']} at {palace_path}")
        if hint := result.get("hint"):
            print(f"  {hint}")
        raise SearchError(result["error"])

    hits = result["results"]
    if not hits:
        print(f'\n  No results found for: "{query}"')
        return

    print(f"\n{'=' * 60}")
    print(f'  Results for: "{query}"')
    if wing:
        print(f"  Wing: {wing}")
    if room:
        print(f"  Room: {room}")
    print(f"{'=' * 60}\n")

    for i, hit in enumerate(hits, 1):
        print(f"  [{i}] {hit['wing']} / {hit['room']}")
        print(f"      Source: {hit['source_file']}")
        print(f"      Match:  {hit['similarity']}")
        print()
        for line in hit["text"].strip().split("\n"):
            print(f"      {line}")
        print()
        print(f"  {'─' * 56}")

    print()


def search_memories(
    query: str,
    palace_path: str,
    wing: str = None,
    room: str = None,
    n_results: int = 5,
    max_distance: float = 0.0,
) -> dict:
    """Programmatic search — returns a dict instead of printing.

    Used by the MCP server and other callers that need data.

    Args:
        query: Natural language search query.
        palace_path: Path to the ChromaDB palace directory.
        wing: Optional wing filter.
        room: Optional room filter.
        n_results: Max results to return.
        max_distance: Max cosine distance threshold (0.0 disables).
    """
    return _run_search(
        query,
        palace_path,
        wing=wing,
        room=room,
        n_results=n_results,
        max_distance=max_distance,
    )
