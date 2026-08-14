"""메일 관리번호·PMF 원료 정보로 판독 결과를 교차검증한다.

자동확정 안전 원칙이 구현된 곳이다 — 기관이 불일치하면 MANUAL_REVIEW로 내리고,
PMF 기존 값을 새 결과로 덮어쓰지 않는다."""

from __future__ import annotations

from typing import Any
import re

from app.services.rules.text import (
    clean_ocr_text,
    lines_of,
)
from app.services.rules.products import (
    best_product_match,
)
from app.services.rules.core import (
    parse_certificate_rule,
)


_CONTEXT_ORG_ALIASES = {
    "LLSISA": "ISA",
    "LLS-ISA": "ISA",
    "LPPOMMUI": "MUI",
    "LPPOM-MUI": "MUI",
}


def _context_clean(value: Any) -> str:
    text = clean_ocr_text(str(value or ""))
    if text.strip().lower() in {"", "-", "none", "null", "nan"}:
        return ""
    return text.strip()


def _context_norm(value: Any) -> str:
    text = _context_clean(value).upper()
    text = text.replace("®", "").replace("™", "")
    text = re.sub(r"[^A-Z0-9가-힣]+", "", text)
    return text


def _context_org(value: Any) -> str:
    raw = _context_clean(value).upper()
    key = _context_norm(raw)
    return _CONTEXT_ORG_ALIASES.get(raw) or _CONTEXT_ORG_ALIASES.get(key) or raw


def _context_similarity(left: Any, right: Any) -> float:
    left_key = _context_norm(left)
    right_key = _context_norm(right)

    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    if left_key in right_key or right_key in left_key:
        shorter = min(len(left_key), len(right_key))
        longer = max(len(left_key), len(right_key))
        if shorter >= 4:
            return 0.75 + 0.20 * (shorter / max(longer, 1))
    return SequenceMatcher(None, left_key, right_key).ratio()


def _context_text_match(raw_text: str, expected: Any) -> dict[str, Any]:
    expected_text = _context_clean(expected)
    expected_key = _context_norm(expected_text)
    raw_key = _context_norm(raw_text)

    if not expected_key:
        return {"matched": False, "score": 0.0, "method": "EMPTY"}

    if expected_key in raw_key:
        return {"matched": True, "score": 1.0, "method": "NORMALIZED_SUBSTRING"}

    # OCR 줄 단위로 유사도를 확인한다. 긴 전체문서와 직접 비교하지 않는다.
    best_score = 0.0
    best_line = ""

    for line in lines_of(raw_text):
        score = _context_similarity(expected_text, line)
        if score > best_score:
            best_score = score
            best_line = line

    return {
        "matched": best_score >= 0.74,
        "score": round(best_score, 4),
        "method": "LINE_SIMILARITY",
        "matched_line": best_line[:240],
    }


def reconcile_certificate_rule_with_context(
    rule_result: dict[str, Any],
    raw_text: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    메일 관리번호/첨부 순번/PMF에서 확정된 원료 문맥을 OCR 결과와 교차검증한다.

    원칙:
    - PMF의 기존 인증번호와 유효기간은 새 인증서 값으로 복사하지 않는다.
    - OCR 기관과 메일 기관이 다르면 자동 확정을 차단한다.
    - 제조사/제품명은 실제 OCR 원문에서 확인되는 경우에만 PMF 표준명으로 정규화한다.
    - 원 OCR 값은 ocr_* 필드에 보존한다.
    """
    output = dict(rule_result or {})
    context = dict(context or {})

    reliability = _context_clean(context.get("reliability") or "LOW").upper()
    selection_reason = _context_clean(context.get("selection_reason"))
    expected_org = _context_org(context.get("org"))
    expected_maker = _context_clean(context.get("maker"))
    expected_country = _context_clean(context.get("maker_country")).upper()
    expected_cert_no = _context_clean(context.get("cert_no"))
    current_expiry = _context_clean(context.get("current_expiry"))
    expected_names = [
        _context_clean(context.get("english_name")),
        _context_clean(context.get("material_name")),
    ]
    expected_names = list(dict.fromkeys(name for name in expected_names if name))

    ocr_org = _context_org(output.get("cert_org"))
    ocr_maker = _context_clean(output.get("manufacturer"))
    ocr_country = _context_clean(output.get("manufacturing_country")).upper()
    ocr_cert_no = _context_clean(output.get("cert_no"))
    ocr_expiry = _context_clean(output.get("expiry_date"))

    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    conflicts: list[str] = []

    output["ocr_cert_org"] = ocr_org
    output["ocr_manufacturer"] = ocr_maker
    output["ocr_manufacturing_country"] = ocr_country
    output["ocr_cert_no"] = ocr_cert_no
    output["ocr_expiry_date"] = ocr_expiry

    org_match = False
    if expected_org:
        if ocr_org and ocr_org != "UNKNOWN":
            org_match = ocr_org == expected_org
            checks.append({
                "field": "cert_org",
                "status": "MATCH" if org_match else "CONFLICT",
                "ocr": ocr_org,
                "context": expected_org,
            })
            if not org_match:
                conflicts.append(
                    f"OCR 인증기관({ocr_org})과 메일/PMF 인증기관({expected_org})이 다릅니다."
                )
        elif reliability in {"HIGH", "MEDIUM"}:
            output["cert_org"] = expected_org
            output["cert_org_source"] = "MAIL_PMF_CONTEXT_FALLBACK"
            org_match = True
            checks.append({
                "field": "cert_org",
                "status": "CONTEXT_FALLBACK",
                "ocr": ocr_org or "UNKNOWN",
                "context": expected_org,
            })
        else:
            checks.append({
                "field": "cert_org",
                "status": "UNRESOLVED",
                "ocr": ocr_org or "UNKNOWN",
                "context": expected_org,
            })
    else:
        output["cert_org_source"] = output.get("cert_org_source") or "OCR_RULE"

    maker_text_match = _context_text_match(raw_text, expected_maker)
    maker_value_match = _context_similarity(ocr_maker, expected_maker)
    maker_verified = bool(expected_maker) and (
        maker_text_match.get("matched") or maker_value_match >= 0.72
    )

    if expected_maker:
        checks.append({
            "field": "manufacturer",
            "status": "MATCH" if maker_verified else "NOT_VERIFIED",
            "ocr": ocr_maker,
            "context": expected_maker,
            "value_score": round(maker_value_match, 4),
            "text_match": maker_text_match,
        })

        if maker_verified and not conflicts:
            output["manufacturer"] = expected_maker
            output["manufacturer_source"] = "MAIL_PMF_CONTEXT_VERIFIED_IN_OCR"
            if expected_country:
                output["manufacturing_country"] = expected_country
                output["manufacturing_country_source"] = "MAIL_PMF_CONTEXT"
        elif not ocr_maker:
            warnings.append("메일/PMF 제조사를 OCR 원문에서 확인하지 못했습니다.")
        elif maker_value_match < 0.45:
            warnings.append(
                f"OCR 제조사({ocr_maker})와 메일/PMF 제조사({expected_maker})의 유사도가 낮습니다."
            )

    product_matches: list[dict[str, Any]] = []
    product_candidates = output.get("product_candidates") or []

    for expected_name in expected_names:
        raw_match = _context_text_match(raw_text, expected_name)
        best_candidate: dict[str, Any] | None = None
        best_score = 0.0

        for candidate in product_candidates:
            score = _context_similarity(expected_name, candidate.get("name"))
            if score > best_score:
                best_score = score
                best_candidate = candidate

        matched = bool(raw_match.get("matched") or best_score >= 0.72)
        product_matches.append({
            "expected_name": expected_name,
            "matched": matched,
            "raw_text_match": raw_match,
            "candidate_score": round(best_score, 4),
            "candidate": best_candidate,
        })

    product_verified_rows = [row for row in product_matches if row.get("matched")]
    product_verified = bool(product_verified_rows)

    if expected_names:
        checks.append({
            "field": "product",
            "status": "MATCH" if product_verified else "NOT_VERIFIED",
            "matches": product_matches,
        })

        if product_verified and not conflicts:
            best_row = max(
                product_verified_rows,
                key=lambda row: max(
                    float(row.get("candidate_score") or 0.0),
                    float((row.get("raw_text_match") or {}).get("score") or 0.0),
                ),
            )
            candidate_score = float(best_row.get("candidate_score") or 0.0)
            canonical_product = (
                best_row.get("candidate")
                if candidate_score >= 0.72
                else {
                    "name": best_row.get("expected_name"),
                    "source": "MAIL_PMF_CONTEXT_VERIFIED_IN_OCR",
                }
            )
            output["best_product_match"] = {
                "score": max(
                    float(best_row.get("candidate_score") or 0.0),
                    float((best_row.get("raw_text_match") or {}).get("score") or 0.0),
                ),
                "product": canonical_product,
                "source": "MAIL_PMF_CONTEXT",
            }
        else:
            warnings.append("메일/PMF 제품명을 OCR 원문 또는 제품 목록에서 확인하지 못했습니다.")

    cert_no_match = False
    if expected_cert_no and ocr_cert_no:
        cert_no_match = _context_norm(expected_cert_no) == _context_norm(ocr_cert_no)
        checks.append({
            "field": "cert_no",
            "status": "MATCH" if cert_no_match else "CHANGED_OR_CONFLICT",
            "ocr": ocr_cert_no,
            "context_previous": expected_cert_no,
        })
        if not cert_no_match:
            warnings.append(
                "OCR 인증번호와 PMF의 기존 인증번호가 다릅니다. 갱신으로 번호가 변경된 것인지 확인해야 합니다."
            )

    date_regression = False
    if current_expiry and ocr_expiry and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", current_expiry) and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", ocr_expiry):
        date_regression = ocr_expiry < current_expiry
        checks.append({
            "field": "expiry_date",
            "status": "REGRESSION" if date_regression else "NOT_OLDER",
            "ocr": ocr_expiry,
            "context_previous": current_expiry,
        })
        if date_regression:
            warnings.append(
                f"OCR 유효기간({ocr_expiry})이 PMF 기존 유효기간({current_expiry})보다 과거입니다."
            )

    context_score = 0
    if org_match:
        context_score += 35
    if maker_verified:
        context_score += 30
    if product_verified:
        context_score += 25
    if cert_no_match:
        context_score += 10

    high_reliability = reliability == "HIGH"
    non_bpjph_has_expiry = output.get("cert_org") == "BPJPH" or bool(ocr_expiry)
    profile_blocking_flags = list(output.get("blocking_quality_flags") or [])

    if profile_blocking_flags:
        warnings.append(
            "기관 규칙 품질 검사에서 자동확정 차단 사유가 발견되었습니다: "
            + ", ".join(profile_blocking_flags)
        )

    auto_confirm_eligible = bool(
        high_reliability
        and not conflicts
        and not profile_blocking_flags
        and not date_regression
        and org_match
        and (maker_verified or product_verified)
        and non_bpjph_has_expiry
    )

    if conflicts:
        output["ok"] = False
        output["parse_status"] = "MANUAL_REVIEW"
        output["confidence"] = "LOW"
        context_status = "CONFLICT"
    elif profile_blocking_flags:
        output["ok"] = False
        output["parse_status"] = "MANUAL_REVIEW"
        output["confidence"] = "LOW"
        context_status = "PROFILE_REVIEW"
    elif auto_confirm_eligible:
        output["ok"] = True
        output["parse_status"] = "RULE_MATCHED"
        output["confidence"] = "HIGH"
        context_status = "VERIFIED"
    elif context_score >= 35:
        # 문맥은 도움을 줬지만 자동확정 기준까지는 부족하다.
        if output.get("parse_status") not in {"BPJPH_MAINTENANCE_ONLY", "NON_CERTIFICATE_DOC"}:
            output["parse_status"] = "LOW_CONFIDENCE"
            output["confidence"] = "MEDIUM"
        context_status = "ASSISTED"
    else:
        context_status = "UNVERIFIED"

    output["context_status"] = context_status
    output["context_score"] = context_score
    output["context_reliability"] = reliability
    output["context_selection_reason"] = selection_reason
    output["context_checks"] = checks
    output["context_warnings"] = list(dict.fromkeys(warnings))
    output["context_conflicts"] = list(dict.fromkeys(conflicts))
    output["auto_confirm_eligible"] = auto_confirm_eligible
    output["linked_request_id"] = _context_clean(context.get("request_id"))
    output["linked_item_index"] = context.get("item_index")

    return output


def parse_certificate_rule_with_context(
    raw_text: str,
    filename: str = "",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """기존 규칙 판독 후 메일/PMF 문맥으로 안전하게 교차검증한다."""
    context = dict(context or {})
    expected_name = _context_clean(context.get("english_name") or context.get("material_name"))
    base = parse_certificate_rule(
        raw_text=raw_text,
        filename=filename,
        expected_name=expected_name,
        expected_org="",  # expected_org를 OCR 본문에 섞지 않는다.
    )
    return reconcile_certificate_rule_with_context(base, raw_text, context)
