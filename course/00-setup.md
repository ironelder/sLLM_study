# 0단계 — Ollama 설치하고 모델 받기

## 왜 하나요

모델을 내 Mac 안에서 돌려야 문서가 밖으로 안 나가요. Ollama 는 모델 파일을 받아 두고, 내 Mac 안에서만 받는 작은 서버(`127.0.0.1:11434`)를 켜서 질문을 받게 해 주는 프로그램이에요.

## 준비물

| 항목 | 확인 명령 | 기준 |
|---|---|---|
| Mac (Apple 칩) | `uname -m` | `arm64` |
| 메모리 | `sysctl -n hw.memsize` (바이트) | 16GB 권장. 아래 표 참고 |
| 빈 디스크 | `df -h ~` | 6GB 이상 (8단계까지 하면 14GB) |
| Python 3 | `python3 --version` | 3.9 이상 |
| AI 코딩 도구 | Claude Code 등 | 코드 시키기용 |

메모리별 가능 범위

| 메모리 | 4B 모델 (4GB) | 9B 모델 (7.6GB) |
|---|---|---|
| 8GB | 다른 앱을 줄이면 가능할 것 (실측 아님) | 어려움 |
| 16GB (1회차 M1 Pro) | 여유 | 다른 앱을 거의 다 꺼야 함. 1회차에 스왑 21GB, 실행 1번 강제 종료 |
| 32GB 이상 | 여유 | 여유일 것 (실측 아님) |

- Windows·Linux 는 아래 설치 스크립트 대신 Ollama 공식 설치 방법을 쓰고, 서버를 켤 때 환경 변수 `OLLAMA_NO_CLOUD=1` 을 같이 줘요. 1단계부터의 파이썬 코드는 표준 라이브러리만 써서 그대로 돌아가요

## 1. 설치 파일 받기

1회차는 앱이 아니라 GitHub 공식 릴리스의 압축 파일로 설치했어요. 서버를 직접 켜고 끄면서 무엇이 도는지 보이게 하려고요.

1. [Ollama 릴리스 페이지](https://github.com/ollama/ollama/releases)에서 최신 버전을 골라 `ollama-darwin.tgz` 를 받아요
2. 같은 페이지의 그 파일 옆에 적힌 `sha256:` 값을 복사해 둬요 (파일이 중간에 바뀌지 않았는지 확인하는 지문이에요)
3. 받은 파일을 `sLLM_retake/setup/` 에 넣어요

```sh
mkdir -p ~/Project/Study/sLLM_retake/setup
mv ~/Downloads/ollama-darwin.tgz ~/Project/Study/sLLM_retake/setup/
cp ~/Project/Study/sLLM_study/setup/install-ollama.sh ~/Project/Study/sLLM_retake/setup/
```

4. `setup/install-ollama.sh` 의 맨 위 두 줄을 내가 받은 버전으로 고쳐요

```sh
VER=v0.40.16        # ← 받은 버전
SHA=a74371…         # ← 복사한 sha256 값
```

5. `.gitignore` 에 `setup/*.tgz` 도 넣어요 (큰 파일이라 git 에 안 올려요)

## 2. 스크립트 읽고 실행

실행 전에 AI 에게 이렇게 물어봐요.

```text
setup/install-ollama.sh 가 단계마다 무엇을 하는지, 내 컴퓨터의 어느 폴더에 무엇이 생기는지 표로 알려 줘. 실행하지는 마.
```

스크립트가 하는 일

| 단계 | 하는 일 | 생기는 것 |
|---|---|---|
| 1/4 | 받은 파일의 sha256 을 계산해 적어 둔 값과 비교. 다르면 멈춤 | 없음 |
| 2/4 | 압축 풀기 | `~/.local/opt/ollama-<버전>/` |
| 3/4 | 어디서든 `ollama` 로 부를 수 있게 짧은 실행 파일 만들기 | `~/.local/bin/ollama` |
| 4/4 | 서버를 내 Mac 전용 주소로 켜고, 클라우드 기능을 끔 (`OLLAMA_NO_CLOUD=1`) | `~/.ollama/serve.log` (서버 기록) |

실행은 내가 해요.

```sh
cd ~/Project/Study/sLLM_retake
sh setup/install-ollama.sh
```

마지막에 이렇게 나오면 성공이에요.

```
서버 응답: {"version":"…"}
Ollama cloud disabled: true
```

- `ollama: command not found` 가 나오면 `~/.local/bin` 이 PATH 에 없는 거예요. `~/.zshrc` 에 `export PATH="$HOME/.local/bin:$PATH"` 를 넣고 새 터미널을 열어요
- `서버 응답 없음` 이면 `tail -20 ~/.ollama/serve.log` 를 AI 에게 보여 주고 원인을 물어봐요

## 3. 모델 받기

```sh
ollama pull qwen3.5:4b    # 답하는 모델, 약 4GB
ollama pull bge-m3        # 임베딩 모델, 약 1.2GB
ollama list               # 두 개가 보이면 성공
```

- 태그 이름에 `cloud` 가 들어간 모델은 받지 않아요. 그 모델은 내 질문을 외부 서버로 보내요

## 4. 첫 대화

```sh
ollama run qwen3.5:4b --think=false
```

- `--think=false` = 답하기 전에 생각 과정을 길게 쓰는 기능을 끔. 생각 기능이 있는 모델(qwen3.5 등)에서만 의미가 있어요
- 끝내기 = `/bye`
- 다른 터미널에서 `ollama ps` 를 치면 지금 메모리에 올라간 모델과 `PROCESSOR`(GPU 를 쓰는지)가 보여요. 1회차는 `100% GPU`

## 평소에 쓰는 명령

| 할 일 | 명령 |
|---|---|
| 재부팅 뒤 서버 다시 켜기 | `OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 nohup ollama serve > ~/.ollama/serve.log 2>&1 &` |
| 서버 켜졌나 | `curl -s 127.0.0.1:11434/api/version` |
| 클라우드 꺼졌나 | `grep 'Ollama cloud disabled' ~/.ollama/serve.log \| tail -1` → `true` |
| 메모리에 올라간 모델 | `ollama ps` |
| 모델 지우기 | `ollama rm <모델>` |
| 서버 끄기 | `pkill -f 'ollama serve'` |
| 전부 지우기 | 서버를 끈 뒤 `rm -rf ~/.local/opt/ollama-* ~/.local/bin/ollama ~/.ollama` |

## 확인하기 (`내기록.md` 에 적기)

- 설치한 Ollama 버전, 클라우드 꺼짐 `true` 확인
- `ollama ps` 의 `PROCESSOR` 값
- 첫 질문에 답이 나오기까지 걸린 시간 (모델을 메모리에 올리는 시간. 1회차 13초)
