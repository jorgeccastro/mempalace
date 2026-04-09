#!/usr/bin/env python3
"""
searcher.py — Find anything. Exact words.

Semantic search against the palace.
Returns verbatim text — the actual words, never summaries.
"""

import logging
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import chromadb

logger = logging.getLogger("mempalace_mcp")


DEFAULT_OVERFETCH_FACTOR = 5
DEFAULT_MIN_CANDIDATES = 25
DEFAULT_HYBRID_WEIGHT = 0.30
DEFAULT_PREFIX_MATCH_WEIGHT = 0.92
DEFAULT_FUZZY_MATCH_WEIGHT = 0.84

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
    "as",
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


class SearchError(Exception):
    """Raised when search cannot proceed (e.g. no palace found)."""


def _normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def _extract_keywords(text: str) -> list[str]:
    normalized = _normalize_text(text)
    tokens = re.findall(r"\b[a-z0-9]{3,}\b", normalized)
    seen = set()
    keywords = []
    for token in tokens:
        if token in STOP_WORDS or token in seen:
            continue
        seen.add(token)
        keywords.append(token)
    return keywords


def _token_match_score(query_token: str, doc_token: str) -> float:
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


def _keyword_overlap(query_keywords: list[str], doc_text: str) -> float:
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


def _distance_to_similarity(distance: float) -> float:
    # Chroma's default metric is l2, so 1 - distance can go negative.
    # Convert to a bounded "closer is higher" score for display/API stability.
    return round(1.0 / (1.0 + max(distance, 0.0)), 3)


def _build_query_variants(query: str) -> list[str]:
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

    return variants


def _build_where_filter(wing: str = None, room: str = None) -> dict:
    if wing and room:
        return {"$and": [{"wing": wing}, {"room": room}]}
    if wing:
        return {"wing": wing}
    if room:
        return {"room": room}
    return {}


def _semantic_candidates(collection, query: str, where: dict, n_results: int) -> list[dict]:
    total = collection.count()
    if total <= 0:
        return []

    fetch_limit = min(total, max(n_results * DEFAULT_OVERFETCH_FACTOR, DEFAULT_MIN_CANDIDATES))
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
        ids = results["ids"][0]
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results["distances"][0]

        for doc_id, doc, meta, dist in zip(ids, docs, metas, dists):
            current = merged.get(doc_id)
            if current is None or dist < current["distance"]:
                merged[doc_id] = {
                    "id": doc_id,
                    "text": doc,
                    "metadata": meta,
                    "distance": dist,
                }

    return list(merged.values())


def _rerank_candidates(query: str, candidates: list[dict], n_results: int) -> list[dict]:
    query_keywords = _extract_keywords(query)

    for candidate in candidates:
        overlap = _keyword_overlap(query_keywords, candidate["text"])
        fused_distance = candidate["distance"] * (1.0 - DEFAULT_HYBRID_WEIGHT * overlap)
        candidate["keyword_overlap"] = round(overlap, 3)
        candidate["fused_distance"] = fused_distance

    candidates.sort(key=lambda item: (item["fused_distance"], item["distance"]))
    return candidates[:n_results]


def _run_search(
    query: str, palace_path: str, wing: str = None, room: str = None, n_results: int = 5
) -> dict:
    """Run search and return normalized search results for both CLI and MCP."""
    try:
        client = chromadb.PersistentClient(path=palace_path)
        col = client.get_collection("mempalace_drawers")
    except Exception as e:
        logger.error("No palace found at %s: %s", palace_path, e)
        return {
            "error": "No palace found",
            "hint": "Run: mempalace init <dir> && mempalace mine <dir>",
        }

    where = _build_where_filter(wing=wing, room=room)

    try:
        candidates = _semantic_candidates(col, query=query, where=where, n_results=n_results)
    except Exception as e:
        return {"error": f"Search error: {e}"}

    hits = []
    for candidate in _rerank_candidates(query=query, candidates=candidates, n_results=n_results):
        meta = candidate["metadata"]
        hits.append(
            {
                "text": candidate["text"],
                "wing": meta.get("wing", "unknown"),
                "room": meta.get("room", "unknown"),
                "source_file": Path(meta.get("source_file", "?")).name,
                "similarity": _distance_to_similarity(candidate["fused_distance"]),
            }
        )

    return {
        "query": query,
        "filters": {"wing": wing, "room": room},
        "results": hits,
    }


def search(query: str, palace_path: str, wing: str = None, room: str = None, n_results: int = 5):
    """
    Search the palace. Returns verbatim drawer content.
    Optionally filter by wing (project) or room (aspect).
    """
    results = _run_search(query, palace_path, wing=wing, room=room, n_results=n_results)
    if "error" in results:
        print(f"\n  {results['error']} at {palace_path}")
        if hint := results.get("hint"):
            print(f"  {hint}")
        raise SearchError(results["error"])

    docs = results["results"]
    if not docs:
        print(f'\n  No results found for: "{query}"')
        return

    print(f"\n{'=' * 60}")
    print(f'  Results for: "{query}"')
    if wing:
        print(f"  Wing: {wing}")
    if room:
        print(f"  Room: {room}")
    print(f"{'=' * 60}\n")

    for i, hit in enumerate(docs, 1):
        print(f"  [{i}] {hit['wing']} / {hit['room']}")
        print(f"      Source: {hit['source_file']}")
        print(f"      Match:  {hit['similarity']}")
        print()
        # Print the verbatim text, indented
        for line in hit["text"].strip().split("\n"):
            print(f"      {line}")
        print()
        print(f"  {'─' * 56}")

    print()


def search_memories(
    query: str, palace_path: str, wing: str = None, room: str = None, n_results: int = 5
) -> dict:
    """
    Programmatic search — returns a dict instead of printing.
    Used by the MCP server and other callers that need data.
    """
    return _run_search(query, palace_path, wing=wing, room=room, n_results=n_results)
