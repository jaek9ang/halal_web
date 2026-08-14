# 아키텍처

## 전체 흐름

```
  PMF(.xlsm, 공유폴더)
        │  읽기: pmf_service
        ▼
  ① 만료 선별 ───────────► /pmf/summary, /suppliers/email-review
        │
        ▼
  ② 요청 메일 생성·발송 ──► /mail/targets, /mail/send
        │                      mail_service (SMTP, 관리번호 부여)
        ▼
  ③ 회신 수신·첨부 저장 ──► /mail/inbox/*
        │                      mail_inbox_service (IMAP, 관리번호 매칭)
        ▼
  ④ OCR 판독 ────────────► /ocr/jobs
        │                      ocr_service (tesseract / rapidocr / PyMuPDF)
        │                      certificate_rule_service (기관별 필드 추출)
        │                      ocr_context_service (메일·PMF 문맥 교차검증)
        ▼
  ⑤ 교차인정 판정 ───────► lhln_service (BPJPH 인정기관 대조)
        │                      certificate_change_service (변경 유형 분류)
        ▼
  ⑥ 검토·확정 ───────────► /certificate-filing/preview, /confirm
        │                      certificate_filing_workflow_service
        │                      filing_name_service (파일명 규칙)
        ▼
  PMF 업데이트 + 이력 로그 ─► pmf_filing_service (openpyxl, keep_vba)
                              certificate_filing_service (history.jsonl)
```

## 계층

`routers/` (HTTP) → `services/` (업무 로직) → SQLite / 엑셀 / 파일시스템.

큰 서비스 넷은 패키지로 나뉘어 있고, 각 패키지 안의 의존 방향은 한 방향이다.

| 패키지 | 계층 순서 |
|---|---|
| `services/rules/` | text → dates → organizations → companies → products → overrides → core → context |
| `services/filing/` | store → helpers → history → gate → preview → confirm |
| `services/ocr/` | engines → store → paths → templates → jobs → failures |
| `services/mail_inbox/` | text → parsing → store → matching → sync → queries → ocr_targets |

옛 모듈명(`certificate_rule_service.py` 등)은 re-export shim으로 남아 있다.

DI 계층이나 리포지토리 패턴은 없다. 서비스는 모듈 함수의 모음이고, 필요한 DB 연결을
각자 연다. `core/config.py`가 경로·상수를 제공한다.

## 저장소

| 저장소 | 경로 | 소유 |
|---|---|---|
| `pmf_app.db` | `backend/db/` | suppliers, mail 로그·요청항목, material link, ocr jobs, filing |
| `halal_lhln.db` | `backend/db/` | BPJPH LHLN 인정기관 목록 |
| `ocr_test.db` | `backend/db/` | OCR 테스트 업로드·실행 결과 |
| `cert_template_features.db` | `backend/db/` | 인증서 양식 pHash/ORB 특징 |
| PMF `.xlsm` | 공유폴더 → `backend/cache/source_pmf/` 캐시 | 원재료 마스터. 읽고 쓴다 |
| 규칙 JSON/JSONL | `backend/data/rules/` | 규칙 후보, 오버라이드, 승인 이력 |
| 필링 이력 | `backend/data/filing/*.jsonl` | 확정·롤백 감사 로그 |
| 첨부·업로드·출력 | `backend/data/*`, `backend/output/*` | 런타임 산출물 (git 제외) |

`backend/db/`, `backend/cache/`, `backend/output/`, `backend/data/`의 런타임 하위 폴더는
전부 gitignore 대상이다. 스키마 덤프만 `backend/schema_export/*.sql`로 커밋된다.

## 라우터

| prefix | 파일 | 역할 |
|---|---|---|
| `/pmf` | `routers/pmf.py` | PMF 동기화, 원재료 조회·검색, 연관 파일 |
| `/suppliers` | `routers/suppliers.py` | 업체 메일주소 검토·오버라이드 |
| `/mail` | `routers/mail.py` | 발송, 발송로그, 수신함 동기화·첨부·OCR 대상 선정 |
| `/ocr` | `routers/ocr.py` | OCR 잡 생성·조회, 수동 업로드, 데이터 export |
| `/certificate-filing` | `routers/certificate_filing.py` | 자동분류 미리보기·확정·이력 |
| `/lhln` | `routers/lhln.py` | BPJPH LHLN 동기화, 안내 PDF 생성 |
| `/ai-rule-review` | `routers/ai_rule_review.py` | OCR 규칙 후보 AI 리뷰·검증·적용 |
| `/cert-template` | `routers/cert_template.py` | 인증서 양식 학습·분류 (prefix는 라우터 파일에 있음) |

## 프론트엔드

React 19 + Vite SPA. 라우터 라이브러리 없이 `App.jsx`의 `useState` 문자열 스위치로
화면을 전환한다. URL 라우팅·딥링크 없음.

API 호출은 `src/api/`의 얇은 `fetch` 래퍼를 거친다. 백엔드 주소는 `VITE_API_BASE_URL`,
기본값 `http://127.0.0.1:8000`. Vite 프록시를 쓰지 않으므로 호출은 cross-origin이고
백엔드 CORS 설정에 의존한다.

## ML (런타임 미연결)

`backend/app/ml/`의 인증서 분류기·필드 추출기는 어떤 라우터·서비스도 import하지 않는다.
`backend/scripts/ml_*`의 학습·평가 스크립트에서만 사용하는 실험 코드다.
교차인정 판정은 ML이 아니라 `certificate_rule_service`의 규칙으로 한다.
