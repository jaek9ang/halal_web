# 개요

할랄 인증 관리 자동화(`halal_web`) 프로젝트의 문서 진입점.
설치·실행법과 도메인 용어는 [README.md](../README.md)에 있다. 이 문서는
**"무엇이 어떻게 돌아가는지"를 한 장으로 보고, 그 다음 어느 문서로 갈지**를 정하는 용도다.

## 이 시스템이 하는 일

세우(농심 그룹사, 인도네시아)의 원재료 할랄 인증서 관리를 자동화한다.
원재료 약 310종의 인증서를 엑셀(PMF)로 수기 관리하던 월 5시간짜리 루프를 파이프라인으로 대체한다.

```
① 만료 선별 → ② 요청 메일 발송 → ③ 회신 첨부 저장 → ④ OCR 판독
   → ⑤ 교차인정 판정(BPJPH LHLN 대조) → ⑥ 사람이 예외만 확정 → PMF 갱신 + 이력 로그
```

교차인정 판정은 **규칙 기반**이다(ML 아님). `backend/app/ml/`은 실험 코드이며 런타임에 연결되어 있지 않다.

## 구성 요소

| 영역 | 스택 | 위치 |
|---|---|---|
| 백엔드 | FastAPI (라우터 → 서비스 → SQLite/엑셀) | `backend/app/` |
| 프론트엔드 | React 19 + Vite SPA | `frontend/src/` |
| 판독 규칙 | 기관별 필드 추출 규칙 패키지 | `backend/app/services/rules/` |
| 확정 워크플로 | 미리보기 · 게이트 · 확정 · 롤백 · 이력 | `backend/app/services/filing/` |
| 저장소 | SQLite 4개 + PMF `.xlsm`(공유폴더) | `backend/db/`, 공유폴더 |

ORM·마이그레이션은 없다. 스키마는 각 서비스의 `CREATE TABLE IF NOT EXISTS`가 소유하고,
현재 덤프는 `backend/schema_export/*.sql`에 있다.

## 절대 깨면 안 되는 것

인증서 만료를 놓치면 수출이 중단된다. 자동확정 로직은 항상 다음을 지킨다.

- PMF의 기존 인증번호·유효기간을 새 OCR 결과로 **덮어쓰지 않는다**
- OCR 발급기관과 메일 발신 기관이 **다르면 `MANUAL_REVIEW`**
- BPJPH 인증서의 OCR 유효기간은 **비워둔다**
- PMF 기존 유효기간보다 **과거인** OCR 날짜는 자동확정 차단

전체 목록은 [README.md](../README.md#안전-원칙-건드리면-안-되는-것), 구현은
`backend/app/services/filing/gate.py`와 `backend/app/services/rules/context.py`.

## 문서 지도

| 알고 싶은 것 | 문서 |
|---|---|
| 왜 만드는가 — 배경, 목표, 범위, 예상 산출물 | [project-brief.md](project-brief.md) |
| 데이터 흐름, 계층 구조, 저장소 구성 | [architecture.md](architecture.md) |
| 로컬(macOS/Windows) 개발 환경 설정 | [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md) |
| 이 저장소에서 Claude Code로 작업하는 법 | [claude-code-guide.md](claude-code-guide.md) |
| OCR 규칙 V2 + 메일/PMF 문맥 보강 내역 | [ocr-rule-v2.md](ocr-rule-v2.md) |
| 코드 수정 시 어느 파일을 보나, 금지 사항 | [../CLAUDE.md](../CLAUDE.md) |
| 벤치마크·검증 결과 (JSON) | [reports/](reports/) |
| 지난 단계 기록 (현행 아님, 참고용) | [archive/](archive/) |

## 검증

코드를 고쳤으면 실행해서 확인한다.

```bash
cd backend && ../.venv/bin/python -m pytest
cd frontend && npm run build && npm run lint
```

`backend/tests/test_certificate_rules.py`는 기관별 샘플 판독 결과를 골든 파일로 고정한다.
규칙 코드를 건드렸는데 이게 깨지면 판독 동작이 바뀐 것이다.

## 문서화 규칙

새로 쓰는 문서는 모두 `docs/`에 둔다. 자세한 규칙은 [../CLAUDE.md](../CLAUDE.md#문서화-규칙).
