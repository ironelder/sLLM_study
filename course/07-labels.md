# 7단계 — 조각에 프로젝트 이름표 붙이기

## 왜 하나요

6단계에서 가장 위험한 답은 **비슷하지만 다른 대상의 조각**을 보고 자신 있게 틀린 경우였어요. 조각만 떼어 보면 어느 프로젝트(어느 폴더) 문서인지 모르기 때문이라고 보고, 조각 맨 앞에 "프로젝트: …" 줄을 붙여요. 그리고 세 가지를 같은 질문으로 비교해요.

| 실행 | 색인 | 지시 |
|---|---|---|
| 기존 | 6단계 색인 | 6단계 그대로 |
| 이름표만 | 이름표 붙인 새 색인 | 6단계 그대로 |
| 이름표 + 확인 지시 | 이름표 붙인 새 색인 | "프로젝트가 다르면 그 자료는 근거로 쓰지 마" 추가 |

먼저 짐작해서 적어요: "이름표만 붙여도 위험한 답이 줄까?"

## 준비: 함정 만들기 (내 문서에 비슷한 대상이 없을 때)

1. `private/corpus/` 안에 폴더 두 개를 만들어요 (예: `작년규칙/`·`올해규칙/`)
2. 문서 하나를 두 폴더에 복사하고, 한쪽만 사실 하나를 바꿔요 (예: 마감일, 담당 이름, 버전 번호)
3. 6단계 `extra.json` 에 질문을 하나 더해요: 한쪽 대상을 콕 집어 묻는 질문 (정답 = 그쪽 문서)
4. 3단계 색인을 다시 만들고 6단계 기존 실행도 다시 해 둬요 (같은 문서로 비교해야 공정해요)

이름표 표 `private/projects.json` — 경로 앞부분 → 이름

```json
{
  "작년규칙/": "2025년 동아리 규칙",
  "올해규칙/": "2026년 동아리 규칙",
  "공부/": "개인 공부 노트"
}
```

## AI 에게 줄 말 1: 색인에 이름표

```text
step3_index.py 에 옵션 두 개를 추가해줘.
- --projects <이름표.json>: {"경로 앞부분": "이름"} 표. 조각 path 가 가장 길게 맞는 앞부분의 이름을 쓰고,
  표에 없으면 최상위 폴더 이름을 써. 주면 조각 앞머리 맨 앞에 "프로젝트: 이름\n" 줄을 붙이고 조각 정보에 "project" 칸을 추가
- --same-files-as <기존 색인 폴더>: 그 색인의 chunks.jsonl 에 있는 path 들만 다시 색인 (비교 실험용)
- meta.json 에 "projects": true/false 추가
- 옵션을 안 주면 지금과 똑같이 동작해야 해
```

## AI 에게 줄 말 2: 답하기에 이름표와 확인 지시

```text
step6_rag.py 를 고쳐줘.
- 조각에 project 칸이 있으면 사용자 메시지의 자료 줄을 "[n] 프로젝트: 이름 · 출처: 경로 > 헤딩" 으로
- --check-project 옵션: 주면 system 지시 끝에 " 자료마다 붙은 프로젝트가 질문이 묻는 대상과 다르면 그 자료는 근거로 쓰지 마." 를 붙여
- 옵션을 안 주고 project 칸도 없으면 지금과 똑같이 동작해야 해
```

## AI 에게 줄 말 3: 실행 결과 비교기

```text
compare_runs.py 를 만들어줘.
- 실행: python3 compare_runs.py 이름=결과.json [이름=결과.json …] [--no-answer-ids N1,…]
- step6_rag.py 의 is_refusal 을 import 해서, 모든 결과를 같은 거절 판정으로 다시 칸을 나눠
  (실행 때 판정이 달랐어도 공정하게 비교하려고). --no-answer-ids 의 문항은 "답 없는 질문 · 거절/답함"
- 출력 1: 실행마다 칸별 개수 + 문항당 시간 중앙값
- 출력 2: 실행끼리 칸이 다른 문항만, 실행마다 칸과 답 앞 140자를 나란히
```

## 직접 실행

```sh
python3 step3_index.py --root private/corpus --projects private/projects.json \
  --same-files-as private/index --out private/index-proj
python3 step6_rag.py results/step7-label.json private/eval/testset.json private/eval/extra.json --index private/index-proj
python3 step6_rag.py results/step7-check.json private/eval/testset.json private/eval/extra.json --index private/index-proj --check-project
python3 compare_runs.py 기존=results/step6.json 이름표=results/step7-label.json 확인=results/step7-check.json --no-answer-ids N1
```

## 확인하기 (`내기록.md` 에 적기)

칸이 달라진 문항의 답을 읽고 뜻으로 판정해요.

| | 1회차 기존 | 1회차 이름표만 | 1회차 이름표+확인 | 내 기존 | 내 이름표만 | 내 이름표+확인 |
|---|---|---|---|---|---|---|
| 위험한 답 | 2 | 3 | 1 | | | |
| 잃은 정답 (찾고도 거절) | 0 | 1 | 1 | | | |

- 함정 질문에서 모델이 어느 쪽 문서를 근거로 썼나 (`cited` 와 `context`)
- 4단계 시험지로 `--index private/index-proj` 를 채점하면 이름표가 **찾기**에 준 영향도 보여요

## 코드에서 꼭 읽을 곳

1. 경로 앞부분이 가장 길게 맞는 이름을 고르는 부분 — `공부/` 와 `공부/rag/` 가 둘 다 있으면
2. `--same-files-as` — 비교 실험에서 문서 집합을 고정하는 이유
3. `compare_runs.py` 가 거절 판정을 다시 하는 부분 — 채점기가 바뀌면 옛 숫자를 그대로 비교하면 안 되는 이유

## 1회차와 비교

- 1회차 정리: [`../notes/step7.md`](../notes/step7.md) · 정답지: `../sLLM_study/step3_index.py`(`project_of`)·`step6_rag.py`(`CHECK_PROJECT`)·`compare_runs.py`
- 1회차 결론: 이름표는 **찾기**에서 질문이 가리킨 프로젝트 쪽 조각을 끌어왔지만, 이름표만으로는 **답**이 좋아지지 않았어요(위험 2 → 3). "이름표로 걸러라"고 시켜야 줄었어요(→ 1). 대신 맞는 자료까지 걸러 정답 1개를 잃었어요 — 안전과 도움은 맞바꿈이에요
