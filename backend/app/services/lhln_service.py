import os
import re
import sqlite3
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import fitz
import pandas as pd
import requests

from app.core.config import (
    LHLN_DB_PATH,
    LHLN_BASE_URL,
    LHLN_OUTPUT_DIR,
    LHLN_GUIDE_PDF_PATH,
)
from app.core.db import connect as db_connect


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_lhln_name(raw_name: str):
    raw_name = normalize_text(raw_name)

    if not raw_name:
        return "", ""

    m = re.match(r"^(.*?)\s*\(([^()]*)\)", raw_name)

    if m:
        cert_name = normalize_text(m.group(1))
        abbreviation = normalize_text(m.group(2))
        return cert_name, abbreviation

    return raw_name, ""


def get_lhln_conn():
    return db_connect(LHLN_DB_PATH)


def init_lhln_db() -> None:
    conn = get_lhln_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS lhln_reference (
        lph_id TEXT PRIMARY KEY,
        nama_lhln_raw TEXT,
        nama_lhln TEXT,
        abbreviation TEXT,
        negara TEXT,
        kota TEXT,
        alamat TEXT,
        lokasi TEXT,
        jenis TEXT,
        no_reg TEXT,
        tgl_berlaku TEXT,
        status TEXT,
        updated_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS lhln_sync_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        crawled_at TEXT,
        total_count INTEGER,
        saved_count INTEGER,
        source_url TEXT
    )
    """)

    conn.commit()
    conn.close()


def request_lhln_page(
    page: int,
    size: int = 20,
    nama_lhln: str = "",
    flag_statuses: str = "ACREDITATIONMRAMoU",
    timeout: int = 30,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    session = session or requests.Session()

    params = {
        "nama_lhln": nama_lhln,
        "page": page,
        "size": size,
        "flag_statuses": flag_statuses,
    }

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    response = session.get(
        LHLN_BASE_URL,
        params=params,
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()

    data = response.json()

    if data.get("statusCode") != 200 or data.get("error") is True:
        raise ValueError(f"LHLN API 오류: {data}")

    return data


def convert_item_to_record(item: dict[str, Any]) -> dict[str, Any]:
    raw_nama_lhln = normalize_text(item.get("nama_lhln"))
    cert_name, abbreviation = split_lhln_name(raw_nama_lhln)

    return {
        "lph_id": normalize_text(item.get("lph_id")),
        "nama_lhln_raw": raw_nama_lhln,
        "nama_lhln": cert_name,
        "abbreviation": abbreviation,
        "negara": normalize_text(item.get("negara")),
        "kota": normalize_text(item.get("kota")),
        "alamat": normalize_text(item.get("alamat")),
        "lokasi": normalize_text(item.get("lokasi")),
        "jenis": normalize_text(item.get("jenis")),
        "no_reg": normalize_text(item.get("no_reg")),
        "tgl_berlaku": normalize_text(item.get("tgl_berlaku")),
        "status": normalize_text(item.get("status")),
    }


def crawl_lhln_all_pages(
    start_page: int = 1,
    end_page: int | None = None,
    size: int = 20,
    nama_lhln: str = "",
    flag_statuses: str = "ACREDITATIONMRAMoU",
    sleep_sec: float = 0.2,
) -> dict[str, Any]:
    session = requests.Session()
    all_records = []

    first_response = request_lhln_page(
        page=start_page,
        size=size,
        nama_lhln=nama_lhln,
        flag_statuses=flag_statuses,
        session=session,
    )

    data = first_response.get("data", {})
    total_pages = int(data.get("total_pages", 1))

    if end_page is None:
        end_page = total_pages
    else:
        end_page = min(end_page, total_pages)

    for item in data.get("datas", []):
        all_records.append(convert_item_to_record(item))

    for page in range(start_page + 1, end_page + 1):
        time.sleep(sleep_sec)

        response = request_lhln_page(
            page=page,
            size=size,
            nama_lhln=nama_lhln,
            flag_statuses=flag_statuses,
            session=session,
        )

        for item in response.get("data", {}).get("datas", []):
            all_records.append(convert_item_to_record(item))

    return {
        "meta": {
            "source": LHLN_BASE_URL,
            "crawled_at": datetime.now().isoformat(timespec="seconds"),
            "start_page": start_page,
            "end_page": end_page,
            "size": size,
            "flag_statuses": flag_statuses,
            "keyword": nama_lhln,
            "total_count": len(all_records),
        },
        "items": all_records,
    }


def upsert_lhln_records(items: list[dict[str, Any]]) -> int:
    init_lhln_db()

    if not items:
        return 0

    conn = get_lhln_conn()
    cur = conn.cursor()
    now_ts = datetime.now().isoformat(timespec="seconds")

    normalized_items = []
    for row in items:
        if not row.get("lph_id"):
            continue

        normalized_items.append({
            **row,
            "updated_at": now_ts,
        })

    cur.executemany("""
    INSERT INTO lhln_reference (
        lph_id,
        nama_lhln_raw,
        nama_lhln,
        abbreviation,
        negara,
        kota,
        alamat,
        lokasi,
        jenis,
        no_reg,
        tgl_berlaku,
        status,
        updated_at
    )
    VALUES (
        :lph_id,
        :nama_lhln_raw,
        :nama_lhln,
        :abbreviation,
        :negara,
        :kota,
        :alamat,
        :lokasi,
        :jenis,
        :no_reg,
        :tgl_berlaku,
        :status,
        :updated_at
    )
    ON CONFLICT(lph_id) DO UPDATE SET
        nama_lhln_raw = excluded.nama_lhln_raw,
        nama_lhln = excluded.nama_lhln,
        abbreviation = excluded.abbreviation,
        negara = excluded.negara,
        kota = excluded.kota,
        alamat = excluded.alamat,
        lokasi = excluded.lokasi,
        jenis = excluded.jenis,
        no_reg = excluded.no_reg,
        tgl_berlaku = excluded.tgl_berlaku,
        status = excluded.status,
        updated_at = excluded.updated_at
    """, normalized_items)

    saved_count = len(normalized_items)

    cur.execute("""
    INSERT INTO lhln_sync_history (
        crawled_at,
        total_count,
        saved_count,
        source_url
    )
    VALUES (?, ?, ?, ?)
    """, (
        now_ts,
        len(items),
        saved_count,
        LHLN_BASE_URL,
    ))

    conn.commit()
    conn.close()

    return saved_count


def sync_lhln_reference() -> dict[str, Any]:
    init_lhln_db()

    result = crawl_lhln_all_pages(
        start_page=1,
        end_page=None,
        size=20,
    )

    saved_count = upsert_lhln_records(result["items"])

    return {
        "ok": True,
        "meta": result["meta"],
        "saved_count": saved_count,
    }


def get_lhln_status() -> dict[str, Any]:
    init_lhln_db()

    conn = get_lhln_conn()

    count_row = conn.execute("""
        SELECT COUNT(*) AS cnt
        FROM lhln_reference
    """).fetchone()

    country_row = conn.execute("""
        SELECT COUNT(DISTINCT negara) AS cnt
        FROM lhln_reference
        WHERE COALESCE(negara, '') != ''
    """).fetchone()

    last_sync = conn.execute("""
        SELECT crawled_at, total_count, saved_count
        FROM lhln_sync_history
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    conn.close()

    pdf_exists = LHLN_GUIDE_PDF_PATH.exists()

    return {
        "db_exists": LHLN_DB_PATH.exists(),
        "db_path": str(LHLN_DB_PATH),
        "record_count": int(count_row["cnt"]),
        "country_count": int(country_row["cnt"]),
        "last_sync": dict(last_sync) if last_sync else None,
        "pdf_exists": pdf_exists,
        "pdf_path": str(LHLN_GUIDE_PDF_PATH),
        "pdf_name": LHLN_GUIDE_PDF_PATH.name if pdf_exists else "",
    }


def get_lhln_records(
    country: str = "",
    keyword: str = "",
    limit: int = 300,
) -> dict[str, Any]:
    init_lhln_db()

    limit = max(1, min(int(limit), 1000))

    where = []
    params = []

    if country:
        where.append("negara = ?")
        params.append(country)

    if keyword:
        where.append("""
        (
            nama_lhln LIKE ?
            OR nama_lhln_raw LIKE ?
            OR abbreviation LIKE ?
            OR kota LIKE ?
            OR no_reg LIKE ?
            OR status LIKE ?
        )
        """)
        like = f"%{keyword}%"
        params.extend([like, like, like, like, like, like])

    where_sql = ""
    if where:
        where_sql = "WHERE " + " AND ".join(where)

    conn = get_lhln_conn()

    rows = conn.execute(f"""
        SELECT
            negara,
            nama_lhln,
            abbreviation,
            kota,
            no_reg,
            tgl_berlaku,
            status
        FROM lhln_reference
        {where_sql}
        ORDER BY negara, nama_lhln
        LIMIT ?
    """, params + [limit]).fetchall()

    countries = conn.execute("""
        SELECT DISTINCT negara
        FROM lhln_reference
        WHERE COALESCE(negara, '') != ''
        ORDER BY negara
    """).fetchall()

    conn.close()

    return {
        "rows": [dict(row) for row in rows],
        "countries": [row["negara"] for row in countries],
        "limit": limit,
    }


def get_lhln_reference_df() -> pd.DataFrame:
    init_lhln_db()

    conn = get_lhln_conn()

    try:
        df = pd.read_sql_query("""
            SELECT
                negara,
                nama_lhln,
                abbreviation,
                kota,
                no_reg,
                tgl_berlaku,
                status
            FROM lhln_reference
            ORDER BY negara, nama_lhln
        """, conn)
    finally:
        conn.close()

    return df


def find_korean_font_file() -> str | None:
    candidates = [
        r"C:\Windows\Fonts\malgun.ttf",
        r"C:\Windows\Fonts\malgunbd.ttf",
        r"C:\Windows\Fonts\gulim.ttc",
        r"C:\Windows\Fonts\batang.ttc",
    ]

    for path in candidates:
        if os.path.exists(path):
            return path

    return None


def safe_pdf_text(value: Any) -> str:
    text = normalize_text(value)
    return text


def insert_pdf_textbox(page, rect, text, fontsize=8, align=0):
    font_path = find_korean_font_file()
    fontname = "korfont" if font_path else "helv"

    kwargs = {
        "fontsize": fontsize,
        "fontname": fontname,
        "align": align,
        "color": (0, 0, 0),
    }

    if font_path:
        kwargs["fontfile"] = font_path

    try:
        page.insert_textbox(rect, safe_pdf_text(text), **kwargs)
    except Exception:
        page.insert_textbox(
            rect,
            safe_pdf_text(text),
            fontsize=fontsize,
            fontname="helv",
            align=align,
            color=(0, 0, 0),
        )


def draw_pdf_cell(page, x, y, w, h, text, fontsize=7.5, fill=None, align=0):
    rect = fitz.Rect(x, y, x + w, y + h)

    if fill:
        page.draw_rect(rect, color=(0.80, 0.80, 0.80), fill=fill, width=0.5)
    else:
        page.draw_rect(rect, color=(0.75, 0.75, 0.75), width=0.5)

    insert_pdf_textbox(
        page,
        fitz.Rect(x + 3, y + 3, x + w - 3, y + h - 3),
        text,
        fontsize=fontsize,
        align=align,
    )


def create_lhln_guide_pdf(output_path: Path = LHLN_GUIDE_PDF_PATH) -> dict[str, Any]:
    df = get_lhln_reference_df()

    if df.empty:
        raise ValueError("LHLN DB가 비어 있습니다. 먼저 교차인정기관 DB 동기화를 실행하세요.")

    for col in ["negara", "nama_lhln", "abbreviation", "kota", "no_reg", "tgl_berlaku", "status"]:
        if col not in df.columns:
            df[col] = ""

    df = df.fillna("").copy()

    doc = fitz.open()

    page_w = 842
    page_h = 595
    margin_x = 32
    row_h = 31
    header_h = 25

    col_defs = [
        ("국가", 75),
        ("기관명", 275),
        ("약어", 70),
        ("도시", 95),
        ("등록번호", 95),
        ("유효/등록일", 105),
        ("상태", 85),
    ]

    def new_page(page_no):
        page = doc.new_page(width=page_w, height=page_h)

        insert_pdf_textbox(
            page,
            fitz.Rect(margin_x, 18, page_w - margin_x, 42),
            "BPJPH 교차인정 할랄 인증기관 안내",
            fontsize=15,
            align=1,
        )

        insert_pdf_textbox(
            page,
            fitz.Rect(margin_x, 44, page_w - margin_x, 68),
            f"발행일: {datetime.now().strftime('%Y-%m-%d')} / 기준: BPJPH LHLN DB / Page {page_no}",
            fontsize=8,
            align=1,
        )

        note = (
            "본 자료는 BPJPH LHLN 교차인정기관 확인을 위한 참고자료입니다. "
            "최종 인정 여부는 인증서 원문, 제조국, 인증기관 소재국, BPJPH 최신 기준을 함께 확인해야 합니다."
        )

        insert_pdf_textbox(
            page,
            fitz.Rect(margin_x, 70, page_w - margin_x, 95),
            note,
            fontsize=8,
            align=0,
        )

        y = 105
        x = margin_x

        for title, w in col_defs:
            draw_pdf_cell(
                page,
                x,
                y,
                w,
                header_h,
                title,
                fontsize=8,
                fill=(0.90, 0.93, 0.96),
                align=1,
            )
            x += w

        return page, y + header_h

    page_no = 1
    page, y = new_page(page_no)

    for _, row in df.iterrows():
        if y + row_h > page_h - 35:
            page_no += 1
            page, y = new_page(page_no)

        values = [
            row.get("negara", ""),
            row.get("nama_lhln", ""),
            row.get("abbreviation", ""),
            row.get("kota", ""),
            row.get("no_reg", ""),
            row.get("tgl_berlaku", ""),
            row.get("status", ""),
        ]

        x = margin_x

        for value, (_, w) in zip(values, col_defs):
            draw_pdf_cell(
                page,
                x,
                y,
                w,
                row_h,
                value,
                fontsize=7.2,
                fill=None,
                align=0,
            )
            x += w

        y += row_h

    LHLN_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    doc.save(output_path)
    doc.close()

    return {
        "ok": True,
        "pdf_path": str(output_path),
        "pdf_name": output_path.name,
        "row_count": int(len(df)),
    }