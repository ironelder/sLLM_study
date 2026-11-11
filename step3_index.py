#!/usr/bin/env python3
"""3단계: 문서 폴더의 md 를 헤딩 단위 조각으로 자르고 bge-m3 로 임베딩해 색인을 만든다.

사용: python3 step3_index.py --root <문서 루트> [--dirs docs tools] [--out private/index] [--dry-run]
읽는 범위: <root>/<dirs>/**/*.md, 점(.)으로 시작하는 폴더와 `.kb-mirror` 표식 폴더 아래는 제외
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from array import array
from pathlib import Path

API = "http://127.0.0.1:11434/api/embed"
MODEL = "bge-m3"
MIRROR_MARKER = ".kb-mirror"
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
MAX_CHARS = 1200
MIN_BODY = 20
BATCH = 32


def scan(root, dirs):
    files, mirror_skipped = [], 0
    for top in dirs:
        mirror_dirs = set()
        for base, subdirs, names in os.walk(os.path.join(root, top)):
            subdirs[:] = sorted(d for d in subdirs if not d.startswith("."))
            mirror = MIRROR_MARKER in names or os.path.dirname(base) in mirror_dirs
            if mirror:
                mirror_dirs.add(base)
            for name in sorted(names):
                if not name.endswith(".md"):
                    continue
                if mirror:
                    mirror_skipped += 1
                    continue
                files.append(os.path.join(base, name))
    return files, mirror_skipped


def strip_frontmatter(lines):
    if not lines or lines[0].strip() != "---":
        return {}, 0
    meta = {}
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            return meta, i + 1
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip().strip("\"'")
    return {}, 0


def split_long(body):
    """MAX_CHARS 를 넘는 절은 빈 줄 단위 문단으로 나눠 붙인다."""
    if len(body) <= MAX_CHARS:
        return [body]
    pieces, cur = [], ""
    for para in re.split(r"\n\s*\n", body):
        if cur and len(cur) + len(para) + 2 > MAX_CHARS:
            pieces.append(cur)
            cur = ""
        cur = f"{cur}\n\n{para}" if cur else para
        while len(cur) > MAX_CHARS:
            pieces.append(cur[:MAX_CHARS])
            cur = cur[MAX_CHARS:]
    if cur:
        pieces.append(cur)
    return pieces


def chunk_doc(rel, text):
    lines = text.split("\n")
    meta, start = strip_frontmatter(lines)
    title = meta.get("title") or next((x[2:].strip() for x in lines[start:] if x.startswith("# ")), rel)
    keywords = meta.get("keywords", "")
    sections, path, cur_line, cur_body, in_fence = [], [], start + 1, [], False

    def flush():
        body = "\n".join(cur_body).strip()
        if len(body) >= MIN_BODY:
            sections.append((cur_line, " > ".join(path), body))

    for i, line in enumerate(lines[start:], start + 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
        m = None if in_fence else HEADING_RE.match(line)
        if m:
            flush()
            level = len(m.group(1))
            path = path[: level - 1] + [m.group(2).strip()]
            cur_line, cur_body = i, []
        else:
            cur_body.append(line)
    flush()

    chunks = []
    for line_no, heading, body in sections:
        for piece in split_long(body):
            prefix = f"문서: {title}\n" + (f"키워드: {keywords}\n" if keywords else "") + (f"절: {heading}\n" if heading else "")
            chunks.append({"path": rel, "line": line_no, "heading": heading, "text": prefix + piece})
    return chunks


def embed(texts):
    body = json.dumps({"model": MODEL, "input": texts}).encode()
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as res:
        return json.load(res)["embeddings"]


def normalize(vec):
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--dirs", nargs="+", default=["docs", "tools"])
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "private" / "index"))
    ap.add_argument("--dry-run", action="store_true")
    opts = ap.parse_args()

    root = os.path.expanduser(opts.root)
    files, mirror_skipped = scan(root, opts.dirs)
    chunks, unreadable = [], 0
    for path in files:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            unreadable += 1
            continue
        chunks.extend(chunk_doc(os.path.relpath(path, root), text))

    sizes = sorted(len(c["text"]) for c in chunks)
    print(f"문서 {len(files)}편 (미러 제외 {mirror_skipped}, 읽기 실패 {unreadable}) → 조각 {len(chunks)}개")
    if sizes:
        print(f"조각 글자 수: 중앙값 {sizes[len(sizes) // 2]}, 90% {sizes[int(len(sizes) * 0.9)]}, 최대 {sizes[-1]}, 합계 {sum(sizes):,}")
    if opts.dry_run:
        return

    out = Path(opts.out)
    out.mkdir(parents=True, exist_ok=True)
    vectors = array("f")
    t0 = time.time()
    for i in range(0, len(chunks), BATCH):
        for vec in embed([c["text"] for c in chunks[i : i + BATCH]]):
            vectors.extend(normalize(vec))
        done = min(i + BATCH, len(chunks))
        if done % (BATCH * 20) == 0 or done == len(chunks):
            print(f"  임베딩 {done}/{len(chunks)} ({time.time() - t0:.0f}초)", flush=True)
    elapsed = time.time() - t0

    dim = len(vectors) // len(chunks)
    with open(out / "vectors.f32", "wb") as f:
        vectors.tofile(f)
    with open(out / "chunks.jsonl", "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    meta = {"model": MODEL, "dim": dim, "count": len(chunks), "docs": len(files), "seconds": round(elapsed, 1),
            "max_chars": MAX_CHARS, "built": time.strftime("%Y-%m-%d %H:%M")}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"완료: {len(chunks)}개 × {dim}차원, {elapsed:.0f}초 (초당 {len(chunks) / elapsed:.1f}개) → {out}")


if __name__ == "__main__":
    sys.exit(main())
