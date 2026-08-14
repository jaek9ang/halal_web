"""IMAP 메시지에서 본문·첨부·날짜 후보를 뽑아낸다."""

from __future__ import annotations

from datetime import date
from typing import Any
import html
import re

from app.services.mail_inbox.text import (
    decode_mime_text,
    normalize_candidate_text,
    to_iso_date,
)


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
