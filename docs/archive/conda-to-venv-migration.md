# 로컬 개발환경 전환 절차

## 적용 위치

이 ZIP의 내용은 `halal_web` 프로젝트 루트에 덮어쓴다.

```text
halal_web/
├─ .venv/
├─ backend/
├─ frontend/
├─ scripts/
├─ .gitignore
└─ CHANGELOG.md
```

## 1. Conda 환경은 바로 삭제하지 않는다

`.venv` 검증이 끝날 때까지 기존 Conda 환경을 보관한다.

## 2. `.venv` 생성

프로젝트 루트 PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup_venv.ps1
```

현재 환경과 맞추기 위해 Python 3.10을 사용한다.

## 3. 테스트 경로 확인

`scripts/local_env.ps1` 기본값:

```text
HALAL_RAW_MATERIAL_ROOT=C:\TEMP\halal_filing_test
HALAL_DOC_ROOT=C:\TEMP\halal_filing_test
PMF_SOURCE_DIR=C:\TEMP\halal_pmf_source
```

PMF 기능을 테스트하려면 `C:\TEMP\halal_pmf_source`에 실제 PMF xlsm 복사본을 둔다.

## 4. 런타임 검증

```powershell
cd .\backend
..\.venv\Scripts\python.exe .\scripts\verify_runtime.py
```

## 5. 백엔드 실행

프로젝트 루트:

```powershell
.\scripts\run_backend.ps1
```

확인:

```text
http://127.0.0.1:8000/health
```

## 6. 로컬 Git 초기화

원격 저장소를 만들거나 연결하지 않는다.

```powershell
.\scripts\init_local_git.ps1
```

작업 단위 저장:

```powershell
.\scripts\git_checkpoint.ps1 -Message "feat: 파일자동분류 백엔드 1차 연결"
```

변경이력 확인:

```powershell
.\scripts\git_log.ps1
```

## 7. Conda 환경 정리 시점

다음 조건을 모두 통과한 뒤에만 기존 Conda 환경 삭제를 검토한다.

- `verify_runtime.py` 통과
- `/health` 정상
- OCR 테스트 정상
- PMF 읽기 정상
- 파일 복사 테스트 정상
- OpenAI 규칙 리뷰 정상
