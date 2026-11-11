#!/usr/bin/env python3
"""4단계: 시험지 질문을 임베딩 검색에 넣어 문서 단위 순위를 매기고 recall@1·@5 를 센다.

사용: python3 step4_eval.py <시험지.json> <결과.json> [--index private/index] [--top 20]
시험지 형식: {"exclude_prefix": 경로 접두|null, "items": [{"id", "group", "question", "gold_paths": [...]}]}
결과 형식은 키워드 검색 채점기와 같게 맞춤: {"method": "E", "items": {id: {"keywords": [[]], "top5": [...]}}}
"""
import argparse
import json
import sys
from pathlib import Path

import step3_search as s3

HERE = Path(__file__).resolve().parent


def doc_ranking(query, meta, chunks, rows, exclude, top):
    """조각 점수를 문서별 최고점으로 모아 문서 순위를 만든다."""
    q = s3.embed(meta["model"], query)
    best = {}
    for row, c in zip(rows, chunks):
        path = c["path"]
        if exclude and path.startswith(exclude):
            continue
        score = sum(a * b for a, b in zip(q, row))
        if score > best.get(path, -1.0):
            best[path] = score
    return sorted(best.items(), key=lambda kv: kv[1], reverse=True)[:top]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("testset")
    ap.add_argument("out")
    ap.add_argument("--index", default=str(HERE / "private" / "index"))
    ap.add_argument("--top", type=int, default=20)
    opts = ap.parse_args()

    testset = json.loads(Path(opts.testset).read_text(encoding="utf-8"))
    meta, chunks, rows = s3.load_index(Path(opts.index))
    exclude = testset.get("exclude_prefix")
    result, table = {"method": "E", "items": {}}, {}
    for it in testset["items"]:
        ranked = doc_ranking(it["question"], meta, chunks, rows, exclude, opts.top)
        paths = [p for p, _ in ranked]
        gold_ranks = [paths.index(g) + 1 for g in it["gold_paths"] if g in paths]
        rank = min(gold_ranks) if gold_ranks else None
        result["items"][it["id"]] = {"keywords": [[]], "chosen_attempt": 1, "top5": paths[:5],
                                     "gold_rank_top": rank, "top1_score": round(ranked[0][1], 3) if ranked else None}
        g = table.setdefault(it["group"], {"n": 0, "r1": 0, "r5": 0})
        g["n"] += 1
        g["r1"] += rank == 1
        g["r5"] += rank is not None and rank <= 5
        shown = rank if rank is not None else f">{opts.top}"
        print(f"{it['id']}: 정답 순위 {shown}  (1위 점수 {result['items'][it['id']]['top1_score']})")

    Path(opts.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print()
    for grp, g in table.items():
        print(f"{grp}: recall@1={g['r1']}/{g['n']} recall@5={g['r5']}/{g['n']}")


if __name__ == "__main__":
    sys.exit(main())
