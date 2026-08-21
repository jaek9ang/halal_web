# CLAUDE.md

할랄 인증 관리 자동화 웹앱. 문서 진입점은 [docs/overview.md](docs/overview.md) —
어느 문서로 가야 할지는 거기 "문서 지도"를 본다.
설치·실행법은 [README.md](README.md), 데이터 흐름은 [docs/architecture.md](docs/architecture.md).

**응답은 항상 한국어.**

## 문서화 규칙

**새로 만드는 문서는 전부 `docs/`에 둔다.** 저장소 루트나 `backend/`, `frontend/` 안에
설명용 마크다운을 흩뿌리지 않는다. 예외는 루트의 `README.md`와 이 `CLAUDE.md` 둘뿐이다.

- 문서를 새로 만들면 [docs/overview.md](docs/overview.md)의 **문서 지도 표에 한 줄 추가**한다.
  표에 없는 문서는 아무도 찾지 못한다.
- 파일명은 소문자 케밥케이스(`ocr-rule-v2.md`). 날짜·버전 접미사로 사본을 늘리지 않는다.
  개정은 같은 파일을 고치고 git 이력에 맡긴다.
- 현행이 아닌 지난 단계 기록은 지우지 말고 `docs/archive/`로 옮긴다.
- 실행 결과물(벤치마크 JSON, 검증 리포트)은 `docs/reports/`에 둔다. 서술 문서와 섞지 않는다.

## 이 저장소의 금지 사항

이 프로젝트는 한때 "패치 스크립트를 만들어 소스에 적용하고, 적용 전 백업을 소스 트리에 남기는"
방식으로 개발되어 백업 사본 600여 개가 git에 쌓였다. `certificate_rule_service.py` 하나에만
사본이 11개 있었고, `*_backup_*.py`는 import 가능한 모듈명이라 잘못된 파일을 편집할 위험이 있었다.
2026-08-14에 전부 정리했다. 되돌아가지 않는다.

- **소스 트리에 백업 파일을 만들지 않는다.** `*.bak`, `*_backup_*`, `*_old*`, `*_broken_*` 금지.
  되돌리기는 git으로 한다. 불안하면 브랜치를 파거나 태그를 찍는다.
- **패치 스크립트로 소스를 수정하지 않는다.** `_patch_*.py` 같은 AST/텍스트 패처를 만들지 말고
  파일을 직접 편집한다. 패처는 같은 코드 블록을 중복 삽입하는 버그를 남긴다 (실제로 남겼다).
- **생성물을 커밋하지 않는다.** 트리 덤프, 검증 리포트, 소스 스냅샷, pip freeze 결과.
  `.gitignore`가 대부분 막지만 규칙보다 습관이 먼저다.
- **의존성 명세는 `backend/requirements.txt` 하나.** conda yml이나 pip freeze 사본을 늘리지 않는다.

## 코드를 고칠 때 어디를 보나

| 하려는 일 | 파일 |
|---|---|
| API 엔드포인트 추가·수정 | `backend/app/routers/` — 얇게 유지. 로직은 서비스로 |
| 유효기간·발급일 인식 규칙 | `backend/app/services/rules/dates.py` |
| 발급기관 판별, 기관 별칭 (JAKIM, MUIS, CICOT, ARA, JUHF, JMA, BPJPH …) | `backend/app/services/rules/organizations.py` |
| 인증번호 추출, 판독 진입점 | `backend/app/services/rules/core.py` |
| 제조사명 / 제품명 추출 | `backend/app/services/rules/companies.py`, `rules/products.py` |
| 메일·PMF 교차검증, 자동확정 안전 원칙 | `backend/app/services/rules/context.py` |
| 확정 게이트 (사람이 자동 판정을 뒤집지 못하게) | `backend/app/services/filing/gate.py` |
| 확정 실행·롤백 | `backend/app/services/filing/confirm.py` |
| 인증서 이력 (주/부 승격·강등) | `backend/app/services/filing/history.py` |
| OCR 엔진 호출 (tesseract / rapidocr) | `backend/app/services/ocr/engines.py` |
| OCR job 생성·조회 | `backend/app/services/ocr/jobs.py` |
| 메일 수신·첨부 다운로드 | `backend/app/services/mail_inbox/sync.py` |
| 관리번호 매칭 | `backend/app/services/mail_inbox/matching.py` |
| 메일 발송·본문 템플릿 | `backend/app/services/mail_service.py` |
| PMF 엑셀 읽기 | `backend/app/services/pmf_service.py` |
| PMF 엑셀 쓰기 (`keep_vba`) | `backend/app/services/pmf_filing_service.py` |
| 경로·DB·상수 설정 | `backend/app/core/config.py` |
| SQLite 연결 | `backend/app/core/db.py` |
| 메일 계정 환경변수 | `backend/app/core/mail_credentials.py` |
| 공유폴더 ↔ 로컬 폴더 대체 판정 | `backend/app/services/storage_path_service.py` |
| 화면 | `frontend/src/pages/` (화면별), `frontend/src/components/` |
| 프론트 API 호출 | `frontend/src/api/` (백엔드 라우터별) |

`certificate_rule_service.py`, `certificate_filing_workflow_service.py`,
`ocr_service.py`, `mail_inbox_service.py`는 각각 위 패키지로 옮겨졌고, 기존 경로는
re-export shim만 남아 있다. 새 코드는 패키지에서 직접 가져온다.

**모듈 전역을 monkeypatch할 때 주의**: 하위 모듈이 `from .store import get_conn`처럼
이름을 자기 네임스페이스에 묶으므로, 한 모듈만 패치하면 나머지는 원본을 계속 쓴다.
`tests/test_filing_integration_job521.py`의 `_patch_across_package` 참고.

## 검증

코드를 고쳤으면 실행해서 확인한다. 눈으로 읽고 통과시키지 않는다.

```bash
cd backend && ../.venv/bin/python -m pytest        # 백엔드
cd frontend && npm run build && npm run lint       # 프론트
```

`backend/tests/test_certificate_rules.py`는 기관별 인증서 샘플(`tests/fixtures/
certificate_samples.py`)에 대한 판독 결과를 골든 파일로 고정한다. 규칙 코드를 건드렸는데
이게 깨지면 판독 동작이 바뀐 것이다 — 의도한 변경인지 반드시 확인하고, 맞다면
`UPDATE_CERTIFICATE_RULE_GOLDEN=1`로 골든을 다시 만든 뒤 diff를 눈으로 본다.

`tests/test_filing_integration_job521.py`는 실제 PMF·DB가 있어야 돌아간다. 없으면 skip된다.
`HALAL_TEST_PMF` / `HALAL_TEST_DB`로 경로를 준다.

## 조심할 지점

- **`storage_path_service`가 런타임에 `os.environ`을 쓴다** (`HALAL_ACTIVE_RAW_MATERIAL_ROOT`,
  `HALAL_STORAGE_MODE`). 사이드채널이라 어디까지 의존이 퍼졌는지 불명확. 건드릴 때 주의.
- **`backend/app/ml/`은 런타임에 연결되어 있지 않다.** 라우터·서비스 어디에서도 import하지 않고
  `backend/scripts/ml_*`의 학습 스크립트에서만 쓴다. 실험 코드로 취급.
- **DB는 SQLite 4개**(`pmf_app.db`, `halal_lhln.db`, `ocr_test.db`, `cert_template_features.db`).
  ORM·마이그레이션 없음. 스키마는 각 서비스의 `CREATE TABLE IF NOT EXISTS`가 소유.
  현재 스키마 덤프는 `backend/schema_export/*.sql` (`backend/dump_schema.py`로 갱신).
- **PMF는 `.xlsm`**(VBA 포함). openpyxl로 쓸 때 `keep_vba=True`를 빠뜨리면 매크로가 날아간다.
- **운영 경로는 Windows UNC 공유폴더**다. macOS에서는 PMF 연동 기능이 동작하지 않는다.

## 스타일

- 함수는 짧게. 요청 범위만 고친다. 인접 코드를 "개선"하지 않는다.
- 요청되지 않은 기능·추상화·설정을 추가하지 않는다.
- 해석이 갈리면 나열하고 물어본다.
