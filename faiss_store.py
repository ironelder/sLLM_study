#!/usr/bin/env python3
"""10단계: 3단계 색인(vectors.f32)으로 FAISS 색인을 만들고 찾는다. 실행은 .venv/bin/python (faiss-cpu·numpy).

- flat: 전부 비교(정확). 3단계의 파이썬 전수 비교와 같은 결과
- hnsw: 이웃 그래프를 따라가는 근사 탐색. 빠르지만 가끔 놓칠 수 있음
"""
import json
from pathlib import Path

import faiss
import numpy as np

KINDS = ("flat", "hnsw")
HNSW_M = 32
EF_CONSTRUCTION = 100
EF_SEARCH = 64


def load_vectors(folder):
    folder = Path(folder)
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    vecs = np.fromfile(folder / "vectors.f32", dtype=np.float32).reshape(meta["count"], meta["dim"])
    return meta, vecs


def build(vecs, kind):
    dim = vecs.shape[1]
    if kind == "flat":
        index = faiss.IndexFlatIP(dim)
    else:
        index = faiss.IndexHNSWFlat(dim, HNSW_M, faiss.METRIC_INNER_PRODUCT)
        index.hnsw.efConstruction = EF_CONSTRUCTION
    index.add(vecs)
    return index


def index_path(folder, kind):
    return Path(folder) / f"faiss-{kind}.index"


def open_index(folder, kind):
    meta, vecs = load_vectors(folder)
    path = index_path(folder, kind)
    index = faiss.read_index(str(path)) if path.exists() else None
    if index is None or index.ntotal != meta["count"]:
        index = build(vecs, kind)
        faiss.write_index(index, str(path))
    if kind == "hnsw":
        index.hnsw.efSearch = EF_SEARCH
    return index


def search(index, qvec, k):
    scores, ids = index.search(np.asarray([qvec], dtype=np.float32), k)
    return [(float(s), int(i)) for s, i in zip(scores[0], ids[0]) if i >= 0]
