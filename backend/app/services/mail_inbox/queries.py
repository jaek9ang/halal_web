"""수신함 화면이 쓰는 조회·상태 변경."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import os

from app.core.config import MAIL_INBOX_DOWNLOAD_DIR

from app.services.mail_inbox.parsing import (
    is_bounce_mail,
)
from app.services.mail_inbox.store import (
    get_db_conn,
    init_inbox_tables,
)


def list_inbound_mails(
    match_status: str = "",
    mailbox: str = "",
    include_excluded: bool = False,
    limit: int = 100,
) -> dict[str, Any]:
    init_inbox_tables()

    conn = get_db_conn()
    cur = conn.cursor()

    params = []
    where = []

    sql = """
        SELECT
            id,
            provider,
            mailbox,
            subject,
            sender,
            received_at,
            body_preview,
            matched_request_id,
            match_status,
            match_reason,
            attachment_count,
            download_dir,
            downloaded_at,
            is_excluded,
            exclude_reason
        FROM inbound_mail
    """

    if match_status:
        where.append("match_status = ?")
        params.append(match_status)

    if mailbox:
        where.append("mailbox = ?")
        params.append(mailbox)

    if not include_excluded:
        where.append("COALESCE(is_excluded, 0) = 0")

    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))

    cur.execute(sql, params)
    rows = [dict(x) for x in cur.fetchall()]

    conn.close()

    return {
        "rows": rows,
        "count": len(rows),
    }


def list_inbound_attachments(
    request_id: str = "",
    mailbox: str = "",
    limit: int = 200,
) -> dict[str, Any]:
    init_inbox_tables()

    conn = get_db_conn()
    cur = conn.cursor()

    params = []
    where = []

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
            a.ocr_status,
            a.ocr_selected,
            a.filename_date_candidates_json,
            a.created_at,
            m.subject,
            m.sender,
            m.received_at,
            m.match_status,
            m.mailbox,
            m.date_candidates_json AS mail_date_candidates_json
        FROM inbound_attachment a
        LEFT JOIN inbound_mail m ON a.mail_id = m.id
    """

    if request_id:
        where.append("a.request_id = ?")
        params.append(request_id)

    if mailbox:
        where.append("m.mailbox = ?")
        params.append(mailbox)

    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += " ORDER BY a.id DESC LIMIT ?"
    params.append(int(limit))

    cur.execute(sql, params)
    rows = [dict(x) for x in cur.fetchall()]

    conn.close()

    return {
        "rows": rows,
        "count": len(rows),
    }


def open_inbound_attachment_folder(saved_path: str) -> dict[str, Any]:
    """
    다운로드된 수신 메일 저장폴더 또는 첨부파일 폴더를 연다.
    상대경로/절대경로 모두 대응.
    """
    if not saved_path:
        return {
            "ok": False,
            "message": "saved_path가 없습니다.",
        }

    base = Path(MAIL_INBOX_DOWNLOAD_DIR).resolve()
    raw = Path(str(saved_path))

    candidates = []

    if raw.is_absolute():
        candidates.append(raw.resolve())
    else:
        candidates.append((Path.cwd() / raw).resolve())

        # saved_path가 data/mail_downloads 아래 상대경로가 아닌 경우 대비
        if not str(raw).replace("\\", "/").startswith("data/mail_downloads"):
            candidates.append((base / raw).resolve())

    target = None

    for candidate in candidates:
        if candidate.exists():
            target = candidate
            break

    if target is None:
        return {
            "ok": False,
            "message": "경로가 존재하지 않습니다.",
            "base": str(base),
            "candidates": [str(x) for x in candidates],
        }

    folder = target if target.is_dir() else target.parent

    # base 하위인지 확인
    try:
        folder.relative_to(base)
    except Exception:
        return {
            "ok": False,
            "message": "허용되지 않은 경로입니다.",
            "base": str(base),
            "path": str(folder),
        }

    try:
        os.startfile(str(folder))
        return {
            "ok": True,
            "path": str(folder),
        }
    except Exception as e:
        return {
            "ok": False,
            "message": str(e),
            "path": str(folder),
        }


def cleanup_bounced_inbound_records() -> dict[str, Any]:
    """
    이미 DB에 저장된 반송메일 기록을 삭제한다.
    파일 자체는 삭제하지 않고 DB 기록만 제거한다.
    """
    init_inbox_tables()

    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, subject, sender, body_text
        FROM inbound_mail
    """)

    rows = cur.fetchall()

    bounce_ids = []

    for row in rows:
        if is_bounce_mail(
            subject=row["subject"],
            sender=row["sender"],
            body_text=row["body_text"],
        ):
            bounce_ids.append(int(row["id"]))

    if not bounce_ids:
        conn.close()
        return {
            "ok": True,
            "deleted_mails": 0,
            "deleted_attachments": 0,
        }

    placeholders = ",".join(["?"] * len(bounce_ids))

    cur.execute(
        f"DELETE FROM inbound_attachment WHERE mail_id IN ({placeholders})",
        bounce_ids,
    )
    deleted_attachments = cur.rowcount

    cur.execute(
        f"DELETE FROM inbound_mail WHERE id IN ({placeholders})",
        bounce_ids,
    )
    deleted_mails = cur.rowcount

    conn.commit()
    conn.close()

    return {
        "ok": True,
        "deleted_mails": deleted_mails,
        "deleted_attachments": deleted_attachments,
    }


def get_inbound_mail_detail(mail_id: int) -> dict[str, Any]:
    init_inbox_tables()

    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM inbound_mail
        WHERE id = ?
    """, (int(mail_id),))

    row = cur.fetchone()
    conn.close()

    if not row:
        return {
            "ok": False,
            "message": "메일을 찾지 못했습니다.",
        }

    return {
        "ok": True,
        "mail": dict(row),
    }


def set_inbound_mail_excluded(
    mail_ids: list[int],
    excluded: bool = True,
    reason: str = "사용자 제외",
) -> dict[str, Any]:
    init_inbox_tables()

    ids = [int(x) for x in mail_ids if str(x).strip()]

    if not ids:
        return {
            "ok": False,
            "message": "대상 mail_id가 없습니다.",
        }

    conn = get_db_conn()
    cur = conn.cursor()

    placeholders = ",".join(["?"] * len(ids))

    cur.execute(
        f"""
        UPDATE inbound_mail
        SET is_excluded = ?, exclude_reason = ?
        WHERE id IN ({placeholders})
        """,
        [1 if excluded else 0, reason] + ids,
    )

    updated = cur.rowcount

    conn.commit()
    conn.close()

    return {
        "ok": True,
        "updated": updated,
        "excluded": excluded,
    }


def set_inbound_attachment_ocr_selected(
    attachment_ids: list[int],
    selected: bool = True,
) -> dict[str, Any]:
    init_inbox_tables()

    ids = [int(x) for x in attachment_ids if str(x).strip()]

    if not ids:
        return {
            "ok": False,
            "message": "대상 attachment_id가 없습니다.",
        }

    conn = get_db_conn()
    cur = conn.cursor()

    placeholders = ",".join(["?"] * len(ids))

    cur.execute(
        f"""
        UPDATE inbound_attachment
        SET ocr_selected = ?
        WHERE id IN ({placeholders})
        """,
        [1 if selected else 0] + ids,
    )

    updated = cur.rowcount

    conn.commit()
    conn.close()

    return {
        "ok": True,
        "updated": updated,
        "selected": selected,
    }
