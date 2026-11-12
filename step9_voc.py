#!/usr/bin/env python3
"""9단계: VOC 티켓 해석 → 고객 로그 조회 → 개인정보 가림 → 요약 → 메일 초안(.eml)·발송.

사용: python3 step9_voc.py <티켓.json> <로그.jsonl> <출력 폴더> [--expected 정답.json] [--smtp 127.0.0.1:2525]
      [--to cs-team@example.com] [--model qwen3.5:4b] [--only VOC-101]
티켓 = Jira 검색 API 응답 모양 {"issues": [{"key", "fields": {"summary", "description", "created"}}]}
"""
import argparse
import datetime as dt
import json
import re
import smtplib
import sys
import time
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path

CHAT_API = "http://127.0.0.1:11434/api/chat"
TIMEOUT = 240
CATEGORIES = ["결제", "로그인", "앱 오류", "환불·취소", "배송", "기타"]
URGENCY = ["높음", "보통", "낮음"]
LEAD_HOURS = 12
LOOKBACK_HOURS = 72
RETENTION_DAYS = 14
MAX_LINES = 30
WEEKDAYS = "월화수목금토일"

CUSTOMER_RE = re.compile(r"C-\d{6}")
PHONE_RE = re.compile(r"(01[016789])-?(\d{3,4})-?(\d{4})")
EMAIL_RE = re.compile(r"([\w.+-])[\w.+-]*@([\w-]+(?:\.[\w-]+)+)")
NAME_RE = re.compile(r"(이름\s*[:：]?\s*)([가-힣])([가-힣]{1,3})")
CODE_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
CITE_RE = re.compile(r"\[(L\d+(?:\s*,\s*L?\d+)*)\]")

SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": CATEGORIES},
        "symptom": {"type": "string"},
        "occurred_at": {"type": "string"},
        "urgency": {"type": "string", "enum": URGENCY},
    },
    "required": ["category", "symptom", "occurred_at", "urgency"],
}
# 칸 순서 = 생성 순서. 요약을 먼저 쓰게 한 뒤 판단 칸을 채우게 함
SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "cause_found": {"type": "boolean"},
        "next_action": {"type": "string"},
    },
    "required": ["summary", "cause_found", "next_action"],
}
INTERPRET_SYSTEM = "너는 고객 문의(VOC) 티켓을 읽고 칸을 채우는 도우미야. 티켓에 적힌 내용만 쓰고 지어내지 마."
SUMMARY_SYSTEM = (
    "너는 고객 문의(VOC) 분석 도우미야. 한국어로만 써. 아래 [로그]만 근거로 칸을 채우고, 지어내거나 추측하지 마.\n"
    "- summary: 문의와 관련된 로그 사실을 3문장 이내로. 문장마다 근거 로그 번호를 [L1]처럼 붙여\n"
    "- cause_found: 문의한 문제를 직접 설명하는 오류·실패 기록이 로그에 있으면 true, 없으면 false\n"
    "- next_action: 상담사가 할 일 한 가지"
)


def mask(text):
    text = CUSTOMER_RE.sub(lambda m: m.group()[:4] + "****", text)
    text = PHONE_RE.sub(lambda m: f"{m.group(1)}-****-{m.group(3)}", text)
    text = EMAIL_RE.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", text)
    return NAME_RE.sub(lambda m: m.group(1) + m.group(2) + "*" * len(m.group(3)), text)


def find_leaks(text, raw_names):
    leaks = CUSTOMER_RE.findall(text) + ["-".join(m) for m in PHONE_RE.findall(text)]
    leaks += re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)
    return leaks + [n for n in raw_names if n in text]


def chat(model, system, user, fmt=None):
    body = {
        "model": model, "stream": False, "think": False,
        "options": {"temperature": 0, "num_ctx": 8192},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if fmt:
        body["format"] = fmt
    req = urllib.request.Request(CHAT_API, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.load(r)["message"]["content"]
    except urllib.error.URLError as e:
        sys.exit(f"Ollama 서버 호출 실패({e}) — 서버가 켜져 있는지 확인")


def recent_calendar(created):
    labels = {0: ", 오늘", 1: ", 어제", 2: ", 그제"}
    days = [(created - dt.timedelta(days=i)).date() for i in range(7)]
    return " · ".join(f"{d:%Y-%m-%d}({WEEKDAYS[d.weekday()]}{labels.get(i, '')})" for i, d in enumerate(days))


def interpret(model, fields, masked_desc, created, calendar):
    user = (
        f"접수 시각: {created:%Y-%m-%d %H:%M} ({WEEKDAYS[created.weekday()]}요일)\n"
        + (f"최근 7일: {recent_calendar(created)}\n" if calendar else "") +
        f"제목: {fields['summary']}\n내용:\n{masked_desc}\n\n칸 설명\n"
        f"- category: {', '.join(CATEGORIES)} 중 하나\n"
        "- symptom: 고객이 겪은 문제를 한 문장으로\n"
        "- occurred_at: 문제가 처음 생긴 시각 'YYYY-MM-DD HH:MM'. '어제'·'월요일' 같은 말은 접수 시각 기준으로 계산하고, "
        "날짜만 알면 시각은 00:00, 알 수 없으면 빈 문자열\n"
        "- urgency: 높음·보통·낮음 (돈이 걸렸거나 서비스를 못 쓰면 높음)"
    )
    for _ in range(2):
        try:
            data = json.loads(chat(model, INTERPRET_SYSTEM, user, SCHEMA))
        except json.JSONDecodeError:
            continue
        if data.get("category") in CATEGORIES and data.get("urgency") in URGENCY:
            return data, True
    return {"category": "기타", "symptom": "", "occurred_at": "", "urgency": "보통"}, False


def parse_occurred(value, created):
    try:
        t = dt.datetime.strptime(value.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=created.tzinfo)
    except ValueError:
        return None
    if t > created or t < created - dt.timedelta(days=365):
        return None
    return t


def log_window(occurred, created):
    if occurred:
        start = occurred - dt.timedelta(hours=LEAD_HOURS)
    else:
        start = created - dt.timedelta(hours=LOOKBACK_HOURS)
    floor = created - dt.timedelta(days=RETENTION_DAYS)
    return max(start, floor), created, start < floor


def log_line(n, r):
    detail = f" {r['detail']}" if r["detail"] else ""
    return mask(f"L{n} {r['t']:%Y-%m-%d %H:%M:%S} {r['device']} {r['event']} {r['code']}{detail}")


def summarize(model, user):
    for _ in range(2):
        try:
            data = json.loads(chat(model, SUMMARY_SYSTEM, user, SUMMARY_SCHEMA))
        except json.JSONDecodeError:
            continue
        if isinstance(data.get("cause_found"), bool) and data.get("summary"):
            return data["cause_found"], f"{data['summary'].strip()}\n다음 조치: {data['next_action'].strip()}"
    return None, "요약 형식이 두 번 다 깨져 요약을 만들지 못했어요.\n다음 조치: 로그를 직접 확인해 주세요."


def grade(exp, rec):
    g = {"category": rec["category"] in exp["category"]}
    occ = rec["occurred_at_valid"]
    if "occurred_at" in exp:
        g["time"] = occ == exp["occurred_at"]
    elif "occurred_date" in exp:
        g["time"] = bool(occ) and occ[:10] == exp["occurred_date"]
    if "key_codes" in exp:
        cited = " ".join(rec["lines"][c - 1] for c in rec["cited"] if 1 <= c <= len(rec["lines"]))
        g["key_log"] = all(code in cited for code in exp["key_codes"])
    if exp.get("no_customer"):
        g["no_customer"] = rec["customer"] is None
    if "cause" in exp:
        g["cause"] = rec["cause_found"] is exp["cause"]
    return g


def build_mail(args, key, rec, body):
    msg = EmailMessage()
    msg["From"] = "voc-bot@example.com"
    msg["To"] = args.to
    msg["Subject"] = f"[{key}] {rec['category']} · 긴급도 {rec['urgency']} — VOC 요약(AI 초안)"
    msg.set_content(body)
    return msg


def process(args, issue, logs, expected):
    key, fields = issue["key"], issue["fields"]
    created = dt.datetime.strptime(fields["created"], "%Y-%m-%dT%H:%M:%S.%f%z")
    raw = fields["description"]
    customers = CUSTOMER_RE.findall(raw)
    raw_names = [m.group(2) + m.group(3) for m in NAME_RE.finditer(raw)]
    masked_desc = mask(raw)

    t0 = time.time()
    data, ok = interpret(args.model, fields, masked_desc, created, not args.no_calendar)
    t_interpret = time.time() - t0
    occurred = parse_occurred(data["occurred_at"], created)
    rec = {
        "key": key, "category": data["category"], "urgency": data["urgency"], "symptom": data["symptom"],
        "occurred_at_raw": data["occurred_at"], "interpret_ok": ok,
        "occurred_at_valid": f"{occurred:%Y-%m-%d %H:%M}" if occurred else "",
        "customer": customers[0] if customers else None, "cause_found": None, "lines": [], "cited": [], "bad_cites": [],
        "invented_codes": [], "note": "", "seconds_interpret": round(t_interpret, 1), "seconds_summary": 0.0,
    }

    if not rec["customer"]:
        rec["summary"] = "회원번호가 티켓에 없어 로그를 조회하지 않았어요.\n다음 조치: 고객에게 회원번호나 가입 이메일을 확인해 주세요."
        window_text = "조회 안 함"
    else:
        start, end, clipped = log_window(occurred, created)
        hits = sorted((r for r in logs if r["customer"] == rec["customer"] and start <= r["t"] <= end), key=lambda r: r["t"])
        rec["lines"] = [log_line(n, r) for n, r in enumerate(hits[:MAX_LINES], 1)]
        window_text = f"{start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M} · {len(hits)}건"
        if clipped:
            rec["note"] = f"요청한 시점 일부가 로그 보관 기간({RETENTION_DAYS}일) 밖이라 {start:%Y-%m-%d %H:%M} 부터 조회했어요."
        if len(hits) > MAX_LINES:
            rec["note"] += f" 로그가 많아 앞 {MAX_LINES}건만 요약에 썼어요."
        if not hits:
            rec["summary"] = "조회 범위 안에 이 고객의 로그가 없어요.\n다음 조치: 고객에게 문제가 생긴 날짜를 다시 확인해 주세요."
        else:
            user = (
                f"[문의]\n제목: {fields['summary']}\n{masked_desc}\n\n"
                f"[로그] 이 고객의 {window_text}\n" + "\n".join(rec["lines"])
            )
            t1 = time.time()
            rec["cause_found"], rec["summary"] = summarize(args.model, user)
            rec["seconds_summary"] = round(time.time() - t1, 1)
            rec["cited"] = sorted({int(n) for group in CITE_RE.findall(rec["summary"]) for n in re.findall(r"\d+", group)})
            rec["bad_cites"] = [c for c in rec["cited"] if not 1 <= c <= len(rec["lines"])]
            allowed = set(CODE_RE.findall("\n".join(rec["lines"])))
            rec["invented_codes"] = sorted({c for c in CODE_RE.findall(rec["summary"]) if c not in allowed})

    check = f"인용 번호 이상 {len(rec['bad_cites'])} · 로그에 없는 코드 {len(rec['invented_codes'])}"
    body = "\n".join([
        f"티켓: {key} (접수 {created:%Y-%m-%d %H:%M})",
        f"제목: {fields['summary']}",
        f"고객: {mask(rec['customer']) if rec['customer'] else '확인 필요'} (전체 정보는 티켓에서 확인)",
        f"분류: {rec['category']} · 긴급도 {rec['urgency']}",
        f"증상: {rec['symptom']}",
        f"발생 시각(해석): {rec['occurred_at_valid'] or '알 수 없음'}",
        f"로그 조회: {window_text}",
        f"로그로 원인 확인: {({True: '예', False: '아니요'}).get(rec['cause_found'], '판단 안 함')}",
        *([rec["note"].strip()] if rec["note"] else []),
        "", "[요약]", rec["summary"],
        "", "[근거 로그]", *(rec["lines"] or ["없음"]),
        "", "[자동 확인]", check,
        "", f"이 메일은 로컬 AI({args.model})가 만든 초안이에요. 회신 전에 티켓 원문과 로그를 확인해 주세요.",
    ])
    rec["leaks"] = find_leaks(body, raw_names)
    msg = build_mail(args, key, rec, body)
    (args.out / "outbox").mkdir(parents=True, exist_ok=True)
    (args.out / "outbox" / f"{key}.eml").write_bytes(bytes(msg))
    rec["sent"] = False
    if args.smtp:
        host, port = args.smtp.rsplit(":", 1)
        with smtplib.SMTP(host, int(port), timeout=10) as s:
            s.send_message(msg)
        rec["sent"] = True
    if expected and key in expected:
        rec["grade"] = grade(expected[key], rec)
    return rec


def load_logs(path):
    rows = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            r["t"] = dt.datetime.fromisoformat(r["ts"])
            rows.append(r)
    return rows


def print_grades(results):
    cols = [("category", "분류"), ("time", "발생 시각"), ("key_log", "핵심 로그 인용"),
            ("no_customer", "회원번호 없음 처리"), ("cause", "원인 확인 여부")]
    print("\n[채점]")
    for r in results:
        g = r.get("grade", {})
        marks = " · ".join(f"{label} {'O' if g[k] else 'X'}" for k, label in cols if k in g)
        print(f"  {r['key']}: {marks} · 지어낸 코드 {len(r['invented_codes'])} · 개인정보 노출 {len(r['leaks'])}")
    for k, label in cols:
        vals = [r["grade"][k] for r in results if k in r.get("grade", {})]
        if vals:
            print(f"  {label}: {sum(vals)}/{len(vals)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tickets")
    ap.add_argument("logs")
    ap.add_argument("out", type=Path)
    ap.add_argument("--expected")
    ap.add_argument("--smtp", help="host:port — 주면 메일을 보냄")
    ap.add_argument("--to", default="cs-team@example.com")
    ap.add_argument("--model", default="qwen3.5:4b")
    ap.add_argument("--only")
    ap.add_argument("--no-calendar", action="store_true", help="해석 지시에서 최근 7일 달력을 뺌 (비교 실험용)")
    args = ap.parse_args()

    issues = json.loads(Path(args.tickets).read_text())["issues"]
    if args.only:
        issues = [i for i in issues if i["key"] == args.only]
    logs = load_logs(args.logs)
    expected = json.loads(Path(args.expected).read_text()) if args.expected else None

    results = []
    for issue in issues:
        rec = process(args, issue, logs, expected)
        results.append(rec)
        print(f"{rec['key']} {rec['category']}·{rec['urgency']} 발생 {rec['occurred_at_valid'] or '-'} 원인확인 {rec['cause_found']}"
              f" · 로그 {len(rec['lines'])}건 · 인용 {rec['cited']} · 지어낸 코드 {rec['invented_codes']}"
              f" · 개인정보 노출 {len(rec['leaks'])} · 발송 {'O' if rec['sent'] else '-'}"
              f" · 해석 {rec['seconds_interpret']}초 요약 {rec['seconds_summary']}초")
        print("   " + rec["summary"].replace("\n", " / ")[:240])

    if expected:
        print_grades(results)
    total_leaks = sum(len(r["leaks"]) for r in results)
    print(f"\n메일 {len(results)}통 → {args.out / 'outbox'} · 개인정보 노출 합계 {total_leaks}")
    (args.out / "step9.json").write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
