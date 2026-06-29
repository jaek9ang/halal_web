# OCR Rule V2 + 메일/PMF 문맥 보강

## 적용 내용

- 현재 규칙 파일의 중복 함수 정의 제거
- 날짜 후보를 정규식 순서가 아니라 문서 위치 순서로 처리
- ARA 인증번호 및 만료일 보강
- JUHF 인증번호 및 Date of Expiry 보강
- JAKIM 발급일/만료일 구분
- CICOT Effective/Expired date 구분
- JMA `284-TSRU/24` 형식 인증번호 보강
- MUIS 날짜 누락 시 파일명 만료일과 라벨 인접 날짜 비교
- 메일 관리번호 + 첨부순번 + 발송메일 항목 + PMF를 OCR 교차검증 문맥으로 사용

## 문맥 보강 안전 원칙

- PMF의 기존 인증번호와 유효기간을 새 인증서 결과로 복사하지 않음
- OCR 기관과 메일 기관이 다르면 `MANUAL_REVIEW`
- 제품명과 제조사는 OCR 원문에서 확인될 때만 PMF 표준명으로 정규화
- BPJPH OCR 유효기간은 계속 비워둠
- PMF 기존 유효기간보다 과거인 OCR 날짜는 자동확정 차단

## 적용

프로젝트 루트에서:

```powershell
git add .
git commit -m "checkpoint: before OCR rule v2"

Set-ExecutionPolicy -Scope Process Bypass
& "C:\TEMP\ocr_rule_v2_package\apply_ocr_rule_v2.ps1"
```

압축 해제 경로가 다르면 실제 경로를 사용합니다.

## 회귀 테스트

```powershell
.\.venv\Scripts\python.exe `
  .\backend\scripts\test_ocr_rule_v2.py `
  --bundle "C:\TEMP\halal_ocr_rule_review\ocr_rule_review_bundle_20260629_102333.zip"
```

정상 기준:

- records_tested: 517
- unique_documents: 144
- runtime_errors: 0
- duplicate_function_definitions: 빈 객체
- targeted_regressions: 전부 passed
- context_tests: 전부 passed

## 파일

- `backend/app/services/certificate_rule_service.py`
- `backend/app/services/ocr_context_service.py`
- `backend/scripts/patch_ocr_service_v2.py`
- `backend/scripts/test_ocr_rule_v2.py`
- `ocr_rule_v2_test_report.json`
- `baseline_comparison_report.json`
