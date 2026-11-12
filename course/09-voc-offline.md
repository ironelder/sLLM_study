# 9단계 — 분리망 가정: 모델 옮기기 + 가상 VOC 처리 흐름 (응용)

## 왜 하나요

RAG 를 업무 모양으로 넓혀 봐요. **인터넷이 없는 망에 모델을 들여가서**, 고객 문의(VOC) 티켓을 읽고 → 그 고객 로그를 찾고 → 개인정보를 가리고 → 요약해서 → 메일로 보내요. 데이터는 전부 **가상**이에요. 실제 고객 정보는 절대 쓰지 않아요.

먼저 짐작해서 적어요: "4B 모델이 '어제 밤 9시'·'이번 주 월요일'을 정확한 날짜로 바꿀 수 있을까?", "원인이 로그에 있는지 없는지 판단할 수 있을까?"

## 만들 것

| 파일 | 하는 일 |
|---|---|
| `setup/move_models.py` | 모델 파일을 tar 하나로 묶고 지문(sha256) 파일 만들기 / 지문 대조 후 풀기 |
| `samples/voc/` | 가상 티켓(Jira 응답 모양)·가상 로그·정답표 |
| `step9_voc.py` | 해석 → 로그 조회 → 가림 → 요약 → 메일 |
| `mail_sink.py` | 이 기기 안에서만 메일을 받는 시험용 서버 |
| `setup/no-network.sb`·`setup/offline-check.sh` | 밖으로 나가는 연결을 막고 전체를 한 번에 확인 |

## AI 에게 줄 말 1: 모델 옮기기

```text
setup/move_models.py 를 만들어줘. 표준 라이브러리만, Python 3.9 문법.
- pack <묶음.tar> <모델 이름…>: ~/.ollama/models/manifests/registry.ollama.ai/library/<이름>/<태그> 목록표를 읽고,
  거기 적힌 config·layers 의 digest 파일(blobs/sha256-<값>, 목록표의 ':' 가 파일 이름에선 '-')만 골라 tar 하나로 묶어.
  압축은 하지 마. 묶은 뒤 sha256 을 계산해 "<지문>  <파일 이름>" 형식으로 <묶음.tar>.sha256 에 써
- unpack <묶음.tar> <풀 폴더>: ① 묶음 지문 대조(다르면 풀지 말고 멈춤) ② 풀기(폴더 밖으로 나가는 경로면 멈춤)
  ③ blob 마다 sha256 을 다시 계산해 파일 이름과 같은지 ④ 목록표가 가리키는 blob 이 다 있는지. 단계마다 걸린 초를 출력
```

```sh
mkdir -p private/offline
python3 setup/move_models.py pack private/offline/models.tar qwen3.5:4b bge-m3
python3 setup/move_models.py unpack private/offline/models.tar private/offline/models
```

- 대조군도 해 봐요: 묶음 끝에 글자 하나를 붙이면(`printf x >> 사본.tar`) ①에서 멈추나
- 압축하면 얼마나 줄까? `gzip -6 -c private/offline/models.tar | wc -c` 로 직접 재 봐요 (1회차: 14% 줄고 226초)

## AI 에게 줄 말 2: 가상 데이터

```text
samples/voc/ 에 가상 데이터를 만들어줘. 회사·제품 이름은 쓰지 말고, 이메일은 example.com, 전화는 010-0000-xxxx.
- tickets.json: Jira 검색 API 응답 모양 {"issues": [{"key": "VOC-101", "fields": {"summary", "description", "created": "2026-11-10T10:12:00.000+0900"}}]}
  6건. description 은 상담 메모처럼, 회원번호(C-6자리)와 "어제 밤 9시쯤" 같은 상대 시각을 넣어.
  어려운 경우 3개 포함: 회원번호 없는 티켓, 회원번호는 있는데 관련 로그가 없는 티켓, 같은 시각 다른 고객의 오류 로그
- logs.jsonl: 한 줄에 {"ts", "customer", "device", "event", "code", "detail"}. 몇 줄은 detail 에 전화·이메일을 넣어 (가리기 시험용)
- expected.json: 티켓마다 정답 분류, 발생 시각(또는 날짜), 원인이 되는 로그의 코드, 원인이 로그에 있나(true/false)
```

## AI 에게 줄 말 3: VOC 흐름

```text
step9_voc.py 를 만들어줘. 표준 라이브러리만.
- 실행: python3 step9_voc.py <티켓.json> <로그.jsonl> <출력 폴더> [--expected 정답.json] [--smtp 127.0.0.1:2525]
- 회원번호·전화·이메일·이름은 정규식으로 뽑고, 모델에 넣기 전에 가려 (C-10****, 010-****-1111, k***@example.com)
- 해석: /api/chat 에 format 으로 JSON 스키마를 줘서 category(정해진 목록)·symptom·occurred_at('YYYY-MM-DD HH:MM')·urgency 를 받아.
  접수 시각과 요일을 같이 주고, 결과 시각이 형식에 안 맞거나 접수보다 뒤면 버려
- 로그 조회는 코드로: 같은 회원번호 + (발생 시각 12시간 전 ~ 접수 시각), 모르면 접수 72시간 전부터. 로그에 L1, L2 번호를 붙여
- 요약: JSON 스키마로 summary(문장마다 [L번호])·cause_found(참/거짓)·next_action 을 받아
- 자동 확인: 인용 번호가 실제 줄인지, 요약 속 오류 코드(대문자_대문자)가 로그에 있는지, 메일 본문에 가리지 않은 개인정보가 있는지
- 메일: email.message.EmailMessage 로 만들어 출력 폴더/outbox/<티켓>.eml 저장, --smtp 를 주면 smtplib 로 발송
- --expected 를 주면 티켓마다 O/X 와 항목별 합계를 출력
```

```text
mail_sink.py 를 만들어줘. socketserver 로 127.0.0.1 에서만 받는 최소 SMTP 서버.
HELO/EHLO/MAIL/RCPT 에는 250, DATA 는 '.' 한 줄까지 받아 폴더에 001.eml 처럼 저장하고 제목을 출력. smtpd 모듈은 쓰지 마(3.12 에서 없어짐)
```

## 직접 실행

```sh
python3 mail_sink.py --port 2525 --out results/step9/inbox      # 터미널 하나 더 열어서
python3 step9_voc.py samples/voc/tickets.json samples/voc/logs.jsonl results/step9 --expected samples/voc/expected.json --smtp 127.0.0.1:2525
```

마지막으로 **Wi-Fi 를 끄고** 전체를 한 번에 확인해요 (유선 랜이 꽂혀 있으면 그것도 빼요).

```sh
sh setup/offline-check.sh            # Wi-Fi 끈 상태
sh setup/offline-check.sh --sandbox  # Wi-Fi 를 둔 채 밖으로 나가는 연결만 막기 (macOS)
```

- 스크립트가 하는 일: 인터넷 끊김 확인 → 원래 서버 끄기 → 옮긴 폴더로 서버 켜기 → 모델 목록·임베딩 확인 → 메일 받는 쪽 켜기 → VOC 흐름 → 받은 메일 수 → 원래 서버 다시 켜기
- 실행 전에 스크립트를 열어 줄마다 무엇을 하는지 먼저 읽어요

## 확인하기 (`내기록.md` 에 적기)

| 항목 | 1회차 | 내 값 |
|---|---|---|
| 묶음 크기·묶기 시간 | 5.13GB · 9초 | |
| gzip 압축 시 | 4.40GB (14% 줄어듦) · 226초 | |
| blob 지문 일치 | 738/738 | |
| 분류 (고칠 때 본 6건 / 새 20건) | 6/6 / 17/20 | |
| 발생 시각 (6건 / 20건) | 3/4 / 7/15 | |
| 원인 확인 여부 (6건 / 20건) | 4/4 / 18/18 | |
| 지어낸 코드 · 개인정보 노출 | 0 · 0 | |
| 메일 발송 → 받음 | 6 → 6 | |

### 처음 보는 데이터로 한 번 더

고치면서 본 티켓으로 잰 점수는 부풀려져요(과적합). 다 고쳤으면 **새 AI 대화창**(지금까지 대화를 모르는 쪽)에게 같은 형식으로 새 티켓 20건을 만들게 하고, 코드는 그대로 둔 채 **한 번만** 재요.

```text
samples/voc-holdout/ 에 가상 VOC 평가 데이터 20건을 만들어줘. step9_voc.py 와 samples/voc/ 는 읽지 마.
형식은 tickets.json(Jira 응답 모양)·logs.jsonl·expected.json(category·occurred_at 또는 occurred_date·key_codes·cause·no_customer).
보통 11건, 로그는 있지만 원인 기록이 없는 4건, 회원번호 없는 2건, 함정 3건(같은 시각 다른 고객 오류, 원인이 여러 줄, 고객 주장과 실제 원인이 다름)
```

```sh
python3 step9_voc.py samples/voc-holdout/tickets.json samples/voc-holdout/logs.jsonl results/step9-holdout --expected samples/voc-holdout/expected.json
```

- 1회차: 발생 시각이 6건 3/4 → 새 20건 7/15 로 떨어졌어요. 원인 판단은 18/18 로 유지

## 코드에서 꼭 읽을 곳

1. 가리기를 모델 호출 **전에** 하는 부분 — 왜 이 순서면 메일에 개인정보가 나갈 수 없나
2. 요약 JSON 스키마의 칸 순서 — summary 가 cause_found 보다 앞에 있는 이유
3. `move_models.py` 의 ③ blob 지문 확인 — 묶음 지문만으로는 왜 모자라나 (풀다가 깨질 수 있음)

## 고쳐 보기

| 바꿀 것 | 짐작 먼저 | 확인 |
|---|---|---|
| `--no-calendar` (해석 지시에서 최근 7일 달력 빼기) | 발생 시각이 몇 개 틀릴까? | 발생 시각 점수 |
| 요약 스키마 칸 순서를 cause_found 먼저로 | 원인 판단이 달라질까? | 원인 확인 여부 점수 |
| 가리기를 모델 호출 **뒤로** 옮기기 | 메일에 개인정보가 남을까? | 개인정보 노출 수 |

## 1회차와 비교

- 1회차 정리: [`../notes/step9.md`](../notes/step9.md) — 실제로 한 것과 가정한 것 표, 고쳐 가며 잰 숫자, 정리 스크립트 실수
- 1회차 결론: 틀리면 안 되는 일(식별자·조회·가림·검증)은 코드, 해석·요약은 모델. 판단은 문장이 아니라 JSON 칸으로, 칸 순서는 "근거 → 판단"
