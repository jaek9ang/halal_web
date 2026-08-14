from __future__ import annotations

import os
from pathlib import Path


# backend 폴더 기준 경로
BACKEND_DIR = Path(__file__).resolve().parents[2]


def _env_text(name: str, default: str) -> str:
    value = os.getenv(name, '').strip()
    return value or default


def _env_path(name: str, default: Path | str) -> Path:
    return Path(_env_text(name, str(default)))


# PMF 원본 폴더
# 공유폴더가 끊긴 개발 환경에서는 PMF_SOURCE_DIR 환경변수로 테스트 폴더를 사용한다.
PMF_SOURCE_DIR = _env_text(
    'PMF_SOURCE_DIR',
    r'\\홍진우\공유\1) 인증심사관련\4. MUI HALAL\★ 자사 PMF 파일',
)
PMF_FILE_PREFIX = 'Products and Materials File'

# 캐시 / 출력 / DB 경로
CACHE_DIR = BACKEND_DIR / 'cache'
PMF_CACHE_DIR = CACHE_DIR / 'source_pmf'
PMF_ACTIVE_PATH = _env_path(
    'PMF_ACTIVE_PATH',
    PMF_CACHE_DIR / 'active_pmf.xlsm',
)
PMF_META_PATH = PMF_CACHE_DIR / 'active_pmf_meta.json'

OUTPUT_DIR = BACKEND_DIR / 'output'
DB_DIR = BACKEND_DIR / 'db'
PMF_APP_DB_PATH = DB_DIR / 'pmf_app.db'

# 수신메일 / 첨부 다운로드
MAIL_RECEIVE_OUTPUT_DIR = OUTPUT_DIR / 'received_certs'
DAUM_IMAP_HOST = 'imap.daum.net'
DAUM_IMAP_PORT = 993
MAIL_INBOX_DOWNLOAD_DIR = _env_path(
    'MAIL_INBOX_DOWNLOAD_DIR',
    BACKEND_DIR / 'data' / 'mail_downloads',
)

# LHLN / BPJPH 안내 PDF 경로
LHLN_DB_PATH = DB_DIR / 'halal_lhln.db'
LHLN_BASE_URL = 'https://prod-api.halal.go.id/v1/referensi/data_lhln'
LHLN_OUTPUT_DIR = OUTPUT_DIR / 'lhln'
LHLN_GUIDE_PDF_PATH = LHLN_OUTPUT_DIR / 'BPJPH_교차인정기관_안내.pdf'

# 메일 로그 테이블명
MAIL_LOG_TABLE = 'mail_send_logs'

# PMF 시트명
RAW_MATERIAL_SHEET = 'Raw material management'
EMAIL_SHEET = 'E-mail'
MAIL_CONTENTS_SHEET = 'Mail Contents'

# OCR / 인증서 판독
OCR_OUTPUT_DIR = OUTPUT_DIR / 'ocr'

# HALAL 하부원료 서류 루트
HALAL_DOC_ROOT = _env_path(
    'HALAL_DOC_ROOT',
    r'\\홍진우\공유\1) 인증심사관련\4. MUI HALAL\2) HALAL 하부원료 서류\1)원재료',
)

# OCR 테스트 파일 DB / 업로드 경로
OCR_TEST_UPLOAD_DIR = BACKEND_DIR / 'data' / 'ocr_test_uploads'
OCR_TEST_DB_PATH = DB_DIR / 'ocr_test.db'

# 인증서 자동분류 이력 (JSONL)
FILING_DATA_DIR = BACKEND_DIR / 'data' / 'filing'
FILING_HISTORY_PATH = FILING_DATA_DIR / 'certificate_filing_history.jsonl'

# 인증서 양식 특징 DB
CERT_TEMPLATE_DB_PATH = DB_DIR / 'cert_template_features.db'

RUNTIME_DIRS = (
    CACHE_DIR,
    PMF_CACHE_DIR,
    OUTPUT_DIR,
    DB_DIR,
    MAIL_INBOX_DOWNLOAD_DIR,
    OCR_OUTPUT_DIR,
    OCR_TEST_UPLOAD_DIR,
)


def ensure_runtime_dirs() -> None:
    """런타임 폴더를 만든다.

    예전에는 이 모듈을 import하는 것만으로 폴더가 생겼다. 테스트나 스크립트가
    설정값 하나 읽으려고 import해도 디스크에 폴더가 생기는 부작용이 있어서
    앱 기동(`main.py`의 lifespan)에서 명시적으로 부르도록 분리했다.
    """
    for directory in RUNTIME_DIRS:
        directory.mkdir(parents=True, exist_ok=True)
