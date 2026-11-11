#!/usr/bin/env python3
"""1단계: 로컬 sLLM 에 문서 없이 질문해 보고 속도를 잰다. 사용: python3 step1_chat.py [모델]"""
import json
import sys
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:11434/api/chat"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen3.5:4b"
PRIVATE_QUESTIONS = Path(__file__).resolve().parent / "private" / "questions.json"

# 개인 질문(private/, git 제외)이 없을 때 쓰는 공개 예시
SAMPLE_QUESTIONS = [
    ["일반 지식", "안드로이드 ViewModel 이 화면 회전 뒤에도 데이터를 유지하는 이유를 3줄로 설명해줘."],
    ["모르는 사실", "우리 동네 도서관의 이번 주 휴관일은 언제야?"],
]


def load_questions():
    if PRIVATE_QUESTIONS.is_file():
        return json.loads(PRIVATE_QUESTIONS.read_text(encoding="utf-8"))
    return SAMPLE_QUESTIONS


def chat(question):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": question}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as res:
        return json.load(res)


for label, question in load_questions():
    r = chat(question)
    tokens = r.get("eval_count", 0)
    seconds = r.get("eval_duration", 0) / 1e9
    load = r.get("load_duration", 0) / 1e9
    print(f"## [{label}] {question}")
    print(r["message"]["content"].strip())
    print(f"-- 답 {tokens}토큰, {seconds:.1f}초, 초당 {tokens / seconds if seconds else 0:.1f}토큰, 모델 로딩 {load:.1f}초\n")
