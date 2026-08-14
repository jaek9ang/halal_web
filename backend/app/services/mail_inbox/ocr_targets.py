"""OCR 대상 첨부 선정과 판독 결과 후보 저장."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from app.services.mail_inbox.text import (
    is_exact_pdf_ocr_candidate,
    now_text,
)
from app.services.mail_inbox.store import (
    get_db_conn,
    init_inbox_tables,
)


def auto_select_exact_inbound_ocr_targets(mail_id: int | None = None) -> dict[str, Any]:
    """
    기존 DB에 이미 저장된 EXACT PDF 첨부를 OCR 대상으로 자동 지정한다.
    """
    init_inbox_tables()

    conn = get_db_conn()
    cur = conn.cursor()

    params = []

    sql = """
        SELECT
            a.id,
            a.mail_id,
            a.saved_filename,
            a.original_filename,
            a.ext,
            m.match_status,
            COALESCE(m.is_excluded, 0) AS is_excluded
        FROM inbound_attachment a
        LEFT JOIN inbound_mail m ON a.mail_id = m.id
        WHERE m.match_status = 'exact'
          AND COALESCE(m.is_excluded, 0) = 0
    """

    if mail_id is not None:
        sql += " AND m.id = ?"
        params.append(int(mail_id))

    cur.execute(sql, params)
    rows = [dict(x) for x in cur.fetchall()]

    selected_ids = []
    skipped_rows = []

    for row in rows:
        filename = row.get("saved_filename") or row.get("original_filename") or ""
        ext = row.get("ext") or Path(filename).suffix.lower()

        if is_exact_pdf_ocr_candidate(filename=filename, ext=ext):
            selected_ids.append(int(row["id"]))
        else:
            skipped_rows.append({
                "id": int(row["id"]),
                "filename": filename,
                "reason": "PDF가 아니므로 자동 OCR 제외",
            })

    updated = 0

    if selected_ids:
        placeholders = ",".join(["?"] * len(selected_ids))

        cur.execute(
            f"""
            UPDATE inbound_attachment
            SET ocr_selected = 1
            WHERE id IN ({placeholders})
            """,
            selected_ids,
        )

        updated = cur.rowcount

    conn.commit()
    conn.close()

    return {
        "ok": True,
        "mail_id": mail_id,
        "checked": len(rows),
        "selected": len(selected_ids),
        "updated": updated,
        "skipped": len(skipped_rows),
        "selected_ids": selected_ids,
        "skipped_rows": skipped_rows[:30],
    }


def list_selected_inbound_ocr_targets(
    limit: int = 500,
    only_pending: bool = True,
) -> dict[str, Any]:
    """
    OCR 대상으로 저장된 첨부파일 목록.
    인증서 판독/일괄 판독에서 사용한다.
    """
    init_inbox_tables()

    conn = get_db_conn()
    cur = conn.cursor()

    params = []

    sql = """
        SELECT
            a.id,
            a.mail_id,
            a.request_id,
            a.original_filename,
            a.saved_filename,
            a.saved_path,
            a.ext,
            a.file_size,
            COALESCE(a.ocr_status, 'pending') AS ocr_status,
            COALESCE(a.ocr_selected, 0) AS ocr_selected,
            a.filename_date_candidates_json,
            a.created_at,
            m.subject,
            m.sender,
            m.received_at,
            m.match_status,
            m.mailbox,
            m.date_candidates_json AS mail_date_candidates_json,
            COALESCE(m.is_excluded, 0) AS is_excluded
        FROM inbound_attachment a
        LEFT JOIN inbound_mail m ON a.mail_id = m.id
        WHERE COALESCE(a.ocr_selected, 0) = 1
          AND COALESCE(m.is_excluded, 0) = 0
    """

    if only_pending:
        sql += """
          AND COALESCE(a.ocr_status, 'pending') IN ('pending', 'error', 'not_run', '')
        """

    sql += " ORDER BY a.id DESC LIMIT ?"
    params.append(int(limit))

    cur.execute(sql, params)
    rows = [dict(x) for x in cur.fetchall()]

    conn.close()

    return {
        "ok": True,
        "rows": rows,
        "count": len(rows),
    }


def save_inbound_ocr_candidate_result(
    attachment_id: int,
    ocr_job_id: int | None = None,
    status: str = "",
    filename: str = "",
    best_expiry: str = "",
    expiry_candidates: list[dict[str, Any]] | None = None,
    filename_candidates: list[dict[str, Any]] | None = None,
    mail_candidates: list[dict[str, Any]] | None = None,
    ocr_candidates: list[dict[str, Any]] | None = None,
    message: str = "",
) -> dict[str, Any]:
    """
    OCR 실행 후 파일명/메일본문/OCR 원문 날짜 후보를 통합 저장한다.
    """
    init_inbox_tables()

    expiry_candidates = expiry_candidates or []
    filename_candidates = filename_candidates or []
    mail_candidates = mail_candidates or []
    ocr_candidates = ocr_candidates or []

    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            a.id,
            a.mail_id,
            a.request_id,
            a.saved_filename,
            a.original_filename
        FROM inbound_attachment a
        WHERE a.id = ?
    """, (int(attachment_id),))

    row = cur.fetchone()

    if not row:
        conn.close()
        return {
            "ok": False,
            "message": "attachment_id를 찾지 못했습니다.",
            "attachment_id": attachment_id,
        }

    data = dict(row)

    final_filename = (
        filename
        or data.get("saved_filename")
        or data.get("original_filename")
        or ""
    )

    cur.execute("""
        INSERT INTO inbound_ocr_candidate (
            attachment_id,
            mail_id,
            request_id,
            ocr_job_id,
            filename,
            status,
            best_expiry,
            expiry_candidates_json,
            filename_candidates_json,
            mail_candidates_json,
            ocr_candidates_json,
            message,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        int(attachment_id),
        data.get("mail_id"),
        data.get("request_id") or "",
        ocr_job_id,
        final_filename,
        status,
        best_expiry,
        json.dumps(expiry_candidates, ensure_ascii=False),
        json.dumps(filename_candidates, ensure_ascii=False),
        json.dumps(mail_candidates, ensure_ascii=False),
        json.dumps(ocr_candidates, ensure_ascii=False),
        message,
        now_text(),
    ))

    next_status = "done" if str(status or "").upper() not in {"ERROR", "FAILED"} else "error"

    cur.execute("""
        UPDATE inbound_attachment
        SET ocr_status = ?
        WHERE id = ?
    """, (
        next_status,
        int(attachment_id),
    ))

    conn.commit()
    conn.close()

    return {
        "ok": True,
        "attachment_id": int(attachment_id),
        "ocr_job_id": ocr_job_id,
        "best_expiry": best_expiry,
        "candidate_count": len(expiry_candidates),
        "ocr_status": next_status,
    }
