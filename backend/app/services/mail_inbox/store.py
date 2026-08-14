"""수신메일 테이블 스키마와 저장."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import json

from app.core.config import PMF_APP_DB_PATH, MAIL_INBOX_DOWNLOAD_DIR
from app.core.db import connect as db_connect

from app.services.mail_inbox.text import (
    is_exact_pdf_ocr_candidate,
    now_text,
    safe_filename,
)
from app.services.mail_inbox.parsing import (
    extract_date_candidates_from_text,
)


def get_db_conn():
    return db_connect(PMF_APP_DB_PATH)


def init_inbox_tables():
    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inbound_mail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT,
            mailbox TEXT,
            message_uid TEXT UNIQUE,
            subject TEXT,
            sender TEXT,
            received_at TEXT,
            body_text TEXT,
            matched_request_id TEXT,
            match_status TEXT,
            match_reason TEXT,
            attachment_count INTEGER DEFAULT 0,
            download_dir TEXT,
            downloaded_at TEXT
        )
    """)

        # 기존 DB에 컬럼 추가. 이미 있으면 무시.
    for col_name, col_type in [
        ("is_excluded", "INTEGER DEFAULT 0"),
        ("exclude_reason", "TEXT"),
        ("body_preview", "TEXT"),
    ]:
        try:
            cur.execute(f"ALTER TABLE inbound_mail ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inbound_attachment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mail_id INTEGER,
            request_id TEXT,
            original_filename TEXT,
            saved_filename TEXT,
            saved_path TEXT,
            ext TEXT,
            file_size INTEGER,
            ocr_status TEXT DEFAULT 'pending',
            created_at TEXT,
            FOREIGN KEY(mail_id) REFERENCES inbound_mail(id)
        )
    """)

        # 후보 날짜 저장 컬럼. 기존 DB에는 ALTER로 보강.
    for col_name, col_type in [
        ("date_candidates_json", "TEXT"),
    ]:
        try:
            cur.execute(f"ALTER TABLE inbound_mail ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass

    for col_name, col_type in [
        ("ocr_selected", "INTEGER DEFAULT 0"),
        ("filename_date_candidates_json", "TEXT"),
    ]:
        try:
            cur.execute(f"ALTER TABLE inbound_attachment ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inbound_ocr_candidate (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attachment_id INTEGER,
            mail_id INTEGER,
            request_id TEXT,
            ocr_job_id INTEGER,
            filename TEXT,
            status TEXT,
            best_expiry TEXT,
            expiry_candidates_json TEXT,
            filename_candidates_json TEXT,
            mail_candidates_json TEXT,
            ocr_candidates_json TEXT,
            message TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_inbound_ocr_candidate_attachment
        ON inbound_ocr_candidate(attachment_id)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_inbound_ocr_candidate_request
        ON inbound_ocr_candidate(request_id)
    """)

    # 기존 inbound_ocr_candidate 테이블에 새 컬럼 보강
    for col_name, col_type in [
        ("filename_candidates_json", "TEXT"),
        ("mail_candidates_json", "TEXT"),
        ("ocr_candidates_json", "TEXT"),
    ]:
        try:
            cur.execute(f"ALTER TABLE inbound_ocr_candidate ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass

    conn.commit()
    conn.close()


def make_download_dir(request_id: str, received_at: str, sender: str) -> Path:
    """
    수신일 + 관리번호 기준 저장.

    관리번호 있음:
    data/mail_downloads/2026-05-06/HALAL-REQ-...

    관리번호 없음:
    data/mail_downloads/_unmatched/2026-05-06/MAIL-20260506-142509-XXXXXX
    """
    base = Path(MAIL_INBOX_DOWNLOAD_DIR)

    date_text = ""

    try:
        date_text = str(received_at or "")[:10]
        datetime.strptime(date_text, "%Y-%m-%d")
    except Exception:
        date_text = datetime.now().strftime("%Y-%m-%d")

    if request_id:
        folder = base / date_text / request_id
    else:
        stamp = (
            str(received_at or "")
            .replace("-", "")
            .replace(":", "")
            .replace(" ", "_")
        )

        if not stamp:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        sender_key = safe_filename(sender.split("<")[-1].replace(">", ""), "unknown_sender")
        sender_hash = abs(hash(sender_key)) % 1000000

        folder = base / "_unmatched" / date_text / f"MAIL-{stamp}-{sender_hash:06d}"

    folder.mkdir(parents=True, exist_ok=True)

    return folder


def save_message_files(folder: Path, meta: dict[str, Any], body_text: str):
    meta_path = folder / "mail_meta.json"
    body_path = folder / "body.txt"

    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    body_path.write_text(body_text or "", encoding="utf-8")


def insert_inbound_mail(meta: dict[str, Any]) -> tuple[int, bool]:
    """
    return: (mail_id, inserted_new)
    """
    init_inbox_tables()

    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM inbound_mail WHERE message_uid = ?",
        (meta["message_uid"],),
    )
    existing = cur.fetchone()

    if existing:
        mail_id = int(existing["id"])
        conn.close()
        return mail_id, False

    cur.execute("""
        INSERT INTO inbound_mail (
            provider,
            mailbox,
            message_uid,
            subject,
            sender,
            received_at,
            body_text,
            body_preview,
            matched_request_id,
            match_status,
            match_reason,
            attachment_count,
            download_dir,
            downloaded_at,
            is_excluded,
            exclude_reason,
            date_candidates_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        meta.get("provider", "daum"),
        meta.get("mailbox", "INBOX"),
        meta.get("message_uid", ""),
        meta.get("subject", ""),
        meta.get("sender", ""),
        meta.get("received_at", ""),
        meta.get("body_text", ""),
        meta.get("body_preview", ""),
        meta.get("matched_request_id", ""),
        meta.get("match_status", "unmatched_candidate"),
        meta.get("match_reason", ""),
        int(meta.get("attachment_count", 0)),
        meta.get("download_dir", ""),
        now_text(),
        int(meta.get("is_excluded", 0)),
        meta.get("exclude_reason", ""),
        meta.get("date_candidates_json", "[]"),
    ))

    mail_id = int(cur.lastrowid)

    conn.commit()
    conn.close()

    return mail_id, True


def insert_attachment(
    mail_id: int,
    request_id: str,
    original_filename: str,
    saved_filename: str,
    saved_path: str,
    file_size: int,
    match_status: str = "",
):
    init_inbox_tables()

    ext = Path(saved_filename).suffix.lower()

    filename_candidates = extract_date_candidates_from_text(
        saved_filename or original_filename,
        source="filename",
    )

    ocr_selected = 1 if (
        str(match_status or "").lower() == "exact"
        and is_exact_pdf_ocr_candidate(filename=saved_filename, ext=ext)
    ) else 0

    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO inbound_attachment (
            mail_id,
            request_id,
            original_filename,
            saved_filename,
            saved_path,
            ext,
            file_size,
            ocr_status,
            ocr_selected,
            filename_date_candidates_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        mail_id,
        request_id or "",
        original_filename,
        saved_filename,
        saved_path,
        ext,
        file_size,
        "pending",
        int(ocr_selected),
        json.dumps(filename_candidates, ensure_ascii=False),
        now_text(),
    ))

    conn.commit()
    conn.close()


def init_inbound_ocr_candidate_table():
    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inbound_ocr_candidate (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attachment_id INTEGER,
            mail_id INTEGER,
            request_id TEXT,
            ocr_job_id INTEGER,
            filename TEXT,
            status TEXT,
            best_expiry TEXT,
            expiry_candidates_json TEXT,
            message TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_inbound_ocr_candidate_attachment
        ON inbound_ocr_candidate(attachment_id)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_inbound_ocr_candidate_request
        ON inbound_ocr_candidate(request_id)
    """)

    conn.commit()
    conn.close()
