from __future__ import annotations

import html
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.core.config import PMF_APP_DB_PATH
from app.services.pmf_service import read_pmf_bundle
from app.services.supplier_service import clean, get_full_row_data, nfkc_text


TAG_PATTERN = re.compile(r"<[^>]+>")
SPACE_PATTERN = re.compile(r"\s+")
NUMBERED_ITEM_PATTERN = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$")
FIELD_LINE_PATTERN = re.compile(r"^\s*-\s*([^:：]+)\s*[:：]\s*(.*?)\s*$")
DATE_PATTERN = re.compile(r"\b(20\d{2})[-./](0?[1-9]|1[0-2])[-./](0?[1-9]|[12]\d|3[01])\b")


@dataclass(frozen=True)
class MailRequestItem:
    request_id: str
    supplier: str
    mail_type: str
    item_index: int
    material_path: str
    material_name: str
    english_name: str
    maker: str
    maker_country: str
    org: str
    cert_no: str
    current_expiry: str
    planned_expiry: str
    source: str = "mail_log"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(PMF_APP_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def normalize_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = SPACE_PATTERN.sub(" ", text).strip()
    if text.lower() in {"", "-", "nan", "none", "null"}:
        return ""
    return text


def normalize_key(value: Any) -> str:
    text = normalize_text(value).lower()
    return re.sub(r"[^0-9a-z가-힣]", "", text)


def normalize_date(value: Any) -> str:
    text = normalize_text(value)
    match = DATE_PATTERN.search(text)
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def html_to_lines(body_html: str) -> list[str]:
    text = str(body_html or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</div\s*>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = TAG_PATTERN.sub("", text)
    text = html.unescape(text)

    lines: list[str] = []
    for line in text.replace("\r", "\n").split("\n"):
        line = SPACE_PATTERN.sub(" ", line).strip()
        if line:
            lines.append(line)
    return lines


def _field_name_to_key(label: str) -> str:
    key = normalize_key(label)
    mapping = {
        "영문명": "english_name",
        "제조사": "maker",
        "제조국": "maker_country",
        "인증기관": "org",
        "인증번호": "cert_no",
        "유효기간": "expiry",
        "현재유효기간": "current_expiry",
    }
    return mapping.get(key, "")


def parse_mail_request_items(
    body_html: str,
    request_id: str = "",
    supplier: str = "",
    mail_type: str = "",
) -> list[dict[str, Any]]:
    """
    기존 발송메일의 고정 형식에서 원료 항목을 구조화한다.
    본문을 다시 AI에 보내지 않고 라벨 기반으로 파싱한다.
    """
    lines = html_to_lines(body_html)
    parsed: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def flush_current() -> None:
        nonlocal current
        if not current:
            return

        path = normalize_text(current.get("material_path"))
        material_name = path.split(">")[-1].strip() if path else ""

        item = MailRequestItem(
            request_id=normalize_text(request_id),
            supplier=normalize_text(supplier),
            mail_type=normalize_text(mail_type),
            item_index=int(current.get("item_index") or len(parsed) + 1),
            material_path=path,
            material_name=material_name,
            english_name=normalize_text(current.get("english_name")),
            maker=normalize_text(current.get("maker")),
            maker_country=normalize_text(current.get("maker_country")),
            org=normalize_text(current.get("org")),
            cert_no=normalize_text(current.get("cert_no")),
            current_expiry=normalize_date(
                current.get("current_expiry") or current.get("expiry")
            ),
            planned_expiry=normalize_date(current.get("planned_expiry")),
        )
        parsed.append(item.to_dict())
        current = None

    for line in lines:
        numbered = NUMBERED_ITEM_PATTERN.match(line)
        if numbered:
            flush_current()
            current = {
                "item_index": int(numbered.group(1)),
                "material_path": normalize_text(numbered.group(2)),
            }
            continue

        if current is None:
            continue

        field_match = FIELD_LINE_PATTERN.match(line)
        if not field_match:
            continue

        label = normalize_text(field_match.group(1))
        value = normalize_text(field_match.group(2))
        label_key = normalize_key(label)

        if label_key == "현재유효기간":
            current_match = re.search(
                r"현재\s*유효기간\s*[:：]\s*([^/]+)",
                line,
                flags=re.I,
            )
            planned_match = re.search(
                r"유지\s*확인\s*시\s*적용\s*예정\s*[:：]\s*(.+)$",
                line,
                flags=re.I,
            )
            if current_match:
                current["current_expiry"] = normalize_date(current_match.group(1))
            if planned_match:
                current["planned_expiry"] = normalize_date(planned_match.group(1))
            continue

        key = _field_name_to_key(label)
        if key:
            current[key] = value

    flush_current()
    return parsed


def get_latest_mail_log(request_id: str) -> dict[str, Any] | None:
    request_id = normalize_text(request_id)
    if not request_id or not PMF_APP_DB_PATH.exists():
        return None

    conn = get_conn()
    try:
        if not table_exists(conn, "mail_send_logs"):
            return None
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(mail_send_logs)").fetchall()
        }
        deleted_clause = "AND deleted_at IS NULL" if "deleted_at" in columns else ""
        row = conn.execute(
            f"""
            SELECT *
            FROM mail_send_logs
            WHERE UPPER(COALESCE(request_id, '')) = UPPER(?)
              AND COALESCE(success, 0) = 1
              {deleted_clause}
            ORDER BY id DESC
            LIMIT 1
            """,
            (request_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_attachment_context_for_source(source_path: str, filename: str = "") -> dict[str, Any]:
    """
    OCR source_path를 수신첨부 테이블과 연결한다.
    정확한 saved_path 우선, 실패 시 파일명 최신 건을 사용한다.
    """
    if not PMF_APP_DB_PATH.exists():
        return {}

    source_norm = str(Path(source_path)).replace("/", "\\").lower()
    filename = normalize_text(filename or Path(source_path).name)

    conn = get_conn()
    try:
        if not table_exists(conn, "inbound_attachment"):
            return {}

        rows = conn.execute(
            """
            SELECT
                a.*,
                m.subject,
                m.sender,
                m.received_at,
                m.body_text,
                m.match_status,
                m.match_reason,
                m.mailbox
            FROM inbound_attachment a
            LEFT JOIN inbound_mail m ON a.mail_id = m.id
            WHERE LOWER(REPLACE(COALESCE(a.saved_path, ''), '/', '\\')) = ?
            ORDER BY a.id DESC
            LIMIT 3
            """,
            (source_norm,),
        ).fetchall()

        if not rows and filename:
            rows = conn.execute(
                """
                SELECT
                    a.*,
                    m.subject,
                    m.sender,
                    m.received_at,
                    m.body_text,
                    m.match_status,
                    m.match_reason,
                    m.mailbox
                FROM inbound_attachment a
                LEFT JOIN inbound_mail m ON a.mail_id = m.id
                WHERE LOWER(COALESCE(a.original_filename, '')) = LOWER(?)
                   OR LOWER(COALESCE(a.saved_filename, '')) = LOWER(?)
                ORDER BY a.id DESC
                LIMIT 3
                """,
                (filename, filename),
            ).fetchall()

        if not rows:
            return {}

        data = dict(rows[0])
        data["match_count"] = len(rows)
        return data
    finally:
        conn.close()


def get_request_context_for_ocr_job(job: dict[str, Any]) -> dict[str, Any]:
    attachment = get_attachment_context_for_source(
        source_path=str(job.get("source_path") or ""),
        filename=str(job.get("filename") or ""),
    )
    request_id = normalize_text(attachment.get("request_id"))
    mail_log = get_latest_mail_log(request_id) if request_id else None
    items: list[dict[str, Any]] = []

    if mail_log:
        items = parse_mail_request_items(
            body_html=str(mail_log.get("body_html") or ""),
            request_id=request_id,
            supplier=str(mail_log.get("supplier") or ""),
            mail_type=str(mail_log.get("mail_type") or ""),
        )

    return {
        "request_id": request_id,
        "attachment": attachment,
        "mail_log": mail_log or {},
        "mail_items": items,
    }


def _similarity_score(left: str, right: str) -> int:
    left_key = normalize_key(left)
    right_key = normalize_key(right)
    if not left_key or not right_key:
        return 0
    if left_key == right_key:
        return 100
    if left_key in right_key or right_key in left_key:
        shorter = min(len(left_key), len(right_key))
        longer = max(len(left_key), len(right_key))
        if shorter >= 4:
            return int(75 + (shorter / max(longer, 1)) * 20)
    return 0


def match_mail_item_to_pmf(
    mail_item: dict[str, Any],
    supplier: str = "",
    limit: int = 5,
) -> list[dict[str, Any]]:
    bundle = read_pmf_bundle()
    df_raw = bundle["df_raw"]
    supplier_expected = normalize_text(supplier or mail_item.get("supplier"))

    candidates: list[dict[str, Any]] = []
    for row_pos, (_, row) in enumerate(df_raw.iterrows()):
        row_supplier = clean(row.iloc[6]) if len(row) > 6 else ""

        for depth in range(5):
            data = get_full_row_data(row, depth)
            if not data:
                continue

            material_name = clean(data.get("n"))
            if material_name in {"", "-"}:
                continue

            score = 0
            reasons: list[str] = []

            fields = [
                ("cert_no", mail_item.get("cert_no"), data.get("i"), 120),
                ("material_name", mail_item.get("material_name"), material_name, 90),
                ("english_name", mail_item.get("english_name"), data.get("e"), 90),
                ("maker", mail_item.get("maker"), data.get("m"), 60),
                ("org", mail_item.get("org"), data.get("h"), 35),
                ("current_expiry", mail_item.get("current_expiry"), data.get("v"), 25),
                ("supplier", supplier_expected, row_supplier, 35),
            ]

            for kind, expected, actual, weight in fields:
                similarity = _similarity_score(
                    normalize_date(expected) if kind.endswith("expiry") else expected,
                    normalize_date(actual) if kind.endswith("expiry") else actual,
                )
                if similarity >= 100:
                    score += weight
                    reasons.append(f"{kind}:exact")
                elif similarity >= 75:
                    score += int(weight * 0.65)
                    reasons.append(f"{kind}:partial")

            if score <= 0:
                continue

            candidates.append(
                {
                    "row_pos": row_pos,
                    "depth": depth,
                    "material_no": clean(get_full_row_data(row, 0).get("id")),
                    "supplier": clean(row_supplier),
                    "material_name": material_name,
                    "english_name": clean(data.get("e")),
                    "maker": clean(data.get("m")),
                    "maker_country": clean(data.get("o")),
                    "org": clean(data.get("h")),
                    "cert_no": clean(data.get("i")),
                    "expiry_date": normalize_date(data.get("v")),
                    "score": score,
                    "reasons": reasons,
                }
            )

    candidates.sort(key=lambda item: (item["score"], -item["depth"]), reverse=True)
    return candidates[: max(1, int(limit))]


def build_pmf_candidates_for_request_context(
    request_context: dict[str, Any],
    limit_per_item: int = 5,
) -> list[dict[str, Any]]:
    supplier = normalize_text((request_context.get("mail_log") or {}).get("supplier"))
    rows: list[dict[str, Any]] = []

    for item in request_context.get("mail_items") or []:
        matches = match_mail_item_to_pmf(item, supplier=supplier, limit=limit_per_item)
        rows.append({
            "mail_item": item,
            "pmf_matches": matches,
            "top_match": matches[0] if matches else None,
        })

    return rows
