#!/usr/bin/env python3
"""6단계: 임베딩으로 조각 5개를 찾아 출처 번호를 붙여 sLLM 에 주고, 답을 '찾기 성공 × 답함' 4칸으로 나눠 센다.

사용: python3 step6_rag.py <결과.json> <시험지.json> [<시험지.json> ...] [--model qwen3.5:4b] [-k 5]
시험지 항목: {"id", "question", "gold_paths": [...]} — gold_paths 가 빈 목록이면 문서 폴더에 답이 없는 질문(거절이 정답)
"""
import argparse
import json
import re
import socket
import sys
import urllib.request
from pathlib import Path

import step3_search as s3

HERE = Path(__file__).resolve().parent
CHAT_API = "http://127.0.0.1:11434/api/chat"
EMBED_API = "http://127.0.0.1:11434/api/embed"
ASK_TIMEOUT = 240
NUM_CTX = 12288
REFUSAL = "자료에 없어요"
SYSTEM = (
    "너는 문서 도우미야. 한국어로만 답해. 아래 [자료]만 근거로 답하고, 근거가 된 자료 번호를 문장 끝에 [1]처럼 붙여. "
    f"자료로 답할 수 없으면 '{REFUSAL}'라고만 답해. 3문장 이내로 답해."
)


REFUSE_RE = re.compile(r"자료.{0,80}(없(어요|습니다|음|다)|않습니다|부족)")


def is_refusal(answer):
    # 모델이 거절 문구를 바꿔 말하고 이유를 덧붙임("제공된 자료에는 …가 명시되어 있지 않습니다 … 근거 자료가 없습니다", 11-11 실측)
    # → 첫 문장이 '자료에 없음'이고, 짧거나 마지막 문장도 '자료에 없음'이면 거절
    sentences = re.split(r"(?<=[.!?])\s", answer.strip())
    if not REFUSE_RE.search(sentences[0]):
        return False
    return len(answer) < 160 or bool(REFUSE_RE.search(sentences[-1]))


def top_chunks(query, meta, chunks, rows, exclude, k):
    q = s3.embed(meta["model"], query)
    scored = []
    for row, c in zip(rows, chunks):
        if exclude and c["path"].startswith(exclude):
            continue
        scored.append((sum(a * b for a, b in zip(q, row)), c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:k]]


def build_prompt(question, found):
    parts = []
    for n, c in enumerate(found, 1):
        source = c["path"] + (f" > {c['heading']}" if c["heading"] else "")
        project = f"프로젝트: {c['project']} · " if c.get("project") else ""
        parts.append(f"[{n}] {project}출처: {source}\n{c['text']}")
    return "[자료]\n" + "\n\n".join(parts) + f"\n\n[질문]\n{question}"


CHECK_PROJECT = " 자료마다 붙은 프로젝트가 질문이 묻는 대상과 다르면 그 자료는 근거로 쓰지 마."


def ask(model, user, system=SYSTEM):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_ctx": NUM_CTX},
    }).encode()
    req = urllib.request.Request(CHAT_API, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=ASK_TIMEOUT) as res:
        return json.load(res)


def unload(model):
    body = json.dumps({"model": model, "input": "", "keep_alive": 0}).encode()
    req = urllib.request.Request(EMBED_API, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("testsets", nargs="+")
    ap.add_argument("--model", default="qwen3.5:4b")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--index", default=str(HERE / "private" / "index"))
    ap.add_argument("--check-project", action="store_true", help="지시에 '프로젝트가 다른 자료는 쓰지 마' 추가")
    opts = ap.parse_args()

    system = SYSTEM + (CHECK_PROJECT if opts.check_project else "")
    meta, chunks, rows = s3.load_index(Path(opts.index))
    # 찾기를 먼저 다 끝내고 임베딩 모델을 내린 뒤 답하기 — 큰 답하기 모델과 둘이 같이 메모리에 오르지 않게(16GB 실측)
    jobs = []
    for ts_path in opts.testsets:
        ts = json.loads(Path(ts_path).read_text(encoding="utf-8"))
        exclude = ts.get("exclude_prefix")
        for it in ts["items"]:
            jobs.append((it, top_chunks(it["question"], meta, chunks, rows, exclude, opts.k)))
    unload(meta["model"])
    del rows

    records, cells = [], {}
    for it, found in jobs:
        try:
            r = ask(opts.model, build_prompt(it["question"], found), system)
        except (socket.timeout, TimeoutError):
            print(f"{it['id']}: 답이 {ASK_TIMEOUT}초 안에 안 옴 — 메모리 부족 의심, 여기까지 저장하고 멈춤")
            Path(opts.out).write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
            return 2
        answer = r["message"]["content"].strip()
        gold = set(it["gold_paths"])
        hit = [n for n, c in enumerate(found, 1) if c["path"] in gold]
        cited = sorted({int(x) for x in re.findall(r"\[(\d)\]", answer)})
        refused = is_refusal(answer)
        if not gold:
            cell = "답 없는 질문 · 거절" if refused else "답 없는 질문 · 답함"
        else:
            cell = ("찾기 성공" if hit else "찾기 실패") + " · " + ("거절" if refused else "답함")
        cells[cell] = cells.get(cell, 0) + 1
        records.append({"id": it["id"], "question": it["question"], "cell": cell, "gold_in_context": hit,
                        "cited": cited, "cited_gold": bool(set(cited) & set(hit)), "answer": answer,
                        "context": [f"{c['path']}:{c['line']}" for c in found],
                        "prompt_tokens": r.get("prompt_eval_count"), "answer_tokens": r.get("eval_count"),
                        "seconds": round(r.get("total_duration", 0) / 1e9, 1)})
        print(f"{it['id']} [{cell}] 정답 조각 위치={hit or '-'} 인용={cited or '-'} "
              f"({records[-1]['prompt_tokens']}→{records[-1]['answer_tokens']}토큰, {records[-1]['seconds']}초)", flush=True)
        print(f"   {answer[:220]}".replace("\n", " "), flush=True)

    Path(opts.out).write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n칸별 개수")
    for cell, n in sorted(cells.items()):
        print(f"  {cell}: {n}")


if __name__ == "__main__":
    sys.exit(main())
