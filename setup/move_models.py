#!/usr/bin/env python3
"""9단계: 인터넷 없는 기기로 Ollama 모델 옮기기 (묶기 → 지문 대조 → 풀기 → blob 지문 확인).

사용:
  python3 setup/move_models.py pack   <묶음.tar> qwen3.5:4b bge-m3 [--models-dir ~/.ollama/models]
  python3 setup/move_models.py unpack <묶음.tar> <풀 폴더>
"""
import argparse
import hashlib
import json
import sys
import tarfile
import time
from pathlib import Path

REGISTRY = "registry.ollama.ai"
CHUNK = 8 * 1024 * 1024


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def manifest_path(models_dir, name):
    repo, _, tag = name.partition(":")
    tag = tag or "latest"
    if "/" not in repo:
        repo = "library/" + repo
    return models_dir / "manifests" / REGISTRY / repo / tag


def blob_path(models_dir, digest):
    # 목록표 표기는 "sha256:…", 디스크 파일 이름은 "sha256-…"
    return models_dir / "blobs" / digest.replace(":", "-")


def referenced_digests(manifest_file):
    m = json.loads(manifest_file.read_text())
    return [m["config"]["digest"]] + [layer["digest"] for layer in m["layers"]]


def gb(n):
    return f"{n / 1e9:.2f}GB"


def pack(args):
    models_dir = Path(args.models_dir).expanduser()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    files = []
    for name in args.models:
        mf = manifest_path(models_dir, name)
        if not mf.exists():
            sys.exit(f"모델 목록표 없음: {name} ({mf}) — ollama list 로 이름 확인")
        digests = referenced_digests(mf)
        size = sum(blob_path(models_dir, d).stat().st_size for d in digests)
        print(f"{name}: blob {len(digests)}개, {gb(size)}")
        files.append(mf)
        files += [blob_path(models_dir, d) for d in digests]
    unique = list(dict.fromkeys(files))
    total = sum(p.stat().st_size for p in unique)
    with tarfile.open(out, "w") as tar:
        for p in unique:
            tar.add(p, arcname=str(p.relative_to(models_dir)))
    packed = time.time()
    digest = sha256_of(out)
    # shasum -a 256 -c 로도 대조되는 형식
    (out.parent / (out.name + ".sha256")).write_text(f"{digest}  {out.name}\n")
    print(f"묶음: {out} — 파일 {len(unique)}개, {gb(total)}, 묶기 {packed - started:.0f}초 + 지문 {time.time() - packed:.0f}초")
    print(f"지문: {digest}")


def safe_members(tar, dest):
    root = dest.resolve()
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if not (member.isfile() or member.isdir()) or root not in target.parents:
            sys.exit(f"이상한 항목이라 멈춤: {member.name}")
        yield member


def unpack(args):
    src = Path(args.tar)
    dest = Path(args.dest)
    sha_file = src.parent / (src.name + ".sha256")
    if not sha_file.exists():
        sys.exit(f"지문 파일 없음: {sha_file}")
    expected = sha_file.read_text().split()[0]

    t0 = time.time()
    actual = sha256_of(src)
    ok = actual == expected
    print(f"① 묶음 지문 {'일치' if ok else '불일치'} ({time.time() - t0:.0f}초)")
    if not ok:
        sys.exit(f"   기대 {expected}\n   실제 {actual}\n옮기는 중에 파일이 바뀌었어요. 풀지 않고 멈춰요")

    t1 = time.time()
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(src) as tar:
        tar.extractall(dest, members=safe_members(tar, dest))
    print(f"② 풀기 완료 → {dest} ({time.time() - t1:.0f}초)")

    t2 = time.time()
    blobs = sorted((dest / "blobs").glob("sha256-*"))
    bad = [b.name for b in blobs if "sha256-" + sha256_of(b) != b.name]
    print(f"③ blob {len(blobs)}개 지문 확인: 일치 {len(blobs) - len(bad)} · 불일치 {len(bad)} ({time.time() - t2:.0f}초)")

    manifests = [p for p in (dest / "manifests").rglob("*") if p.is_file()]
    missing = []
    for mf in manifests:
        missing += [d for d in referenced_digests(mf) if not blob_path(dest, d).exists()]
    names = [f"{p.parent.name}:{p.name}" for p in manifests]
    print(f"④ 모델 {len(manifests)}개({', '.join(names)}) 목록표가 가리키는 blob 빠짐: {len(missing)}")
    if bad or missing:
        sys.exit("확인 실패 — 이 폴더로 서버를 띄우지 마세요")
    print("확인 통과 — OLLAMA_MODELS 를 이 폴더로 두고 서버를 띄우면 돼요")


def main():
    ap = argparse.ArgumentParser(description="Ollama 모델을 tar 하나로 묶고, 지문 대조 후 푸는 도구")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack")
    p.add_argument("out")
    p.add_argument("models", nargs="+")
    p.add_argument("--models-dir", default="~/.ollama/models")
    u = sub.add_parser("unpack")
    u.add_argument("tar")
    u.add_argument("dest")
    args = ap.parse_args()
    pack(args) if args.cmd == "pack" else unpack(args)


if __name__ == "__main__":
    main()
