# 로컬 개발환경

기본 설치·기동 절차는 [README.md](../README.md)에 있다. 이 문서는 그 위에서 필요한
로컬 전용 설정을 다룬다.

## 왜 별도 설정이 필요한가

운영 환경은 Windows이고 PMF 원본과 하부원료 서류가 사내 공유폴더(UNC 경로)에 있다.
개발 PC에서 그 공유폴더에 붙지 못하면 앱이 기동 시점에 경로를 찾지 못한다.
그래서 로컬 테스트 폴더를 환경변수로 주입한다.

## Windows

`scripts/local_env.ps1.example`를 `scripts/local_env.ps1`로 복사해 값을 채운다.
`run_backend.ps1`이 기동 시 자동으로 읽는다 (이 파일은 gitignore 대상).

```powershell
$env:HALAL_RAW_MATERIAL_ROOT = 'C:\TEMP\halal_filing_test'
$env:HALAL_DOC_ROOT          = 'C:\TEMP\halal_filing_test'
$env:PMF_SOURCE_DIR          = 'C:\TEMP\halal_pmf_source'
```

PMF 기능을 테스트하려면 `PMF_SOURCE_DIR`에 실제 PMF `.xlsm` 복사본을 둔다.
파일명은 `Products and Materials File`로 시작해야 인식된다.

## macOS / Linux

`scripts/run_backend.sh`가 `.local_runtime/` 아래 폴더를 만들어 자동으로 주입한다.
직접 지정하려면 기동 전에 export 한다.

```bash
export PMF_SOURCE_DIR=~/halal_test/pmf
export HALAL_DOC_ROOT=~/halal_test/원재료
export HALAL_RAW_MATERIAL_ROOT=~/halal_test/원재료
```

공유폴더 연동이 필요한 기능(PMF 동기화, 인증서 자동분류의 실제 파일 복사)은
이 환경에서 동작하지 않는다. OCR 규칙·판정 로직은 정상 동작한다.

## 런타임 점검

의존 모듈과 tesseract 설치 상태를 한 번에 확인한다.

```bash
cd backend && ../.venv/bin/python scripts/verify_runtime.py
```

기동 확인:

```bash
curl http://127.0.0.1:8000/health     # {"ok":true}
```

## 외부 의존 도구

| 도구 | 용도 | 없으면 |
|---|---|---|
| Tesseract OCR | 기본 OCR 엔진 | OCR 판독 실패. `TESSERACT_CMD`, `TESSDATA_PREFIX`로 경로 지정 가능 |
| rapidocr (onnxruntime) | 보조 OCR 엔진 | requirements에 포함되어 별도 설치 불필요 |
| OpenAI API | AI 규칙 리뷰 | `/ai-rule-review` 기능만 사용 불가 (`OPENAI_API_KEY`) |
| Daum 메일 계정 | 발송·수신 | 메일 기능만 사용 불가 |

## 관련 문서

- [architecture.md](architecture.md) — 데이터 흐름과 모듈 지도
- [archive/conda-to-venv-migration.md](archive/conda-to-venv-migration.md) — 2026-06 Conda→.venv 전환 기록 (완료됨)
