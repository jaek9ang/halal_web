# Rule vs OpenAI vs Hybrid 벤치마크

- 대상: 할랄 인증서 100건, 6필드(인증기관/인증국가/인증번호/유효기간/제조사/제조국)
- 스크립트: [backend/scripts/benchmark/run_benchmark.py](../backend/scripts/benchmark/run_benchmark.py)
- 에이전트 판독기: [backend/scripts/benchmark/agent_reader.py](../backend/scripts/benchmark/agent_reader.py)
- 채점·에이전트 테스트: [backend/tests/test_benchmark_scoring.py](../backend/tests/test_benchmark_scoring.py)

## 1차 측정 (2026-08-21)

| 방식 | 필드 정확도(600필드) | 완전일치 문서 |
|---|---|---|
| Rule (기존 판독기) | 83.0% | 39/100 |
| Hybrid (LOW conf만 LLM 대체) | 69.8% | 13/100 |
| Full LLM (gpt-4o-mini) | 61.5% | 2/100 |

필드별 정확도(Rule / LLM / Hybrid):

- 인증기관 100.0 / 32.0 / 47.0
- 인증국가 92.0 / 73.0 / 78.0
- 인증번호 69.0 / 56.0 / 62.0
- 유효기간 78.0 / 80.0 / 78.0
- 제조사 78.0 / 62.0 / 77.0
- 제조국 81.0 / 66.0 / 77.0

### 1차 인사이트

1. **인증기관 판별은 Rule이 압도적 우위** (100% vs 32%). LLM은 별칭을 정규화하지 않고
   원문 그대로 반환했다 (BPJPH → "Majelis Ulama Indonesia"). `organizations.py`의
   기관 별칭 테이블이 실질적 가치를 만들고 있다.
2. **Hybrid가 Rule 단독보다 낮다** (69.8% < 83.0%). "confidence 낮을 때 LLM으로 보완"이라는
   전제가 이 실험에서는 성립하지 않았다.
3. LLM이 Rule을 앞선 유일한 필드는 유효기간(80.0 vs 78.0)이고 차이가 근소하다.

## 2차 준비 — 1차 수치를 그대로 믿으면 안 되는 이유 (2026-08-21)

1차 측정의 채점은 `.strip().lower()` 후 **문자열 완전일치**였다. 그런데 비교 대상 둘의
출력 성질이 다르다.

- **Rule**은 값을 내보내기 전에 이미 정규화 단계를 거친다 (`normalize_manufacturer_output` 등).
- **LLM**은 서류에 적힌 표기를 그대로 뱉는다.

그래서 `Nongshim Co., Ltd` vs `Nongshim Co.,Ltd`, `USA` vs `United States`,
`2027-02-28` vs `28 February 2027` 같은 **표기 차이가 전부 LLM 오답으로 집계**됐다.
1차 결론(“LLM은 신뢰 보완재로 쓰기 어렵다”)은 실력 차이와 표기 차이가 섞인 수치 위에 서 있다.
**LLM 61.5%는 과소평가일 가능성이 있고, 그 크기는 아직 모른다.**

이걸 고치지 않으면 앞으로 어떤 개선을 해도 좋아졌는지 측정할 수 없다. 그래서 재측정 전에
스크립트를 아래처럼 바꿨다.

### 바뀐 것

| # | 변경 | 근거 |
|---|---|---|
| 1 | 채점을 **strict / normalized** 두 축으로 산출 | 실력 차이와 표기 차이 분리 |
| 2 | 기관·국가 응답을 **폐쇄집합(enum)으로 강제** | 1차 인사이트 1의 직접 대응 |
| 3 | **양식 분류(pHash/ORB) 힌트** 주입 옵션 | 이미 계산해 놓고 LLM에 안 주던 정보 |
| 4 | 경로 하드코딩 제거, **CLI 인자화** | 1차 스크립트는 다른 PC에서 재현 불가였음 |

**1. 두 축 채점.** `strict`는 1차 방식 그대로 두어 비교 기준으로 쓴다. `normalized`는
기관 별칭·국가 표기·날짜 형식·구두점 차이만 흡수한다. 정규화 함수는 판독기와 같은 것을
쓴다(`rules/` 패키지). 채점기가 자기만의 정규화를 갖게 되면 판독기가 바뀔 때 채점이
조용히 어긋난다.

정규화의 원칙은 하나다 — **표기 차이만 접고 의미 차이는 남긴다.** 채점기가 필드별로
더 똑똑해지면 실제 오답까지 정답으로 접어서, 개선을 측정하는 대신 개선을 만들어낸다.
[`test_benchmark_scoring.py`](../backend/tests/test_benchmark_scoring.py)의 `REAL_MISMATCHES`가 그 방어선이다.

**2. 폐쇄집합.** 1차 스키마는 `cert_org: str`이라 모델이 원문 기관명을 그대로 뱉을 수
있었다. 보기를 주면 구조적으로 불가능해진다. 보기는 `rules/organizations.py`의
`ORG_ALIASES`(21개)와 `COUNTRY_WORDS`(18개)에서 만든다 — 단일 소스를 유지해야 LLM이
시스템에 없는 값을 고르는 일이 없다. 폐쇄집합 밖은 `UNKNOWN`.

**3. 양식 힌트 — 기본값 off.** 정답 누출 위험이 있다. 양식 분류는
`cert_template_features.db`의 참조 특징과 대조하는데, 벤치마크 대상 PDF가 그 참조
집합에 들어 있으면 힌트가 사실상 정답이 되어 점수가 부풀려진다.

- 사람이 확정한 판정(`feature_kind == "manual"`)은 코드가 자동으로 건너뛴다.
- 참조 집합 자체의 중복은 **코드가 막지 못한다.** 이 옵션으로 낸 수치는 참조 집합과
  대상이 분리되어 있음을 확인한 뒤에만 쓸 것.
- 분류 신뢰도가 `AUTO_IMAGE`(운영 코드의 자동 판정 기준)가 아니면 힌트를 만들지 않는다.
  틀린 힌트는 힌트 없음보다 나쁘다.

**PMF 기존값은 의도적으로 주입하지 않는다.** 기존 인증번호·제조사를 보여주면 모델이
그대로 베껴 써서 "갱신되지 않은 인증서"를 잡지 못한다. 업체가 작년 인증서를 재발송한
경우 시스템이 정상 갱신으로 통과시키게 된다. `rules/context.py`의 자동확정 안전 원칙
("PMF 기존 값을 새 결과로 덮어쓰지 않는다")과 같은 이유다. 기존값 대조가 필요하면
추출 호출이 아니라 별도 검증 단계에서 한다.

## 재현

원본 PDF와 API 키는 이 저장소에 없다. 운영 PC의 `backend/scripts/benchmark/`에서 실행한다.

```bash
set OPENAI_API_KEY=...
python run_benchmark.py ^
  --pdf-dir D:\halal_baseline_review_100 ^
  --baseline C:\path\halal_ocr_baseline_google_dashboard.html ^
  --out report.html ^
  --schema enum
```

1차와 같은 조건으로 재현하려면 `--schema free`. 배선만 점검하려면 `--offline`
(OpenAI를 호출하지 않으므로 LLM/Hybrid 수치는 무의미하다).

### 2차 측정 시 먼저 볼 것

1. `--schema free`로 돌려서 **strict와 normalized의 차이**를 본다. 이 차이가
   1차 결론이 얼마나 표기 문제였는지를 말해준다.
2. 그다음 `--schema enum`으로 돌려 **인증기관 32%가 어디까지 올라가는지** 본다.
3. 두 결과를 비교해야 "무엇이 효과가 있었는지"가 분리된다. 한 번에 다 바꾸고
   총점만 보면 알 수 없다.

## 3차 준비 — 도구를 쓰는 에이전트 판독 (`--mode agent`)

1·2차의 LLM 판독은 **단발 호출**이었다. 1페이지를 PNG로 렌더해 던지고 JSON을 받는다.
모델이 뭘 더 봐야 하는지 알아도 가져올 수단이 없었다. 실제로 이런 손해가 있었다.

- **1페이지만 봤다.** BPJPH `LAMPIRAN`(부속서)처럼 제품·제조사가 뒤 페이지에 있는
  다페이지 인증서에서 뒷장을 아예 못 봤다.
- **텍스트 레이어를 버렸다.** PDF에 글자가 박혀 있어도 이미지만 보고 인증번호를 읽었다.
  인증번호가 6필드 중 최저(69.0%)인 것과 무관하지 않을 수 있다.
- **우리 기관 목록을 몰랐다.** 정규명 목록이 있는데도 서류 원문 표기를 그대로 뱉었다.
- **이미 계산된 양식 분류를 못 썼다.**

[`agent_reader.py`](../backend/scripts/benchmark/agent_reader.py)는 이 정보들을 **도구**로 열고 모델이 필요할 때 직접 부르게 한다.
루프는 두 단계다: 도구로 탐색 → 마지막에 구조화 스키마로 확정.

### 도구 (전부 읽기 전용)

| 도구 | 하는 일 |
|---|---|
| `get_document_overview` | 페이지 수, 페이지별 텍스트 레이어 유무 |
| `read_page_text` | PDF 텍스트 레이어 직독 (이미지 판독보다 정확) |
| `view_page_image` | 임의 페이지를 이미지로 첨부 |
| `list_certification_organizations` | 정규 기관명 + 별칭 (`ORG_ALIASES`) |
| `classify_document_template` | 양식 pHash/ORB 분류 |
| `read_with_rule_engine` | 기존 규칙 판독기 결과 (참고 의견) |
| `lookup_cross_recognition` | BPJPH 인정기관(LHLN) 조회 |

### 의도적으로 넣지 않은 도구

- **PMF 기존값 조회.** 기존 인증번호·제조사를 보여주면 모델이 그대로 베껴 쓴다.
  업체가 작년 인증서를 재발송해도 "일치"로 통과시키게 된다. 기존값 대조는 판독이
  끝난 뒤 별도 검증 단계(`rules/context.py`)에서 한다. 판독 중에는 서류만 본다.
  이 성질은 도구가 늘어날 때 조용히 깨지기 쉬워서 테스트로 박아뒀다
  (`test_agent_has_no_tool_exposing_existing_pmf_values`).
- **쓰기 도구 전부.** 판독 결과만 돌려준다. 아무것도 바꾸지 않는다.
- **메일 본문 조회.** 업체가 메일에 적어 보낸 제품명은 업체 주장이지 인증서 내용이
  아니다. 교차검증 재료지 판독 재료가 아니다.

### 비용 상한

도구 호출은 매 라운드 컨텍스트를 키운다. `--max-iterations`(기본 6),
`--max-tool-calls`(기본 12)로 문서당 상한을 두고, 넘으면 그 시점까지의 정보로 확정한다.
리포트에 문서당 평균 도구 호출 수가 찍히므로 비용 대비 효과를 볼 수 있다.

`agent` 모드에서는 `--template-hint`가 자동으로 꺼진다. 양식 분류가 도구로 열려 있어
같은 정보를 두 경로로 주게 되기 때문이다.

### 측정 방법

에이전트는 **단발 호출보다 확실히 나은지 확인되기 전에는 운영에 붙이지 않는다.**
비교는 조건 하나씩만 바꿔서 한다.

```bash
python run_benchmark.py ... --schema enum --mode single --out single.html
python run_benchmark.py ... --schema enum --mode agent  --out agent.html
```

봐야 할 것:

1. **normalized 정확도 차이.** 도구가 실제로 판독을 개선했는가.
2. **문서당 도구 호출 수.** 개선 대비 비용이 맞는가. 호출 6회에 1%p면 남는 장사가 아니다.
3. **어떤 도구가 실제로 쓰였는가.** 아무도 안 부르는 도구는 프롬프트만 늘리는 짐이다.
4. **다페이지 문서에서의 차이.** `read_page_text`/`view_page_image`가 뒷장을 보는
   효과가 여기서 나와야 한다. 안 나오면 도구 설명이 부족한 것이다.
