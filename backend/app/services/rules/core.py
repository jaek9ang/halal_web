"""인증번호·유효기간 추출과 전체 판독 진입점."""

from __future__ import annotations

from datetime import date
from typing import Any
import re

from app.services.rules.text import (
    clean_ocr_text,
    upper_text,
)
from app.services.rules.dates import (
    extract_cicot_expiry_date,
    extract_date_after,
    extract_latest_date_near_anchors,
    extract_mui_valid_until_date,
    extract_muis_expiry_date,
    find_dates,
    parse_date_text,
)
from app.services.rules.organizations import (
    detect_org,
    resolve_cert_country,
)
from app.services.rules.companies import (
    extract_manufacturer,
    extract_manufacturing_country,
    normalize_manufacturer_output,
)
from app.services.rules.products import (
    best_product_match,
    extract_products,
    finalize_product_candidates,
)
from app.services.rules.overrides import (
    apply_certificate_rule_overrides,
)


def extract_cert_no(text: str, org: str) -> tuple[str, list[str]]:
    t = clean_ocr_text(text)
    u = t.upper()
    candidates: list[str] = []

    org_patterns = {
        "IFANCA": [r"\bHC-[A-Z0-9]{6,}\b", r"DOCUMENT\s*#\s*[:：]?\s*([A-Z0-9./-]+)"],
        "MUI": [r"\bLPPOM[- ]\d{6,}\b"],
        "BPJPH": [
            r"(?<![A-Z0-9])ID00\d{8,}(?![A-Z0-9])",
            r"ID00\d{8,}",
            r"\bID\d{10,}\b",
            r"\bLPPOM[- ]\d{6,}\b",
        ],
        "HQC": [r"CERT\.?\s*NO\s*[:：]?\s*([A-Z]{0,3}\d{6,}[A-Z0-9-]*)", r"CERTIFICATE\s*NO\s*[:：]?\s*([A-Z]{0,3}\d{6,}[A-Z0-9-]*)"],
        "ISA": [r"CERTIFICATE\s*NO\.?\s*[:：]?\s*([0-9]{4}-[0-9]{2}-[0-9]{4,})"],
        "LLS-ISA": [r"CERTIFICATE\s*NO\.?\s*[:：]?\s*([0-9]{4}-[0-9]{2}-[0-9]{4,})"],
        "HCE": [r"CERTIFICATE\s*NO\s*[:：]?\s*([A-Z0-9/.-]+)"],
        "HFCE": [
            r"CERTIFICATE\s*NO\.?\s*[:：]?\s*([A-Z0-9/.-]+)",
            r"\bHC-\d{2}[A-Z0-9]{4,12}\b",
        ],
        "HFQ": [
            r"\bHFQ\s*-\s*\d{1,6}\s*/\s*\d{1,4}\s*/\s*[A-Z]{2,10}\b",
            r"WITH\s+CERTIFICATE\s+NUMBER\s*[:：]?\s*(HFQ\s*-\s*\d{1,6}\s*/\s*\d{1,4}\s*/\s*[A-Z]{2,10})\b",
            r"CON\s+N[ºO]\s+DE\s+CERTIFICADO\s*[:：]?\s*(HFQ\s*-\s*\d{1,6}\s*/\s*\d{1,4}\s*/\s*[A-Z]{2,10})\b",
        ],
        "HALAL CONTROL": [r"CERT\.-NO\.?:?\s*([A-Z0-9/.-]+)", r"CERTIFICATE\s+REGISTRATION\s+NO\.?\s*[:：]?\s*([A-Z0-9/.-]+)", r"\bC-\d{2}-[0-9-]+\b"],
        "HCA": [
            r"CERT\s*[I1L]D\s*[:：]?\s*(HCA\s*[A-Z0-9/ -]+)",
            r"\bHCA\s*\d{2,5}\s*/\s*[A-Z]{2,10}\b",
        ],
        "CICOT": [r"CICOT\s*HL\s*[:：]?\s*([0-9/.-]+)", r"\b\d{3}/\d{4}\b", r"\b\d{3}\s+\d{3}\s+\d{3}\s+\d{2}\s+\d{2}\b"],
        "JAKIM": [r"JAKIM[./A-Z0-9() -]{8,}", r"NO\.\s*RUJ\.?\s*/\s*REF\s*NO\.?\s*[:：]?\s*([A-Z0-9./() -]+)"],
        "MUIS": [
            r"\bPRN[A-Z0-9]{8,20}\b",
            r"CERTIFICATE\s*NO\.?\s*[:?]?\s*([A-Z0-9/.-]+)",
            r"REF\s*NO\.?\s*[:?]?\s*([A-Z0-9/.-]+)",
        ],
        "JMA": [
            r"\bNO\.?\s*[:：]?\s*(\d{1,6}\s*-\s*[A-Z]{2,12}\s*/\s*\d{2,4})",
            r"CERTIFICATE\s*NO\.?\s*[:：]?\s*([0-9A-Z/ -]{5,})",
        ],
        "ARA": [
            r"CERTIFICATE\s*NO[\s\S]{0,220}?(ARA-\d{6,}(?:-\d+)?)",
            r"\bARA-\d{6,}(?:-\d+)?\b",
        ],
        "JUHF": [
            r"CERTIFICATE\s*NO[\s\S]{0,120}?(JUHF-\d{3,6}-\d{3,6})",
            r"\bJUHF-\d{3,6}-\d{3,6}\b",
        ],
        "KMF": [
            r"\bKMFHC\d{2}-\d{2,6}(?:-\d{1,3})?\b",
            r"\bKMFHC\d{2,4}[-\s]?\d{2,6}(?:[-\s]?\d{1,3})?\b",
            r"Certificate\s*No\.?\s*[:：]?\s*([A-Z0-9/.-]+)",
            r"인증\s*번호\s*[:：]?\s*([A-Z0-9가-힣/.-]+)",
        ],
        "TQHCC": [r"HCC[A-Z0-9-]{6,}", r"CERTIFICATE\s*(?:NO|NR)\.?\s*[:：]?\s*([A-Z0-9-]+)"],
        "HFFIA": [
            r"CERTIFICATE\s*NO\.?\s*[:：]?\s*([A-Z0-9/.-]+)",
            r"\bH\d{4,}-\d{2}\b",
            r"\b\d{2}-[A-Z]{2,4}\b",
        ],
    }
    for pat in org_patterns.get(org, []):
        for m in re.finditer(pat, u, re.I):
            val = m.group(1) if m.groups() else m.group(0)
            val = re.sub(r"\s+", " ", val).strip(" .:-")
            if val and val not in candidates:
                candidates.append(val)

    if org == "JMA":
        candidates = [re.sub(r"\s+", "", value) for value in candidates]

    # ARA attachment의 Certificate No가 Ref No보다 더 구체적인 경우(-1 등)
    # 긴 값을 우선하되 후보 전체는 유지한다.
    if org in {"ARA", "JUHF"} and candidates:
        candidates = sorted(
            dict.fromkeys(candidates),
            key=lambda value: (len(value), value.count("-")),
            reverse=True,
        )

    return (candidates[0] if candidates else "", candidates)


def extract_expiry(text: str, filename: str, org: str) -> tuple[str, list[dict[str, str]]]:
    # BPJPH는 유지확인용으로만 사용한다. 발급일/파일명 날짜를 유효기간으로 오인하지 않는다.
    if org == "BPJPH":
        return "", []

    # MUI는 Valid until만 신뢰한다. Issued date / footer 날짜 fallback 금지.
    if org == "MUI":
        date, raw = extract_mui_valid_until_date(text)

        if date:
            return date, [{"date": date, "raw": raw, "source": "MUI_VALID_UNTIL"}]

        # MUI에서 본문 Valid until 실패 시에는 파일명 괄호/물결 날짜만 보조 사용.
        fname = filename or ""
        for raw in re.findall(
            r"(?:\[|\(|~)(?:[A-Z-]+_)?(20\d{2}[-.][0-9]{1,2}[-.][0-9]{1,2}|\d{2}[.]\d{1,2}[.]\d{1,2})(?:\]|\))?",
            fname,
            re.I,
        ):
            d = parse_date_text(raw)

            if d:
                return d, [{"date": d, "raw": raw, "source": "FILENAME"}]

        return "", []

    if org == "CICOT":
        date, raw = extract_cicot_expiry_date(text, filename)

        if date:
            return date, [{"date": date, "raw": raw, "source": "CICOT_EXPIRED_DATE"}]

    if org == "ARA":
        date, raw = extract_latest_date_near_anchors(
            text,
            ["EXPIRED DATE", "EXPIRY DATE"],
            before=40,
            after=700,
        )
        if date:
            return date, [{"date": date, "raw": raw, "source": "ARA_EXPIRED_DATE"}]

    if org == "MUIS":
        date, raw = extract_muis_expiry_date(text, filename)
        if date:
            return date, [{"date": date, "raw": raw, "source": "MUIS_EXPIRY"}]

    anchors_by_org = {
        "IFANCA": ["THIS CERTIFICATE IS VALID UNTIL", "THIS CERTIFICATE IS VALID THROUGH"],
        "MUI": ["VALID UNTIL"],
        "BPJPH": [],
        "HQC": ["EXPIRY DATE", "DATE OF EXPIRY"],
        "ISA": ["VALID UNTIL", "VALID THROUGH"],
        "LLS-ISA": ["VALID UNTIL", "VALID THROUGH"],
        "HCE": ["EXPIRY DATE", "EXPIRY"],
        "HFCE": ["VALID UNTIL"],
        "HFQ": ["CERTIFICATE VALID UNTIL", "CERTIFICADO VÁLIDO HASTA", "VALID UNTIL"],
        "HALAL CONTROL": ["VALID UNTIL", "THIS CERTIFICATE IS VALID UNTIL"],
        "HCA": ["EXPIRED DATE", "EXPIRY DATE", "VALID UNTIL"],
        "CICOT": ["VALID UNTIL", "SAH SEHINGGA", "EFFECTIVE FROM"],
        "JAKIM": ["SAH SEHINGGA", "VALID UNTIL"],
        "MUIS": ["VALID UNTIL", "EXPIRY DATE", "DATE OF EXPIRY"],
        "JMA": ["VALID UNTIL"],
        "KMF": ["유효기간", "인증기간", "VALID UNTIL"],
        "TQHCC": ["CERTIFICATE VALID UNTIL", "VALID UNTIL"],
        "HFFIA": ["VALID UNTIL", "EXPIRY DATE"],
        "ARA": ["EXPIRED DATE", "EXPIRY DATE", "VALID UNTIL"],
        "JUHF": ["DATE OF EXPIRY", "EXPIRY DATE", "VALID UNTIL"],
    }

    candidates: list[dict[str, str]] = []

    for anchor in anchors_by_org.get(org, ["VALID UNTIL", "EXPIRY DATE"]):
        date, raw = extract_date_after(text, [anchor], window=520)

        if date:
            candidates.append({"date": date, "raw": raw, "source": anchor})
            break

    # CICOT/JAKIM처럼 issue date와 expiry date가 연속일 때 anchor 주변 두 번째 날짜를 만료 후보로 사용
    if not candidates and org in {"CICOT", "JAKIM"}:
        all_dates = find_dates(text)

        if len(all_dates) >= 2:
            candidates.append({**all_dates[-1], "source": "LAST_DATE_FALLBACK"})

    # 파일명 보조 규칙: [ORG_YYYY-MM-DD], ORG(YYYY-MM-DD), (~26.12.17)
    fname = filename or ""

    for raw in re.findall(
        r"(?:\[|\(|~)(?:[A-Z-]+_)?(20\d{2}[-.][0-9]{1,2}[-.][0-9]{1,2}|\d{2}[.]\d{1,2}[.]\d{1,2})(?:\]|\))?",
        fname,
        re.I,
    ):
        d = parse_date_text(raw)

        if d:
            candidates.append({"date": d, "raw": raw, "source": "FILENAME"})
            break

    # 전체 날짜 fallback은 위험하므로 MUI/BPJPH는 제외
    if not candidates and org not in {"BPJPH", "MUI"}:
        all_dates = find_dates(text)

        if all_dates:
            candidates.append({**all_dates[-1], "source": "DATE_FALLBACK"})

    seen = set()
    unique = []

    for c in candidates:
        k = (c.get("date"), c.get("source"))

        if c.get("date") and k not in seen:
            seen.add(k)
            unique.append(c)

    return (unique[0]["date"] if unique else "", unique)


def country_match(manufacturing_country: str | None, cert_country: str | None) -> str:
    if not manufacturing_country or not cert_country:
        return "확인필요"
    return "일치" if manufacturing_country == cert_country else "불일치"


def is_non_certificate_document(text: str, filename: str = "") -> bool:
    u = upper_text("\n".join([filename or "", text or ""]))

    strong_non_cert_markers = [
        "MATERIAL SAFETY DATA SHEETS",
        "MSDS",
        "CERTIFICATION PROCESS IS CURRENTLY UNDERWAY",
        "CERTIFICATE IS EXPECTED TO BE AWARDED",
        "EXPECTED TO BE AWARDED",
        "NOT CERTIFIED",
        "NOT A HALAL CERTIFICATE",
        "갱신 해당 없음",
        "해당 사항 없음",
        "제출 대상에 해당하지 않습니다",
        "할랄 인증을 취득 또는 유지하고 있는 품목이 아니",
    ]

    return any(marker in u for marker in strong_non_cert_markers)


def parse_certificate_rule(raw_text: str, filename: str = "", expected_name: str = "", expected_org: str = "") -> dict[str, Any]:
    text = clean_ocr_text(raw_text)
    blob = upper_text("\n".join([filename or "", expected_org or "", text]))

    if (
        "TESSERACT IS NOT INSTALLED" in blob
        or "NOT IN YOUR PATH" in blob
        or "TESSERACTNOTFOUNDERROR" in blob
        or "[TESSERACT_ERROR]" in blob
    ):
        return {
            "ok": False,
            "parse_status": "TESSERACT_ERROR",
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
            "source_rule": "TESSERACT_ERROR_RULE",
            "confidence": "LOW",
            "has_text": bool(text.strip()),
            "text_length": len(text),
            "message": "Tesseract OCR 엔진이 설치되어 있지 않거나 PATH에 등록되어 있지 않습니다.",
        }

    if is_non_certificate_document(text, filename):
        return {
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
            "source_rule": "NON_CERTIFICATE_DOC_RULE",
            "confidence": "HIGH",
            "has_text": bool(text.strip()),
            "text_length": len(text),
            "message": "MSDS, 갱신 해당 없음 공문 등 인증서가 아닌 문서로 분류되었습니다.",
        }

    org, cert_country, org_hits = detect_org(text, filename=filename, expected_org=expected_org)
    if org == "UNKNOWN":
        # 파일명 기반 기관 힌트
        org, cert_country, org_hits = detect_org("", filename=filename, expected_org=expected_org)

    # 인증기관국가는 본문/LHLN DB/단일국가 fallback 순서로 보정한다.
    cert_country = resolve_cert_country(org, blob, cert_country)

    expiry, expiry_candidates = extract_expiry(text, filename, org)
    cert_no, cert_no_candidates = extract_cert_no(text, org)
    if org == "HFQ":
        hfq_match = (
            re.search(
                r"\b(HFQ\s*-\s*\d{1,6}\s*/\s*\d{1,4}\s*/\s*[A-Z]{2,10})\b",
                text,
                re.I,
            )
            or re.search(
                r"WITH\s+CERTIFICATE\s+NUMBER\s*[:：]?\s*(HFQ\s*-\s*\d{1,6}\s*/\s*\d{1,4}\s*/\s*[A-Z]{2,10})\b",
                text,
                re.I,
            )
            or re.search(
                r"CON\s+N[ºO]\s+DE\s+CERTIFICADO\s*[:：]?\s*(HFQ\s*-\s*\d{1,6}\s*/\s*\d{1,4}\s*/\s*[A-Z]{2,10})\b",
                text,
                re.I,
            )
        )

        cert_no = re.sub(r"\s+", "", hfq_match.group(1).upper()) if hfq_match else ""
        cert_no_candidates = [cert_no] if cert_no else []
    maker = normalize_manufacturer_output(extract_manufacturer(text, org), org)
    manufacturing_country = extract_manufacturing_country(text, org)
    products = finalize_product_candidates(extract_products(text, org))
    product_match = best_product_match(products, expected_name=expected_name, filename=filename)

    # IFANCA는 제품 row의 HC 번호가 있으면 우선 적용
    if org == "IFANCA" and product_match.get("product") and product_match["score"] >= 0.72:
        row_cert = product_match["product"].get("cert_no")
        if row_cert:
            cert_no = row_cert

    has_text = bool(text.strip())
    if not has_text:
        parse_status = "SCANNED_NEED_OCR"
        confidence = "LOW"
    elif org == "BPJPH":
        parse_status = "BPJPH_MAINTENANCE_ONLY"
        confidence = "MEDIUM" if cert_no or products else "LOW"
    elif org in {"HFFIA"} and expiry_candidates and expiry_candidates[0].get("source") == "FILENAME":
        parse_status = "FILENAME_ONLY"
        confidence = "LOW"
    elif org != "UNKNOWN" and expiry and (cert_no or products or maker):
        if products and product_match.get("score", 0) >= 0.72:
            parse_status = "RULE_MATCHED"
            confidence = "HIGH"
        else:
            parse_status = "LOW_CONFIDENCE"
            confidence = "MEDIUM"
    elif org != "UNKNOWN" and (expiry or cert_no):
        parse_status = "LOW_CONFIDENCE"
        confidence = "MEDIUM"
    else:
        parse_status = "MANUAL_REVIEW"
        confidence = "LOW"

    result = {
        "ok": parse_status in {"RULE_MATCHED", "LOW_CONFIDENCE", "BPJPH_MAINTENANCE_ONLY", "FILENAME_ONLY"},
        "parse_status": parse_status,
        "cert_org": org,
        "cert_country": cert_country,
        "org_hits": org_hits,
        "cert_no": cert_no,
        "cert_no_candidates": cert_no_candidates[:20],
        "expiry_date": expiry,
        "expiry_candidates": expiry_candidates[:10],
        "manufacturer": maker,
        "manufacturing_country": manufacturing_country,
        "country_match_status": country_match(manufacturing_country, cert_country),
        "products_count": len(products),
        "product_candidates": products[:80],
        "best_product_match": product_match,
        "source_rule": f"{org}_RULE" if org != "UNKNOWN" else "UNKNOWN_RULE",
        "confidence": confidence,
        "has_text": has_text,
        "text_length": len(text),
    }

    overridden = apply_certificate_rule_overrides(result, text, filename)

    from app.services.certificate_rule_profile_service import (
        finalize_certificate_rule_profile,
    )

    return finalize_certificate_rule_profile(
        overridden,
        raw_text=text,
        filename=filename,
    )


def guess_certificate_fields(raw_text: str, filename: str = "") -> dict[str, Any]:
    parsed = parse_certificate_rule(raw_text=raw_text, filename=filename)
    return {
        "org_candidates": [parsed.get("cert_org")] if parsed.get("cert_org") and parsed.get("cert_org") != "UNKNOWN" else [],
        "has_text": parsed.get("has_text", bool((raw_text or "").strip())),
        "text_length": parsed.get("text_length", len(raw_text or "")),
        "certificate_rule": parsed,
    }
