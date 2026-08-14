"""확정 전 미리보기와 대상 후보 목록."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.pmf_service import read_pmf_bundle
from app.services.certificate_filing_service import preview_certificate_filing
from app.services.filing_name_service import FilingNameInput, get_halal_raw_material_root
from app.services.mail_request_item_service import (
    build_pmf_candidates_for_request_context,
    get_request_context_for_ocr_job,
    match_mail_item_to_pmf,
    select_mail_item_for_ocr_job,
)
from app.services.ocr_service import get_ocr_job, list_ocr_jobs
from app.services.pmf_filing_service import get_pmf_material_snapshot, preview_pmf_update
from app.services.certificate_change_service import classify_certificate_change

from app.services.filing.store import (
    ensure_filing_tables,
)
from app.services.filing.helpers import (
    BLOCKED_PARSE_STATUSES,
    _build_warnings,
    _clean,
    _find_selected_pmf_match,
    resolve_cert_values,
)
from app.services.filing.history import (
    get_confirmed_history_for_job,
)


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

    pmf_expiry = cert_values.get(
        "expiry_date",
        "",
    )

    if cert_values.get("cert_org") == "BPJPH":
        pmf_expiry = _clean(
            (mail_item or {}).get(
                "planned_expiry"
            )
        )

    incoming_certificate = {
        "cert_org": cert_values.get(
            "cert_org",
            "",
        ),
        "cert_no": cert_values.get(
            "cert_no",
            "",
        ),
        "expiry_date": pmf_expiry,
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
            "인증서 변경 판정으로 확정 처리가 차단되었습니다: "
            f"{decision_code}"
        )

        if message not in blockers:
            blockers.append(message)

        if message not in hard_blockers:
            hard_blockers.append(message)

    elif change_decision.get("requires_review"):
        message = (
            "인증서 변경 판정에 수동 검토가 필요합니다: "
            f"{decision_code}"
        )

        if message not in blockers:
            blockers.append(message)

    for reason in change_decision.get("reasons") or []:
        message = f"판정 사유: {reason}"

        if message not in warnings:
            warnings.append(message)
    # CERTIFICATE_CHANGE_BLOCKER_END
    if mail_item and selected_pmf_match is None:
        message = "선택한 PMF 원료가 이 첨부파일에 연결된 메일 원료 후보와 일치하지 않습니다."
        hard_blockers.append(message)
        blockers.append(message)

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
        "effective_certificate": incoming_certificate,
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


def list_filing_candidates(limit: int = 100) -> dict[str, Any]:
    ensure_filing_tables()
    jobs = list_ocr_jobs(limit=max(1, min(int(limit), 500)), status="DONE", include_test=False)
    rows: list[dict[str, Any]] = []
    job_rows = jobs.get("rows") or []
    pmf_bundle: dict[str, Any] | None = None

    for job in job_rows:
        history = get_confirmed_history_for_job(int(job.get("id")))
        if history:
            continue

        if pmf_bundle is None:
            pmf_bundle = read_pmf_bundle()

        cert_values = resolve_cert_values(job)
        request_context = get_request_context_for_ocr_job(job)
        match_validation = select_mail_item_for_ocr_job(
            request_context=request_context,
            job=job,
            cert_values=cert_values,
        )
        selected_mail_item = match_validation.get("selected_mail_item")
        supplier = _clean((request_context.get("mail_log") or {}).get("supplier"))

        pmf_groups = build_pmf_candidates_for_request_context(
            request_context,
            limit_per_item=5,
            pmf_bundle=pmf_bundle,
        )

        selected_matches: list[dict[str, Any]] = []

        if selected_mail_item:
            for group in pmf_groups:
                group_item = group.get("mail_item")

                if (
                    group_item is selected_mail_item
                    or group_item == selected_mail_item
                ):
                    selected_matches = list(
                        group.get("pmf_matches")
                        or []
                    )
                    break

            if not selected_matches:
                selected_matches = match_mail_item_to_pmf(
                    selected_mail_item,
                    supplier=supplier,
                    limit=5,
                    pmf_bundle=pmf_bundle,
                )

        top_match = (
            selected_matches[0]
            if selected_matches
            else None
        )

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
