from __future__ import annotations

from typing import Any


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() in {"", "-", "none", "null", "nan"}:
        return ""
    return text


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _pmf_match_reliability(
    selection: dict[str, Any],
    pmf_matches: list[dict[str, Any]],
) -> str:
    """메일 항목 선택과 PMF 후보의 분리 정도로 문맥 신뢰도를 산정한다."""
    if selection.get("hard_blockers") or not selection.get("selected_mail_item"):
        return "LOW"

    if not selection.get("auto_selectable"):
        return "LOW"

    if not pmf_matches:
        return "MEDIUM"

    top_score = int(pmf_matches[0].get("score") or 0)
    second_score = int(pmf_matches[1].get("score") or 0) if len(pmf_matches) > 1 else 0
    margin = top_score - second_score
    top_reasons = set(pmf_matches[0].get("reasons") or [])

    strong_identity = bool(
        {"cert_no:exact", "material_name:exact", "english_name:exact"} & top_reasons
    )

    if top_score >= 180 and (margin >= 30 or strong_identity):
        return "HIGH"

    if top_score >= 100:
        return "MEDIUM"

    return "LOW"


def assemble_ocr_context(
    request_context: dict[str, Any],
    selection: dict[str, Any],
    pmf_matches: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    메일 관리번호/첨부순번/PMF 후보를 OCR 교차검증용 단일 문맥으로 정리한다.

    PMF의 기존 인증번호·유효기간은 비교값으로만 전달된다. 신규 인증서 값으로
    덮어쓰는 판단은 이 서비스에서 하지 않는다.
    """
    selected = dict(selection.get("selected_mail_item") or {})
    top_pmf = dict(pmf_matches[0] or {}) if pmf_matches else {}
    reliability = _pmf_match_reliability(selection, pmf_matches)

    # 충분히 연결된 PMF 후보만 표준 표기값으로 사용한다.
    use_pmf = bool(top_pmf and int(top_pmf.get("score") or 0) >= 100)

    material_name = _clean(
        top_pmf.get("material_name") if use_pmf else selected.get("material_name")
    )
    english_name = _clean(
        top_pmf.get("english_name") if use_pmf else selected.get("english_name")
    )
    maker = _clean(top_pmf.get("maker") if use_pmf else selected.get("maker"))
    maker_country = _clean(
        top_pmf.get("maker_country") if use_pmf else selected.get("maker_country")
    )
    org = _clean(top_pmf.get("org") if use_pmf else selected.get("org"))

    # 메일에는 발송 당시 PMF의 기존 인증번호와 유효기간이 구조화되어 있다.
    # 둘 다 새 OCR 값을 대체하지 않고 변경 여부 비교에만 사용한다.
    previous_cert_no = _clean(selected.get("cert_no") or top_pmf.get("cert_no"))
    current_expiry = _clean(
        selected.get("current_expiry") or top_pmf.get("expiry_date")
    )

    warnings = _unique(
        list(selection.get("warnings") or [])
        + [
            warning
            for match in pmf_matches[:1]
            for warning in (match.get("warnings") or [])
        ]
    )
    blockers = _unique(list(selection.get("hard_blockers") or []))

    return {
        "request_id": _clean(request_context.get("request_id")),
        "item_index": selected.get("item_index"),
        "selection_reason": _clean(selection.get("selection_reason")),
        "attachment_index": selection.get("attachment_index"),
        "reliability": reliability,
        "material_name": material_name,
        "english_name": english_name,
        "maker": maker,
        "maker_country": maker_country,
        "org": org,
        "cert_no": previous_cert_no,
        "current_expiry": current_expiry,
        "planned_expiry": _clean(selected.get("planned_expiry")),
        "supplier": _clean(selected.get("supplier") or top_pmf.get("supplier")),
        "mail_type": _clean(selected.get("mail_type")),
        "pmf_row_pos": top_pmf.get("row_pos") if use_pmf else None,
        "pmf_depth": top_pmf.get("depth") if use_pmf else None,
        "pmf_material_no": _clean(top_pmf.get("material_no")) if use_pmf else "",
        "pmf_score": int(top_pmf.get("score") or 0) if use_pmf else 0,
        "pmf_reasons": list(top_pmf.get("reasons") or []) if use_pmf else [],
        "warnings": warnings,
        "hard_blockers": blockers,
        "mail_item": selected,
        "pmf_top_match": top_pmf if use_pmf else {},
    }


def build_ocr_context_for_job(
    job: dict[str, Any],
    certificate_rule: dict[str, Any],
    *,
    pmf_limit: int = 5,
) -> dict[str, Any]:
    """
    실제 DB의 수신첨부 → 관리번호 → 발송메일 항목 → PMF 후보를 연결한다.

    Phase 2.1의 안전 매칭 서비스가 없거나 데이터 연결이 없으면 빈 문맥을
    반환하여 기존 OCR 판독을 방해하지 않는다.
    """
    try:
        from app.services.mail_request_item_service import (
            get_request_context_for_ocr_job,
            match_mail_item_to_pmf,
            select_mail_item_for_ocr_job,
        )
    except Exception as exc:
        return {
            "reliability": "LOW",
            "context_status": "UNAVAILABLE",
            "hard_blockers": [f"메일/PMF 연결 서비스를 불러오지 못했습니다: {exc}"],
        }

    try:
        request_context = get_request_context_for_ocr_job(job)
        selection = select_mail_item_for_ocr_job(
            request_context=request_context,
            job=job,
            cert_values=certificate_rule,
        )
        selected = selection.get("selected_mail_item") or {}
        pmf_matches = (
            match_mail_item_to_pmf(
                selected,
                supplier=(request_context.get("mail_log") or {}).get("supplier", ""),
                limit=pmf_limit,
            )
            if selected
            else []
        )
        context = assemble_ocr_context(request_context, selection, pmf_matches)
        context["context_status"] = "READY" if selected else "NO_MATCH"
        return context
    except Exception as exc:
        return {
            "reliability": "LOW",
            "context_status": "ERROR",
            "hard_blockers": [f"메일/PMF 문맥 연결 중 오류가 발생했습니다: {exc}"],
        }


def parse_certificate_with_linked_context(
    *,
    raw_text: str,
    filename: str,
    source_path: str,
    ocr_job_id: int | None = None,
) -> dict[str, Any]:
    """기본 OCR 규칙 판독 후 연결된 메일/PMF 문맥으로 안전하게 재검증한다."""
    from app.services.certificate_rule_service import (
        parse_certificate_rule,
        reconcile_certificate_rule_with_context,
    )

    base = parse_certificate_rule(raw_text=raw_text, filename=filename)
    job = {
        "id": ocr_job_id,
        "ocr_job_id": ocr_job_id,
        "source_path": source_path,
        "filename": filename,
        "certificate_rule": base,
    }
    context = build_ocr_context_for_job(job, base)

    # 연결 불가/오류는 기존 OCR 결과를 유지하고 진단 정보만 추가한다.
    if context.get("context_status") in {"UNAVAILABLE", "ERROR", "NO_MATCH"}:
        output = dict(base)
        output["context_status"] = context.get("context_status")
        output["context_reliability"] = context.get("reliability", "LOW")
        output["context_warnings"] = list(context.get("warnings") or [])
        output["context_conflicts"] = list(context.get("hard_blockers") or [])
        output["auto_confirm_eligible"] = False
        return output

    return reconcile_certificate_rule_with_context(base, raw_text, context)
