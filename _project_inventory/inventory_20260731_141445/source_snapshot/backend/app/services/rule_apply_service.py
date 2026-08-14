from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.rule_candidate_service import (
    append_approved_rule_history,
    get_rule_candidate,
    get_rule_overrides,
    save_rule_overrides,
    update_rule_candidate_status,
)
from app.services.rule_validation_service import get_validation_report


def rule_already_applied(overrides: dict[str, Any], rule_candidate_id: str) -> bool:
    return any(rule.get("rule_candidate_id") == rule_candidate_id for rule in overrides.get("rules") or [])


def build_override_rule_from_candidate(candidate: dict[str, Any], validation_report_id: str = "", actor: str = "user") -> dict[str, Any]:
    return {
        "enabled": True,
        "rule_candidate_id": candidate.get("rule_candidate_id"),
        "review_version": candidate.get("review_version") or "ai_rule_review_v1",
        "target_org": candidate.get("target_org") or "",
        "target_field": candidate.get("target_field") or "",
        "rule_kind": candidate.get("rule_kind") or "",
        "proposed_rule": deepcopy(candidate.get("proposed_rule") or {}),
        "risk_level": candidate.get("risk_level") or "MEDIUM",
        "source": "AI_RULE_REVIEW",
        "validation_report_id": validation_report_id or candidate.get("validation_report_id") or "",
        "applied_by": actor,
    }


def validate_apply_allowed(candidate: dict[str, Any], validation_report: dict[str, Any] | None = None) -> tuple[bool, str]:
    if not candidate:
        return False, "규칙 후보가 없습니다."
    if candidate.get("apply_status") == "APPLIED":
        return False, "이미 적용된 규칙입니다."

    target_org = str(candidate.get("target_org") or "").upper().strip()
    target_field = candidate.get("target_field") or ""
    rule_kind = candidate.get("rule_kind") or ""
    risk_level = str(candidate.get("risk_level") or "MEDIUM").upper()

    if target_org in {"", "ALL", "ANY", "*"}:
        return False, "전체 기관 대상 규칙은 자동 적용할 수 없습니다. 기관별 규칙으로 좁혀야 합니다."
    
    if target_field in {"cert_org", "cert_country"}:
        return False, "cert_org/cert_country 변경 규칙은 자동 적용할 수 없습니다."
    if rule_kind == "global_fallback_rule":
        return False, "global fallback 규칙은 자동 적용할 수 없습니다."
    if risk_level == "HIGH":
        return False, "HIGH 위험도 규칙은 자동 적용할 수 없습니다."

    summary = (validation_report or {}).get("summary") or candidate.get("validation_summary") or {}
    if not summary:
        return False, "검증 리포트가 없습니다. 먼저 테스트 적용을 실행해야 합니다."
    if int(summary.get("regression_count") or 0) > 0:
        return False, "regression_count가 1건 이상입니다."
    if int(summary.get("improved_count") or 0) <= 0:
        return False, "개선 건수가 없습니다."
    if not bool(summary.get("auto_apply_allowed")):
        return False, "검증 결과가 자동 적용 허용 상태가 아닙니다."
    return True, ""


def apply_rule_candidate(rule_candidate_id: str, validation_report_id: str = "", actor: str = "user") -> dict[str, Any]:
    candidate = get_rule_candidate(rule_candidate_id)
    if not candidate:
        raise ValueError(f"rule_candidate_id를 찾을 수 없습니다: {rule_candidate_id}")

    validation_report = None
    report_id = validation_report_id or candidate.get("validation_report_id") or ""
    if report_id:
        validation_report = get_validation_report(report_id)

    allowed, reason = validate_apply_allowed(candidate, validation_report)
    if not allowed:
        raise ValueError(reason)

    overrides = get_rule_overrides()
    if rule_already_applied(overrides, rule_candidate_id):
        update_rule_candidate_status(rule_candidate_id, "APPLIED", message="이미 override에 존재합니다.")
        return {"ok": True, "applied": False, "message": "이미 적용된 규칙입니다.", "rule_candidate_id": rule_candidate_id, "overrides": overrides}

    override_rule = build_override_rule_from_candidate(candidate, validation_report_id=report_id, actor=actor)
    overrides.setdefault("rules", []).append(override_rule)
    overrides = save_rule_overrides(overrides)

    update_rule_candidate_status(
        rule_candidate_id,
        "APPLIED",
        message="certificate_rule_overrides.json에 반영되었습니다.",
        validation_report_id=report_id,
        validation_summary=(validation_report or {}).get("summary") if validation_report else candidate.get("validation_summary"),
    )
    append_approved_rule_history({
        "event": "APPLY_RULE_CANDIDATE",
        "rule_candidate_id": rule_candidate_id,
        "validation_report_id": report_id,
        "actor": actor,
        "override_rule": override_rule,
    })
    return {"ok": True, "applied": True, "rule_candidate_id": rule_candidate_id, "validation_report_id": report_id, "override_rule": override_rule, "overrides": overrides}


def reject_rule_candidate(rule_candidate_id: str, reason: str = "", actor: str = "user") -> dict[str, Any]:
    candidate = get_rule_candidate(rule_candidate_id)
    if not candidate:
        raise ValueError(f"rule_candidate_id를 찾을 수 없습니다: {rule_candidate_id}")
    updated = update_rule_candidate_status(rule_candidate_id, "REJECTED", message=reason or "사용자 반려")
    append_approved_rule_history({"event": "REJECT_RULE_CANDIDATE", "rule_candidate_id": rule_candidate_id, "actor": actor, "reason": reason or "사용자 반려"})
    return {"ok": True, "rejected": True, "rule_candidate_id": rule_candidate_id, "candidate": updated}
