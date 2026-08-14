# 할랄 인증 관리 자동화 (halal_web)

세우(농심 그룹사, 인도네시아 사업)의 원재료 할랄 인증서 관리를 자동화하는 사내 웹앱.

원재료 약 310종의 인증서를 엑셀로 수기 관리하던 업무 — 만료 임박 건을 눈으로 찾고, 업체에
갱신 요청 메일을 손으로 쓰고, 회신 PDF를 읽어 엑셀에 옮겨 적는 월 5시간짜리 루프 — 를
파이프라인으로 대체한다.

```
만료 자동 선별 → 업체별 요청 메일 생성·발송 → 회신 첨부 자동 저장
   → OCR로 기관·인증번호·유효기간 추출 → 교차인정 룰 판정(BPJPH 인정기관 대조)
   → 사람은 예외만 검토·확정 → PMF 엑셀 자동 업데이트 + 이력 로그
```

교차인정 판정은 규칙 기반이다(ML 아님). 발송·판독 이력 로그는 할랄 심사 근거자료로 재사용된다.

## 도메인 용어

| 용어 | 뜻 |
|---|---|
| **PMF** | Products and Materials File. 원재료 마스터 엑셀(`.xlsm`). 이 시스템의 단일 진실 원천이자 최종 출력 대상 |
| **LHLN** | 인도네시아 BPJPH가 인정하는 해외 할랄 인증기관 목록 |
| **BPJPH** | 인도네시아 할랄 인증청. 교차인정 판정의 기준 |
| **교차인정** | 해외 기관(JAKIM, MUIS, CICOT 등) 인증서를 BPJPH가 인정하는지 여부 |
| **자동확정** | OCR 결과를 사람 검토 없이 PMF에 반영하는 것. 안전 조건을 모두 통과해야만 허용 |
| **MANUAL_REVIEW** | 자동확정을 막고 사람 검토로 넘기는 판정 상태 |

## 안전 원칙 (건드리면 안 되는 것)

인증서 만료를 놓치면 수출이 중단된다. 자동확정 로직은 다음을 항상 지킨다.

- PMF의 기존 인증번호·유효기간을 새 OCR 결과로 **덮어쓰지 않는다**
- OCR이 읽은 발급기관과 메일 발신 기관이 **다르면 `MANUAL_REVIEW`**
- 제품명·제조사는 OCR 원문에서 확인될 때만 PMF 표준명으로 정규화
- BPJPH 인증서의 OCR 유효기간은 **계속 비워둔다**
- PMF 기존 유효기간보다 **과거인** OCR 날짜는 자동확정 차단

## 구조

```
halal_web/
├─ backend/          FastAPI. 라우터 → 서비스 → SQLite/엑셀
│  ├─ app/
│  │  ├─ main.py     앱 조립, 라우터 마운트, CORS
│  │  ├─ core/       설정·경로 유틸
│  │  ├─ routers/    HTTP 계층 (8개)
│  │  ├─ services/   업무 로직 (25개)
│  │  └─ ml/         인증서 분류·필드추출 실험 (런타임 미연결)
│  ├─ scripts/       ML 학습·데이터 스크립트, 수동 점검 도구
│  ├─ tests/         pytest
│  └─ data/rules/    OCR 규칙 후보·오버라이드 (JSON/JSONL)
├─ frontend/         React 19 + Vite SPA
├─ scripts/          실행·환경설정 스크립트
└─ docs/             설계·운영 문서
```

자세한 데이터 흐름과 저장소 구성은 [docs/architecture.md](docs/architecture.md).

## 실행

### 준비

```bash
# macOS / Linux
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
```

```powershell
# Windows
.\scripts\setup_venv.ps1
```

프론트엔드:

```bash
cd frontend && npm install
```

### 기동

```bash
# macOS / Linux
./scripts/run_backend.sh          # http://127.0.0.1:8000
cd frontend && npm run dev        # http://127.0.0.1:5173
```

```powershell
# Windows
.\scripts\run_backend.ps1
.\scripts\run_frontend.ps1
```

확인: `curl http://127.0.0.1:8000/health` → `{"ok":true}`, API 문서는 `/docs`.

### 환경변수

`frontend/.env.example`, `scripts/local_env.ps1.example` 참고. 주요 항목:

| 변수 | 용도 |
|---|---|
| `PMF_SOURCE_DIR` | PMF 원본 폴더. 미설정 시 운영 공유폴더(UNC) |
| `HALAL_DOC_ROOT` | 하부원료 서류 루트 |
| `HALAL_RAW_MATERIAL_ROOT` | 인증서 분류 대상 원재료 폴더 |
| `DAUM_EMAIL` / `DAUM_APP_PASSWORD` | 메일 발송·수신 계정 |
| `OPENAI_API_KEY` | AI 규칙 리뷰 기능 |
| `VITE_API_BASE_URL` | 프론트가 호출할 백엔드 주소 |

운영 공유폴더는 Windows UNC 경로다. macOS에서는 `run_backend.sh`가 `.local_runtime/`
아래 로컬 폴더로 대체한다 — PMF 연동 기능은 그 환경에서 동작하지 않는다.

## 테스트

```bash
cd backend && ../.venv/bin/python -m pytest -q
```

## 문서

- [docs/architecture.md](docs/architecture.md) — 데이터 흐름, 저장소, 모듈 지도
- [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md) — 로컬 개발환경 구성
- [docs/ocr-rule-v2.md](docs/ocr-rule-v2.md) — OCR 규칙 V2 내용과 회귀 기준
- [CHANGELOG.md](CHANGELOG.md)
- [CLAUDE.md](CLAUDE.md) — 이 저장소에서 작업할 때의 규칙
