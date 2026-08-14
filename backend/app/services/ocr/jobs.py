"""OCR job 생성·조회·삭제."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import json

from app.services.certificate_rule_service import parse_certificate_rule
from app.services.ocr_context_service import parse_certificate_with_linked_context

from app.services.ocr.engines import (
    TESSERACT_AVAILABLE,
    extract_image_text,
    extract_pdf_text,
    get_tesseract_runtime_info,
    is_tesseract_error_text,
)
from app.services.ocr.store import (
    ensure_ocr_db,
    get_ocr_conn,
)
from app.services.ocr.paths import (
    is_allowed_cert_file,
    resolve_allowed_ocr_source_path,
)
from app.services.ocr.templates import (
    build_template_classification_for_ocr,
    reconcile_template_classification_with_rule,
)


def guess_certificate_fields(
    raw_text: str,
    filename: str = "",
    source_path: str = "",
    ocr_job_id: int | None = None,
) -> dict[str, Any]:
    """
    OCR 기본 규칙을 실행한 뒤, 메일 관리번호와 PMF 연결이 확인되는 경우에만
    제품명·제조사 문맥으로 교차검증한다.
    """
    if source_path:
        parsed = parse_certificate_with_linked_context(
            raw_text=raw_text,
            filename=filename,
            source_path=source_path,
            ocr_job_id=ocr_job_id,
        )
    else:
        parsed = parse_certificate_rule(
            raw_text=raw_text,
            filename=filename,
        )

    org = parsed.get("cert_org")
    org_candidates = []

    if org and org != "UNKNOWN":
        org_candidates.append(org)

    return {
        "org_candidates": org_candidates,
        "has_text": bool((raw_text or "").strip()),
        "text_length": len(raw_text or ""),
        "certificate_rule": parsed,
    }


def create_ocr_job(
    source_path: str,
    ocr_scanned_pages: bool = True,
    lang: str = "eng",
) -> dict[str, Any]:
    ensure_ocr_db()

    path = resolve_allowed_ocr_source_path(source_path)

    if not path.exists():
        raise FileNotFoundError(f"파일을 찾지 못했습니다: {path}")

    if not is_allowed_cert_file(path):
        raise ValueError(f"지원하지 않는 파일 형식입니다: {path.suffix}")
    
    if path.stat().st_size <= 0:
        raise ValueError(f"OCR 대상 파일이 비어 있습니다: {path}")
    
    now_ts = datetime.now().isoformat(timespec="seconds")

    conn = get_ocr_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO ocr_jobs (
        source_path,
        filename,
        file_ext,
        status,
        raw_text,
        result_json,
        error_message,
        created_at,
        updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(path),
        path.name,
        path.suffix.lower(),
        "RUNNING",
        "",
        "{}",
        "",
        now_ts,
        now_ts,
    ))

    job_id = cur.lastrowid
    conn.commit()
    conn.close()

    image_classification = build_template_classification_for_ocr(path)

    if image_classification.get("is_excluded"):
        result = {
            "source_path": str(path),
            "filename": path.name,
            "file_ext": path.suffix.lower(),
            "page_count": 0,
            "pages": [],
            "field_guess": {
                "org_candidates": [],
                "has_text": False,
                "text_length": 0,
                "certificate_rule": {},
                "image_classification": image_classification,
            },
            "certificate_rule": {},
            "image_classification": image_classification,
            "tesseract_available": TESSERACT_AVAILABLE,
            "tesseract_info": get_tesseract_runtime_info(),
            "ocr_lang": lang,
            "message": "관리자 판정값이 EXCLUDED라서 OCR을 실행하지 않았습니다.",
        }

        conn = get_ocr_conn()
        conn.execute("""
        UPDATE ocr_jobs
        SET status = ?,
            raw_text = ?,
            result_json = ?,
            error_message = ?,
            updated_at = ?
        WHERE id = ?
        """, (
            "EXCLUDED",
            "",
            json.dumps(result, ensure_ascii=False),
            "관리자 판정값이 EXCLUDED라서 OCR을 실행하지 않았습니다.",
            datetime.now().isoformat(timespec="seconds"),
            job_id,
        ))
        conn.commit()
        conn.close()

        return get_ocr_job(job_id)

    try:
        ext = path.suffix.lower()

        if ext == ".pdf":
            extracted = extract_pdf_text(
                path=path,
                ocr_scanned_pages=ocr_scanned_pages,
                lang=lang,
            )
        else:
            extracted = extract_image_text(
                path=path,
                lang=lang,
            )

        raw_text = extracted.get("text", "")
        field_guess = guess_certificate_fields(
            raw_text,
            filename=path.name,
            source_path=str(path),
            ocr_job_id=job_id,
        )
        certificate_rule = field_guess.get("certificate_rule") or {}

        # 이미지 양식 DB 분류와 OCR 텍스트 규칙 결과를 병합한다.
        # REVIEW/MANUAL_REVIEW에서 이미지 후보를 최종기관으로 오인하지 않도록 한다.
        image_classification = reconcile_template_classification_with_rule(
            image_classification,
            certificate_rule,
        )

        field_guess["image_classification"] = image_classification

        result = {
            "source_path": str(path),
            "filename": path.name,
            "file_ext": ext,
            "page_count": extracted.get("page_count", 0),
            "pages": extracted.get("pages", []),
            "field_guess": field_guess,
            "certificate_rule": certificate_rule,
            "image_classification": image_classification,
            "tesseract_available": TESSERACT_AVAILABLE,
            "tesseract_info": get_tesseract_runtime_info(),
            "ocr_lang": lang,
        }

        if is_tesseract_error_text(raw_text):
            status = "TESSERACT_ERROR"
            error_message = raw_text[:1000]
        elif raw_text.strip():
            status = "DONE"
            error_message = ""
        else:
            status = "NO_TEXT"
            error_message = ""

        conn = get_ocr_conn()
        conn.execute("""
        UPDATE ocr_jobs
        SET status = ?,
            raw_text = ?,
            result_json = ?,
            error_message = ?,
            updated_at = ?
        WHERE id = ?
        """, (
            status,
            raw_text,
            json.dumps(result, ensure_ascii=False),
            error_message,
            datetime.now().isoformat(timespec="seconds"),
            job_id,
        ))
        conn.commit()
        conn.close()

        return get_ocr_job(job_id)

    except Exception as e:
        error_result = {
            "source_path": str(path),
            "filename": path.name,
            "file_ext": path.suffix.lower(),
            "image_classification": image_classification,
            "error": str(e),
            "tesseract_available": TESSERACT_AVAILABLE,
            "tesseract_info": get_tesseract_runtime_info(),
            "ocr_lang": lang,
        }
        conn = get_ocr_conn()
        conn.execute("""
        UPDATE ocr_jobs
        SET status = ?,
            result_json = ?,
            error_message = ?,
            updated_at = ?
        WHERE id = ?
        """, (
            "ERROR",
            json.dumps(error_result, ensure_ascii=False),
            str(e),
            datetime.now().isoformat(timespec="seconds"),
            job_id,
        ))
        conn.commit()
        conn.close()

        return get_ocr_job(job_id)


def normalize_ocr_result_for_response(data: dict[str, Any]) -> dict[str, Any]:
    """
    DB에 이미 저장된 과거 OCR job도 응답 시점에
    image_classification + certificate_rule을 다시 reconcile한다.

    목적:
    - 기존 result_json에 final_org_source/text_rule_org가 없어도 화면에서는 보정값 표시
    - REVIEW/MANUAL_REVIEW 이미지 후보가 OCR 텍스트 규칙기관보다 우선되는 문제 방지
    """
    result = data.get("result") or {}

    if not isinstance(result, dict):
        result = {}

    rule = (
        result.get("certificate_rule")
        or result.get("field_guess", {}).get("certificate_rule")
    )

    if not rule:
        try:
            filename = data.get("filename") or Path(data.get("source_path") or "").name
            rule = parse_certificate_rule(
                raw_text=data.get("raw_text") or "",
                filename=filename,
            )
        except Exception as e:
            rule = {
                "ok": False,
                "parse_status": "RULE_ERROR",
                "message": str(e),
            }

    image_classification = (
        result.get("image_classification")
        or result.get("field_guess", {}).get("image_classification")
        or {}
    )

    if isinstance(image_classification, dict) and image_classification:
        image_classification = reconcile_template_classification_with_rule(
            image_classification,
            rule or {},
        )

    result["certificate_rule"] = rule
    result["image_classification"] = image_classification

    if isinstance(result.get("field_guess"), dict):
        result["field_guess"]["certificate_rule"] = rule
        result["field_guess"]["image_classification"] = image_classification

    data["result"] = result
    data["certificate_rule"] = rule
    data["image_classification"] = image_classification

    return data


def get_ocr_job(job_id: int) -> dict[str, Any]:
    ensure_ocr_db()

    conn = get_ocr_conn()
    row = conn.execute("""
        SELECT *
        FROM ocr_jobs
        WHERE id = ?
    """, (int(job_id),)).fetchone()
    conn.close()

    if not row:
        raise ValueError(f"OCR job을 찾지 못했습니다: {job_id}")

    data = dict(row)

    try:
        data["result"] = json.loads(data.get("result_json") or "{}")
    except Exception:
        data["result"] = {}

    data["raw_text_preview"] = (data.get("raw_text") or "")[:3000]

    return normalize_ocr_result_for_response(data)


def list_ocr_jobs(
    limit: int = 100,
    status: str = "",
    org: str = "",
    keyword: str = "",
    include_test: bool = False,
) -> dict[str, Any]:
    ensure_ocr_db()

    limit = max(1, min(int(limit), 500))

    where = []
    params = []

    if not include_test:
        where.append("""
            COALESCE(source_path, '') NOT LIKE '%ocr_test_uploads%'
            AND COALESCE(source_path, '') NOT LIKE '%data/ocr_test_uploads%'
        """)

    if status:
        where.append("UPPER(COALESCE(status, '')) = ?")
        params.append(status.upper())

    if keyword:
        like = f"%{keyword}%"
        where.append("""
            (
                COALESCE(filename, '') LIKE ?
                OR COALESCE(source_path, '') LIKE ?
                OR COALESCE(raw_text, '') LIKE ?
                OR COALESCE(result_json, '') LIKE ?
                OR COALESCE(error_message, '') LIKE ?
            )
        """)
        params.extend([like, like, like, like, like])

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
        LIMIT ?
    """
    params.append(limit)

    conn = get_ocr_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    result_rows = []

    for row in rows:
        data = dict(row)

        try:
            parsed_result = json.loads(data.get("result_json") or "{}")
        except Exception:
            parsed_result = {}

        data["result"] = parsed_result
        data = normalize_ocr_result_for_response(data)

        rule = data.get("certificate_rule") or {}
        image_classification = data.get("image_classification") or {}

        if org:
            target_org = org.upper()
            rule_org = str(rule.get("cert_org") or "").upper()
            image_orgs = {
                str(image_classification.get("predicted_org") or "").upper(),
                str(image_classification.get("final_org") or "").upper(),
            }

            if rule_org != target_org and target_org not in image_orgs:
                continue

        data["raw_text_preview"] = (data.get("raw_text") or "")[:500]

        # 목록 응답이 너무 커지는 것 방지
        data.pop("raw_text", None)
        data.pop("result_json", None)

        result_rows.append(data)

    return {
        "ok": True,
        "rows": result_rows,
        "count": len(result_rows),
    }


def delete_ocr_jobs(job_ids: list[int]) -> dict[str, Any]:
    ensure_ocr_db()

    ids = []
    for value in job_ids or []:
        try:
            ids.append(int(value))
        except Exception:
            pass

    ids = sorted(set(ids))

    if not ids:
        return {
            "ok": False,
            "deleted": 0,
            "message": "삭제할 OCR 작업 ID가 없습니다.",
        }

    placeholders = ",".join(["?"] * len(ids))

    conn = get_ocr_conn()
    cur = conn.cursor()

    cur.execute(
        f"DELETE FROM ocr_jobs WHERE id IN ({placeholders})",
        ids,
    )

    deleted = cur.rowcount
    conn.commit()
    conn.close()

    return {
        "ok": True,
        "deleted": deleted,
        "job_ids": ids,
    }
