from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import PMF_APP_DB_PATH
from app.services.certificate_filing_service import (
    copy_certificate_atomically,
    preview_certificate_filing,
)
from app.services.filing_name_service import FilingNameInput, get_halal_raw_material_root
from app.services.mail_request_item_service import (
    build_pmf_candidates_for_request_context,
    get_request_context_for_ocr_job,
)
from app.services.ocr_service import get_ocr_job, list_ocr_jobs
from app.services.pmf_filing_service import (
    get_pmf_material_snapshot,
    preview_pmf_update,
    restore_pmf_backup,
    update_pmf_certificate_fields,
)


ALLOWED_OCR_STATUSES = {"DONE"}
BLOCKED_PARSE_STATUSES = {
    "LOW_CONFIDENCE",
    "MANUAL_REVIEW",
    "TESSERACT_ERROR",
    "SCANNED_NEED_OCR",
    "NO_TEXT",
    "ERROR",
}


def get_conn() -> sqlite3.Connection:
    PMF_APP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(PMF_APP_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_filing_tables() -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS certificate_filing_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ocr_job_id INTEGER,
                request_id TEXT,
                pmf_row_pos INTEGER,
                pmf_depth INTEGER,
                source_path TEXT,
                target_path TEXT,
                cert_org TEXT,
                cert_no TEXT,
                expiry_date TEXT,
                status TEXT,
                copy_status TEXT,
                pmf_update_json TEXT,
                warning_json TEXT,
                error_message TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_certificate_filing_ocr_job
            ON certificate_filing_history(ocr_job_id)
            WHERE status IN ('CONFIRMED', 'DUPLICATE_SKIPPED')
            """
        )
        conn.commit()
    finally:
        conn.close()


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"", "-", "nan", "none", "null"} else text


def _rule_from_job(job: dict[str, Any]) -> dict[str, Any]:
    return job.get("certificate_rule") or (job.get("result") or {}).get("certificate_rule") or {}


def _image_org_from_job(job: dict[str, Any]) -> str:
    image = job.get("image_classification") or (job.get("result") or {}).get("image_classification") or {}
    return _clean(image.get("final_org") or image.get("predicted_org"))


def resolve_cert_values(job: dict[str, Any]) -> dict[str, str]:
    rule = _rule_from_job(job)
    cert_org = _clean(rule.get("cert_org")) or _image_org_from_job(job)
    cert_no = _clean(rule.get("cert_no"))
    expiry_date = _clean(rule.get("expiry_date"))
    parse_status = _clean(rule.get("parse_status"))
    confidence = _clean(rule.get("confidence"))

    return {
        "cert_org": cert_org.upper(),
        "cert_no": cert_no,
        "expiry_date": expiry_date,
        "parse_status": parse_status.upper(),
        "confidence": confidence.upper(),
    }


def get_confirmed_history_for_job(ocr_job_id: int) -> dict[str, Any] | None:
    ensure_filing_tables()
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT *
            FROM certificate_filing_history
            WHERE ocr_job_id = ?
              AND status IN ('CONFIRMED', 'DUPLICATE_SKIPPED')
            ORDER BY id DESC
            LIMIT 1
            """,
            (int(ocr_job_id),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _select_mail_item(
    request_context: dict[str, Any],
    pmf_row_pos: int,
    pmf_depth: int,
) -> dict[str, Any] | None:
    groups = build_pmf_candidates_for_request_context(request_context, limit_per_item=10)
    for group in groups:
        for match in group.get("pmf_matches") or []:
            if int(match.get("row_pos")) == int(pmf_row_pos) and int(match.get("depth")) == int(pmf_depth):
                result = dict(group.get("mail_item") or {})
                result["pmf_match_score"] = match.get("score", 0)
                result["pmf_match_reasons"] = match.get("reasons", [])
                return result
    return None


def _build_warnings(
    job: dict[str, Any],
    cert_values: dict[str, str],
    material: dict[str, Any],
    mail_item: dict[str, Any] | None,
) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    blockers: list[str] = []

    status = _clean(job.get("status")).upper()
    if status not in ALLOWED_OCR_STATUSES:
        blockers.append(f"OCR 상태가 확정 가능한 상태가 아닙니다: {status or '-'}")

    parse_status = cert_values.get("parse_status", "")
    if parse_status in BLOCKED_PARSE_STATUSES:
        blockers.append(f"규칙 판정 상태를 확인해야 합니다: {parse_status}")

    if not cert_values.get("cert_org") or cert_values.get("cert_org") == "UNKNOWN":
        blockers.append("인증기관이 확정되지 않았습니다.")

    if not Path(str(job.get("source_path") or "")).exists():
        blockers.append("OCR 원본 파일이 존재하지 않습니다.")

    if not material.get("material_no") or material.get("material_no") == "-":
        blockers.append("PMF 원료번호가 없습니다.")

    if not material.get("english_name") or material.get("english_name") == "-":
        blockers.append("PMF 영문 원료명이 없습니다.")

    if not material.get("maker") or material.get("maker") == "-":
        blockers.append("PMF 제조사가 없습니다.")

    if not material.get("supplier") or material.get("supplier") == "-":
        blockers.append("PMF 공급사가 없습니다.")

    cert_org = cert_values.get("cert_org")
    if cert_org != "BPJPH" and not cert_values.get("expiry_date"):
        blockers.append(f"{cert_org or '일반'} 인증서의 유효기간이 없습니다.")

    if cert_org == "BPJPH":
        if not mail_item:
            blockers.append("BPJPH 메일 요청 항목을 찾지 못해 PMF 예정 유효기간을 결정할 수 없습니다.")
        elif not mail_item.get("planned_expiry"):
            blockers.append("BPJPH 유지 확인 적용 예정일이 메일 로그에 없습니다.")

    if not cert_values.get("cert_no"):
        warnings.append("OCR 결과에 인증번호가 없습니다. PMF 기존 인증번호는 유지됩니다.")

    return warnings, blockers


def preview_filing_workflow(
    ocr_job_id: int,
    pmf_row_pos: int,
    pmf_depth: int = 0,
) -> dict[str, Any]:
    job = get_ocr_job(int(ocr_job_id))
    cert_values = resolve_cert_values(job)
    material_snapshot = get_pmf_material_snapshot(pmf_row_pos, pmf_depth)
    material = material_snapshot.to_dict()
    request_context = get_request_context_for_ocr_job(job)
    mail_item = _select_mail_item(request_context, pmf_row_pos, pmf_depth)

    warnings, blockers = _build_warnings(job, cert_values, material, mail_item)

    pmf_expiry = cert_values.get("expiry_date", "")
    if cert_values.get("cert_org") == "BPJPH":
        pmf_expiry = _clean((mail_item or {}).get("planned_expiry"))

    source_path = Path(str(job.get("source_path") or ""))
    naming_input = FilingNameInput(
        material_no=material["material_no"],
        material_name_en=material["english_name"],
        manufacturer=material["maker"],
        supplier=material["supplier"],
        cert_org=cert_values.get("cert_org", ""),
        expiry_date=cert_values.get("expiry_date", ""),
        source_extension=source_path.suffix or job.get("file_ext") or ".pdf",
    )

    filing_preview = preview_certificate_filing(
        source_path=source_path,
        naming_input=naming_input,
        root=get_halal_raw_material_root(),
    ).to_dict()

    # 원본 부재와 같은 치명 경고는 workflow blocker에 이미 반영한다.
    for warning in filing_preview.get("warnings") or []:
        if warning not in warnings and "원본" not in warning:
            warnings.append(warning)

    pmf_preview = preview_pmf_update(
        row_pos=pmf_row_pos,
        depth=pmf_depth,
        cert_org=cert_values.get("cert_org", ""),
        cert_no=cert_values.get("cert_no", ""),
        expiry_date=pmf_expiry,
    )
    for warning in pmf_preview.get("warnings") or []:
        if warning not in warnings:
            warnings.append(warning)

    history = get_confirmed_history_for_job(ocr_job_id)
    if history:
        blockers.append("이미 확정판정된 OCR Job입니다.")

    return {
        "ok": len(blockers) == 0,
        "ocr_job_id": int(ocr_job_id),
        "job": {
            "id": job.get("id"),
            "filename": job.get("filename"),
            "source_path": job.get("source_path"),
            "status": job.get("status"),
            "created_at": job.get("created_at"),
        },
        "certificate": cert_values,
        "request_context": {
            "request_id": request_context.get("request_id", ""),
            "attachment": request_context.get("attachment") or {},
            "mail_log": {
                "supplier": (request_context.get("mail_log") or {}).get("supplier", ""),
                "mail_type": (request_context.get("mail_log") or {}).get("mail_type", ""),
                "subject": (request_context.get("mail_log") or {}).get("subject", ""),
                "sent_at": (request_context.get("mail_log") or {}).get("sent_at", ""),
            },
            "matched_mail_item": mail_item,
        },
        "pmf_material": material,
        "filing_preview": filing_preview,
        "pmf_update_preview": pmf_preview,
        "warnings": warnings,
        "blockers": blockers,
        "existing_history": history,
    }


def _insert_history(payload: dict[str, Any]) -> int:
    ensure_filing_tables()
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO certificate_filing_history (
                ocr_job_id,
                request_id,
                pmf_row_pos,
                pmf_depth,
                source_path,
                target_path,
                cert_org,
                cert_no,
                expiry_date,
                status,
                copy_status,
                pmf_update_json,
                warning_json,
                error_message,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("ocr_job_id"),
                payload.get("request_id", ""),
                payload.get("pmf_row_pos"),
                payload.get("pmf_depth"),
                payload.get("source_path", ""),
                payload.get("target_path", ""),
                payload.get("cert_org", ""),
                payload.get("cert_no", ""),
                payload.get("expiry_date", ""),
                payload.get("status", ""),
                payload.get("copy_status", ""),
                json.dumps(payload.get("pmf_update") or {}, ensure_ascii=False),
                json.dumps(payload.get("warnings") or [], ensure_ascii=False),
                payload.get("error_message", ""),
                now,
                now,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def confirm_filing_workflow(
    ocr_job_id: int,
    pmf_row_pos: int,
    pmf_depth: int = 0,
    overwrite: bool = False,
    force: bool = False,
    allow_date_regression: bool = False,
) -> dict[str, Any]:
    preview = preview_filing_workflow(
        ocr_job_id=ocr_job_id,
        pmf_row_pos=pmf_row_pos,
        pmf_depth=pmf_depth,
    )

    if preview["blockers"] and not force:
        raise ValueError(" / ".join(preview["blockers"]))

    job = get_ocr_job(int(ocr_job_id))
    material = preview["pmf_material"]
    certificate = preview["certificate"]
    mail_item = (preview.get("request_context") or {}).get("matched_mail_item") or {}

    pmf_expiry = certificate.get("expiry_date", "")
    if certificate.get("cert_org") == "BPJPH":
        pmf_expiry = _clean(mail_item.get("planned_expiry"))

    source_path = Path(str(job.get("source_path") or ""))
    naming_input = FilingNameInput(
        material_no=material["material_no"],
        material_name_en=material["english_name"],
        manufacturer=material["maker"],
        supplier=material["supplier"],
        cert_org=certificate.get("cert_org", ""),
        expiry_date=certificate.get("expiry_date", ""),
        source_extension=source_path.suffix or job.get("file_ext") or ".pdf",
    )

    copy_result = None
    pmf_result = None

    try:
        copy_result = copy_certificate_atomically(
            source_path=source_path,
            naming_input=naming_input,
            root=get_halal_raw_material_root(),
            overwrite=overwrite,
        )

        pmf_result = update_pmf_certificate_fields(
            row_pos=pmf_row_pos,
            depth=pmf_depth,
            cert_org=certificate.get("cert_org", ""),
            cert_no=certificate.get("cert_no", ""),
            expiry_date=pmf_expiry,
            allow_date_regression=allow_date_regression,
        )

        status = "DUPLICATE_SKIPPED" if copy_result.status == "DUPLICATE_SKIPPED" else "CONFIRMED"
        history_id = _insert_history(
            {
                "ocr_job_id": ocr_job_id,
                "request_id": (preview.get("request_context") or {}).get("request_id", ""),
                "pmf_row_pos": pmf_row_pos,
                "pmf_depth": pmf_depth,
                "source_path": str(source_path),
                "target_path": copy_result.target_path,
                "cert_org": certificate.get("cert_org", ""),
                "cert_no": certificate.get("cert_no", ""),
                "expiry_date": pmf_expiry,
                "status": status,
                "copy_status": copy_result.status,
                "pmf_update": pmf_result.to_dict(),
                "warnings": preview.get("warnings") or [],
            }
        )

        return {
            "ok": True,
            "history_id": history_id,
            "status": status,
            "copy": copy_result.to_dict(),
            "pmf_update": pmf_result.to_dict(),
            "preview": preview,
        }

    except Exception as exc:
        # 새로 복사한 파일만 제거한다. 기존 동일 파일은 삭제하지 않는다.
        if copy_result and copy_result.status == "COPIED":
            Path(copy_result.target_path).unlink(missing_ok=True)

        if pmf_result:
            try:
                restore_pmf_backup(pmf_result.backup_path, pmf_result.pmf_path)
            except Exception:
                pass

        _insert_history(
            {
                "ocr_job_id": ocr_job_id,
                "request_id": (preview.get("request_context") or {}).get("request_id", ""),
                "pmf_row_pos": pmf_row_pos,
                "pmf_depth": pmf_depth,
                "source_path": str(source_path),
                "target_path": copy_result.target_path if copy_result else "",
                "cert_org": certificate.get("cert_org", ""),
                "cert_no": certificate.get("cert_no", ""),
                "expiry_date": pmf_expiry,
                "status": "ERROR",
                "copy_status": copy_result.status if copy_result else "",
                "pmf_update": pmf_result.to_dict() if pmf_result else {},
                "warnings": preview.get("warnings") or [],
                "error_message": str(exc),
            }
        )
        raise


def list_filing_candidates(limit: int = 100) -> dict[str, Any]:
    ensure_filing_tables()
    jobs = list_ocr_jobs(limit=max(1, min(int(limit), 500)), status="DONE", include_test=False)
    rows: list[dict[str, Any]] = []

    for job in jobs.get("rows") or []:
        history = get_confirmed_history_for_job(int(job.get("id")))
        if history:
            continue

        cert_values = resolve_cert_values(job)
        request_context = get_request_context_for_ocr_job(job)
        pmf_groups = build_pmf_candidates_for_request_context(request_context, limit_per_item=5)
        top_match = None
        matched_mail_item = None

        all_matches: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
        for group in pmf_groups:
            mail_item = group.get("mail_item") or {}
            for match in group.get("pmf_matches") or []:
                all_matches.append((int(match.get("score") or 0), match, mail_item))

        if all_matches:
            all_matches.sort(key=lambda x: x[0], reverse=True)
            _, top_match, matched_mail_item = all_matches[0]

        rows.append(
            {
                "ocr_job_id": job.get("id"),
                "filename": job.get("filename"),
                "source_path": job.get("source_path"),
                "status": job.get("status"),
                "certificate": cert_values,
                "request_id": request_context.get("request_id", ""),
                "mail_subject": (request_context.get("mail_log") or {}).get("subject", ""),
                "mail_type": (request_context.get("mail_log") or {}).get("mail_type", ""),
                "matched_mail_item": matched_mail_item,
                "top_pmf_match": top_match,
                "pmf_candidate_groups": pmf_groups,
                "auto_match": bool(top_match and int(top_match.get("score") or 0) >= 150),
            }
        )

    return {
        "ok": True,
        "count": len(rows),
        "root_path": str(get_halal_raw_material_root()),
        "rows": rows,
    }


def list_filing_history(limit: int = 100) -> dict[str, Any]:
    ensure_filing_tables()
    limit = max(1, min(int(limit), 500))
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM certificate_filing_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    result_rows: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        for key in ("pmf_update_json", "warning_json"):
            default_value = {} if key == "pmf_update_json" else []
            raw_value = data.get(key)
            try:
                parsed_value = json.loads(raw_value) if raw_value else default_value
            except Exception:
                parsed_value = default_value
            data[key.removesuffix("_json")] = parsed_value
            data.pop(key, None)
        result_rows.append(data)

    return {"ok": True, "count": len(result_rows), "rows": result_rows}
