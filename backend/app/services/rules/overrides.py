"""data/rules/certificate_rule_overrides.json 으로 판독 결과를 덮어쓰는 계층."""

from __future__ import annotations

from datetime import date
from typing import Any
import re

from app.services.rules.text import (
    clean_ocr_text,
    upper_text,
)
from app.services.rules.dates import (
    find_dates,
)
from app.services.rules.companies import (
    normalize_manufacturer_output,
)
from app.services.rules.products import (
    best_product_match,
)


def _load_certificate_rule_overrides() -> list[dict[str, Any]]:
    """
    AI 규칙 리뷰에서 승인된 override rule을 읽는다.
    import 순환을 피하기 위해 함수 내부 import 사용.
    """
    try:
        from app.services.rule_candidate_service import get_rule_overrides
    except Exception:
        return []

    try:
        data = get_rule_overrides()
    except Exception:
        return []

    rules = data.get("rules") or []

    if not isinstance(rules, list):
        return []

    return [rule for rule in rules if isinstance(rule, dict) and rule.get("enabled", True)]


def _override_find_date_after(
    text: str,
    anchors: list[str],
    stop_before: list[str] | None = None,
    window: int = 650,
) -> tuple[str, str]:
    src = str(text or "")
    upper = upper_text(src)
    stop_before = stop_before or []

    for anchor in anchors or []:
        anchor_u = str(anchor or "").upper().strip()

        if not anchor_u:
            continue

        start = 0

        while True:
            idx = upper.find(anchor_u, start)

            if idx < 0:
                break

            chunk = src[idx: idx + window]
            chunk_upper = upper_text(chunk)
            cut_at = len(chunk)

            for stop in stop_before:
                stop_u = str(stop or "").upper().strip()

                if not stop_u:
                    continue

                stop_idx = chunk_upper.find(stop_u)

                if stop_idx > 0:
                    cut_at = min(cut_at, stop_idx)

            chunk = chunk[:cut_at]
            dates = find_dates(chunk)

            if dates:
                return dates[0].get("date") or "", dates[0].get("raw") or ""

            start = idx + len(anchor_u)

    return "", ""


def _override_cleanup_manufacturer(value: str, org: str) -> str:
    cleanup_func = globals().get("normalize_manufacturer_output")

    if callable(cleanup_func):
        return cleanup_func(value, org)

    text = clean_ocr_text(value)
    text = re.sub(
        r"^(Company\s+Name\s*&\s*Address|Company\s+Name|Name\s+of\s+Company|Company|Manufacturer|Manufactured\s+by|For)\s*[:：]\s*",
        "",
        text,
        flags=re.I,
    )
    return clean_ocr_text(text).strip(" ,.-")


def apply_certificate_rule_overrides(
    result: dict[str, Any],
    text: str,
    filename: str = "",
) -> dict[str, Any]:
    """
    certificate_rule_overrides.json에 승인된 AI 규칙을 최종 parse 결과에 적용한다.
    Python 코드 자동수정이 아니라 JSON override만 적용한다.
    """
    output = dict(result or {})
    rules = _load_certificate_rule_overrides()

    if not rules:
        return output

    haystack = upper_text("\n".join([filename or "", text or ""]))

    for rule in rules:
        target_org = str(rule.get("target_org") or "").upper().strip()
        target_field = str(rule.get("target_field") or "").strip()
        rule_kind = str(rule.get("rule_kind") or "").strip()
        proposed_rule = rule.get("proposed_rule") or {}

        current_org = str(output.get("cert_org") or "").upper().strip()

        if target_org and current_org != target_org:
            continue

        if rule_kind == "date_anchor_rule" and target_field:
            anchors = proposed_rule.get("anchors") or []
            stop_before = proposed_rule.get("stop_before") or []
            window = int(proposed_rule.get("window") or 650)

            date, raw = _override_find_date_after(
                text,
                anchors=anchors,
                stop_before=stop_before,
                window=window,
            )

            if date:
                output[target_field] = date

                if target_field == "expiry_date":
                    output["expiry_candidates"] = [{
                        "date": date,
                        "raw": raw,
                        "source": f"AI_OVERRIDE:{rule.get('rule_candidate_id', '')}",
                    }]

        elif rule_kind == "manufacturer_cleanup_rule":
            field = target_field or "manufacturer"
            before = str(output.get(field) or "")
            after = _override_cleanup_manufacturer(before, current_org)

            if after:
                output[field] = after

        elif rule_kind == "cert_no_pattern_rule":
            field = target_field or "cert_no"
            patterns = proposed_rule.get("patterns") or []

            for pattern in patterns:
                try:
                    match = re.search(pattern, text, re.I)
                except re.error:
                    continue

                if not match:
                    continue

                value = match.group(1) if match.groups() else match.group(0)
                value = re.sub(r"\s+", "", value.strip())

                if value:
                    output[field] = value

                    if field == "cert_no":
                        output["cert_no_candidates"] = [value]

                    break

        elif rule_kind == "non_certificate_doc_rule":
            markers = [upper_text(x) for x in proposed_rule.get("markers") or []]

            if markers and any(marker in haystack for marker in markers):
                output.update({
                    "ok": True,
                    "parse_status": "NON_CERTIFICATE_DOC",
                    "cert_org": "UNKNOWN",
                    "cert_country": "",
                    "org_hits": [],
                    "cert_no": "",
                    "cert_no_candidates": [],
                    "expiry_date": "",
                    "expiry_candidates": [],
                    "manufacturer": "",
                    "manufacturing_country": "",
                    "country_match_status": "",
                    "products_count": 0,
                    "product_candidates": [],
                    "best_product_match": {},
                    "source_rule": "AI_NON_CERTIFICATE_DOC_RULE",
                    "confidence": "HIGH",
                })

    return output
