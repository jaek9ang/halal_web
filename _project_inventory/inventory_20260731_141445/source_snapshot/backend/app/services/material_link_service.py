import json
import sqlite3
from typing import Any

from app.core.config import PMF_APP_DB_PATH
from app.services.pmf_service import read_pmf_bundle
from app.services.supplier_service import clean, get_full_row_data


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name=?
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def get_conn():
    conn = sqlite3.connect(PMF_APP_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def build_material_keywords(row_pos: int) -> dict[str, Any]:
    bundle = read_pmf_bundle()
    df_raw = bundle["df_raw"]

    if row_pos < 0 or row_pos >= len(df_raw):
        raise ValueError("row_pos 범위를 벗어났습니다.")

    row = df_raw.iloc[row_pos]
    supplier = clean(row.iloc[6]) if len(row) > 6 else "-"

    levels = []
    keywords = []

    for depth in range(5):
        data = get_full_row_data(row, depth)

        if not data:
            continue

        material_name = clean(data.get("n", ""))
        english_name = clean(data.get("e", ""))
        maker = clean(data.get("m", ""))
        maker_country = clean(data.get("o", ""))
        org = clean(data.get("h", ""))
        cert_no = clean(data.get("i", ""))
        exp = clean(data.get("v", ""))

        if not material_name or material_name == "-":
            continue

        level = {
            "depth": depth,
            "material_name": material_name,
            "english_name": english_name,
            "maker": maker,
            "maker_country": maker_country,
            "org": org,
            "cert_no": cert_no,
            "exp": exp,
        }

        levels.append(level)

        candidates = [
            ("cert_no", cert_no, 60),
            ("english_name", english_name, 18),
            ("material_name", material_name, 16),
            ("maker", maker, 12),
            ("org", org, 8),
            ("supplier", supplier, 6),
        ]

        for kind, value, weight in candidates:
            value = clean(value)

            if not value or value == "-":
                continue

            if len(value) < 2:
                continue

            keywords.append({
                "kind": kind,
                "value": value,
                "weight": weight,
                "depth": depth,
            })

    # 중복 키워드 제거
    dedup = {}
    for item in keywords:
        key = (item["kind"], item["value"].lower())
        if key not in dedup or dedup[key]["weight"] < item["weight"]:
            dedup[key] = item

    return {
        "supplier": supplier,
        "levels": levels,
        "keywords": list(dedup.values()),
    }


def score_text(text: str, keywords: list[dict[str, Any]]) -> tuple[int, list[str]]:
    text_l = clean(text).lower()
    score = 0
    reasons = []

    if not text_l:
        return 0, []

    for item in keywords:
        value = clean(item.get("value", ""))
        value_l = value.lower()

        if not value_l:
            continue

        if value_l in text_l:
            score += int(item.get("weight", 1))
            reasons.append(f"{item.get('kind')}:{value}")

    return score, reasons


def read_received_attachments(limit: int = 500) -> list[dict[str, Any]]:
    if not PMF_APP_DB_PATH.exists():
        return []

    conn = get_conn()

    try:
        if not table_exists(conn, "received_attachments"):
            return []

        rows = conn.execute(
            """
            SELECT
                id,
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
            FROM received_attachments
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        conn.close()


def read_ocr_jobs(limit: int = 500) -> list[dict[str, Any]]:
    if not PMF_APP_DB_PATH.exists():
        return []

    conn = get_conn()

    try:
        if not table_exists(conn, "ocr_jobs"):
            return []

        rows = conn.execute(
            """
            SELECT
                id,
                source_path,
                filename,
                file_ext,
                status,
                raw_text,
                result_json,
                error_message,
                created_at,
                updated_at,
                LENGTH(COALESCE(raw_text, '')) AS text_length
            FROM ocr_jobs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        conn.close()


def get_material_related_files(row_pos: int, limit: int = 30) -> dict[str, Any]:
    base = build_material_keywords(row_pos)
    keywords = base["keywords"]

    results = []

    # 1) 수신메일 첨부파일 로그 검색
    for row in read_received_attachments(limit=700):
        blob = " ".join([
            clean(row.get("filename", "")),
            clean(row.get("filepath", "")),
            clean(row.get("subject", "")),
            clean(row.get("sender", "")),
            clean(row.get("request_id", "")),
            clean(row.get("body_preview", "")),
        ])

        score, reasons = score_text(blob, keywords)

        if score <= 0:
            continue

        results.append({
            "source_type": "received_attachment",
            "score": score,
            "reasons": reasons[:8],
            "id": row.get("id"),
            "filename": row.get("filename", ""),
            "filepath": row.get("filepath", ""),
            "request_id": row.get("request_id", ""),
            "subject": row.get("subject", ""),
            "sender": row.get("sender", ""),
            "status": "DOWNLOADED",
            "text_length": "",
            "created_at": row.get("downloaded_at", ""),
        })

    # 2) OCR 작업 결과 검색
    for row in read_ocr_jobs(limit=700):
        raw_text = clean(row.get("raw_text", ""))

        result_json = row.get("result_json") or "{}"
        try:
            result_obj = json.loads(result_json)
            result_text = json.dumps(result_obj, ensure_ascii=False)
        except Exception:
            result_text = result_json

        blob = " ".join([
            clean(row.get("filename", "")),
            clean(row.get("source_path", "")),
            raw_text[:20000],
            result_text[:5000],
        ])

        score, reasons = score_text(blob, keywords)

        if score <= 0:
            continue

        results.append({
            "source_type": "ocr_job",
            "score": score,
            "reasons": reasons[:8],
            "id": row.get("id"),
            "filename": row.get("filename", ""),
            "filepath": row.get("source_path", ""),
            "request_id": "",
            "subject": "",
            "sender": "",
            "status": row.get("status", ""),
            "text_length": row.get("text_length", 0),
            "created_at": row.get("updated_at", ""),
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    return {
        "row_pos": row_pos,
        "supplier": base["supplier"],
        "levels": base["levels"],
        "keywords": keywords,
        "rows": results[:limit],
        "count": min(len(results), limit),
        "total_matched": len(results),
    }