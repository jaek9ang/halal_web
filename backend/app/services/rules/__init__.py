"""인증서 판독 규칙.

원래 certificate_rule_service.py 한 파일(2,749줄)이었다. 계층별로 나눴고,
기존 import 경로(app.services.certificate_rule_service)는 그대로 동작한다.

의존 방향은 한 방향이다:
    text -> dates -> organizations -> companies -> products -> overrides -> core -> context
"""

from __future__ import annotations

from app.services.rules.text import (
    clean_ocr_text,
    lines_of,
    norm_key,
    normalize_ocr_digits,
    similarity,
    upper_text,
)
from app.services.rules.dates import (
    MONTHS,
    extract_cicot_expiry_date,
    extract_date_after,
    extract_latest_date_near_anchors,
    extract_mui_valid_until_date,
    extract_muis_expiry_date,
    find_dates,
    is_ignored_date_context,
    iso_date,
    normalize_date_ocr_text,
    parse_date_text,
    two_digit_year,
)
from app.services.rules.organizations import (
    BACKEND_DIR,
    COUNTRY_WORDS,
    FIXED_SINGLE_COUNTRY_ORG,
    LHLN_DB_PATH,
    ORG_ALIASES,
    REGION_COUNTRY_HINTS,
    detect_org,
    extract_country_from_parentheses,
    extract_country_from_text,
    infer_org_country,
    resolve_cert_country,
)
from app.services.rules.companies import (
    clean_company_value,
    extract_after_label,
    extract_company_after_marker,
    extract_inline_label_value,
    extract_manufacturer,
    extract_manufacturing_country,
    is_admin_or_address_line,
    is_bad_manufacturer_candidate,
    is_company_like,
    is_halal_control_noise_line,
    looks_like_company_name_for_halal_control,
    normalize_manufacturer_output,
    split_company_country_suffix,
    strip_address_from_company,
    strip_inline_address_tail,
)
from app.services.rules.products import (
    best_product_match,
    extract_products,
    finalize_product_candidates,
    looks_like_product_noise,
    split_pages,
)
from app.services.rules.overrides import (
    apply_certificate_rule_overrides,
)
from app.services.rules.core import (
    country_match,
    extract_cert_no,
    extract_expiry,
    guess_certificate_fields,
    is_non_certificate_document,
    parse_certificate_rule,
)
from app.services.rules.context import (
    parse_certificate_rule_with_context,
    reconcile_certificate_rule_with_context,
)

__all__ = [
    "BACKEND_DIR",
    "COUNTRY_WORDS",
    "FIXED_SINGLE_COUNTRY_ORG",
    "LHLN_DB_PATH",
    "MONTHS",
    "ORG_ALIASES",
    "REGION_COUNTRY_HINTS",
    "apply_certificate_rule_overrides",
    "best_product_match",
    "clean_company_value",
    "clean_ocr_text",
    "country_match",
    "detect_org",
    "extract_after_label",
    "extract_cert_no",
    "extract_cicot_expiry_date",
    "extract_company_after_marker",
    "extract_country_from_parentheses",
    "extract_country_from_text",
    "extract_date_after",
    "extract_expiry",
    "extract_inline_label_value",
    "extract_latest_date_near_anchors",
    "extract_manufacturer",
    "extract_manufacturing_country",
    "extract_mui_valid_until_date",
    "extract_muis_expiry_date",
    "extract_products",
    "finalize_product_candidates",
    "find_dates",
    "guess_certificate_fields",
    "infer_org_country",
    "is_admin_or_address_line",
    "is_bad_manufacturer_candidate",
    "is_company_like",
    "is_halal_control_noise_line",
    "is_ignored_date_context",
    "is_non_certificate_document",
    "iso_date",
    "lines_of",
    "looks_like_company_name_for_halal_control",
    "looks_like_product_noise",
    "norm_key",
    "normalize_date_ocr_text",
    "normalize_manufacturer_output",
    "normalize_ocr_digits",
    "parse_certificate_rule",
    "parse_certificate_rule_with_context",
    "parse_date_text",
    "reconcile_certificate_rule_with_context",
    "resolve_cert_country",
    "similarity",
    "split_company_country_suffix",
    "split_pages",
    "strip_address_from_company",
    "strip_inline_address_tail",
    "two_digit_year",
    "upper_text",
]
