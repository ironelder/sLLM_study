#!/usr/bin/env python3
"""9단계 시험용: 이 기기(127.0.0.1)에서만 받는 최소 SMTP 서버. 받은 메일을 폴더에 .eml 로 저장한다.

사용: python3 mail_sink.py [--port 2525] [--out results/step9/inbox]   (끄기: Ctrl+C)
"""
import argparse
import email
import socketserver
from email.header import decode_header, make_header
from pathlib import Path


class Handler(socketserver.StreamRequestHandler):
    def reply(self, line):
        self.wfile.write((line + "\r\n").encode())

    def handle(self):
        self.reply("220 local mail sink")
        while True:
            line = self.rfile.readline()
            if not line:
                return
            cmd = line.decode(errors="replace").strip().upper()
            if cmd.startswith("DATA"):
                self.reply("354 end with <CRLF>.<CRLF>")
                data = []
                while True:
                    row = self.rfile.readline()
                    if row in (b".\r\n", b".\n", b""):
                        break
                    # 보내는 쪽은 줄 앞 '.' 을 '..' 로 바꿔 보냄
                    data.append(row[1:] if row.startswith(b"..") else row)
                self.server.save(b"".join(data))
                self.reply("250 saved")
            elif cmd.startswith("QUIT"):
                self.reply("221 bye")
                return
            else:
                self.reply("250 ok")


class Sink(socketserver.TCPServer):
    allow_reuse_address = True

    def __init__(self, port, out):
        super().__init__(("127.0.0.1", port), Handler)
        self.out = out
        self.count = 0

    def save(self, raw):
        self.count += 1
        subject = str(make_header(decode_header(email.message_from_bytes(raw).get("Subject", ""))))
        (self.out / f"{self.count:03d}.eml").write_bytes(raw)
        print(f"받음 {self.count}: {subject}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=2525)
    ap.add_argument("--out", type=Path, default=Path("results/step9/inbox"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with Sink(args.port, args.out) as server:
        print(f"메일 받는 중: 127.0.0.1:{args.port} → {args.out}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
