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
    match_mail_item_to_pmf,
    select_mail_item_for_ocr_job,
)
from app.services.ocr_service import get_ocr_job, list_ocr_jobs
from app.services.pmf_filing_service import (
    get_pmf_material_snapshot,
    preview_pmf_update,
    restore_pmf_backup,
    update_pmf_certificate_fields,
)
from app.services.certificate_change_service import classify_certificate_change


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
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_certificate_filing_ocr_job
            ON certificate_filing_history(ocr_job_id)
            WHERE status IN (
                'CONFIRMED',
                'DUPLICATE_SKIPPED'
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS
            material_certificate_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ocr_job_id INTEGER,
                request_id TEXT,
                pmf_row_pos INTEGER NOT NULL,
                pmf_depth INTEGER NOT NULL DEFAULT 0,
                cert_org TEXT,
                cert_no TEXT,
                expiry_date TEXT,
                manufacturer TEXT,
                source_path TEXT,
                target_path TEXT,
                certificate_role TEXT NOT NULL,
                status TEXT NOT NULL,
                change_action TEXT,
                is_primary INTEGER NOT NULL DEFAULT 0,
                supersedes_id INTEGER,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_material_certificate_material
            ON material_certificate_history(
                pmf_row_pos,
                pmf_depth,
                status,
                is_primary
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_material_certificate_ocr_job
            ON material_certificate_history(
                ocr_job_id
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_material_certificate_number
            ON material_certificate_history(
                cert_org,
                cert_no
            )
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
    manufacturer = _clean(
        rule.get("manufacturer")
        or rule.get("maker")
        or rule.get("company_name")
    )
    parse_status = _clean(rule.get("parse_status"))
    confidence = _clean(rule.get("confidence"))

    return {
        "cert_org": cert_org.upper(),
        "cert_no": cert_no,
        "expiry_date": expiry_date,
        "manufacturer": manufacturer,
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


def _find_selected_pmf_match(
    mail_item: dict[str, Any] | None,
    pmf_row_pos: int,
    pmf_depth: int,
    supplier: str = "",
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if not mail_item:
        return None, []

    matches = match_mail_item_to_pmf(
        mail_item,
        supplier=supplier,
        limit=20,
    )
    for match in matches:
        if int(match.get("row_pos")) == int(pmf_row_pos) and int(match.get("depth")) == int(pmf_depth):
            return match, matches
    return None, matches

def _build_warnings(
    job: dict[str, Any],
    cert_values: dict[str, str],
    material: dict[str, Any],
    mail_item: dict[str, Any] | None,
    match_validation: dict[str, Any] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    warnings: list[str] = []
    blockers: list[str] = []
    hard_blockers: list[str] = []

    validation = match_validation or {}
    warnings.extend(validation.get("warnings") or [])
    hard_blockers.extend(validation.get("hard_blockers") or [])

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

    if not mail_item:
        hard_blockers.append("OCR 첨부파일과 연결된 메일 원료 항목을 확정하지 못했습니다.")

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

    warnings = list(dict.fromkeys(warnings))
    hard_blockers = list(dict.fromkeys(hard_blockers))
    blockers = list(dict.fromkeys(hard_blockers + blockers))
    return warnings, blockers, hard_blockers

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
    match_validation = select_mail_item_for_ocr_job(
        request_context=request_context,
        job=job,
        cert_values=cert_values,
    )
    mail_item = match_validation.get("selected_mail_item")
    supplier = _clean((request_context.get("mail_log") or {}).get("supplier"))
    selected_pmf_match, selected_pmf_matches = _find_selected_pmf_match(
        mail_item=mail_item,
        pmf_row_pos=pmf_row_pos,
        pmf_depth=pmf_depth,
        supplier=supplier,
    )

    # CERTIFICATE_CHANGE_DECISION_START
    incoming_manufacturer = _clean(
        cert_values.get("manufacturer")
        or cert_values.get("maker")
        or job.get("manufacturer")
        or job.get("maker")
    )

    current_certificate = {
        "cert_org": material.get("org", ""),
        "cert_no": material.get("cert_no", ""),
        "expiry_date": material.get("expiry_date", ""),
        "manufacturer": material.get("maker", ""),
    }

    incoming_certificate = {
        "cert_org": cert_values.get("cert_org", ""),
        "cert_no": cert_values.get("cert_no", ""),
        "expiry_date": cert_values.get("expiry_date", ""),
        "manufacturer": incoming_manufacturer,
    }

    product_match_for_change = (
        bool(selected_pmf_match)
        if mail_item
        else True
    )

    change_decision = classify_certificate_change(
        current=current_certificate,
        incoming=incoming_certificate,
        product_match=product_match_for_change,
        manufacturer_match=None,
        current_active=True,
    )
    # CERTIFICATE_CHANGE_DECISION_END

    warnings, blockers, hard_blockers = _build_warnings(
        job,
        cert_values,
        material,
        mail_item,
        match_validation=match_validation,
    )

    # CERTIFICATE_CHANGE_BLOCKER_START
    decision_code = change_decision.get(
        "decision_code",
        "",
    )

    if change_decision.get("blocked"):
        message = (
            "???? ?? ??? ?? ?? ??? "
            f"???????: {decision_code}"
        )

        if message not in blockers:
            blockers.append(message)

        if message not in hard_blockers:
            hard_blockers.append(message)

    elif change_decision.get("requires_review"):
        message = (
            "???? ?? ??? ?????: "
            f"{decision_code}"
        )

        if message not in blockers:
            blockers.append(message)

    for reason in change_decision.get("reasons") or []:
        message = f"?? ??: {reason}"

        if message not in warnings:
            warnings.append(message)
    # CERTIFICATE_CHANGE_BLOCKER_END
    if mail_item and selected_pmf_match is None:
        message = "선택한 PMF 원료가 이 첨부파일에 연결된 메일 원료 후보와 일치하지 않습니다."
        hard_blockers.append(message)
        blockers.append(message)

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
            "match_validation": match_validation,
            "selected_pmf_match": selected_pmf_match,
            "selected_pmf_matches": selected_pmf_matches,
        },
        "pmf_material": material,
        "filing_preview": filing_preview,
        "pmf_update_preview": pmf_preview,
        "warnings": list(dict.fromkeys(warnings)),
        "blockers": list(dict.fromkeys(blockers)),
        "hard_blockers": list(dict.fromkeys(hard_blockers)),
        "change_decision": change_decision,
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

def insert_material_certificate_history(
    payload: dict[str, Any],
) -> int:
    ensure_filing_tables()

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    is_primary = (
        1
        if payload.get("is_primary")
        else 0
    )

    certificate_role = _clean(
        payload.get("certificate_role")
    ).upper()

    if not certificate_role:
        certificate_role = (
            "PRIMARY"
            if is_primary
            else "SECONDARY"
        )

    status = (
        _clean(payload.get("status")).upper()
        or "ACTIVE"
    )

    conn = get_conn()

    try:
        cur = conn.execute(
            """
            INSERT INTO material_certificate_history (
                ocr_job_id,
                request_id,
                pmf_row_pos,
                pmf_depth,
                cert_org,
                cert_no,
                expiry_date,
                manufacturer,
                source_path,
                target_path,
                certificate_role,
                status,
                change_action,
                is_primary,
                supersedes_id,
                created_at,
                updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                payload.get("ocr_job_id"),
                payload.get("request_id", ""),
                int(payload.get("pmf_row_pos")),
                int(payload.get("pmf_depth") or 0),
                _clean(payload.get("cert_org")).upper(),
                _clean(payload.get("cert_no")),
                _clean(payload.get("expiry_date")),
                _clean(payload.get("manufacturer")),
                _clean(payload.get("source_path")),
                _clean(payload.get("target_path")),
                certificate_role,
                status,
                _clean(
                    payload.get("change_action")
                ).upper(),
                is_primary,
                payload.get("supersedes_id"),
                now,
                now,
            ),
        )

        conn.commit()
        return int(cur.lastrowid)

    finally:
        conn.close()


def list_material_certificate_history(
    pmf_row_pos: int | None = None,
    pmf_depth: int | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    ensure_filing_tables()

    limit = max(
        1,
        min(int(limit), 500),
    )

    where_parts: list[str] = []
    params: list[Any] = []

    if pmf_row_pos is not None:
        where_parts.append(
            "pmf_row_pos = ?"
        )
        params.append(
            int(pmf_row_pos)
        )

    if pmf_depth is not None:
        where_parts.append(
            "pmf_depth = ?"
        )
        params.append(
            int(pmf_depth)
        )

    where_sql = ""

    if where_parts:
        where_sql = (
            " WHERE "
            + " AND ".join(where_parts)
        )

    query = (
        "SELECT * "
        "FROM material_certificate_history"
        + where_sql
        + " ORDER BY id DESC LIMIT ?"
    )

    params.append(limit)

    conn = get_conn()

    try:
        rows = conn.execute(
            query,
            tuple(params),
        ).fetchall()

    finally:
        conn.close()

    result_rows = [
        dict(row)
        for row in rows
    ]

    return {
        "ok": True,
        "count": len(result_rows),
        "rows": result_rows,
    }


def get_active_material_certificates(
    pmf_row_pos: int,
    pmf_depth: int = 0,
) -> list[dict[str, Any]]:
    ensure_filing_tables()

    conn = get_conn()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM material_certificate_history
            WHERE pmf_row_pos = ?
              AND pmf_depth = ?
              AND status = 'ACTIVE'
            ORDER BY
                is_primary DESC,
                expiry_date DESC,
                id DESC
            """,
            (
                int(pmf_row_pos),
                int(pmf_depth),
            ),
        ).fetchall()

    finally:
        conn.close()

    return [
        dict(row)
        for row in rows
    ]



def validate_change_decision_for_confirm(
    preview: dict[str, Any],
    change_action: str = "",
) -> dict[str, str]:
    decision = preview.get("change_decision") or {}
    decision_code = _clean(
        decision.get("decision_code")
    ).upper()

    requested_action = _clean(
        change_action
    ).upper()

    aliases = {
        "APPROVE_RENEWAL": "UPDATE_CURRENT",
        "REGISTER_AS_PRIMARY": "UPDATE_CURRENT",
    }

    requested_action = aliases.get(
        requested_action,
        requested_action,
    )

    if decision.get("blocked"):
        raise ValueError(
            "Change decision blocks confirmation: "
            + decision_code
        )

    if decision.get("requires_review"):
        review_options = {
            aliases.get(value, value)
            for value in (
                _clean(item).upper()
                for item in (
                    decision.get("review_options")
                    or []
                )
                if _clean(item)
            )
        }

        if not requested_action:
            raise ValueError(
                "change_action is required for review decision: "
                + decision_code
            )

        if (
            review_options
            and requested_action not in review_options
        ):
            raise ValueError(
                "Invalid change_action for "
                + decision_code
                + ": "
                + requested_action
            )

        resolved_action = requested_action

    else:
        automatic_action = _clean(
            decision.get("auto_action")
        ).upper()

        automatic_action = aliases.get(
            automatic_action,
            automatic_action,
        )

        if (
            requested_action
            and requested_action != automatic_action
        ):
            raise ValueError(
                "change_action cannot override automatic decision: "
                + decision_code
            )

        resolved_action = automatic_action

    allowed_actions = {
        "UPDATE_CURRENT",
        "REPLACE_CURRENT",
        "ADD_SECONDARY",
    }

    if resolved_action not in allowed_actions:
        raise ValueError(
            "The selected action does not confirm the certificate: "
            + (
                resolved_action
                or decision_code
            )
        )

    return {
        "decision_code": decision_code,
        "change_action": resolved_action,
    }



def apply_material_certificate_history_action(
    payload: dict[str, Any],
    change_action: str,
) -> dict[str, Any]:
    ensure_filing_tables()

    action = _clean(change_action).upper()

    action_aliases = {
        "APPROVE_RENEWAL": "UPDATE_CURRENT",
        "REGISTER_AS_PRIMARY": "UPDATE_CURRENT",
    }

    action = action_aliases.get(
        action,
        action,
    )

    allowed_actions = {
        "UPDATE_CURRENT",
        "REPLACE_CURRENT",
        "ADD_SECONDARY",
    }

    if action not in allowed_actions:
        raise ValueError(
            "Unsupported material certificate action: "
            + action
        )

    if payload.get("pmf_row_pos") is None:
        raise ValueError(
            "pmf_row_pos is required"
        )

    pmf_row_pos = int(
        payload["pmf_row_pos"]
    )

    pmf_depth = int(
        payload.get("pmf_depth")
        or 0
    )

    cert_org = _clean(
        payload.get("cert_org")
    ).upper()

    cert_no = _clean(
        payload.get("cert_no")
    )

    expiry_date = _clean(
        payload.get("expiry_date")
    )

    manufacturer = _clean(
        payload.get("manufacturer")
    )

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    if not cert_org:
        raise ValueError(
            "cert_org is required"
        )

    previous_primary: (
        dict[str, Any] | None
    ) = None

    conn = get_conn()

    try:
        conn.execute(
            "BEGIN IMMEDIATE"
        )

        if action in {
            "UPDATE_CURRENT",
            "REPLACE_CURRENT",
        }:
            row = conn.execute(
                """
                SELECT *
                FROM material_certificate_history
                WHERE pmf_row_pos = ?
                  AND pmf_depth = ?
                  AND status = 'ACTIVE'
                  AND is_primary = 1
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    pmf_row_pos,
                    pmf_depth,
                ),
            ).fetchone()

            if row:
                previous_primary = dict(
                    row
                )

                conn.execute(
                    """
                    UPDATE material_certificate_history
                    SET status = 'SUPERSEDED',
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        now,
                        int(
                            previous_primary["id"]
                        ),
                    ),
                )

            certificate_role = "PRIMARY"
            is_primary = 1

            supersedes_id = (
                int(previous_primary["id"])
                if previous_primary
                else None
            )

        else:
            duplicate = conn.execute(
                """
                SELECT *
                FROM material_certificate_history
                WHERE pmf_row_pos = ?
                  AND pmf_depth = ?
                  AND status = 'ACTIVE'
                  AND is_primary = 0
                  AND cert_org = ?
                  AND cert_no = ?
                  AND expiry_date = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    pmf_row_pos,
                    pmf_depth,
                    cert_org,
                    cert_no,
                    expiry_date,
                ),
            ).fetchone()

            if duplicate:
                conn.commit()

                return {
                    "ok": True,
                    "changed": False,
                    "action": action,
                    "status": (
                        "DUPLICATE_ACTIVE"
                    ),
                    "inserted_id": int(
                        duplicate["id"]
                    ),
                    "previous_primary_id": None,
                    "previous_primary_status": "",
                }

            certificate_role = "SECONDARY"
            is_primary = 0
            supersedes_id = None

        cur = conn.execute(
            """
            INSERT INTO material_certificate_history (
                ocr_job_id,
                request_id,
                pmf_row_pos,
                pmf_depth,
                cert_org,
                cert_no,
                expiry_date,
                manufacturer,
                source_path,
                target_path,
                certificate_role,
                status,
                change_action,
                is_primary,
                supersedes_id,
                created_at,
                updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                payload.get("ocr_job_id"),
                _clean(
                    payload.get("request_id")
                ),
                pmf_row_pos,
                pmf_depth,
                cert_org,
                cert_no,
                expiry_date,
                manufacturer,
                _clean(
                    payload.get("source_path")
                ),
                _clean(
                    payload.get("target_path")
                ),
                certificate_role,
                "ACTIVE",
                action,
                is_primary,
                supersedes_id,
                now,
                now,
            ),
        )

        inserted_id = int(
            cur.lastrowid
        )

        conn.commit()

        return {
            "ok": True,
            "changed": True,
            "action": action,
            "status": "INSERTED",
            "inserted_id": inserted_id,
            "previous_primary_id": (
                int(previous_primary["id"])
                if previous_primary
                else None
            ),
            "previous_primary_status": (
                _clean(
                    previous_primary.get(
                        "status"
                    )
                )
                if previous_primary
                else ""
            ),
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def rollback_material_certificate_history_action(
    result: dict[str, Any] | None,
) -> None:
    if not result:
        return

    if not result.get("changed"):
        return

    inserted_id = result.get(
        "inserted_id"
    )

    previous_primary_id = result.get(
        "previous_primary_id"
    )

    previous_primary_status = (
        _clean(
            result.get(
                "previous_primary_status"
            )
        )
        or "ACTIVE"
    )

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    conn = get_conn()

    try:
        conn.execute(
            "BEGIN IMMEDIATE"
        )

        if inserted_id is not None:
            conn.execute(
                """
                DELETE FROM material_certificate_history
                WHERE id = ?
                """,
                (
                    int(inserted_id),
                ),
            )

        if previous_primary_id is not None:
            conn.execute(
                """
                UPDATE material_certificate_history
                SET status = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    previous_primary_status,
                    now,
                    int(
                        previous_primary_id
                    ),
                ),
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def confirm_filing_workflow(
    ocr_job_id: int,
    pmf_row_pos: int,
    pmf_depth: int = 0,
    overwrite: bool = False,
    force: bool = False,
    allow_date_regression: bool = False,
    change_action: str = "",
) -> dict[str, Any]:
    preview = preview_filing_workflow(
        ocr_job_id=ocr_job_id,
        pmf_row_pos=pmf_row_pos,
        pmf_depth=pmf_depth,
    )

    if preview.get("hard_blockers"):
        raise ValueError(
            " / ".join(
                preview["hard_blockers"]
            )
        )

    change_gate = (
        validate_change_decision_for_confirm(
            preview=preview,
            change_action=change_action,
        )
    )

    if (
        preview.get("blockers")
        and not force
    ):
        raise ValueError(
            " / ".join(
                preview["blockers"]
            )
        )

    job = get_ocr_job(
        int(ocr_job_id)
    )

    material = preview[
        "pmf_material"
    ]

    certificate = preview[
        "certificate"
    ]

    request_context = (
        preview.get("request_context")
        or {}
    )

    mail_item = (
        request_context.get(
            "matched_mail_item"
        )
        or {}
    )

    request_id = request_context.get(
        "request_id",
        "",
    )

    pmf_expiry = certificate.get(
        "expiry_date",
        "",
    )

    if (
        certificate.get("cert_org")
        == "BPJPH"
    ):
        pmf_expiry = _clean(
            mail_item.get(
                "planned_expiry"
            )
        )

    source_path = Path(
        str(
            job.get("source_path")
            or ""
        )
    )

    naming_input = FilingNameInput(
        material_no=material[
            "material_no"
        ],
        material_name_en=material[
            "english_name"
        ],
        manufacturer=material[
            "maker"
        ],
        supplier=material[
            "supplier"
        ],
        cert_org=certificate.get(
            "cert_org",
            "",
        ),
        expiry_date=certificate.get(
            "expiry_date",
            "",
        ),
        source_extension=(
            source_path.suffix
            or job.get("file_ext")
            or ".pdf"
        ),
    )

    copy_result = None
    pmf_result = None
    material_history_result = None
    legacy_primary_history_id = None

    try:
        copy_result = (
            copy_certificate_atomically(
                source_path=source_path,
                naming_input=naming_input,
                root=(
                    get_halal_raw_material_root()
                ),
                overwrite=overwrite,
            )
        )

        resolved_action = change_gate[
            "change_action"
        ]

        if (
            resolved_action
            != "ADD_SECONDARY"
        ):
            pmf_result = (
                update_pmf_certificate_fields(
                    row_pos=pmf_row_pos,
                    depth=pmf_depth,
                    cert_org=certificate.get(
                        "cert_org",
                        "",
                    ),
                    cert_no=certificate.get(
                        "cert_no",
                        "",
                    ),
                    expiry_date=pmf_expiry,
                    allow_date_regression=(
                        allow_date_regression
                    ),
                )
            )

        active_certificates = (
            get_active_material_certificates(
                pmf_row_pos=pmf_row_pos,
                pmf_depth=pmf_depth,
            )
        )

        has_active_primary = any(
            int(
                item.get(
                    "is_primary"
                )
                or 0
            )
            == 1
            for item in active_certificates
        )

        current_org = _clean(
            material.get("org")
        ).upper()

        current_cert_no = _clean(
            material.get("cert_no")
        )

        current_expiry = _clean(
            material.get(
                "expiry_date"
            )
        )

        if (
            not has_active_primary
            and (
                current_org
                or current_cert_no
                or current_expiry
            )
        ):
            legacy_primary_history_id = (
                insert_material_certificate_history(
                    {
                        "ocr_job_id": None,
                        "request_id": (
                            request_id
                        ),
                        "pmf_row_pos": (
                            pmf_row_pos
                        ),
                        "pmf_depth": (
                            pmf_depth
                        ),
                        "cert_org": (
                            current_org
                        ),
                        "cert_no": (
                            current_cert_no
                        ),
                        "expiry_date": (
                            current_expiry
                        ),
                        "manufacturer": (
                            material.get(
                                "maker",
                                "",
                            )
                        ),
                        "source_path": "",
                        "target_path": "",
                        "certificate_role": (
                            "PRIMARY"
                        ),
                        "status": "ACTIVE",
                        "change_action": (
                            "LEGACY_IMPORT"
                        ),
                        "is_primary": True,
                    }
                )
            )

        material_history_result = (
            apply_material_certificate_history_action(
                {
                    "ocr_job_id": (
                        ocr_job_id
                    ),
                    "request_id": (
                        request_id
                    ),
                    "pmf_row_pos": (
                        pmf_row_pos
                    ),
                    "pmf_depth": (
                        pmf_depth
                    ),
                    "cert_org": (
                        certificate.get(
                            "cert_org",
                            "",
                        )
                    ),
                    "cert_no": (
                        certificate.get(
                            "cert_no",
                            "",
                        )
                    ),
                    "expiry_date": (
                        pmf_expiry
                    ),
                    "manufacturer": (
                        certificate.get(
                            "manufacturer"
                        )
                        or material.get(
                            "maker",
                            "",
                        )
                    ),
                    "source_path": (
                        str(source_path)
                    ),
                    "target_path": (
                        copy_result.target_path
                    ),
                },
                resolved_action,
            )
        )

        status = (
            "DUPLICATE_SKIPPED"
            if (
                copy_result.status
                == "DUPLICATE_SKIPPED"
            )
            else "CONFIRMED"
        )

        pmf_update_payload = (
            pmf_result.to_dict()
            if pmf_result
            else {
                "skipped": True,
                "reason": (
                    "ADD_SECONDARY"
                ),
            }
        )

        history_id = _insert_history(
            {
                "ocr_job_id": (
                    ocr_job_id
                ),
                "request_id": (
                    request_id
                ),
                "pmf_row_pos": (
                    pmf_row_pos
                ),
                "pmf_depth": (
                    pmf_depth
                ),
                "source_path": (
                    str(source_path)
                ),
                "target_path": (
                    copy_result.target_path
                ),
                "cert_org": (
                    certificate.get(
                        "cert_org",
                        "",
                    )
                ),
                "cert_no": (
                    certificate.get(
                        "cert_no",
                        "",
                    )
                ),
                "expiry_date": (
                    pmf_expiry
                ),
                "status": status,
                "copy_status": (
                    copy_result.status
                ),
                "pmf_update": (
                    pmf_update_payload
                ),
                "warnings": (
                    preview.get(
                        "warnings"
                    )
                    or []
                ),
            }
        )

        return {
            "ok": True,
            "history_id": history_id,
            "status": status,
            "change_gate": (
                change_gate
            ),
            "copy": (
                copy_result.to_dict()
            ),
            "pmf_update": (
                pmf_update_payload
            ),
            "material_certificate_history": (
                material_history_result
            ),
            "legacy_primary_history_id": (
                legacy_primary_history_id
            ),
            "preview": preview,
        }

    except Exception as exc:
        if material_history_result:
            try:
                rollback_material_certificate_history_action(
                    material_history_result
                )
            except Exception:
                pass

        if pmf_result:
            try:
                restore_pmf_backup(
                    pmf_result.backup_path,
                    pmf_result.pmf_path,
                )
            except Exception:
                pass

        if (
            copy_result
            and (
                copy_result.status
                == "COPIED"
            )
        ):
            Path(
                copy_result.target_path
            ).unlink(
                missing_ok=True
            )

        _insert_history(
            {
                "ocr_job_id": (
                    ocr_job_id
                ),
                "request_id": (
                    request_id
                ),
                "pmf_row_pos": (
                    pmf_row_pos
                ),
                "pmf_depth": (
                    pmf_depth
                ),
                "source_path": (
                    str(source_path)
                ),
                "target_path": (
                    copy_result.target_path
                    if copy_result
                    else ""
                ),
                "cert_org": (
                    certificate.get(
                        "cert_org",
                        "",
                    )
                ),
                "cert_no": (
                    certificate.get(
                        "cert_no",
                        "",
                    )
                ),
                "expiry_date": (
                    pmf_expiry
                ),
                "status": "ERROR",
                "copy_status": (
                    copy_result.status
                    if copy_result
                    else ""
                ),
                "pmf_update": (
                    pmf_result.to_dict()
                    if pmf_result
                    else {}
                ),
                "warnings": (
                    preview.get(
                        "warnings"
                    )
                    or []
                ),
                "error_message": (
                    str(exc)
                ),
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
        match_validation = select_mail_item_for_ocr_job(
            request_context=request_context,
            job=job,
            cert_values=cert_values,
        )
        selected_mail_item = match_validation.get("selected_mail_item")
        supplier = _clean((request_context.get("mail_log") or {}).get("supplier"))

        selected_matches = (
            match_mail_item_to_pmf(selected_mail_item, supplier=supplier, limit=5)
            if selected_mail_item
            else []
        )
        top_match = selected_matches[0] if selected_matches else None

        # 전체 후보는 수동 검토 화면용으로 유지한다. 자동판정에는 선택된 메일 항목만 사용한다.
        pmf_groups = build_pmf_candidates_for_request_context(request_context, limit_per_item=5)

        auto_match_blockers = list(match_validation.get("hard_blockers") or [])
        if cert_values.get("parse_status") in BLOCKED_PARSE_STATUSES:
            auto_match_blockers.append(
                f"규칙 판정 상태를 확인해야 합니다: {cert_values.get('parse_status')}"
            )
        if not top_match or int(top_match.get("score") or 0) < 150:
            auto_match_blockers.append("선택된 메일 항목의 PMF 매칭 점수가 부족합니다.")

        auto_match_blockers = list(dict.fromkeys(auto_match_blockers))
        auto_match = bool(
            top_match
            and int(top_match.get("score") or 0) >= 150
            and match_validation.get("auto_selectable")
            and not auto_match_blockers
        )

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
                "attachment_index": match_validation.get("attachment_index"),
                "matched_mail_item": selected_mail_item,
                "match_validation": match_validation,
                "top_pmf_match": top_match,
                "selected_pmf_matches": selected_matches,
                "pmf_candidate_groups": pmf_groups,
                "auto_match": auto_match,
                "auto_match_blockers": auto_match_blockers,
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
