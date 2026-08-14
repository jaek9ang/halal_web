"""인증서 양식(pHash/ORB) 분류 결과를 규칙 판독 결과와 대조한다."""

from __future__ import annotations

from pathlib import Path
from typing import Any


IMAGE_TEMPLATE_DECISIONS = {"AUTO_IMAGE", "REVIEW", "MANUAL_REVIEW", "NO_REFERENCE", "ERROR"}


ADMIN_TEMPLATE_DECISIONS = {
    "AUTO_CONFIRMED",
    "MANUAL_CONFIRMED",
    "MANUAL_CORRECTED",
    "EXCLUDED",
    "RESTORED",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _upper_text(value: Any) -> str:
    return str(value or "").strip().upper()


def build_template_classification_for_ocr(path: Path) -> dict[str, Any]:
    """
    OCR 실행 전에 인증서 양식 DB로 기관 후보를 먼저 판정한다.
    관리자 확정/정정/제외값이 저장되어 있으면 classify_file_path 내부에서 우선 적용된다.
    이 함수는 실패해도 OCR 자체를 막지 않고 error 정보를 result_json에 남긴다.
    """
    try:
        # Lazy import: cert_template_service <-> ocr_service circular import 방지
        from app.services.cert_template_service import classify_file_path

        row = classify_file_path(
            str(path),
            enhanced_retry=True,
            max_pages=1,
        )

        manual = row.get("manual_decision") or {}
        manual_type = _upper_text(manual.get("decision_type"))
        raw_decision = _upper_text(row.get("decision"))
        is_excluded = (
            raw_decision == "EXCLUDED"
            or manual_type == "EXCLUDED"
            or int(manual.get("is_excluded") or 0) == 1
        )

        image_decision = _upper_text(
            manual.get("original_decision")
            or row.get("image_decision")
            or row.get("original_decision")
            or row.get("decision")
        )

        if image_decision not in IMAGE_TEMPLATE_DECISIONS:
            # 관리자 판정값이 decision에 들어온 경우에는 원본 이미지 판정값이 없을 수 있다.
            score = _safe_float(row.get("score"))
            margin = _safe_float(row.get("margin"))
            if score >= 0.82 and margin >= 0.07:
                image_decision = "AUTO_IMAGE"
            elif score < 0.70 or margin < 0.04:
                image_decision = "MANUAL_REVIEW"
            else:
                image_decision = "REVIEW"

        predicted_org = str(
            manual.get("predicted_org")
            or row.get("predicted_org")
            or "-"
        ).strip() or "-"

        final_org = str(
            manual.get("final_org")
            or row.get("final_org")
            or row.get("predicted_org")
            or "-"
        ).strip() or "-"

        if is_excluded:
            final_org = "-"

        top_candidates = row.get("top_candidates") or []
        top_candidates = top_candidates[:5] if isinstance(top_candidates, list) else []

        return {
            "ok": True,
            "file_hash": row.get("file_hash") or "",
            "filename": path.name,
            "file_path": str(path),
            "predicted_org": predicted_org,
            "final_org": final_org,
            "image_decision": image_decision,
            "decision": raw_decision or image_decision,
            "admin_decision": manual_type if manual_type in ADMIN_TEMPLATE_DECISIONS else "",
            "is_excluded": bool(is_excluded),
            "score": _safe_float(row.get("score")),
            "second_org": row.get("second_org") or "-",
            "second_score": _safe_float(row.get("second_score")),
            "margin": _safe_float(row.get("margin")),
            "feature_kind": row.get("feature_kind") or "-",
            "top_candidates": top_candidates,
            "top_evidence": row.get("top_evidence") or {},
            "manual_decision": manual or None,
        }

    except Exception as e:
        return {
            "ok": False,
            "filename": path.name,
            "file_path": str(path),
            "predicted_org": "-",
            "final_org": "-",
            "image_decision": "ERROR",
            "decision": "ERROR",
            "admin_decision": "",
            "is_excluded": False,
            "score": 0.0,
            "second_org": "-",
            "second_score": 0.0,
            "margin": 0.0,
            "feature_kind": "-",
            "top_candidates": [],
            "error": str(e),
        }


def reconcile_template_classification_with_rule(
    image_classification: dict[str, Any],
    certificate_rule: dict[str, Any],
) -> dict[str, Any]:
    """
    이미지 양식 분류와 OCR 텍스트 규칙 결과가 충돌할 때 최종기관을 보정한다.

    원칙:
    1. 관리자 확정/정정/제외값은 최우선으로 유지한다.
    2. 이미지 판정이 AUTO_IMAGE면 이미지기관을 유지하되, 텍스트기관과 다르면 conflict만 표시한다.
    3. 이미지 판정이 REVIEW/MANUAL_REVIEW이고 텍스트 규칙기관이 명확하면 최종기관은 텍스트 규칙기관으로 보정한다.
    4. 텍스트 규칙기관이 없으면 이미지기관을 후보로만 유지한다.
    """
    info = dict(image_classification or {})
    rule = certificate_rule or {}

    if not info:
        return info

    if info.get("is_excluded"):
        info["final_org"] = "-"
        info["final_org_source"] = "ADMIN_EXCLUDED"
        return info

    manual_obj = info.get("manual_decision") if isinstance(info.get("manual_decision"), dict) else {}
    admin_type = _upper_text(info.get("admin_decision") or manual_obj.get("decision_type"))
    image_decision = _upper_text(info.get("image_decision") or info.get("decision"))
    predicted_org = str(info.get("predicted_org") or "-").strip() or "-"

    rule_org = str(rule.get("cert_org") or "").strip().upper()
    if not rule_org or rule_org == "UNKNOWN":
        rule_org = ""

    if admin_type in {"AUTO_CONFIRMED", "MANUAL_CONFIRMED", "MANUAL_CORRECTED"}:
        info["final_org"] = str(info.get("final_org") or predicted_org or "-").strip() or "-"
        info["final_org_source"] = "ADMIN"
        if rule_org:
            info["text_rule_org"] = rule_org
            info["text_image_conflict"] = predicted_org.upper() != rule_org
        return info

    if image_decision == "AUTO_IMAGE":
        info["final_org"] = str(info.get("final_org") or predicted_org or "-").strip() or "-"
        info["final_org_source"] = "IMAGE_AUTO"
        if rule_org:
            info["text_rule_org"] = rule_org
            info["text_image_conflict"] = predicted_org.upper() != rule_org
        return info

    if rule_org:
        info["final_org"] = rule_org
        info["final_org_source"] = "TEXT_RULE"
        info["text_rule_org"] = rule_org
        info["text_image_conflict"] = predicted_org.upper() != rule_org
        return info

    info["final_org"] = predicted_org
    info["final_org_source"] = "IMAGE_REVIEW_CANDIDATE"
    info["text_image_conflict"] = False
    return info
