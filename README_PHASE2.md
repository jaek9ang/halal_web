# 인증서 파일자동분류 백엔드 Phase 2

## 추가 기능

- OCR 완료 Job 목록 조회
- 수신 첨부파일과 `request_id` 연결
- 발송메일 본문의 구조화 원료정보 파싱
- 메일 원료와 PMF 원료 후보 점수 매칭
- 저장 예정 폴더/파일명 미리보기
- 확정판정 시 로컬 테스트 폴더로 안전 복사
- 확정판정 시 PMF 캐시의 인증기관/인증번호/유효기간 업데이트
- BPJPH 파일명은 `[BPJPH]`
- BPJPH PMF 유효기간은 메일의 `유지 확인 시 적용 예정` 값 사용
- PMF 변경 전 자동 백업
- 처리 이력 SQLite 저장

## API

- `GET /certificate-filing/status`
- `GET /certificate-filing/candidates`
- `POST /certificate-filing/preview`
- `POST /certificate-filing/confirm`
- `GET /certificate-filing/history`

## 테스트 환경변수

PowerShell에서 백엔드 실행 전:

```powershell
$env:HALAL_RAW_MATERIAL_ROOT = "C:\TEMP\halal_filing_test"
```

PMF 캐시가 아닌 별도 테스트 PMF 복사본을 수정하려면:

```powershell
$env:PMF_UPDATE_PATH = "C:\TEMP\halal_pmf_test\active_pmf_test.xlsm"
```

`PMF_UPDATE_PATH`를 지정하지 않으면 기존 `backend/cache/source_pmf/active_pmf.xlsm`만 수정한다. 네트워크 원본 PMF는 수정하지 않는다.

## 적용

ZIP을 별도 폴더에 풀고, `halal_web` 프로젝트 루트에서:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& "압축해제경로\apply_phase2.ps1"
```

## 실행 확인

```powershell
$env:HALAL_RAW_MATERIAL_ROOT = "C:\TEMP\halal_filing_test"
.\.venv\Scripts\Activate.ps1
cd .\backend
python -m uvicorn app.main:app --reload --port 8000
```

브라우저 확인:

- `http://127.0.0.1:8000/certificate-filing/status`
- `http://127.0.0.1:8000/certificate-filing/candidates`

## 주의

- `LOW_CONFIDENCE`, `MANUAL_REVIEW`는 기본 확정 차단
- 일반 인증서는 유효기간이 없으면 확정 차단
- BPJPH는 메일 요청항목과 예정 유효기간이 없으면 확정 차단
- 유효기간이 기존 PMF보다 과거이면 확정 차단
- `force=true`, `allow_date_regression=true`는 초기 테스트에서 사용하지 않는 것을 권장
