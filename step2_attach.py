#!/usr/bin/env python3
"""2단계: 같은 질문을 문서 없음·정답 문서·엉뚱한 문서로 나눠 묻고 답과 입력 토큰을 비교한다.

사용: python3 step2_attach.py [모델]
설정: private/step2.json — {"system": 지시, "docs": {이름: private/ 기준 경로}, "cases": [{"label", "question", "doc": 이름|null}]}
"""
import json
import sys
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:11434/api/chat"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen3.5:4b"
NUM_CTX = 8192
PRIVATE = Path(__file__).resolve().parent / "private"

# private/step2.json 이 없을 때 쓰는 공개 예시(가상의 공지)
SAMPLE = {
    "system": "한국어로만 답해. 아래 [문서]에 적힌 내용으로만 답하고, 문서에 답이 없으면 '문서에 없어요'라고만 답해.",
    "docs": {"도서관 공지": "11월 정기 휴관일은 매주 월요일입니다. 11월 20일(목)은 소독으로 임시 휴관합니다."},
    "cases": [
        {"label": "문서 없음", "question": "11월 20일에 도서관 문 열어?", "doc": None},
        {"label": "정답 문서", "question": "11월 20일에 도서관 문 열어?", "doc": "도서관 공지"},
    ],
}


def load_config():
    path = PRIVATE / "step2.json"
    if not path.is_file():
        return SAMPLE, lambda name: SAMPLE["docs"][name]
    config = json.loads(path.read_text(encoding="utf-8"))
    return config, lambda name: (PRIVATE / config["docs"][name]).read_text(encoding="utf-8").strip()


def build_user_message(question, doc_name, read_doc):
    if doc_name is None:
        docs = "(없음)"
    else:
        docs = f"[문서 1] 출처: {doc_name}\n{read_doc(doc_name)}"
    return f"[문서]\n{docs}\n\n[질문]\n{question}"


def chat(system, user):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_ctx": NUM_CTX},
    }).encode()
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as res:
        return json.load(res)


def main():
    config, read_doc = load_config()
    print(f"모델 {MODEL}, num_ctx {NUM_CTX}\n")
    for case in config["cases"]:
        r = chat(config["system"], build_user_message(case["question"], case["doc"], read_doc))
        read_tokens = r.get("prompt_eval_count", 0)
        read_sec = r.get("prompt_eval_duration", 0) / 1e9
        out_tokens = r.get("eval_count", 0)
        out_sec = r.get("eval_duration", 0) / 1e9
        print(f"## [{case['label']}]")
        print(r["message"]["content"].strip())
        print(f"-- 읽은 입력 {read_tokens}토큰({read_sec:.1f}초), 답 {out_tokens}토큰({out_sec:.1f}초)\n")


if __name__ == "__main__":
    main()
