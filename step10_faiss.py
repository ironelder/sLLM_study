#!/usr/bin/env python3
"""10단계: 같은 시험지로 파이썬 전수 비교·numpy·FAISS Flat·FAISS HNSW 의 찾기 정확도와 속도를 비교하고,
벡터 수를 불려 규모별 속도를 잰다.

사용: .venv/bin/python step10_faiss.py <시험지.json> <결과.json> [--index private/index] [--scale 200000]
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import faiss
import numpy as np

import faiss_store as fs
import step3_search as s3

HERE = Path(__file__).resolve().parent
DEPTH = 200
TOP_DOCS = 20
SCALE_NOISE = 0.02
SCALE_BATCH = 20000


def doc_ranking(hits, chunks, exclude):
    seen, ranked = set(), []
    for score, i in hits:
        path = chunks[i]["path"]
        if (exclude and path.startswith(exclude)) or path in seen:
            continue
        seen.add(path)
        ranked.append(path)
        if len(ranked) == TOP_DOCS:
            break
    return ranked


def numpy_top(vecs, q, k):
    scores = vecs @ q
    idx = np.argpartition(-scores, k)[:k]
    idx = idx[np.argsort(-scores[idx])]
    return [(float(scores[i]), int(i)) for i in idx]


def ms(seconds_list):
    return round(statistics.median(seconds_list) * 1000, 2)


def timed(fn, q):
    t0 = time.perf_counter()
    hits = fn(q)
    return hits, time.perf_counter() - t0


def scale_test(vecs, queries, n_total, py_per_vector):
    rng = np.random.default_rng(0)
    n_real, dim = vecs.shape
    big = np.empty((n_total, dim), dtype=np.float32)
    big[:n_real] = vecs
    for start in range(n_real, n_total, SCALE_BATCH):
        end = min(start + SCALE_BATCH, n_total)
        part = vecs[rng.integers(0, n_real, end - start)] + rng.standard_normal((end - start, dim), dtype=np.float32) * SCALE_NOISE
        big[start:end] = part / np.linalg.norm(part, axis=1, keepdims=True)

    t0 = time.perf_counter()
    flat = fs.build(big, "flat")
    t_flat = time.perf_counter() - t0
    t0 = time.perf_counter()
    hnsw = fs.build(big, "hnsw")
    t_hnsw = time.perf_counter() - t0
    hnsw.hnsw.efSearch = fs.EF_SEARCH

    t_np, t_f, t_h, overlap = [], [], [], []
    for q in queries:
        _, t = timed(lambda v: numpy_top(big, v, 10), q)
        t_np.append(t)
        exact, t = timed(lambda v: fs.search(flat, v, 10), q)
        t_f.append(t)
        approx, t = timed(lambda v: fs.search(hnsw, v, 10), q)
        t_h.append(t)
        overlap.append(len({i for _, i in exact} & {i for _, i in approx}) / 10)
    return {
        "vectors": n_total,
        "memory_mb_flat": round(faiss.serialize_index(flat).nbytes / 1e6),
        "memory_mb_hnsw": round(faiss.serialize_index(hnsw).nbytes / 1e6),
        "build_s_flat": round(t_flat, 1), "build_s_hnsw": round(t_hnsw, 1),
        "ms_python_estimate": round(py_per_vector * n_total * 1000),
        "ms_numpy": ms(t_np), "ms_faiss_flat": ms(t_f), "ms_faiss_hnsw": ms(t_h),
        "hnsw_recall_at10": round(sum(overlap) / len(overlap), 3),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("testset")
    ap.add_argument("out")
    ap.add_argument("--index", default=str(HERE / "private" / "index"))
    ap.add_argument("--scale", type=int, default=200000, help="0 이면 규모 시험 생략")
    opts = ap.parse_args()
    folder = Path(opts.index)

    testset = json.loads(Path(opts.testset).read_text(encoding="utf-8"))
    exclude = testset.get("exclude_prefix")
    meta, chunks, rows = s3.load_index(folder)
    _, vecs = fs.load_vectors(folder)
    norms = np.linalg.norm(vecs, axis=1)
    print(f"색인: 조각 {meta['count']}개 × {meta['dim']}차원, 벡터 길이 {norms.min():.4f}~{norms.max():.4f}")

    built = {}
    for kind in fs.KINDS:
        t0 = time.perf_counter()
        index = fs.build(vecs, kind)
        built[kind] = {"seconds": round(time.perf_counter() - t0, 2)}
        faiss.write_index(index, str(fs.index_path(folder, kind)))
        built[kind]["file_mb"] = round(fs.index_path(folder, kind).stat().st_size / 1e6, 1)
        if kind == "hnsw":
            index.hnsw.efSearch = fs.EF_SEARCH
        built[kind]["index"] = index
        print(f"FAISS {kind}: 만들기 {built[kind]['seconds']}초, 파일 {built[kind]['file_mb']}MB")

    t_embed, queries = [], []
    for it in testset["items"]:
        q, t = timed(lambda text: s3.embed(meta["model"], text), it["question"])
        queries.append(np.asarray(q, dtype=np.float32))
        t_embed.append(t)

    methods = {
        "python": lambda q: sorted(((sum(a * b for a, b in zip(q, row)), i) for i, row in enumerate(rows)), reverse=True)[:DEPTH],
        "numpy": lambda q: numpy_top(vecs, q, DEPTH),
        "faiss_flat": lambda q: fs.search(built["flat"]["index"], q, DEPTH),
        "faiss_hnsw": lambda q: fs.search(built["hnsw"]["index"], q, DEPTH),
    }
    report = {"chunks": meta["count"], "dim": meta["dim"], "build": {k: {kk: vv for kk, vv in v.items() if kk != "index"} for k, v in built.items()},
              "ms_embed": ms(t_embed), "methods": {}}
    rankings = {}
    for name, fn in methods.items():
        times, table, ranks = [], {}, {}
        q_list = [q.tolist() for q in queries] if name == "python" else queries
        for it, q in zip(testset["items"], q_list):
            hits, t = timed(fn, q)
            times.append(t)
            docs = doc_ranking(hits, chunks, exclude)
            rankings.setdefault(name, []).append(docs)
            found = [docs.index(g) + 1 for g in it["gold_paths"] if g in docs]
            rank = min(found) if found else None
            ranks[it["id"]] = rank
            g = table.setdefault(it["group"], {"n": 0, "r1": 0, "r5": 0})
            g["n"] += 1
            g["r1"] += rank == 1
            g["r5"] += rank is not None and rank <= 5
        same = sum(a[:5] == b[:5] for a, b in zip(rankings[name], rankings["python"]))
        report["methods"][name] = {"ms_search": ms(times), "groups": table, "same_top5_as_python": same, "gold_rank": ranks}
        groups = " · ".join(f"{k} @1 {v['r1']}/{v['n']} @5 {v['r5']}/{v['n']}" for k, v in table.items())
        print(f"{name:11s} 찾기 중앙값 {ms(times):>8}ms · {groups} · 파이썬과 문서 top5 같음 {same}/{len(queries)}")
    print(f"질문 임베딩(bge-m3) 중앙값 {report['ms_embed']}ms")

    if opts.scale:
        py_per_vector = report["methods"]["python"]["ms_search"] / 1000 / meta["count"]
        print(f"\n규모 시험: 실제 벡터 {meta['count']}개 + 잡음 섞은 복제로 {opts.scale}개 (만드는 중…)", flush=True)
        report["scale"] = scale_test(vecs, queries, opts.scale, py_per_vector)
        for k, v in report["scale"].items():
            print(f"  {k}: {v}")

    Path(opts.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
