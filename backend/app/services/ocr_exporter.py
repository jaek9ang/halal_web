from __future__ import annotations

import csv
import json
import sqlite3
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import BACKEND_DIR, PMF_APP_DB_PATH, OCR_TEST_DB_PATH
from app.services.certificate_rule_service import parse_certificate_rule
from app.services.ocr_service import (
    get_ocr_job,
    normalize_ocr_result_for_response,
    reconcile_template_classification_with_rule,
)
from app.core.db import connect as db_connect

EXPORT_VERSION = "ocr_rule_review_v1"
OCR_EXPORT_DIR = BACKEND_DIR / "data" / "ocr_exports"


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _safe_json_loads(value: Any, default: Any = None) -> Any:
    if default is None:
        default = {}

    if isinstance(value, (dict, list)):
        return value

    if not value:
        return default

    try:
        return json.loads(str(value))
    except Exception:
        return default


def _table_exists(db_path: Path, table_name: str) -> bool:
    if not db_path.exists():
        return False

    conn = db_connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = ?
            """,
            (table_name,),
        ).fetchone()

        return row is not None
    finally:
        conn.close()


def _connect(db_path: Path) -> sqlite3.Connection:
    return db_connect(db_path)


def _infer_source_category(source_path: str) -> str:
    text = str(source_path or "").replace("\\", "/").lower()

    if "ocr_test_uploads" in text or "data/ocr_test_uploads" in text:
        return "OCR_TEST_RESULT"

    if "ocr_manual_uploads" in text or "manual_upload" in text:
        return "MANUAL_UPLOAD_FILE"

    if "mail_downloads" in text or "received_certs" in text:
        return "MAIL_RECEIVED_FILE"

    if "halal 하부원료" in text or "halal_doc" in text:
        return "HALAL_DOC_FILE"

    if "cert_template" in text or "양식" in text:
        return "TEMPLATE_RELATED_FILE"

    return "OCR_JOB"


def _normalize_pages(pages: Any) -> list[dict[str, Any]]:
    if not isinstance(pages, list):
        return []

    normalized = []

    for idx, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            normalized.append({
                "page": idx,
                "method": "",
                "text_length": len(str(page or "")),
            })
            continue

        normalized.append({
            "page": page.get("page") or page.get("page_no") or idx,
            "method": page.get("method") or "",
            "text_length": int(page.get("text_length") or page.get("char_count") or 0),
            "text_preview": page.get("text_preview") or page.get("preview") or "",
        })

    return normalized


def _get_rule_value(rule: dict[str, Any], *keys: str) -> Any:
    if not isinstance(rule, dict):
        return ""

    for key in keys:
        value = rule.get(key)

        if value not in [None, "", [], {}]:
            return value

    return ""

def _json_fingerprint(value: Any) -> str:
    try:
        return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value or "")

def _build_record_from_ocr_job(
    data: dict[str, Any],
    *,
    source_type: str = "ocr_job",
    source_id: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = data.get("result") or _safe_json_loads(data.get("result_json"), {})
    data["result"] = result

    try:
        data = normalize_ocr_result_for_response(data)
    except Exception:
        pass

    result = data.get("result") or {}
    certificate_rule = (
        data.get("certificate_rule")
        or result.get("certificate_rule")
        or result.get("field_guess", {}).get("certificate_rule")
        or {}
    )
    image_classification = (
        data.get("image_classification")
        or result.get("image_classification")
        or result.get("field_guess", {}).get("image_classification")
        or {}
    )

    raw_text = data.get("raw_text") or ""
    pages = _normalize_pages(result.get("pages") or [])

    file_path = data.get("source_path") or result.get("source_path") or ""
    filename = data.get("filename") or result.get("filename") or Path(file_path).name
    file_ext = data.get("file_ext") or result.get("file_ext") or Path(filename).suffix.lower()

    certificate_rule_saved = certificate_rule if isinstance(certificate_rule, dict) else {}
    image_classification_saved = image_classification if isinstance(image_classification, dict) else {}

    try:
        certificate_rule_current = parse_certificate_rule(
            raw_text=raw_text,
            filename=filename,
        )
    except Exception as e:
        certificate_rule_current = {
            "ok": False,
            "parse_status": "RULE_ERROR",
            "cert_org": "UNKNOWN",
            "message": str(e),
            "confidence": "LOW",
        }

    image_classification_current = dict(image_classification_saved)

    if image_classification_current:
        try:
            image_classification_current = reconcile_template_classification_with_rule(
                image_classification_current,
                certificate_rule_current,
            )
        except Exception as e:
            image_classification_current["reconcile_error"] = str(e)

    certificate_rule_changed = (
        _json_fingerprint(certificate_rule_saved)
        != _json_fingerprint(certificate_rule_current)
    )

    record = {
        "export_version": EXPORT_VERSION,
        "source_type": source_type,
        "source_category": _infer_source_category(file_path),
        "source_id": int(source_id if source_id is not None else data.get("id") or 0),

        "ocr_job_id": int(data.get("id") or 0),
        "filename": filename,
        "file_path": file_path,
        "file_ext": file_ext,
        "status": data.get("status") or "",
        "error_message": data.get("error_message") or "",
        "created_at": data.get("created_at") or "",
        "updated_at": data.get("updated_at") or "",

        "page_count": int(result.get("page_count") or len(pages) or 0),
        "text_length": len(raw_text),
        "raw_text": raw_text,
        "pages": pages,

        # 기본 필드는 현재 규칙 기준으로 둔다.
        # 과거 DB 저장값은 *_saved로 별도 보존한다.
        "certificate_rule": certificate_rule_current,
        "certificate_rule_saved": certificate_rule_saved,
        "certificate_rule_current": certificate_rule_current,
        "certificate_rule_changed": certificate_rule_changed,

        "image_classification": image_classification_current,
        "image_classification_saved": image_classification_saved,
        "image_classification_current": image_classification_current,
    }

    if extra:
        record.update(extra)

    return record


def _build_record_from_ocr_test_row(row: dict[str, Any]) -> dict[str, Any]:
    ocr_job_id = row.get("ocr_job_id")

    if ocr_job_id:
        try:
            job = get_ocr_job(int(ocr_job_id))
            return _build_record_from_ocr_job(
                job,
                source_type="ocr_test_result",
                source_id=int(row.get("id") or 0),
                extra={
                    "ocr_test_file_id": int(row.get("id") or 0),
                    "ocr_test_status": row.get("status") or "",
                    "ocr_test_original_filename": row.get("original_filename") or "",
                    "ocr_test_saved_path": row.get("saved_path") or "",
                    "ocr_test_file_hash": row.get("file_hash") or "",
                },
            )
        except Exception:
            pass

    raw_text = row.get("raw_text_preview") or ""

    return {
        "export_version": EXPORT_VERSION,
        "source_type": "ocr_test_result",
        "source_category": "OCR_TEST_RESULT",
        "source_id": int(row.get("id") or 0),

        "ocr_job_id": int(ocr_job_id or 0),
        "ocr_test_file_id": int(row.get("id") or 0),
        "ocr_test_file_hash": row.get("file_hash") or "",

        "filename": row.get("original_filename") or row.get("saved_filename") or "",
        "file_path": row.get("saved_path") or "",
        "file_ext": Path(row.get("saved_path") or row.get("saved_filename") or "").suffix.lower(),
        "status": row.get("status") or "",
        "error_message": row.get("error_message") or "",
        "created_at": row.get("created_at") or "",
        "updated_at": row.get("updated_at") or "",

        "page_count": 0,
        "text_length": len(raw_text),
        "raw_text": raw_text,
        "pages": [],

        "certificate_rule": {},
        "image_classification": {},
    }


def _load_ocr_job_records(limit: int) -> list[dict[str, Any]]:
    if not _table_exists(PMF_APP_DB_PATH, "ocr_jobs"):
        return []

    conn = _connect(PMF_APP_DB_PATH)

    try:
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
                updated_at
            FROM ocr_jobs
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    finally:
        conn.close()

    records = []

    for row in rows:
        data = dict(row)
        data["result"] = _safe_json_loads(data.get("result_json"), {})
        records.append(_build_record_from_ocr_job(data))

    return records


def _load_ocr_test_records(limit: int) -> list[dict[str, Any]]:
    if not _table_exists(OCR_TEST_DB_PATH, "ocr_test_files"):
        return []

    conn = _connect(OCR_TEST_DB_PATH)

    try:
        rows = conn.execute(
            """
            SELECT
                id,
                file_hash,
                original_filename,
                saved_filename,
                saved_path,
                size_bytes,
                status,
                ocr_job_id,
                raw_text_preview,
                error_message,
                created_at,
                updated_at
            FROM ocr_test_files
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    finally:
        conn.close()

    return [_build_record_from_ocr_test_row(dict(row)) for row in rows]


def _summary_row(record: dict[str, Any]) -> dict[str, Any]:
    rule = record.get("certificate_rule") or {}
    image = record.get("image_classification") or {}

    return {
        "source_type": record.get("source_type") or "",
        "source_category": record.get("source_category") or "",
        "source_id": record.get("source_id") or "",
        "ocr_job_id": record.get("ocr_job_id") or "",
        "filename": record.get("filename") or "",
        "status": record.get("status") or "",
        "cert_org": _get_rule_value(rule, "cert_org"),
        "image_final_org": image.get("final_org") or "",
        "image_decision": image.get("image_decision") or image.get("decision") or "",
        "text_image_conflict": image.get("text_image_conflict"),
        "cert_country": _get_rule_value(rule, "cert_country"),
        "cert_no": _get_rule_value(rule, "cert_no", "certificate_no", "certificate_number"),
        "expiry_date": _get_rule_value(rule, "expiry_date", "valid_until", "expired_date"),
        "manufacturer": _get_rule_value(rule, "manufacturer", "company", "company_name"),
        "manufacturing_country": _get_rule_value(rule, "manufacturing_country", "mfg_country"),
        "products_count": _get_rule_value(rule, "products_count"),
        "source_rule": _get_rule_value(rule, "source_rule"),
        "confidence": _get_rule_value(rule, "confidence"),
        "parse_status": _get_rule_value(rule, "parse_status"),
        "text_length": record.get("text_length") or 0,
        "page_count": record.get("page_count") or 0,
        "created_at": record.get("created_at") or "",
        "updated_at": record.get("updated_at") or "",
        "file_path": record.get("file_path") or "",
        "error_message": record.get("error_message") or "",
    }


def _write_export_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _write_summary_csv(records: list[dict[str, Any]], path: Path) -> None:
    rows = [_summary_row(record) for record in records]

    fieldnames = [
        "source_type",
        "source_category",
        "source_id",
        "ocr_job_id",
        "filename",
        "status",
        "cert_org",
        "image_final_org",
        "image_decision",
        "text_image_conflict",
        "cert_country",
        "cert_no",
        "expiry_date",
        "manufacturer",
        "manufacturing_country",
        "products_count",
        "source_rule",
        "confidence",
        "parse_status",
        "text_length",
        "page_count",
        "created_at",
        "updated_at",
        "file_path",
        "error_message",
    ]

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_combined_ocr_text(records: list[dict[str, Any]], path: Path) -> None:
    parts = [
        "# OCR Data Export",
        "",
        f"- export_version: `{EXPORT_VERSION}`",
        f"- generated_at: `{_now_text()}`",
        f"- record_count: `{len(records)}`",
        "",
    ]

    for idx, record in enumerate(records, start=1):
        rule = record.get("certificate_rule") or {}
        image = record.get("image_classification") or {}

        parts.extend([
            "---",
            "",
            f"## {idx}. {record.get('filename') or '-'}",
            "",
            f"- source_type: `{record.get('source_type')}`",
            f"- source_category: `{record.get('source_category')}`",
            f"- source_id: `{record.get('source_id')}`",
            f"- ocr_job_id: `{record.get('ocr_job_id')}`",
            f"- status: `{record.get('status')}`",
            f"- file_path: `{record.get('file_path')}`",
            f"- cert_org: `{rule.get('cert_org') or '-'}`",
            f"- image_final_org: `{image.get('final_org') or '-'}`",
            f"- cert_no: `{rule.get('cert_no') or rule.get('certificate_no') or '-'}`",
            f"- expiry_date: `{rule.get('expiry_date') or rule.get('valid_until') or '-'}`",
            f"- manufacturer: `{rule.get('manufacturer') or '-'}`",
            f"- manufacturing_country: `{rule.get('manufacturing_country') or '-'}`",
            f"- cert_country: `{rule.get('cert_country') or '-'}`",
            f"- text_length: `{record.get('text_length') or 0}`",
            "",
            "```text",
            record.get("raw_text") or "",
            "```",
            "",
        ])

    path.write_text("\n".join(parts), encoding="utf-8")


def create_ocr_data_export_zip(
    *,
    limit: int = 10000,
    include_ocr_jobs: bool = True,
    include_ocr_tests: bool = True,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 50000))

    OCR_EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []

    if include_ocr_jobs:
        records.extend(_load_ocr_job_records(limit=limit))

    if include_ocr_tests:
        records.extend(_load_ocr_test_records(limit=limit))

    stamp = _stamp()
    work_dir = OCR_EXPORT_DIR / f"ocr_data_export_{stamp}"
    work_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = work_dir / "export.jsonl"
    summary_path = work_dir / "summary.csv"
    combined_text_path = work_dir / "combined_ocr_text.md"
    zip_path = OCR_EXPORT_DIR / f"ocr_data_export_{stamp}.zip"

    _write_export_jsonl(records, jsonl_path)
    _write_summary_csv(records, summary_path)
    _write_combined_ocr_text(records, combined_text_path)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(jsonl_path, "export.jsonl")
        zf.write(summary_path, "summary.csv")
        zf.write(combined_text_path, "combined_ocr_text.md")

    counts_by_source_type = dict(Counter(record.get("source_type") for record in records))
    counts_by_source_category = dict(Counter(record.get("source_category") for record in records))
    counts_by_status = dict(Counter(record.get("status") for record in records))

    return {
        "ok": True,
        "export_version": EXPORT_VERSION,
        "generated_at": _now_text(),
        "zip_path": str(zip_path),
        "zip_filename": zip_path.name,
        "record_count": len(records),
        "counts_by_source_type": counts_by_source_type,
        "counts_by_source_category": counts_by_source_category,
        "counts_by_status": counts_by_status,
        "files": {
            "export_jsonl": str(jsonl_path),
            "summary_csv": str(summary_path),
            "combined_ocr_text_md": str(combined_text_path),
        },
    }