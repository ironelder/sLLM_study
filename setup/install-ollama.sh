#!/bin/sh
# Ollama v0.40.16 CLI(GitHub 공식 tgz)를 sha256 대조 후 ~/.local 에 설치, 서버는 127.0.0.1 전용으로 기동
set -eu

VER=v0.40.16
SHA=a743717494315da7cd352982b805f6b992d4b4452ca117fd5fbf86c4ee46fca0
HERE=$(cd "$(dirname "$0")" && pwd)
TGZ="$HERE/ollama-darwin.tgz"
DEST="$HOME/.local/opt/ollama-$VER"
BIN="$HOME/.local/bin/ollama"

echo "[1/4] sha256 대조"
echo "$SHA  $TGZ" | shasum -a 256 -c -

echo "[2/4] 압축 풀기 → $DEST"
mkdir -p "$DEST"
tar -xzf "$TGZ" -C "$DEST"

echo "[3/4] 래퍼 생성 → $BIN"
mkdir -p "$HOME/.local/bin"
cat > "$BIN" <<EOF
#!/bin/sh
exec "$DEST/ollama" "\$@"
EOF
chmod +x "$BIN"

echo "[4/4] 서버 기동 (127.0.0.1:11434)"
mkdir -p "$HOME/.ollama"
if lsof -nP -iTCP:11434 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "11434 포트가 이미 사용 중 — 기동 생략"
else
  OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 nohup "$DEST/ollama" serve > "$HOME/.ollama/serve.log" 2>&1 &
fi

# 첫 기동은 키 생성·GPU 탐색으로 3초를 넘김(11-11 실측) → 최대 30초 대기
i=0
until curl -s -m 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1; do
  i=$((i + 1))
  [ "$i" -ge 30 ] && { echo "서버 응답 없음 — ~/.ollama/serve.log 확인"; exit 1; }
  sleep 1
done
printf '서버 응답: '
curl -s http://127.0.0.1:11434/api/version
echo
grep -o 'Ollama cloud disabled: [a-z]*' "$HOME/.ollama/serve.log" | tail -1
"$BIN" --version
