"""OCR job 테이블 스키마와 연결."""

from __future__ import annotations

from app.core.config import OCR_OUTPUT_DIR, PMF_APP_DB_PATH
from app.core.db import connect as db_connect


def ensure_ocr_db() -> None:
    OCR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = db_connect(PMF_APP_DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ocr_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_path TEXT,
        filename TEXT,
        file_ext TEXT,
        status TEXT,
        raw_text TEXT,
        result_json TEXT,
        error_message TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """)

    conn.commit()
    conn.close()


def get_ocr_conn():
    ensure_ocr_db()
    return db_connect(PMF_APP_DB_PATH)
