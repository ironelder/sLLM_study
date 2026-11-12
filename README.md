# sLLM_study — sLLM·RAG 개인 학습

내 Mac 에서 작은 언어 모델(sLLM)을 돌리고, 내 문서 폴더에 묻는 RAG 를 직접 만들어 보는 개인 공부 저장소예요(2026-11-11 시작).

- **다시 해 보기(재수강)** = [`course/README.md`](course/README.md) — 다른 기기에서 내가 직접 설치하고, AI 에게 코드를 시키며 8단계를 따라가는 교재. 이 저장소의 `step*.py` 는 정답지

## 지킬 것

- 회사·개인 문서 원문, 임베딩 결과, 개인 질문, 실험 결과는 `private/`·`results/`(git 제외)에만 둬요. GitHub 에는 범용 코드와 정리 노트(`notes/`)만 올려요
- 임베딩 벡터에서도 원문 일부를 되살릴 수 있어서 원문과 같은 등급으로 다뤄요
- Ollama 모델은 로컬 태그만 써요. `cloud` 가 붙은 태그(`gemma4:cloud` 등)는 질문을 외부 서버로 보내니 쓰지 않아요. `ollama signin` 도 하지 않아요
- 서버는 `OLLAMA_NO_CLOUD=1` 로 켜요

## 구성

| 역할 | 선택 |
|---|---|
| 실행 도구 | Ollama v0.40.16 CLI (`setup/install-ollama.sh`) |
| 답하는 sLLM | `qwen3.5:4b` (3.3~4.0GB). 비교 후보 `qwen3:4b`(2.5GB)·`gemma4:e4b` |
| 임베딩 | `bge-m3` (1.2GB, 입력 8192토큰) |
| 코드 | Python 표준 라이브러리만. 10단계 FAISS 비교만 `.venv`(Python 3.11)에 `faiss-cpu`·`numpy` (`setup/requirements-faiss.txt`) |
| 벡터 저장·찾기 | 벡터 DB 없이 직접 구현 — 길이 1로 맞춘 벡터를 `vectors.f32` 에 저장하고 질문과 전부 내적. 10단계에서 FAISS Flat·HNSW 와 비교 |
| 키워드 찾기 | 기존에 쓰던 BM25 키워드 검색 도구와 비교 |

## 단계

| 단계 | 할 일 | 볼 것 |
|---|---|---|
| 1 | Ollama 설치, sLLM 과 대화, 모르는 질문에 지어내는지 확인 | 한국어 품질, 초당 토큰, GPU 사용 |
| 2 | 문서 1편 붙여 질문 vs 안 붙이고 질문 | 붙이면 맞히는지 |
| 3 | 문서 폴더를 헤딩 단위로 자르고 bge-m3 임베딩 + 가까운 조각 5개 찾기 | 조각 수, 첫 색인 시간 |
| 4 | 기존 시험지로 recall@5 채점 → 키워드 검색과 비교 | 바꿔 말한 질문에서 얼마나 오르나 |
| 5 | 키워드 검색 + 임베딩 섞기(RRF), 리랭킹 선택 | 4단계 대비 상승 |
| 6 | 조각 + 출처 번호로 sLLM 답 생성, "없으면 모른다" 지시, 답 채점 | 지어내는 비율 |
| 7 | 조각에 프로젝트 이름표, "다른 프로젝트 자료는 쓰지 마" 지시 | 위험한 답·잃은 정답 |
| 8 | 같은 비교를 9B 모델로 | 위험한 답, 속도, 메모리 |
| 9 | 분리망 가정: 모델을 묶어 옮기고 인터넷 없이 띄우기 + 가상 VOC 티켓 해석 → 고객 로그 조회 → 개인정보 가림 → 요약 → 메일 | 원인 판단, 개인정보 노출, 인터넷 없이 동작 |
| 10 | 직접 만든 벡터 찾기를 FAISS(Flat·HNSW)와 비교, 20만 개로 불려 규모 시험 | recall 같은가, 찾기 시간, HNSW 정확도 |

단계별 정리 = `notes/`.

## 지금까지 결과 (2026-11-11, `qwen3.5:4b` · `bge-m3` · M1 Pro 16GB)

| 단계 | 핵심 숫자 | 한 줄 |
|---|---|---|
| 1 문서 없이 질문 | 초당 약 40토큰, 첫 로딩 13초 | 회사 내부 질문엔 지어내거나 관례로 찍음 |
| 2 정답 문서 붙이기 | 6건 중 지어내기 0 | 표현이 다르면(질문 말 ≠ 문서 말) 정답 문서가 있어도 판단 보류 |
| 3 조각내기·임베딩 | 474편 → 6,855조각, 색인 689초, 찾기 0.4초 | 바꿔 말한 질문은 임베딩, 숫자 코드는 키워드가 잘 찾음 |
| 4 시험지 채점 | 바꿔 말함 recall@5: 키워드 1회 0/10 → 임베딩 1회 6/10 | AI 가 검색어를 바꿔 가며 찾는 방식(9/10)이 여전히 최고 |
| 5 섞어 찾기(RRF) | 바꿔 말함 recall@5 6 → 4 | 한쪽이 자신 있게 틀리면 섞기가 손해 |
| 6 찾기+답하기 | 22문항: 찾기 성공·답함 15, 안전한 거절 4, 위험 3 | 가장 위험 = 비슷하지만 다른 대상의 조각으로 자신 있게 틀림 |
| 7 조각에 프로젝트 이름표 | 위험한 답 2 → 이름표만 3 → 이름표+확인 지시 1, 잃은 정답 0 → 1 | 이름표는 찾기를 끌어오지만, 답에 효과를 내려면 '이름표로 걸러라' 지시가 필요 |
| 8 4B vs 9B | 위험한 답 4B 2 → 9B 0, 문항당 7초 → 27초 | 큰 모델은 이름표 없이도 다른 대상을 알아챔. 대신 느리고 16GB 에서 메모리 빠듯, 문서 없이는 더 그럴듯하게 지어냄 |
| 9 분리망 가정 VOC (11-12) | 모델 5.13GB tar 이동·blob 지문 738/738, 외부 차단 상태 메일 발송. 고칠 때 안 본 새 가상 티켓 20건: 원인 판단 18/18·분류 17/20·핵심 로그 13/14·발생 시각 7/15·개인정보 노출 0 | 식별자·조회·가림·검증은 코드, 해석·요약은 모델. 판단은 JSON 칸으로 받고 "요약 먼저, 판단 나중". 4B 는 상대 날짜 계산이 약함 → 코드로 해야 함 |
| 10 FAISS 비교 (11-12) | 찾기 1회: 파이썬 243ms → numpy·FAISS Flat 약 1ms → HNSW 0.3ms, recall 4가지 모두 같음, RAG 4칸 같음. 20만 개: 파이썬 약 7초(추정) → HNSW 9ms·정확도 90% | 이 규모에선 느린 원인이 파이썬 for 문이라 numpy 로 충분. FAISS 는 수십만 개 이상에서 의미, HNSW 는 근사라 정확도를 같이 재야 함 |

## 실행

- 질문 실험: `python3 step1_chat.py [모델]` — `private/questions.json`(`[["라벨", "질문"], …]`)이 있으면 그 질문, 없으면 공개 예시
- 문서 붙이기 실험: `python3 step2_attach.py [모델]` — `private/step2.json`(지시·문서·질문 묶음)이 있으면 그 설정, 없으면 공개 예시(가상의 도서관 공지)
- 색인 만들기: `python3 step3_index.py --root <문서 루트> [--dirs docs tools] [--projects <이름표.json>] [--same-files-as <기존 색인>] [--out <폴더>]` → 기본 `private/index/` (git 제외)
- 임베딩 찾기: `python3 step3_search.py [-k 5] "질문" …` — 질문을 안 주면 `private/step3_queries.json`
- 시험지 채점: `python3 step4_eval.py <시험지.json> <결과.json>` — 임베딩 검색의 문서 순위로 recall@1·@5 (시험지는 `private/`)
- 섞어 찾기 채점: `python3 step5_hybrid.py <시험지.json> <결과.json> --keyword-cmd "<BM25 검색 명령 --json>" [--rrf-k 60] [--kw-weight 1.0]`
- 실행 결과 비교: `python3 compare_runs.py 이름=결과.json [이름=결과.json …] [--no-answer-ids N1]` — 같은 거절 판정으로 다시 세고 칸이 다른 문항을 나란히
- 찾기+답하기: `python3 step6_rag.py <결과.json> <시험지.json> [<시험지.json> …] [--model qwen3.5:4b] [-k 5] [--index <색인>] [--check-project]`
- 모델 옮기기: `python3 setup/move_models.py pack <묶음.tar> qwen3.5:4b bge-m3` → `python3 setup/move_models.py unpack <묶음.tar> <풀 폴더>` (지문 대조)
- VOC 흐름: `python3 step9_voc.py samples/voc/tickets.json samples/voc/logs.jsonl <출력 폴더> [--expected samples/voc/expected.json] [--smtp 127.0.0.1:2525]` — 시험용 메일 받는 쪽 `python3 mail_sink.py --port 2525`
- FAISS 비교: `.venv/bin/python step10_faiss.py <시험지.json> <결과.json> [--scale 200000]` — RAG 를 FAISS 로: `.venv/bin/python step6_rag.py … --faiss hnsw` (설치 = `course/10-faiss.md`)
- 인터넷 없이 전체 확인: Wi-Fi 끄고 `sh setup/offline-check.sh` (또는 `--sandbox` 로 밖으로 나가는 연결만 차단). 옮긴 모델 폴더 = `private/offline/models`

## Ollama 다루기

- 설치·기동: `sh setup/install-ollama.sh` (설치 파일 `setup/ollama-darwin.tgz` 는 git 제외 — [GitHub 릴리스](https://github.com/ollama/ollama/releases/tag/v0.40.16)에서 받아 같은 폴더에 두면 스크립트가 sha256 대조)
- 재부팅 뒤 서버 다시 켜기: `OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 nohup ollama serve > ~/.ollama/serve.log 2>&1 &`
- 클라우드 꺼짐 확인: `grep 'Ollama cloud disabled' ~/.ollama/serve.log | tail -1` → `true`
- 대화: `ollama run qwen3.5:4b --think=false` (끝내기 `/bye`)
- 끄기: `pkill -f 'ollama-v0.40.16/ollama serve'`
- 지우기: 끈 뒤 `rm -rf ~/.local/opt/ollama-v0.40.16 ~/.local/bin/ollama ~/.ollama`
