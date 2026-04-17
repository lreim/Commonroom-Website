from functools import lru_cache

try:
    from sentence_transformers import SentenceTransformer, util
except Exception:  # pragma: no cover
    SentenceTransformer = None
    util = None


MODEL_NAME = "all-MiniLM-L6-v2"
DEFAULT_THRESHOLD = 0.28
MAX_RESULTS = 30


@lru_cache(maxsize=1)
def get_model():
    if SentenceTransformer is None:
        return None
    try:
        return SentenceTransformer(MODEL_NAME, local_files_only=True)
    except Exception:
        return None


@lru_cache(maxsize=256)
def _cached_tag_embeddings(tags_key):
    model = get_model()
    if model is None:
        return None
    tags = list(tags_key)
    if not tags:
        return []
    return model.encode(tags, convert_to_tensor=True, normalize_embeddings=True)


def semantic_scores(query, candidates):
    model = get_model()
    if model is None or util is None:
        return None
    if not query.strip() or not candidates:
        return []

    query_embedding = model.encode([query], convert_to_tensor=True, normalize_embeddings=True)
    candidate_embeddings = _cached_tag_embeddings(tuple(candidates))
    if candidate_embeddings is None:
        return None
    sims = util.cos_sim(query_embedding, candidate_embeddings)[0].tolist()
    return [float(s) for s in sims]


def match_tags(query, candidates, semantic_threshold=DEFAULT_THRESHOLD):
    if not query.strip():
        return []

    scores = semantic_scores(query, candidates)
    if scores is None:
        return []

    results = []
    for idx, tag_name in enumerate(candidates):
        score = scores[idx] if idx < len(scores) else 0.0
        if score < semantic_threshold:
            continue
        results.append(
            {
                "name": tag_name,
                "semantic": round(score, 4),
                "score": round(score, 4),
                "reasons": ["semantic"],
            }
        )

    results.sort(key=lambda item: (item["score"], item["name"]), reverse=True)
    return results[:MAX_RESULTS]
