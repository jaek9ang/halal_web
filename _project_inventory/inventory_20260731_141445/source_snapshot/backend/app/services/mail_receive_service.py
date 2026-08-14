import email
import imaplib
import os
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from email.header import decode_header
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from app.core.config import (
    DAUM_IMAP_HOST,
    DAUM_IMAP_PORT,
    MAIL_RECEIVE_OUTPUT_DIR,
    PMF_APP_DB_PATH,
)


REQUEST_ID_PATTERN = re.compile(
    r"(HALAL-REQ-\d{8}-[A-Z0-9]{6,12})",
    re.IGNORECASE,
)

DEFAULT_ALLOWED_EXTS = (
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".xlsx",
    ".xlsm",
    ".xls",
    ".docx",
    ".doc",
)


@dataclass
class MailPreviewRow:
    uid: str
    message_id: str
    subject: str
    sender: str
    to: str
    sent_at: str
    request_id: str
    body_preview: str
    attachment_count: int
    attachment_names: str


@dataclass
class DownloadedAttachmentRow:
    uid: str
    message_id: str
    subject: str
    sender: str
    to: str
    sent_at: str
    request_id: str
    body_preview: str
    filename: str
    filepath: str
    size_bytes: int
    downloaded_at: str


def ensure_receive_db() -> None:
    PMF_APP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(PMF_APP_DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS received_attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid TEXT,
        message_id TEXT,
        subject TEXT,
        sender TEXT,
        receiver TEXT,
        sent_at TEXT,
        request_id TEXT,
        body_preview TEXT,
        filename TEXT,
        filepath TEXT,
        size_bytes INTEGER,
        downloaded_at TEXT
    )
    """)

    conn.commit()
    conn.close()


def get_receive_conn():
    ensure_receive_db()
    conn = sqlite3.connect(PMF_APP_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def decode_mime_text(value: Any) -> str:
    if not value:
        return ""

    result = []

    for part, enc in decode_header(str(value)):
        if isinstance(part, bytes):
            for candidate in [enc, "utf-8", "cp949", "euc-kr", "latin1"]:
                if not candidate:
                    continue

                try:
                    result.append(part.decode(candidate, errors="ignore"))
                    break
                except Exception:
                    continue
            else:
                result.append(part.decode("utf-8", errors="ignore"))
        else:
            result.append(str(part))

    return "".join(result).strip()


def safe_filename(name: Any, fallback: str = "attachment") -> str:
    name = decode_mime_text(name or "")
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")

    if not name:
        name = fallback

    return name[:180]


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent

    for i in range(1, 1000):
        candidate = parent / f"{stem}_{i}{suffix}"

        if not candidate.exists():
            return candidate

    return parent / f"{stem}_{datetime.now().strftime('%H%M%S%f')}{suffix}"


def strip_html(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</p\s*>", "\n", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("&nbsp;", " ")
    value = value.replace("&amp;", "&")
    value = value.replace("&lt;", "<")
    value = value.replace("&gt;", ">")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def decode_part_payload(part: email.message.Message) -> str:
    payload = part.get_payload(decode=True)

    if payload is None:
        return ""

    charset = part.get_content_charset() or "utf-8"

    for enc in [charset, "utf-8", "cp949", "euc-kr", "latin1"]:
        try:
            return payload.decode(enc, errors="ignore")
        except Exception:
            continue

    return payload.decode("utf-8", errors="ignore")


def get_message_body_text(msg: email.message.Message) -> str:
    plain_parts = []
    html_parts = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", "")).lower()

            if "attachment" in disposition:
                continue

            if content_type == "text/plain":
                plain_parts.append(decode_part_payload(part))
            elif content_type == "text/html":
                html_parts.append(strip_html(decode_part_payload(part)))
    else:
        content_type = msg.get_content_type()
        text = decode_part_payload(msg)

        if content_type == "text/html":
            html_parts.append(strip_html(text))
        else:
            plain_parts.append(text)

    body = "\n".join([x for x in plain_parts if x.strip()]).strip()

    if body:
        return re.sub(r"\s+", " ", body).strip()

    body = "\n".join([x for x in html_parts if x.strip()]).strip()
    return re.sub(r"\s+", " ", body).strip()


def extract_request_id(*texts: str) -> str:
    for text in texts:
        if not text:
            continue

        match = REQUEST_ID_PATTERN.search(str(text))

        if match:
            return match.group(1).upper()

    return ""


def parse_sent_at(date_header: str) -> str:
    if not date_header:
        return ""

    try:
        return parsedate_to_datetime(date_header).isoformat(timespec="seconds")
    except Exception:
        return date_header


def open_daum_imap(
    user_email: str,
    app_password: str,
    mailbox: str = "INBOX",
    readonly: bool = True,
) -> imaplib.IMAP4_SSL:
    user_email = str(user_email or "").strip() or os.getenv("DAUM_EMAIL", "").strip()
    app_password = str(app_password or "").strip() or os.getenv("DAUM_APP_PASSWORD", "").strip()

    if not user_email:
        raise ValueError("Daum 메일 주소가 없습니다.")

    if not app_password:
        raise ValueError("Daum 앱 비밀번호가 없습니다.")

    conn = imaplib.IMAP4_SSL(DAUM_IMAP_HOST, DAUM_IMAP_PORT)
    conn.login(user_email, app_password)

    status, _ = conn.select(mailbox, readonly=readonly)

    if status != "OK":
        conn.logout()
        raise RuntimeError(f"메일함 선택 실패: {mailbox}")

    return conn


def test_daum_imap_login(
    user_email: str,
    app_password: str,
    mailbox: str = "INBOX",
) -> dict[str, Any]:
    try:
        conn = open_daum_imap(
            user_email=user_email,
            app_password=app_password,
            mailbox=mailbox,
            readonly=True,
        )
        conn.logout()

        return {
            "ok": True,
            "message": "Daum IMAP 접속 성공",
        }

    except Exception as e:
        return {
            "ok": False,
            "message": str(e),
        }


def fetch_recent_messages(
    user_email: str,
    app_password: str,
    mailbox: str = "INBOX",
    limit: int = 30,
    keyword: str = "",
    sender_keyword: str = "",
    request_id: str = "",
    mark_seen: bool = False,
) -> dict[str, Any]:
    limit = max(1, min(int(limit or 30), 300))
    keyword = str(keyword or "").strip().lower()
    sender_keyword = str(sender_keyword or "").strip().lower()
    request_id = str(request_id or "").strip().upper()

    conn = open_daum_imap(
        user_email=user_email,
        app_password=app_password,
        mailbox=mailbox,
        readonly=(not mark_seen),
    )

    try:
        status, data = conn.uid("search", None, "ALL")

        if status != "OK":
            return {
                "rows": [],
                "message": "메일 검색 실패",
            }

        uids = data[0].split()
        uids = uids[-limit:]

        fetch_arg = "(RFC822)" if mark_seen else "(BODY.PEEK[])"
        rows = []

        for uid_b in reversed(uids):
            uid = uid_b.decode("ascii", errors="ignore")

            status, msg_data = conn.uid("fetch", uid_b, fetch_arg)

            if status != "OK" or not msg_data or not msg_data[0]:
                continue

            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = decode_mime_text(msg.get("Subject", ""))
            sender = decode_mime_text(msg.get("From", ""))
            to = decode_mime_text(msg.get("To", ""))
            date_header = decode_mime_text(msg.get("Date", ""))
            sent_at = parse_sent_at(date_header)
            message_id = decode_mime_text(msg.get("Message-ID", ""))
            body_text = get_message_body_text(msg)

            attachment_names = []

            for part in msg.walk():
                filename = part.get_filename()

                if filename:
                    attachment_names.append(safe_filename(filename))

            rid = extract_request_id(
                subject,
                body_text,
                " ".join(attachment_names),
            )

            filter_blob = f"{subject} {sender} {to} {body_text} {' '.join(attachment_names)}".lower()

            if keyword and keyword not in filter_blob:
                continue

            if sender_keyword and sender_keyword not in sender.lower():
                continue

            if request_id and request_id != rid:
                continue

            rows.append(asdict(MailPreviewRow(
                uid=uid,
                message_id=message_id,
                subject=subject,
                sender=sender,
                to=to,
                sent_at=sent_at,
                request_id=rid,
                body_preview=body_text[:700],
                attachment_count=len(attachment_names),
                attachment_names="; ".join(attachment_names),
            )))

        return {
            "rows": rows,
            "count": len(rows),
        }

    finally:
        try:
            conn.logout()
        except Exception:
            pass


def save_received_attachment(row: DownloadedAttachmentRow) -> None:
    ensure_receive_db()

    conn = get_receive_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO received_attachments (
        uid,
        message_id,
        subject,
        sender,
        receiver,
        sent_at,
        request_id,
        body_preview,
        filename,
        filepath,
        size_bytes,
        downloaded_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        row.uid,
        row.message_id,
        row.subject,
        row.sender,
        row.to,
        row.sent_at,
        row.request_id,
        row.body_preview,
        row.filename,
        row.filepath,
        row.size_bytes,
        row.downloaded_at,
    ))

    conn.commit()
    conn.close()


def download_recent_attachments(
    user_email: str,
    app_password: str,
    mailbox: str = "INBOX",
    limit: int = 30,
    keyword: str = "",
    sender_keyword: str = "",
    request_id: str = "",
    allowed_exts: list[str] | None = None,
    mark_seen: bool = False,
) -> dict[str, Any]:
    limit = max(1, min(int(limit or 30), 300))
    keyword = str(keyword or "").strip().lower()
    sender_keyword = str(sender_keyword or "").strip().lower()
    request_id = str(request_id or "").strip().upper()

    if allowed_exts:
        allowed = []
        for ext in allowed_exts:
            ext = str(ext or "").strip().lower()

            if not ext:
                continue

            if not ext.startswith("."):
                ext = "." + ext

            allowed.append(ext)

        allowed_exts = allowed
    else:
        allowed_exts = list(DEFAULT_ALLOWED_EXTS)

    MAIL_RECEIVE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = open_daum_imap(
        user_email=user_email,
        app_password=app_password,
        mailbox=mailbox,
        readonly=(not mark_seen),
    )

    downloaded_rows = []

    try:
        status, data = conn.uid("search", None, "ALL")

        if status != "OK":
            return {
                "rows": [],
                "count": 0,
                "message": "메일 검색 실패",
            }

        uids = data[0].split()
        uids = uids[-limit:]

        fetch_arg = "(RFC822)" if mark_seen else "(BODY.PEEK[])"

        for uid_b in reversed(uids):
            uid = uid_b.decode("ascii", errors="ignore")

            status, msg_data = conn.uid("fetch", uid_b, fetch_arg)

            if status != "OK" or not msg_data or not msg_data[0]:
                continue

            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = decode_mime_text(msg.get("Subject", ""))
            sender = decode_mime_text(msg.get("From", ""))
            to = decode_mime_text(msg.get("To", ""))
            date_header = decode_mime_text(msg.get("Date", ""))
            sent_at = parse_sent_at(date_header)
            message_id = decode_mime_text(msg.get("Message-ID", ""))
            body_text = get_message_body_text(msg)

            attachment_names = [
                safe_filename(part.get_filename())
                for part in msg.walk()
                if part.get_filename()
            ]

            rid = extract_request_id(
                subject,
                body_text,
                " ".join(attachment_names),
            )

            filter_blob = f"{subject} {sender} {to} {body_text} {' '.join(attachment_names)}".lower()

            if keyword and keyword not in filter_blob:
                continue

            if sender_keyword and sender_keyword not in sender.lower():
                continue

            if request_id and request_id != rid:
                continue

            date_folder = datetime.now().strftime("%Y%m%d")
            rid_folder = rid if rid else "no_request_id"
            subject_folder = safe_filename(subject or f"mail_{uid}")[:80]

            save_dir = MAIL_RECEIVE_OUTPUT_DIR / date_folder / rid_folder / subject_folder
            save_dir.mkdir(parents=True, exist_ok=True)

            for part_idx, part in enumerate(msg.walk(), start=1):
                filename = part.get_filename()

                if not filename:
                    continue

                filename = safe_filename(filename, fallback=f"attachment_{part_idx}")
                ext = Path(filename).suffix.lower()

                if allowed_exts and ext not in allowed_exts:
                    continue

                payload = part.get_payload(decode=True)

                if payload is None:
                    continue

                out_path = unique_path(save_dir / filename)

                with open(out_path, "wb") as f:
                    f.write(payload)

                row = DownloadedAttachmentRow(
                    uid=uid,
                    message_id=message_id,
                    subject=subject,
                    sender=sender,
                    to=to,
                    sent_at=sent_at,
                    request_id=rid,
                    body_preview=body_text[:700],
                    filename=out_path.name,
                    filepath=str(out_path),
                    size_bytes=len(payload),
                    downloaded_at=datetime.now().isoformat(timespec="seconds"),
                )

                save_received_attachment(row)
                downloaded_rows.append(asdict(row))

        return {
            "rows": downloaded_rows,
            "count": len(downloaded_rows),
            "output_dir": str(MAIL_RECEIVE_OUTPUT_DIR),
        }

    finally:
        try:
            conn.logout()
        except Exception:
            pass


def get_received_attachment_logs(limit: int = 100) -> dict[str, Any]:
    ensure_receive_db()

    limit = max(1, min(int(limit), 500))

    conn = get_receive_conn()

    rows = conn.execute("""
        SELECT *
        FROM received_attachments
        ORDER BY id DESC
        LIMIT ?
    """, (limit,)).fetchall()

    conn.close()

    return {
        "rows": [dict(row) for row in rows],
    }