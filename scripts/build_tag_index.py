#!/usr/bin/env python3
import argparse
import json
import sqlite3
from pathlib import Path

from sentence_transformers import SentenceTransformer, util


MODEL_NAME = "all-MiniLM-L6-v2"
DEFAULT_THRESHOLD = 0.28
DEFAULT_TOP_K = 12


def fetch_tags_from_sqlite(db_path):
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute("SELECT name FROM tags ORDER BY name ASC").fetchall()
    finally:
        connection.close()
    return [row[0] for row in rows if row and row[0]]


def build_index(tags, model_name, threshold, top_k):
    model = SentenceTransformer(model_name)
    embeddings = model.encode(tags, convert_to_tensor=True, normalize_embeddings=True)
    cosine = util.cos_sim(embeddings, embeddings).tolist()

    index = {
        "_meta": {
            "model_name": model_name,
            "threshold": threshold,
            "top_k": top_k,
            "tag_count": len(tags),
        }
    }

    for row_idx, tag_name in enumerate(tags):
        neighbors = []
        for col_idx, other_name in enumerate(tags):
            if row_idx == col_idx:
                continue
            score = float(cosine[row_idx][col_idx])
            if score < threshold:
                continue
            neighbors.append({
                "name": other_name,
                "score": round(score, 4),
            })
        neighbors.sort(key=lambda item: (item["score"], item["name"]), reverse=True)
        index[tag_name] = {
            "neighbors": neighbors[:top_k],
        }
    return index


def main():
    parser = argparse.ArgumentParser(description="Build offline semantic tag index for release deploys.")
    parser.add_argument("--db", default="data-dev.sqlite", help="Path to the SQLite database file.")
    parser.add_argument(
        "--output",
        default="app/data/tag_similarity_index.json",
        help="Output path for the generated tag index JSON.",
    )
    parser.add_argument("--model", default=MODEL_NAME, help="SentenceTransformer model name.")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="Minimum cosine score to keep.")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Maximum semantic neighbors per tag.")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    db_path = (project_root / args.db).resolve()
    output_path = (project_root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tags = fetch_tags_from_sqlite(db_path)
    index = build_index(tags, args.model, args.threshold, args.top_k)

    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2, ensure_ascii=True)

    print(f"Wrote semantic tag index for {len(tags)} tags to {output_path}")


if __name__ == "__main__":
    main()
