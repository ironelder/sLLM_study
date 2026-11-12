# 10단계 — 직접 만든 벡터 찾기를 FAISS 와 비교 (응용)

## 왜 하나요

3단계에서 벡터 찾기를 직접 만들었어요(전부 하나씩 내적). 실무에서 많이 쓰는 FAISS 로 바꾸면 **정확도는 같은지, 얼마나 빨라지는지, 언제 필요한지** 재 봐요.

| 말 | 쉬운 뜻 |
|---|---|
| FAISS | 벡터를 빠르게 찾아 주는 라이브러리. 서버 없이 Python 에서 바로 써요 |
| Flat | 전부 비교. 느리지만 정확해요 |
| HNSW | 가까운 벡터끼리 이어 둔 그래프를 따라가며 찾는 근사 방법. 빠르지만 가끔 놓쳐요 |

먼저 짐작해서 적어요: "6,855개에서 FAISS 는 지금보다 몇 배 빠를까?", "HNSW 로 바꾸면 recall 이 떨어질까?"

## 설치 (인터넷 없이 설치하는 연습 포함)

FAISS 최신판은 Python 3.10 이상이 필요해요.

```sh
python3 --version                                   # 3.10 이상인지. 아니면 python3.11 등 따로 설치
mkdir -p private/offline/wheels
python3.11 -m pip download faiss-cpu numpy -d private/offline/wheels --only-binary=:all:
(cd private/offline/wheels && shasum -a 256 *.whl > SHA256SUMS)
python3.11 -m venv .venv
(cd private/offline/wheels && shasum -a 256 -c SHA256SUMS)
.venv/bin/pip install --no-index --find-links private/offline/wheels faiss-cpu numpy
```

- 마지막 줄은 Wi-Fi 를 끄고(또는 `sandbox-exec -f setup/no-network.sb` 를 앞에 붙여) 해 봐요. 인터넷 없이 설치되면 분리망 반입도 같은 방법이에요

## AI 에게 줄 말

```text
faiss_store.py 를 만들어줘 (.venv/bin/python 으로 실행, faiss·numpy 사용).
- load_vectors(색인 폴더): meta.json 의 count·dim 으로 vectors.f32 를 numpy float32 (count, dim) 로 읽기
- build(벡터, "flat"|"hnsw"): flat = IndexFlatIP, hnsw = IndexHNSWFlat(dim, 32, 내적), efConstruction 100
- open_index(색인 폴더, 종류): faiss-<종류>.index 가 있고 개수가 맞으면 읽고, 아니면 만들어 저장. hnsw 는 efSearch 64
- search(색인, 질문 벡터, k): [(점수, 조각 번호)]
```

```text
step10_faiss.py 를 만들어줘.
- 실행: .venv/bin/python step10_faiss.py <시험지.json> <결과.json> [--scale 200000]
- 시험지 질문을 한 번씩만 임베딩하고, 같은 질문 벡터로 4가지를 비교: 파이썬 전수 비교(3단계 방식), numpy 행렬 곱, FAISS Flat, FAISS HNSW
- 각각 상위 200개 조각 → 문서별 첫 등장으로 문서 순위 → group 별 recall@1·@5, 찾기 시간 중앙값(임베딩 제외), 파이썬과 문서 top5 가 같은 문항 수
- --scale N: 실제 벡터 + 실제 벡터에 작은 잡음을 섞어 길이를 1로 맞춘 복제로 N 개를 만들고, numpy·Flat·HNSW 시간과
  HNSW 가 Flat 상위 10개 중 찾은 비율, 메모리, 만드는 시간. 파이썬 시간은 실측 개당 시간 × N 으로 추정(추정이라고 표시)
```

```text
step6_rag.py 에 --faiss flat|hnsw 옵션을 추가해줘. 주면 조각 찾기를 faiss_store 로 하고(제외 경로는 찾은 뒤 거르니 k*20 개 받기),
안 주면 지금과 똑같이 동작. faiss 는 옵션을 줄 때만 import
```

## 직접 실행

```sh
.venv/bin/python step10_faiss.py private/eval/testset.json results/step10-faiss.json --scale 200000
.venv/bin/python step6_rag.py results/step10-rag-hnsw.json private/eval/testset.json private/eval/extra.json --faiss hnsw
python3 compare_runs.py 기존=results/step6.json HNSW=results/step10-rag-hnsw.json --no-answer-ids N1
```

## 확인하기 (`내기록.md` 에 적기)

| 항목 | 1회차 | 내 값 |
|---|---|---|
| 찾기 시간: 파이썬 / numpy / Flat / HNSW | 243 / 약 1 / 약 1 / 0.3 ms | |
| recall (4가지 모두) | 같음 | |
| HNSW 문서 top5 가 파이썬과 같음 | 17/20 | |
| RAG 4칸 기존 vs HNSW | 같음 (조각 21/22 같음) | |
| 20만 개: 파이썬(추정) / numpy / Flat / HNSW | 7.1초 / 79 / 24 / 8.7 ms | |
| 20만 개 HNSW 정확도(상위 10개) | 90.5% | |

## 코드에서 꼭 읽을 곳

1. 3단계의 이중 for 문과 numpy `vecs @ q` 한 줄 — 왜 243ms 와 1ms 차이가 날까
2. HNSW 의 `efSearch` — 크게 하면 무엇이 좋아지고 무엇이 나빠질까
3. 제외 경로를 FAISS 검색 **뒤에** 거르는 부분 — 왜 k 개보다 넉넉히 받아야 할까

## 고쳐 보기

| 바꿀 것 | 짐작 먼저 | 확인 |
|---|---|---|
| `EF_SEARCH` 16 / 256 (규모 시험에서) | 시간·정확도가 어떻게 바뀔까? | 20만 개 HNSW 시간·정확도 |
| `--scale 500000` (메모리 여유가 있을 때만) | 차이가 더 벌어질까? | 시간·메모리 |

- 시험지 20문항 점수를 보며 efSearch 를 고르면 과적합이에요. 규모 시험 데이터로만 맞바꿈을 봐요

## 1회차와 비교

- 1회차 정리: [`../notes/step10.md`](../notes/step10.md)
- 1회차 결론: 6,855개에선 numpy 한 줄로 충분했고(243ms → 1ms), FAISS Flat 은 결과가 완전히 같았어요. HNSW 는 규모가 커질 때(20만 개에서 9ms) 의미가 있지만, 근사라서 정확도를 같이 재야 해요
