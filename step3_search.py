#!/usr/bin/env python3
"""3단계: 질문을 bge-m3 로 임베딩해 색인에서 가장 가까운 조각을 찾는다.

사용: python3 step3_search.py [-k 5] [--index private/index] "질문" ["질문" ...]
질문을 안 주면 private/step3_queries.json(["질문", ...]) 을 쓴다.
"""
import argparse
import json
import sys
import time
import urllib.request
from array import array
from pathlib import Path

API = "http://127.0.0.1:11434/api/embed"
HERE = Path(__file__).resolve().parent


def load_index(folder):
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    chunks = [json.loads(line) for line in (folder / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    vectors = array("f")
    with open(folder / "vectors.f32", "rb") as f:
        vectors.fromfile(f, meta["count"] * meta["dim"])
    dim = meta["dim"]
    rows = [vectors[i * dim : (i + 1) * dim] for i in range(meta["count"])]
    return meta, chunks, rows


def embed(model, text):
    body = json.dumps({"model": model, "input": [text]}).encode()
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as res:
        vec = json.load(res)["embeddings"][0]
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]


def search(query, meta, chunks, rows, k):
    q = embed(meta["model"], query)
    scored = [(sum(a * b for a, b in zip(q, row)), i) for i, row in enumerate(rows)]
    scored.sort(reverse=True)
    return [(score, chunks[i]) for score, i in scored[:k]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("queries", nargs="*")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--index", default=str(HERE / "private" / "index"))
    opts = ap.parse_args()

    queries = opts.queries or json.loads((HERE / "private" / "step3_queries.json").read_text(encoding="utf-8"))
    meta, chunks, rows = load_index(Path(opts.index))
    print(f"색인: 조각 {meta['count']}개 × {meta['dim']}차원 ({meta['model']}, {meta['built']})\n")
    for query in queries:
        t0 = time.time()
        hits = search(query, meta, chunks, rows, opts.k)
        print(f"## {query}  ({time.time() - t0:.1f}초)")
        for rank, (score, c) in enumerate(hits, 1):
            snippet = c["text"].split("\n")[-1][:80].replace("\n", " ")
            print(f"{rank}. {score:.3f}  {c['path']}:{c['line']}  [{c['heading'][:50]}]")
            print(f"     {snippet}")
        print()


if __name__ == "__main__":
    sys.exit(main())
