"""실패 집계 화면. 엔진 교체 전의 낡은 TESSERACT_ERROR 이력을 걸러낸다."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os
import re
import sqlite3

from app.services.ocr.engines import (
    TESSERACT_AVAILABLE,
    get_tesseract_runtime_info,
    is_tesseract_error_text,
)
from app.services.ocr.store import (
    ensure_ocr_db,
    get_ocr_conn,
)
from app.services.ocr.jobs import (
    delete_ocr_jobs,
    normalize_ocr_result_for_response,
)


OCR_FAILURE_STATUSES = {
    "TESSERACT_ERROR",
    "SCANNED_NEED_OCR",
    "NO_TEXT",
    "PDF_RENDER_ERROR",
    "IMAGE_READ_ERROR",
    "ERROR",
}


def _resolve_ocr_failure_status(data: dict[str, Any]) -> str:
    status = str(data.get("status") or "").upper()
    error_message = str(data.get("error_message") or "")
    raw_text = str(data.get("raw_text") or "")
    result = data.get("result") or {}

    rule = (
        data.get("certificate_rule")
        or result.get("certificate_rule")
        or result.get("field_guess", {}).get("certificate_rule")
        or {}
    )

    blob = "\n".join([
        status,
        error_message,
        raw_text[:1500],
        str(result.get("error") or ""),
        str(result.get("message") or ""),
        str(rule.get("parse_status") or ""),
        str(rule.get("message") or ""),
    ]).lower()

    if (
        "tesseract is not installed" in blob
        or "not in your path" in blob
        or "tesseractnotfounderror" in blob
        or "[tesseract_error]" in blob
        or str(rule.get("parse_status") or "").upper() == "TESSERACT_ERROR"
    ):
        return "TESSERACT_ERROR"

    if (
        "pdfinfo" in blob
        or "unable to get page count" in blob
        or "[pdf_render_error]" in blob
    ):
        return "PDF_RENDER_ERROR"

    if (
        "cannot identify image file" in blob
        or "[image_read_error]" in blob
    ):
        return "IMAGE_READ_ERROR"

    if (
        "scanned_need_ocr" in blob
        or "[scanned_need_ocr]" in blob
        or "text layer is empty" in blob
        or "텍스트 레이어" in blob
    ):
        return "SCANNED_NEED_OCR"

    if (
        status == "NO_TEXT"
        or "[no_text]" in blob
        or "no text" in blob
        or "추출된 텍스트가 없습니다" in blob
    ):
        return "NO_TEXT"

    if status == "ERROR":
        return "ERROR"

    return status


def _ocr_history_key(data: dict[str, Any]) -> str:
    # ?? ?? ??? key.
    # junction/symlink/????? ?? ??? ?????.
    source_value = str(data.get("source_path") or "").strip()
    filename = str(data.get("filename") or "").strip()

    if source_value:
        backend_dir = Path(__file__).resolve().parents[2]
        raw_path = Path(source_value)

        candidates = (
            [raw_path]
            if raw_path.is_absolute()
            else [
                backend_dir / raw_path,
                Path.cwd() / raw_path,
            ]
        )

        for candidate in candidates:
            try:
                canonical = Path(
                    os.path.realpath(str(candidate))
                ).resolve(strict=False)

                if canonical.exists():
                    value = str(canonical)
                    value = value.replace("\\", "/").lower()
                    value = re.sub(r"/+", "/", value)
                    return value
            except Exception:
                continue

        value = source_value.replace("\\", "/").lower()
        value = re.sub(r"/+", "/", value)
        return value

    value = filename.replace("\\", "/").lower()
    value = re.sub(r"/+", "/", value)
    return value


def _hydrate_ocr_failure_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)

    try:
        data["result"] = json.loads(data.get("result_json") or "{}")
    except Exception:
        data["result"] = {}

    try:
        data = normalize_ocr_result_for_response(data)
    except Exception:
        pass

    return data


def _is_successful_ocr_job(data: dict[str, Any]) -> bool:
    """
    현재 기준 정상 OCR job인지 판단.
    DONE이어도 raw_text 안에 과거 Tesseract 오류문구가 있으면 성공으로 보지 않는다.
    """
    status = str(data.get("status") or "").upper()

    if status != "DONE":
        return False

    failure_status = _resolve_ocr_failure_status(data)

    if failure_status in OCR_FAILURE_STATUSES:
        return False

    raw_text = str(data.get("raw_text") or "")
    error_message = str(data.get("error_message") or "")

    if is_tesseract_error_text(raw_text) or is_tesseract_error_text(error_message):
        return False

    return True


def _build_latest_maps(rows: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, int]]:
    """
    latest_job_id_by_key: 파일별 최신 job id
    latest_success_id_by_key: 파일별 최신 정상 DONE job id
    """
    latest_job_id_by_key: dict[str, int] = {}
    latest_success_id_by_key: dict[str, int] = {}

    for data in rows:
        key = _ocr_history_key(data)

        if not key:
            continue

        try:
            job_id = int(data.get("id") or 0)
        except Exception:
            job_id = 0

        if job_id <= 0:
            continue

        if job_id > latest_job_id_by_key.get(key, 0):
            latest_job_id_by_key[key] = job_id

        if _is_successful_ocr_job(data) and job_id > latest_success_id_by_key.get(key, 0):
            latest_success_id_by_key[key] = job_id

    return latest_job_id_by_key, latest_success_id_by_key


def _is_stale_tesseract_history(
    data: dict[str, Any],
    latest_success_id_by_key: dict[str, int],
) -> bool:
    """
    과거 Tesseract 실패 이력 여부.
    같은 파일에 더 최신 정상 DONE job이 있으면 stale로 판단한다.
    """
    failure_status = _resolve_ocr_failure_status(data)

    if failure_status != "TESSERACT_ERROR":
        return False

    key = _ocr_history_key(data)

    if not key:
        return False

    try:
        job_id = int(data.get("id") or 0)
    except Exception:
        job_id = 0

    return latest_success_id_by_key.get(key, 0) > job_id


def get_ocr_failure_summary(
    limit: int = 300,
    keyword: str = "",
    include_test: bool = True,
    hide_stale_tesseract: bool = True,
    latest_only: bool = False,
) -> dict[str, Any]:
    """
    관리 > 데이터 추출 > OCR 오류 모니터링 패널용.
    현재 오류와 과거 Tesseract 실패 이력을 분리한다.
    """
    ensure_ocr_db()

    limit = max(1, min(int(limit), 1000))
    keyword = str(keyword or "").strip()

    where = []
    params: list[Any] = []

    if not include_test:
        where.append("""
            COALESCE(source_path, '') NOT LIKE '%ocr_test_uploads%'
            AND COALESCE(source_path, '') NOT LIKE '%data/ocr_test_uploads%'
        """)

    sql = """
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
    """

    if where:
        sql += " WHERE " + " AND ".join(f"({x})" for x in where)

    sql += """
        ORDER BY id DESC
        LIMIT 5000
    """

    conn = get_ocr_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    hydrated_rows = [_hydrate_ocr_failure_row(row) for row in rows]
    latest_job_id_by_key, latest_success_id_by_key = _build_latest_maps(hydrated_rows)

    result_rows = []

    counts = {
        "TESSERACT_ERROR": 0,
        "STALE_TESSERACT_HISTORY": 0,
        "SCANNED_NEED_OCR": 0,
        "NO_TEXT": 0,
        "PDF_RENDER_ERROR": 0,
        "IMAGE_READ_ERROR": 0,
        "ERROR": 0,
        "DONE": 0,
        "OTHER": 0,
    }

    for data in hydrated_rows:
        key = _ocr_history_key(data)

        try:
            job_id = int(data.get("id") or 0)
        except Exception:
            job_id = 0

        if latest_only and key and latest_job_id_by_key.get(key) != job_id:
            continue

        if keyword:
            haystack = "\n".join([
                str(data.get("filename") or ""),
                str(data.get("source_path") or ""),
                str(data.get("error_message") or ""),
                str(data.get("raw_text") or "")[:2000],
                str(data.get("result_json") or "")[:2000],
            ]).lower()

            if keyword.lower() not in haystack:
                continue

        failure_status = _resolve_ocr_failure_status(data)
        is_stale_tesseract = _is_stale_tesseract_history(
            data,
            latest_success_id_by_key,
        )

        if is_stale_tesseract:
            bucket = "STALE_TESSERACT_HISTORY"
        elif failure_status in OCR_FAILURE_STATUSES:
            bucket = failure_status
        elif str(data.get("status") or "").upper() == "DONE":
            bucket = "DONE"
        else:
            bucket = "OTHER"

        counts[bucket] = counts.get(bucket, 0) + 1

        if is_stale_tesseract and hide_stale_tesseract:
            continue

        if bucket in OCR_FAILURE_STATUSES or bucket == "STALE_TESSERACT_HISTORY":
            rule = data.get("certificate_rule") or {}
            image = data.get("image_classification") or {}

            result_rows.append({
                "id": data.get("id"),
                "filename": data.get("filename") or "",
                "source_path": data.get("source_path") or "",
                "file_ext": data.get("file_ext") or "",
                "status": data.get("status") or "",
                "failure_status": bucket,
                "is_stale_tesseract": bool(is_stale_tesseract),
                "error_message": data.get("error_message") or "",
                "text_length": data.get("text_length") or len(data.get("raw_text") or ""),
                "raw_text_preview": (data.get("raw_text") or "")[:500],
                "created_at": data.get("created_at") or "",
                "updated_at": data.get("updated_at") or "",
                "cert_org": rule.get("cert_org") or "",
                "parse_status": rule.get("parse_status") or "",
                "image_final_org": image.get("final_org") or "",
                "image_decision": image.get("image_decision") or image.get("decision") or "",
                "tesseract_available": bool((data.get("result") or {}).get("tesseract_available")),
                "current_tesseract_available": TESSERACT_AVAILABLE,
                "current_tesseract_info": get_tesseract_runtime_info(),
            })

        if len(result_rows) >= limit:
            break

    active_failure_count = sum(
        counts.get(k, 0)
        for k in OCR_FAILURE_STATUSES
    )

    return {
        "ok": True,
        "limit": limit,
        "keyword": keyword,
        "include_test": include_test,
        "hide_stale_tesseract": hide_stale_tesseract,
        "latest_only": latest_only,
        "counts": counts,
        "failure_count": len(result_rows),
        "active_failure_count": active_failure_count,
        "stale_tesseract_count": counts.get("STALE_TESSERACT_HISTORY", 0),
        "rows": result_rows,
    }


def delete_stale_tesseract_ocr_jobs(
    include_test: bool = True,
) -> dict[str, Any]:
    """
    같은 source_path/filename에 더 최신 정상 DONE job이 존재하는
    과거 Tesseract 실패 OCR job만 삭제한다.
    """
    ensure_ocr_db()

    where = []
    params: list[Any] = []

    if not include_test:
        where.append("""
            COALESCE(source_path, '') NOT LIKE '%ocr_test_uploads%'
            AND COALESCE(source_path, '') NOT LIKE '%data/ocr_test_uploads%'
        """)

    sql = """
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
    """

    if where:
        sql += " WHERE " + " AND ".join(f"({x})" for x in where)

    sql += " ORDER BY id DESC"

    conn = get_ocr_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    hydrated_rows = [_hydrate_ocr_failure_row(row) for row in rows]
    _, latest_success_id_by_key = _build_latest_maps(hydrated_rows)

    stale_ids = []

    for data in hydrated_rows:
        if _is_stale_tesseract_history(data, latest_success_id_by_key):
            try:
                stale_ids.append(int(data.get("id") or 0))
            except Exception:
                pass

    stale_ids = sorted({x for x in stale_ids if x > 0})

    if not stale_ids:
        return {
            "ok": True,
            "deleted": 0,
            "job_ids": [],
            "message": "삭제할 과거 Tesseract 오류 이력이 없습니다.",
        }

    return delete_ocr_jobs(stale_ids)
