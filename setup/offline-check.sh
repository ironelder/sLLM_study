#!/bin/sh

# 9단계: 인터넷 끊긴 상태에서 옮긴 모델 폴더로 VOC 흐름을 메일 발송까지 확인
# 사용: Wi-Fi 끄고 sh setup/offline-check.sh · Wi-Fi 둔 채 밖만 막기: --sandbox
set -u
cd "$(dirname "$0")/.."
BIN="$HOME/.local/opt/ollama-v0.40.16/ollama"
MODELS="$PWD/private/offline/models"
OUT="results/step9-offline-$(date +%Y%m%d-%H%M%S)"
RUN=""
MODE="Wi-Fi 끔"
if [ "${1:-}" = "--sandbox" ]; then
  RUN="sandbox-exec -f setup/no-network.sb"
  MODE="샌드박스"
fi
mkdir -p "$OUT"

restore() {
  pkill -f 'mail_sink.py --port 2525'
  pkill -f 'ollama-v0.40.16/ollama serve'
  sleep 2
  OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 nohup "$BIN" serve > "$HOME/.ollama/serve.log" 2>&1 &
  wait_ready && echo "정리: 메일 받는 쪽·오프라인 서버 끄고 원래 서버(~/.ollama/models) 다시 켬"
}

wait_ready() {
  for _ in $(seq 1 30); do
    curl -s -m 1 http://127.0.0.1:11434/api/version > /dev/null && return 0
    sleep 1
  done
  return 1
}

main() {
  if $RUN curl -s -m 5 -o /dev/null https://example.com; then
    echo "인터넷이 연결돼 있어요. Wi-Fi 를 끄고 다시 실행해요 (Wi-Fi 를 둔 채 하려면 --sandbox)"
    exit 1
  fi
  echo "① 인터넷 차단 확인($MODE): example.com 연결 실패"

  [ -d "$MODELS/manifests" ] || { echo "옮긴 모델 폴더가 없어요 — python3 setup/move_models.py unpack 먼저"; exit 1; }
  touch "$OUT/.server-swapped"
  pkill -f 'ollama-v0.40.16/ollama serve'
  sleep 2
  OLLAMA_MODELS="$MODELS" OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 $RUN "$BIN" serve > "$OUT/serve.log" 2>&1 &
  wait_ready || { echo "오프라인 서버가 30초 안에 안 켜졌어요 — $OUT/serve.log 확인"; exit 1; }
  echo "② 옮긴 모델 폴더로 서버 켬: $(grep -o 'OLLAMA_MODELS:[^ ]*' "$OUT/serve.log" | head -1) · $(grep -o 'Ollama cloud disabled: [a-z]*' "$OUT/serve.log" | tail -1)"
  OLLAMA_HOST=127.0.0.1:11434 "$BIN" list

  DIM=$($RUN curl -s http://127.0.0.1:11434/api/embed -d '{"model":"bge-m3","input":"결제가 실패했어요"}' \
    | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["embeddings"][0]))')
  echo "③ 임베딩 모델 동작: ${DIM}차원"

  $RUN python3 mail_sink.py --port 2525 --out "$OUT/inbox" > "$OUT/sink.log" 2>&1 &
  sleep 1
  echo "④ VOC 흐름 (가상 티켓 6건)"
  $RUN python3 step9_voc.py samples/voc/tickets.json samples/voc/logs.jsonl "$OUT" \
    --expected samples/voc/expected.json --smtp 127.0.0.1:2525
  sleep 1
  echo "⑤ 메일 받는 쪽이 받은 메일: $(ls "$OUT/inbox" 2>/dev/null | wc -l | tr -d ' ')통"
  grep '^받음' "$OUT/sink.log"
  echo "결과 폴더: $OUT"
}

# 파이프 안 함수의 trap EXIT 는 macOS sh 에서 안 불려서 정리는 파이프 밖에서 부름
main "$@" 2>&1 | tee "$OUT/check.txt"
if [ -f "$OUT/.server-swapped" ]; then
  restore 2>&1 | tee -a "$OUT/check.txt"
fi
