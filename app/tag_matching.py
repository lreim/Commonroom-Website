import json
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path


DEFAULT_THRESHOLD = 0.28
LEXICAL_THRESHOLD = 0.33
MAX_RESULTS = 30
TAG_INDEX_PATH = Path(__file__).resolve().parent / "data" / "tag_similarity_index.json"
TOKEN_RE = re.compile(r"[a-z0-9]+")


def _normalize_text(text):
    return " ".join(TOKEN_RE.findall((text or "").lower()))


def _tokenize(text):
    return [token for token in TOKEN_RE.findall((text or "").lower()) if token]


@lru_cache(maxsize=1)
def load_tag_index():
    if not TAG_INDEX_PATH.exists():
        return {}
    try:
        with TAG_INDEX_PATH.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def get_model():
    return load_tag_index() or None


def _candidate_entry(tag_name, normalized_map):
    entry = load_tag_index().get(tag_name, {})
    normalized = normalized_map.get(tag_name, _normalize_text(tag_name))
    tokens = _tokenize(normalized)
    return {
        "name": tag_name,
        "normalized": normalized,
        "tokens": tokens,
        "neighbors": entry.get("neighbors", []),
    }


def _lexical_score(query, candidate):
    query_normalized = _normalize_text(query)
    candidate_normalized = candidate["normalized"]
    if not query_normalized or not candidate_normalized:
        return 0.0

    if query_normalized == candidate_normalized:
        return 1.0

    query_tokens = set(_tokenize(query_normalized))
    candidate_tokens = set(candidate["tokens"])
    overlap = len(query_tokens & candidate_tokens) / max(len(query_tokens | candidate_tokens), 1)
    substring_bonus = 0.15 if (
        query_normalized in candidate_normalized or candidate_normalized in query_normalized
    ) else 0.0
    sequence = SequenceMatcher(None, query_normalized, candidate_normalized).ratio()
    return max(overlap + substring_bonus, sequence)


def match_tags(query, candidates, semantic_threshold=DEFAULT_THRESHOLD):
    query_normalized = _normalize_text(query)
    if not query_normalized.strip():
        return []

    normalized_map = {candidate: _normalize_text(candidate) for candidate in candidates}
    candidate_entries = {
        candidate: _candidate_entry(candidate, normalized_map)
        for candidate in candidates
    }

    lexical_hits = {}
    for candidate, entry in candidate_entries.items():
        score = _lexical_score(query_normalized, entry)
        if score < LEXICAL_THRESHOLD:
            continue
        lexical_hits[candidate] = {
            "name": candidate,
            "semantic": round(score, 4),
            "score": round(score, 4),
            "reasons": ["lexical"],
        }

    results = dict(lexical_hits)
    for base_tag, base_hit in lexical_hits.items():
        for neighbor in candidate_entries[base_tag]["neighbors"]:
            neighbor_name = neighbor.get("name")
            neighbor_score = float(neighbor.get("score", 0.0))
            if neighbor_name not in candidate_entries or neighbor_score < semantic_threshold:
                continue
            combined_score = max(base_hit["score"] * neighbor_score, neighbor_score)
            existing = results.get(neighbor_name)
            if existing is None or combined_score > existing["score"]:
                results[neighbor_name] = {
                    "name": neighbor_name,
                    "semantic": round(neighbor_score, 4),
                    "score": round(combined_score, 4),
                    "reasons": ["semantic"],
                }
            elif "semantic" not in existing["reasons"]:
                existing["reasons"].append("semantic")

    sorted_results = sorted(
        results.values(),
        key=lambda item: (item["score"], item["name"]),
        reverse=True,
    )
    return sorted_results[:MAX_RESULTS]
