import imaplib
import email
import json
import re
import os
import sqlite3
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from app.core.config import PMF_APP_DB_PATH, MAIL_INBOX_DOWNLOAD_DIR


REQUEST_ID_PATTERN = re.compile(
    r"HALAL-REQ-\d{8}-[A-Z0-9]+",
    re.IGNORECASE,
)


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def quote_imap_mailbox(mailbox: str) -> str:
    """
    IMAP SELECT용 메일함 이름 quote 처리.
    공백/한글/modified UTF-7 폴더명을 안전하게 선택하기 위함.
    """
    text = str(mailbox or "").strip()

    if not text:
        text = "Inbox"

    if text.startswith('"') and text.endswith('"'):
        return text

    text = text.replace("\\", "\\\\").replace('"', '\\"')

    return f'"{text}"'

def safe_filename(value: str, default: str = "file") -> str:
    text = str(value or "").strip()

    if not text:
        text = default

    text = re.sub(r'[\\/:*?"<>|]+', "_", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text[:180] if len(text) > 180 else text


def decode_mime_text(value: Any) -> str:
    if not value:
        return ""

    decoded_parts = []

    for part, enc in decode_header(value):
        if isinstance(part, bytes):
            try:
                decoded_parts.append(part.decode(enc or "utf-8", errors="replace"))
            except Exception:
                decoded_parts.append(part.decode("utf-8", errors="replace"))
        else:
            decoded_parts.append(str(part))

    return "".join(decoded_parts).strip()


def parse_received_at(msg) -> str:
    raw_date = msg.get("Date", "")

    try:
        dt = parsedate_to_datetime(raw_date)

        if dt.tzinfo:
            dt = dt.astimezone().replace(tzinfo=None)

        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def extract_body_text(msg) -> str:
    texts = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "").lower()

            if "attachment" in disposition:
                continue

            if content_type not in {"text/plain", "text/html"}:
                continue

            try:
                payload = part.get_payload(decode=True)

                if not payload:
                    continue

                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")

                if content_type == "text/html":
                    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
                    text = re.sub(r"</p>", "\n", text, flags=re.I)
                    text = re.sub(r"<[^>]+>", " ", text)
                    text = re.sub(r"\s+", " ", text)

                texts.append(text.strip())
            except Exception:
                continue
    else:
        try:
            payload = msg.get_payload(decode=True)

            if payload:
                charset = msg.get_content_charset() or "utf-8"
                texts.append(payload.decode(charset, errors="replace").strip())
        except Exception:
            pass

    return "\n\n".join([x for x in texts if x])


def get_attachment_parts(msg) -> list[dict[str, Any]]:
    rows = []

    for part in msg.walk():
        filename = decode_mime_text(part.get_filename())

        disposition = str(part.get("Content-Disposition") or "").lower()

        if not filename and "attachment" not in disposition:
            continue

        payload = part.get_payload(decode=True)

        if not payload:
            continue

        rows.append({
            "filename": filename or "attachment",
            "content_type": part.get_content_type(),
            "payload": payload,
        })

    return rows


def find_request_id(*texts: str) -> str:
    for text in texts:
        if not text:
            continue

        m = REQUEST_ID_PATTERN.search(str(text))

        if m:
            return m.group(0).upper()

    return ""

def normalize_candidate_text(value: str) -> str:
    """
    파일명/메일본문/OCR 원문에서 날짜 후보 추출 전에 텍스트를 정리한다.
    """
    text = str(value or "")
    text = text.replace("&nbsp;", " ")
    text = text.replace("\r", "\n")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def to_iso_date(year: str, month: str, day: str) -> str:
    try:
        y = int(year)
        m = int(month)
        d = int(day)

        if y < 2000 or y > 2100:
            return ""

        if m < 1 or m > 12:
            return ""

        if d < 1 or d > 31:
            return ""

        return f"{y:04d}-{m:02d}-{d:02d}"
    except Exception:
        return ""


def extract_date_candidates_from_text(
    text: str,
    source: str = "unknown",
) -> list[dict[str, Any]]:
    """
    파일명/메일제목/메일본문/OCR 원문에서 날짜 후보를 추출한다.
    여기서 뽑은 날짜는 '확정 유효기간'이 아니라 '후보'다.
    """
    value = normalize_candidate_text(text)
    low = value.lower()

    month_map = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }

    anchors = [
        "valid",
        "validity",
        "until",
        "expiry",
        "expired",
        "expiration",
        "expire",
        "berlaku",
        "hingga",
        "sampai",
        "유효",
        "만료",
        "유효기간",
        "기간",
        "~",
    ]

    candidates: list[dict[str, Any]] = []

    def add_candidate(date_text: str, index: int, raw: str, pattern: str):
        if not date_text:
            return

        start = max(0, int(index or 0) - 100)
        end = min(len(low), int(index or 0) + 140)
        around = low[start:end]

        has_anchor = any(anchor in around for anchor in anchors)

        score = 90 if has_anchor else 50

        if source == "filename":
            # 파일명 날짜는 강한 후보지만 확정값은 아님
            score += 8

        candidates.append({
            "date": date_text,
            "raw": raw,
            "source": source,
            "pattern": pattern,
            "score": score,
            "reason": "anchor 주변 날짜" if has_anchor else "일반 날짜 후보",
        })

    # 2026-09-23 / 2026.09.23 / 2026/09/23 / 2026년 9월 23일
    for m in re.finditer(
        r"(20\d{2})[.\-/년\s]+(0?[1-9]|1[0-2])[.\-/월\s]+(0?[1-9]|[12]\d|3[01])",
        value,
    ):
        add_candidate(
            to_iso_date(m.group(1), m.group(2), m.group(3)),
            m.start(),
            m.group(0),
            "YYYY-MM-DD",
        )

    # 23 September 2026
    month_names = "|".join(month_map.keys())

    for m in re.finditer(
        rf"\b(0?[1-9]|[12]\d|3[01])\s+({month_names})\s+(20\d{{2}})\b",
        value,
        flags=re.I,
    ):
        month_no = month_map.get(m.group(2).lower(), 0)

        add_candidate(
            to_iso_date(m.group(3), str(month_no), m.group(1)),
            m.start(),
            m.group(0),
            "DD Month YYYY",
        )

    # September 23, 2026
    for m in re.finditer(
        rf"\b({month_names})\s+(0?[1-9]|[12]\d|3[01]),?\s+(20\d{{2}})\b",
        value,
        flags=re.I,
    ):
        month_no = month_map.get(m.group(1).lower(), 0)

        add_candidate(
            to_iso_date(m.group(3), str(month_no), m.group(2)),
            m.start(),
            m.group(0),
            "Month DD YYYY",
        )

    # 중복 제거. 같은 날짜면 점수 높은 후보만 유지.
    unique: dict[str, dict[str, Any]] = {}

    for item in candidates:
        date_key = item.get("date", "")

        if not date_key:
            continue

        prev = unique.get(date_key)

        if not prev or int(item.get("score", 0)) > int(prev.get("score", 0)):
            unique[date_key] = item

    return sorted(
        unique.values(),
        key=lambda x: (-int(x.get("score", 0)), str(x.get("date", ""))),
    )[:10]


def merge_expiry_candidates(*candidate_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    filename/mail/ocr 후보를 합쳐 같은 날짜는 최고 점수 기준으로 정리한다.
    """
    merged: dict[str, dict[str, Any]] = {}

    for candidate_list in candidate_lists:
        for item in candidate_list or []:
            date_key = item.get("date", "")

            if not date_key:
                continue

            prev = merged.get(date_key)

            if not prev or int(item.get("score", 0)) > int(prev.get("score", 0)):
                merged[date_key] = item

    return sorted(
        merged.values(),
        key=lambda x: (-int(x.get("score", 0)), str(x.get("date", ""))),
    )[:10]

def normalize_mail_subject(text: str) -> str:
    """
    RE/FW 접두어와 불필요 공백 제거.
    보낸 제목과 받은 제목 유사 비교용.
    """
    value = str(text or "").strip().lower()

    value = re.sub(r"^\s*(re|fw|fwd)\s*:\s*", "", value, flags=re.I)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def strip_html_text(text: str) -> str:
    value = str(text or "")

    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"</p>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def extract_simple_terms(text: str, max_terms: int = 80) -> list[str]:
    """
    발송 로그 본문/제목에서 비교에 쓸 원료명/업체명 후보를 넓게 추출.
    너무 짧은 단어는 제외.
    """
    value = strip_html_text(text)

    chunks = re.split(r"[\n\r,/|;:()\[\]<>]+", value)

    terms = []

    for chunk in chunks:
        t = str(chunk or "").strip()

        if len(t) < 3:
            continue

        if len(t) > 80:
            continue

        low = t.lower()

        stop_words = [
            "안녕하십니까",
            "확인 요청",
            "부탁드립니다",
            "감사합니다",
            "sewoo",
            "halal",
            "certificate",
            "request",
            "valid",
            "until",
        ]

        if any(x in low for x in stop_words):
            continue

        terms.append(t)

    # 중복 제거
    result = []
    seen = set()

    for t in terms:
        key = t.lower()

        if key in seen:
            continue

        seen.add(key)
        result.append(t)

        if len(result) >= max_terms:
            break

    return result


def get_sent_mail_reference_context(limit: int = 500) -> dict[str, Any]:
    """
    발송 로그 DB에서 보낸 제목/관리번호/업체명/본문 원료명 후보를 읽는다.
    테이블명이 바뀌어도 최대한 찾도록 sqlite_master를 스캔한다.
    """
    init_inbox_tables()

    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
    """)

    tables = [x["name"] for x in cur.fetchall()]

    target_tables = []

    for table in tables:
      try:
          cur.execute(f"PRAGMA table_info({table})")
          cols = [r["name"] for r in cur.fetchall()]
          colset = set(cols)

          if {"request_id", "subject"}.issubset(colset):
              target_tables.append((table, cols))
      except Exception:
          continue

    request_ids = set()
    subjects = []
    terms = set()

    for table, cols in target_tables:
        select_cols = [
            c for c in [
                "request_id",
                "subject",
                "supplier",
                "supplier_name",
                "mail_type",
                "body_html",
                "body",
                "receiver",
                "cc",
                "sent_at",
            ]
            if c in cols
        ]

        if not select_cols:
            continue

        sql = f"""
            SELECT {", ".join(select_cols)}
            FROM {table}
            ORDER BY ROWID DESC
            LIMIT ?
        """

        try:
            cur.execute(sql, (int(limit),))
            rows = cur.fetchall()
        except Exception:
            continue

        for row in rows:
            data = dict(row)

            rid = str(data.get("request_id") or "").strip()
            subject = str(data.get("subject") or "").strip()
            supplier = str(data.get("supplier") or data.get("supplier_name") or "").strip()
            body = str(data.get("body_html") or data.get("body") or "").strip()

            if rid:
                request_ids.add(rid.upper())

            if subject:
                subjects.append({
                    "raw": subject,
                    "norm": normalize_mail_subject(subject),
                    "request_id": rid,
                    "supplier": supplier,
                })

            if supplier:
                terms.add(supplier)

            for t in extract_simple_terms(subject, max_terms=20):
                terms.add(t)

            for t in extract_simple_terms(body, max_terms=80):
                terms.add(t)

    conn.close()

    return {
        "request_ids": sorted(request_ids),
        "subjects": subjects,
        "terms": sorted(terms, key=len, reverse=True)[:300],
    }


HALAL_INBOUND_KEYWORDS = [
    "할랄",
    "halal",
    "certificate",
    "certification",
    "certi",
    "valid",
    "validity",
    "expiry",
    "expired",
    "expiration",
    "bpjph",
    "mui",
    "kmf",
    "jakim",
    "cicot",
    "ifanca",
    "hqc",
    "lhln",
]


def evaluate_inbound_mail_candidate(
    subject: str,
    sender: str,
    body_text: str,
    attachment_names: str,
    reference_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    수신메일이 할랄 인증서 업무 후보인지 판정.
    무조건 첨부메일 전체 저장하지 않고 후보만 저장한다.
    """
    reference_context = reference_context or {}

    haystack = " ".join([
        subject or "",
        sender or "",
        body_text or "",
        attachment_names or "",
    ])

    haystack_low = haystack.lower()

    request_id = find_request_id(subject, body_text, attachment_names)

    if request_id:
        return {
            "should_collect": True,
            "matched_request_id": request_id,
            "match_status": "exact",
            "match_reason": "관리번호 직접 발견",
        }

    # 보낸 제목과 유사 비교
    inbound_subject_norm = normalize_mail_subject(subject)

    for sent in reference_context.get("subjects", []):
        sent_norm = sent.get("norm", "")

        if not sent_norm:
            continue

        # 너무 짧은 제목은 오탐 위험
        if len(sent_norm) < 10:
            continue

        if sent_norm in inbound_subject_norm or inbound_subject_norm in sent_norm:
            return {
                "should_collect": True,
                "matched_request_id": sent.get("request_id", ""),
                "match_status": "probable" if sent.get("request_id") else "unmatched_candidate",
                "match_reason": f"발송 제목 유사: {sent.get('raw', '')}",
            }

    # 할랄 키워드 포함
    matched_keywords = [
        kw for kw in HALAL_INBOUND_KEYWORDS
        if kw.lower() in haystack_low
    ]

    if matched_keywords:
        return {
            "should_collect": True,
            "matched_request_id": "",
            "match_status": "unmatched_candidate",
            "match_reason": "할랄 키워드 포함: " + ", ".join(matched_keywords[:5]),
        }

    # 발송 본문/제목에서 추출한 원료명/업체명 후보 포함
    matched_terms = []

    for term in reference_context.get("terms", []):
        t = str(term or "").strip()

        if len(t) < 3:
            continue

        if t.lower() in haystack_low:
            matched_terms.append(t)

        if len(matched_terms) >= 5:
            break

    if matched_terms:
        return {
            "should_collect": True,
            "matched_request_id": "",
            "match_status": "unmatched_candidate",
            "match_reason": "발송 원료/업체명 후보 포함: " + ", ".join(matched_terms),
        }

    return {
        "should_collect": False,
        "matched_request_id": "",
        "match_status": "excluded",
        "match_reason": "관리번호/발송제목/할랄키워드/원료명 매칭 없음",
    }

def is_bounce_mail(subject: str = "", sender: str = "", body_text: str = "", msg=None) -> bool:
    """
    반송메일 / 메일 배달 실패 알림 여부 판단.
    이런 메일은 첨부파일 다운로드 대상에서 제외한다.
    """
    s = f"{subject or ''} {sender or ''} {body_text or ''}".lower()

    sender_patterns = [
        "mailer-daemon",
        "mail delivery subsystem",
        "postmaster",
        "postmaster@",
        "daemon@",
    ]

    subject_patterns = [
        "delivery status notification",
        "undelivered mail",
        "returned mail",
        "failure notice",
        "mail delivery failed",
        "delivery failure",
        "message not delivered",
        "undeliverable",
        "delivery incomplete",
        "배달 실패",
        "전송 실패",
        "반송",
        "메일 배달",
        "전달 실패",
    ]

    if any(x in s for x in sender_patterns):
        return True

    if any(x in s for x in subject_patterns):
        return True

    # MIME 구조상 delivery-status 파트가 있으면 반송메일로 봄
    try:
        if msg is not None and msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "message/delivery-status":
                    return True
    except Exception:
        pass

    return False

def get_db_conn():
    db_path = Path(PMF_APP_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    return conn


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

def is_exact_pdf_ocr_candidate(filename: str = "", ext: str = "") -> bool:
    """
    EXACT 매칭 메일의 PDF 첨부는 자동 OCR 대상.
    이미지/엑셀/워드는 수동 선택 또는 OCR 제외.
    """
    name = str(filename or "").strip().lower()
    suffix = str(ext or "").strip().lower()

    if not suffix and "." in name:
        suffix = "." + name.rsplit(".", 1)[-1].lower()

    return suffix == ".pdf"


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

def sync_daum_inbox_attachments(
    user_email: str,
    app_password: str,
    mailbox: str = "INBOX",
    days: int = 30,
    limit: int = 50,
    only_with_attachments: bool = True,
) -> dict[str, Any]:
    """
    Daum IMAP 받은메일 동기화.
    첨부파일을 관리번호 기준 폴더에 저장한다.
    """
    if not user_email:
        raise ValueError("user_email이 없습니다.")

    if not app_password:
        raise ValueError("app_password가 없습니다.")

    init_inbox_tables()

    result = {
        "ok": True,
        "provider": "daum",
        "mailbox": mailbox,
        "days": days,
        "limit": limit,
        "checked": 0,
        "inserted_mails": 0,
        "skipped_existing": 0,
        "downloaded_attachments": 0,
        "exact_matched": 0,
        "unmatched": 0,
        "rows": [],
        "skipped_bounce": 0,
        "skipped_non_candidate": 0,
        "probable": 0,
        "unmatched_candidate": 0,
    }

    imap = imaplib.IMAP4_SSL("imap.daum.net", 993)

    try:
        imap.login(user_email, app_password)

        select_mailbox = quote_imap_mailbox(mailbox)
        status, select_data = imap.select(select_mailbox)
        reference_context = get_sent_mail_reference_context(limit=500)

        if status != "OK":
            raise RuntimeError(f"메일함 선택 실패: {mailbox} / {select_data}")

        since_date = (datetime.now() - timedelta(days=int(days))).strftime("%d-%b-%Y")
        status, data = imap.search(None, "SINCE", since_date)

        if status != "OK":
            raise RuntimeError("IMAP 검색에 실패했습니다.")

        msg_nums = data[0].split()
        msg_nums = list(reversed(msg_nums))[: int(limit)]

        for msg_num in msg_nums:
            result["checked"] += 1

            status, fetched = imap.fetch(msg_num, "(RFC822)")

            if status != "OK" or not fetched or not fetched[0]:
                continue

            raw_msg = fetched[0][1]
            msg = email.message_from_bytes(raw_msg)

            subject = decode_mime_text(msg.get("Subject", ""))
            sender = decode_mime_text(msg.get("From", ""))
            received_at = parse_received_at(msg)
            message_id = msg.get("Message-ID", "")

            message_uid = message_id.strip() or f"{mailbox}-{msg_num.decode(errors='ignore')}-{received_at}-{subject}"

            body_text = extract_body_text(msg)

            if is_bounce_mail(
                subject=subject,
                sender=sender,
                body_text=body_text,
                msg=msg,
            ):
                result["skipped_bounce"] += 1
                continue

            attachments = get_attachment_parts(msg)

            if only_with_attachments and not attachments:
                continue

            attachment_names = " ".join([x["filename"] for x in attachments])

            candidate = evaluate_inbound_mail_candidate(
                subject=subject,
                sender=sender,
                body_text=body_text,
                attachment_names=attachment_names,
                reference_context=reference_context,
            )

            if not candidate["should_collect"]:
                result["skipped_non_candidate"] += 1
                continue

            request_id = candidate.get("matched_request_id", "")
            match_status = candidate.get("match_status", "unmatched_candidate")
            match_reason = candidate.get("match_reason", "")

            if match_status == "exact":
                result["exact_matched"] += 1
            elif match_status == "probable":
                result["probable"] += 1
            else:
                result["unmatched_candidate"] += 1

            download_dir = make_download_dir(request_id, received_at, sender)
            attach_dir = download_dir / "attachments"
            attach_dir.mkdir(parents=True, exist_ok=True)

            mail_date_candidates = extract_date_candidates_from_text(
                f"{subject}\n{body_text}",
                source="mail",
            )

            meta = {
                "provider": "daum",
                "mailbox": mailbox,
                "message_uid": message_uid,
                "subject": subject,
                "sender": sender,
                "received_at": received_at,
                "body_text": body_text,
                "body_preview": strip_html_text(body_text)[:1000],
                "date_candidates_json": json.dumps(mail_date_candidates, ensure_ascii=False),
                "matched_request_id": request_id,
                "match_status": match_status,
                "match_reason": match_reason,
                "attachment_count": len(attachments),
                "download_dir": str(download_dir),
                "is_excluded": 0,
                "exclude_reason": "",
            }

            mail_id, inserted_new = insert_inbound_mail(meta)

            if not inserted_new:
                result["skipped_existing"] += 1
                continue

            save_message_files(download_dir, meta, body_text)

            saved_files = []

            for idx, att in enumerate(attachments, start=1):
                original_name = safe_filename(att["filename"], f"attachment_{idx}")
                prefix = request_id if request_id else "UNMATCHED"
                saved_name = safe_filename(f"{prefix}__{idx:03d}__{original_name}")

                saved_path = attach_dir / saved_name
                saved_path.write_bytes(att["payload"])

                auto_ocr_selected = 1 if (
                    match_status == "exact"
                    and is_exact_pdf_ocr_candidate(
                        filename=saved_name,
                        ext=Path(saved_name).suffix.lower(),
                    )
                ) else 0

                insert_attachment(
                    mail_id=mail_id,
                    request_id=request_id,
                    original_filename=original_name,
                    saved_filename=saved_name,
                    saved_path=str(saved_path),
                    file_size=len(att["payload"]),
                    match_status=match_status,
                )

                result["downloaded_attachments"] += 1
                saved_files.append(str(saved_path))

            result["inserted_mails"] += 1
            result["rows"].append({
                "mail_id": mail_id,
                "subject": subject,
                "sender": sender,
                "received_at": received_at,
                "matched_request_id": request_id,
                "match_status": match_status,
                "attachment_count": len(attachments),
                "download_dir": str(download_dir),
                "saved_files": saved_files,
            })

    finally:
        try:
            imap.logout()
        except Exception:
            pass

    return result


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

def sync_daum_multiple_mailboxes(
    user_email: str,
    app_password: str,
    mailboxes: list[str],
    days: int = 30,
    limit_per_mailbox: int = 50,
    only_with_attachments: bool = True,
) -> dict[str, Any]:
    """
    받은메일함 + HALAL 인증서 등 여러 메일함을 순차 동기화.
    """
    final = {
        "ok": True,
        "provider": "daum",
        "mailboxes": mailboxes,
        "days": days,
        "limit_per_mailbox": limit_per_mailbox,
        "checked": 0,
        "inserted_mails": 0,
        "skipped_existing": 0,
        "downloaded_attachments": 0,
        "exact_matched": 0,
        "unmatched": 0,
        "results": [],
        "skipped_bounce": 0,
        "skipped_non_candidate": 0,
        "probable": 0,
        "unmatched_candidate": 0,
    }

    for mailbox in mailboxes:
        try:
            result = sync_daum_inbox_attachments(
                user_email=user_email,
                app_password=app_password,
                mailbox=mailbox,
                days=days,
                limit=limit_per_mailbox,
                only_with_attachments=only_with_attachments,
            )

            final["checked"] += int(result.get("checked", 0))
            final["inserted_mails"] += int(result.get("inserted_mails", 0))
            final["skipped_existing"] += int(result.get("skipped_existing", 0))
            final["downloaded_attachments"] += int(result.get("downloaded_attachments", 0))
            final["exact_matched"] += int(result.get("exact_matched", 0))
            final["unmatched"] += int(result.get("unmatched", 0))
            final["skipped_bounce"] += int(result.get("skipped_bounce", 0))
            final["results"].append({
                "mailbox": mailbox,
                "ok": True,
                "result": result,
            })
            final["skipped_non_candidate"] += int(result.get("skipped_non_candidate", 0))
            final["probable"] += int(result.get("probable", 0))
            final["unmatched_candidate"] += int(result.get("unmatched_candidate", 0))

        except Exception as e:
            final["results"].append({
                "mailbox": mailbox,
                "ok": False,
                "message": str(e),
            })

    return final

def list_daum_mailboxes(user_email: str, app_password: str) -> dict[str, Any]:
    """
    Daum IMAP 메일함 목록 조회.
    한글 폴더명 확인용.
    """
    if not user_email:
        raise ValueError("user_email이 없습니다.")

    if not app_password:
        raise ValueError("app_password가 없습니다.")

    imap = imaplib.IMAP4_SSL("imap.daum.net", 993)

    rows = []

    try:
        imap.login(user_email, app_password)

        status, data = imap.list()

        if status != "OK":
            raise RuntimeError("IMAP 메일함 목록 조회에 실패했습니다.")

        for raw in data:
            line = raw.decode("utf-8", errors="replace")

            mailbox_name = line

            if ' "/" ' in line:
                mailbox_name = line.split(' "/" ')[-1].strip().strip('"')
            elif ' "." ' in line:
                mailbox_name = line.split(' "." ')[-1].strip().strip('"')
            else:
                parts = line.split(" ")
                if parts:
                    mailbox_name = parts[-1].strip().strip('"')

            rows.append({
                "raw": line,
                "mailbox": mailbox_name,
            })

    finally:
        try:
            imap.logout()
        except Exception:
            pass

    return {
        "ok": True,
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

def is_ocr_candidate_attachment(
    filename: str = "",
    ext: str = "",
    file_size: int | None = None,
) -> bool:
    """
    OCR 자동 대상 여부.
    exact 메일이라도 서명 이미지, 로고, 배너류는 제외한다.
    """
    name = str(filename or "").strip().lower()
    suffix = str(ext or "").strip().lower()

    if not suffix and "." in name:
        suffix = "." + name.rsplit(".", 1)[-1].lower()

    allowed_exts = {
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".tif",
        ".tiff",
        ".bmp",
    }

    if suffix not in allowed_exts:
        return False

    block_keywords = [
        "image001",
        "image002",
        "image003",
        "logo",
        "signature",
        "sign",
        "banner",
        "footer",
        "header",
        "facebook",
        "instagram",
        "naver",
        "kakao",
    ]

    if any(x in name for x in block_keywords):
        return False

    try:
        size = int(file_size or 0)
        # 너무 작은 이미지는 서명/아이콘 가능성이 높음
        if suffix in {".jpg", ".jpeg", ".png", ".bmp"} and 0 < size < 20_000:
            return False
    except Exception:
        pass

    return True


def auto_select_exact_inbound_ocr_targets(mail_id: int | None = None) -> dict[str, Any]:
    """
    관리번호 exact 매칭 메일의 첨부파일 중 OCR 가능한 파일을 자동 OCR 대상으로 지정한다.
    """
    init_inbox_tables()

    conn = get_db_conn()
    cur = conn.cursor()

    params = []

    sql = """
        SELECT
            a.id,
            a.mail_id,
            a.original_filename,
            a.saved_filename,
            a.ext,
            a.file_size,
            COALESCE(a.ocr_selected, 0) AS ocr_selected,
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
    skipped = []

    for row in rows:
        filename = row.get("saved_filename") or row.get("original_filename") or ""
        ext = row.get("ext") or ""
        file_size = row.get("file_size") or 0

        if is_ocr_candidate_attachment(filename=filename, ext=ext, file_size=file_size):
            selected_ids.append(int(row["id"]))
        else:
            skipped.append({
                "id": int(row["id"]),
                "filename": filename,
                "reason": "OCR 제외 확장자 또는 서명/로고 이미지",
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
        "skipped": len(skipped),
        "selected_ids": selected_ids,
        "skipped_rows": skipped[:30],
    }

def is_exact_pdf_ocr_candidate(filename: str = "", ext: str = "") -> bool:
    """
    EXACT 매칭 메일의 PDF 첨부는 자동 OCR 대상.
    단, PDF만 자동 대상. 이미지/엑셀/워드는 수동 선택.
    """
    name = str(filename or "").strip().lower()
    suffix = str(ext or "").strip().lower()

    if not suffix and "." in name:
        suffix = "." + name.rsplit(".", 1)[-1].lower()

    return suffix == ".pdf"


def auto_select_exact_inbound_ocr_targets(mail_id: int | None = None) -> dict[str, Any]:
    """
    관리번호 exact 매칭 메일의 PDF 첨부파일을 자동 OCR 대상으로 지정한다.
    """
    init_inbox_tables()

    conn = get_db_conn()
    cur = conn.cursor()

    params = []

    sql = """
        SELECT
            a.id,
            a.mail_id,
            a.original_filename,
            a.saved_filename,
            a.ext,
            a.file_size,
            COALESCE(a.ocr_selected, 0) AS ocr_selected,
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
        ext = row.get("ext") or ""

        if is_exact_pdf_ocr_candidate(filename=filename, ext=ext):
            selected_ids.append(int(row["id"]))
        else:
            skipped_rows.append({
                "id": int(row["id"]),
                "filename": filename,
                "reason": "EXACT 메일이지만 PDF가 아니므로 자동 OCR 제외",
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
    OCR 대상으로 저장된 첨부파일 목록을 조회한다.
    일괄 OCR 실행용.
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
            a.created_at,
            m.subject,
            m.sender,
            m.received_at,
            m.match_status,
            m.mailbox,
            m.body_text,
            m.body_preview,
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


def save_inbound_ocr_candidate_result(
    attachment_id: int,
    ocr_job_id: int | None = None,
    status: str = "",
    filename: str = "",
    best_expiry: str = "",
    expiry_candidates: list[dict[str, Any]] | None = None,
    message: str = "",
) -> dict[str, Any]:
    """
    OCR 실행 후 유효기간 후보를 저장한다.
    """
    init_inbox_tables()
    init_inbound_ocr_candidate_table()

    expiry_candidates = expiry_candidates or []

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
            message,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        int(attachment_id),
        data.get("mail_id"),
        data.get("request_id") or "",
        ocr_job_id,
        final_filename,
        status,
        best_expiry,
        json.dumps(expiry_candidates, ensure_ascii=False),
        message,
        now_text(),
    ))

    next_status = "done" if status and status.upper() not in {"ERROR", "FAILED"} else "error"

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