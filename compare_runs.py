#!/usr/bin/env python3
"""step6_rag.py 결과 여러 개를 같은 거절 판정으로 다시 세고, 칸이 달라진 문항을 나란히 보여 준다.

사용: python3 compare_runs.py 이름=결과.json [이름=결과.json ...] [--no-answer-ids N1,...]
--no-answer-ids: 문서 폴더에 답이 없는 질문 id (거절이 정답)
"""
import argparse
import json
import sys

import step6_rag as s6


def cell_of(rec, no_answer):
    refused = s6.is_refusal(rec["answer"])
    if rec["id"] in no_answer:
        return "답 없는 질문 · " + ("거절" if refused else "답함")
    return ("찾기 성공" if rec["gold_in_context"] else "찾기 실패") + " · " + ("거절" if refused else "답함")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--no-answer-ids", default="")
    opts = ap.parse_args()
    no_answer = set(filter(None, opts.no_answer_ids.split(",")))

    runs = {}
    for spec in opts.runs:
        name, path = spec.split("=", 1)
        with open(path, encoding="utf-8") as f:
            runs[name] = {r["id"]: r for r in json.load(f)}
    names = list(runs)
    ids = list(runs[names[0]])

    print("칸별 개수 (같은 거절 판정)")
    for name in names:
        counts = {}
        for i in ids:
            c = cell_of(runs[name][i], no_answer)
            counts[c] = counts.get(c, 0) + 1
        secs = sorted(r.get("seconds", 0) for r in runs[name].values())
        print(f"  {name}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + f" | 시간 중앙값 {secs[len(secs) // 2]}초")

    print("\n칸이 다른 문항")
    for i in ids:
        cells = [cell_of(runs[n][i], no_answer) for n in names]
        if len(set(cells)) > 1:
            print(f"\n{i}: " + " | ".join(f"{n}={c}" for n, c in zip(names, cells)))
            for n in names:
                print(f"   [{n}] {runs[n][i]['answer'][:140]}".replace("\n", " "))


if __name__ == "__main__":
    sys.exit(main())
