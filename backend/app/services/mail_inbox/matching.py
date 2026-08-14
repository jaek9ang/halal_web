"""발송 메일의 관리번호와 수신 메일을 대조해 exact/partial 매칭을 판정한다."""

from __future__ import annotations

from typing import Any

from app.services.mail_inbox.text import (
    HALAL_INBOUND_KEYWORDS,
    extract_simple_terms,
    find_request_id,
    normalize_mail_subject,
)
from app.services.mail_inbox.store import (
    get_db_conn,
    init_inbox_tables,
)


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
