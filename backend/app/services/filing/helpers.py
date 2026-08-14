"""OCR 결과에서 인증서 값을 뽑고 경고를 만드는 보조 로직."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.mail_request_item_service import match_mail_item_to_pmf


ALLOWED_OCR_STATUSES = {"DONE"}


BLOCKED_PARSE_STATUSES = {
    "LOW_CONFIDENCE",
    "MANUAL_REVIEW",
    "TESSERACT_ERROR",
    "SCANNED_NEED_OCR",
    "NO_TEXT",
    "ERROR",
}


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


def resolve_filing_status(
    copy_status: str,
    change_action: str,
) -> str:
    normalized_copy_status = _clean(
        copy_status
    ).upper()

    normalized_action = _clean(
        change_action
    ).upper()

    if normalized_copy_status == "DUPLICATE_SKIPPED":
        return "DUPLICATE_SKIPPED"

    status_by_action = {
        "UPDATE_CURRENT": "CONFIRMED",
        "REPLACE_CURRENT": "REPLACED",
        "ADD_SECONDARY": "SECONDARY_ADDED",
    }

    return status_by_action.get(
        normalized_action,
        "CONFIRMED",
    )
