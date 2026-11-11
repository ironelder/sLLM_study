#!/usr/bin/env python3
"""5단계: 키워드(BM25) 순위와 임베딩 순위를 RRF 로 섞어 시험지 recall@1·@5 를 센다.

사용: python3 step5_hybrid.py <시험지.json> <결과.json> --keyword-cmd "<BM25 검색 명령 --json>" [--rrf-k 60] [--depth 50] [--kw-weight 1.0]
키워드 쪽: 시험지 항목의 keywords_a 를 명령 뒤에 붙여 실행하고 JSON 출력의 hits[].path 순서를 순위로 씀
RRF 점수: 각 방식에서의 순위 r 마다 1/(k + r) 를 더함 — 한쪽에만 나온 문서도 점수를 받음
"""
import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

import step3_search as s3
import step4_eval as s4

HERE = Path(__file__).resolve().parent


def keyword_ranking(cmd, keywords, exclude, depth):
    out = subprocess.run([*shlex.split(cmd), *keywords], capture_output=True, text=True).stdout
    try:
        hits = json.loads(out).get("hits", [])
    except json.JSONDecodeError:
        return []
    paths = [h["path"] for h in hits if not (exclude and h["path"].startswith(exclude))]
    return paths[:depth]


def rrf(rankings, k, weights):
    score = {}
    for ranking, w in zip(rankings, weights):
        for r, path in enumerate(ranking, 1):
            score[path] = score.get(path, 0.0) + w / (k + r)
    return [p for p, _ in sorted(score.items(), key=lambda kv: kv[1], reverse=True)]


def rank_of(gold, paths):
    ranks = [paths.index(g) + 1 for g in gold if g in paths]
    return min(ranks) if ranks else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("testset")
    ap.add_argument("out")
    ap.add_argument("--keyword-cmd", required=True)
    ap.add_argument("--index", default=str(HERE / "private" / "index"))
    ap.add_argument("--rrf-k", type=int, default=60)
    ap.add_argument("--depth", type=int, default=50)
    ap.add_argument("--kw-weight", type=float, default=1.0)
    opts = ap.parse_args()

    testset = json.loads(Path(opts.testset).read_text(encoding="utf-8"))
    meta, chunks, rows = s3.load_index(Path(opts.index))
    exclude = testset.get("exclude_prefix")
    result, table = {"method": f"H(rrf k={opts.rrf_k}, kw_w={opts.kw_weight})", "items": {}}, {}
    print("문항: 키워드 순위 / 임베딩 순위 / 섞은 순위  (- = 상위 50 밖)")
    for it in testset["items"]:
        kw = keyword_ranking(opts.keyword_cmd, it["keywords_a"], exclude, opts.depth)
        em = [p for p, _ in s4.doc_ranking(it["question"], meta, chunks, rows, exclude, opts.depth)]
        mixed = rrf([kw, em], opts.rrf_k, [opts.kw_weight, 1.0])
        ranks = [rank_of(it["gold_paths"], x) for x in (kw, em, mixed)]
        result["items"][it["id"]] = {"keywords": [it["keywords_a"]], "chosen_attempt": 1, "top5": mixed[:5],
                                     "ranks": {"keyword": ranks[0], "embedding": ranks[1], "hybrid": ranks[2]}}
        g = table.setdefault(it["group"], {"n": 0, "kw": [0, 0], "em": [0, 0], "hy": [0, 0]})
        g["n"] += 1
        for key, r in zip(("kw", "em", "hy"), ranks):
            g[key][0] += r == 1
            g[key][1] += r is not None and r <= 5
        print(f"{it['id']}: " + " / ".join(str(r) if r else "-" for r in ranks))

    Path(opts.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print()
    for grp, g in table.items():
        n = g["n"]
        print(f"{grp}: 키워드 @1 {g['kw'][0]}/{n} @5 {g['kw'][1]}/{n} | 임베딩 @1 {g['em'][0]}/{n} @5 {g['em'][1]}/{n}"
              f" | 섞기 @1 {g['hy'][0]}/{n} @5 {g['hy'][1]}/{n}")


if __name__ == "__main__":
    sys.exit(main())
