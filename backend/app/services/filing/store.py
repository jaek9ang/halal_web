"""인증서 자동분류 관련 테이블 스키마와 연결."""

from __future__ import annotations

import sqlite3

from app.core.config import PMF_APP_DB_PATH
from app.core.db import connect as db_connect


def get_conn() -> sqlite3.Connection:
    return db_connect(PMF_APP_DB_PATH)


def _ensure_filing_history_unique_index(conn) -> None:
    final_statuses = (
        "CONFIRMED",
        "REPLACED",
        "SECONDARY_ADDED",
        "DUPLICATE_SKIPPED",
    )

    placeholders = ", ".join(
        "?" for _ in final_statuses
    )

    duplicate_sql = (
        "SELECT ocr_job_id, COUNT(*) AS row_count "
        "FROM certificate_filing_history "
        "WHERE ocr_job_id IS NOT NULL "
        "AND status IN (" + placeholders + ") "
        "GROUP BY ocr_job_id "
        "HAVING COUNT(*) > 1"
    )

    duplicate_rows = conn.execute(
        duplicate_sql,
        final_statuses,
    ).fetchall()

    if duplicate_rows:
        duplicate_ids = ", ".join(
            str(row[0])
            for row in duplicate_rows
        )

        raise RuntimeError(
            "Duplicate confirmed OCR jobs exist: "
            + duplicate_ids
        )

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "idx_certificate_filing_ocr_job_all "
        "ON certificate_filing_history(ocr_job_id) "
        "WHERE status IN ("
        "'CONFIRMED', "
        "'REPLACED', "
        "'SECONDARY_ADDED', "
        "'DUPLICATE_SKIPPED'"
        ")"
    )


def ensure_filing_tables() -> None:
    conn = get_conn()

    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS certificate_filing_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ocr_job_id INTEGER,
                request_id TEXT,
                pmf_row_pos INTEGER,
                pmf_depth INTEGER,
                source_path TEXT,
                target_path TEXT,
                cert_org TEXT,
                cert_no TEXT,
                expiry_date TEXT,
                status TEXT,
                copy_status TEXT,
                pmf_update_json TEXT,
                warning_json TEXT,
                error_message TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_certificate_filing_ocr_job
            ON certificate_filing_history(ocr_job_id)
            WHERE status IN (
                'CONFIRMED',
                'DUPLICATE_SKIPPED'
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS
            material_certificate_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ocr_job_id INTEGER,
                request_id TEXT,
                pmf_row_pos INTEGER NOT NULL,
                pmf_depth INTEGER NOT NULL DEFAULT 0,
                cert_org TEXT,
                cert_no TEXT,
                expiry_date TEXT,
                manufacturer TEXT,
                source_path TEXT,
                target_path TEXT,
                certificate_role TEXT NOT NULL,
                status TEXT NOT NULL,
                change_action TEXT,
                is_primary INTEGER NOT NULL DEFAULT 0,
                supersedes_id INTEGER,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_material_certificate_material
            ON material_certificate_history(
                pmf_row_pos,
                pmf_depth,
                status,
                is_primary
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_material_certificate_ocr_job
            ON material_certificate_history(
                ocr_job_id
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_material_certificate_number
            ON material_certificate_history(
                cert_org,
                cert_no
            )
            """
        )

        _ensure_filing_history_unique_index(conn)
        conn.commit()

    finally:
        conn.close()
