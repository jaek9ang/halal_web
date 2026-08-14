from __future__ import annotations

import csv
import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.rule_candidate_service import (
    RULE_VALIDATION_REPORT_DIR,
    get_rule_candidate,
    update_rule_candidate_status,
)

VALIDATION_SCHEMA_VERSION = "ai_rule_validation_report_v1"
AUTO_APPLY_ALLOWED_RISK_LEVELS = {"LOW", "MEDIUM"}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def make_validation_report_id(rule_candidate_id: str) -> str:
    suffix = re.sub(r"[^A-Za-z0-9_]+", "_", str(rule_candidate_id or "RULE")).strip("_")
    return f"VR_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{suffix[:80]}"


def get_default_export_jsonl_path() -> Path:
    backend_root = Path(__file__).resolve().parents[2]
    candidates = [
        backend_root / "data" / "ocr_exports" / "export.jsonl",
        backend_root / "data" / "export.jsonl",
        backend_root / "export.jsonl",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def read_export_jsonl(export_path: str | Path | None = None, limit: int = 10000) -> list[dict[str, Any]]:
    path = Path(export_path) if export_path else get_default_export_jsonl_path()
    if not path.exists():
        raise FileNotFoundError(f"export.jsonl 파일을 찾을 수 없습니다: {path}")

    rows: list[dict[str, Any]] = []
    limit = max(1, min(int(limit), 100000))
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if len(rows) >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def clean_text(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def upper_text(value: str) -> str:
    return clean_text(value).upper()


MONTH_MAP = {
    "JANUARY": 1, "JAN": 1,
    "FEBRUARY": 2, "FEB": 2,
    "MARCH": 3, "MAR": 3, "MAC": 3,
    "APRIL": 4, "APR": 4,
    "MAY": 5, "MEI": 5,
    "JUNE": 6, "JUN": 6,
    "JULY": 7, "JUL": 7,
    "AUGUST": 8, "AUG": 8,
    "SEPTEMBER": 9, "SEPT": 9, "SEP": 9,
    "OCTOBER": 10, "OCT": 10, "OKTOBER": 10,
    "NOVEMBER": 11, "NOV": 11,
    "DECEMBER": 12, "DEC": 12, "DISEMBER": 12,
}


def normalize_date_ocr_text(value: str) -> str:
    s = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    months = "|".join(MONTH_MAP.keys())
    s = re.sub(rf"\b({months})\s+(\d{{1,2}})\s*\n\s*(ST|ND|RD|TH|RH)\s*,?\s*(20\d{{2}})\b", r"\1 \2\3, \4", s, flags=re.I)
    s = re.sub(rf"\b({months})\s+(\d{{1,2}})[°º]\s*,?\s*(20\d{{2}})\b", r"\1 \2TH, \3", s, flags=re.I)
    s = re.sub(rf"\b(\d{{1,2}})[°º]\s+({months})\s*,?\s*(20\d{{2}})\b", r"\1TH \2 \3", s, flags=re.I)
    return s


def parse_date_text(value: str) -> str:
    raw = normalize_date_ocr_text(clean_text(value))
    raw = re.sub(r"(\d{1,2})(ST|ND|RD|TH|RH)\b", r"\1", raw, flags=re.I)

    m = re.search(r"\b(20\d{2})[-./](\d{1,2})[-./](\d{1,2})\b", raw)
    if m:
        y, mo, d = map(int, m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}"

    m = re.search(r"\b(\d{1,2})[-./](\d{1,2})[-./](20\d{2})\b", raw)
    if m:
        d, mo, y = map(int, m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}"

    m = re.search(r"\b([A-Za-z]+)\s+(\d{1,2})\s*,?\s*(20\d{2})\b", raw, re.I)
    if m:
        mon = MONTH_MAP.get(m.group(1).upper())
        if mon:
            return f"{int(m.group(3)):04d}-{mon:02d}-{int(m.group(2)):02d}"

    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]+)\s*,?\s*(20\d{2})\b", raw, re.I)
    if m:
        mon = MONTH_MAP.get(m.group(2).upper())
        if mon:
            return f"{int(m.group(3)):04d}-{mon:02d}-{int(m.group(1)):02d}"

    m = re.search(r"\b(\d{2})[.](\d{1,2})[.](\d{1,2})\b", raw)
    if m:
        yy, mo, d = map(int, m.groups())
        return f"{2000 + yy:04d}-{mo:02d}-{d:02d}"

    return ""


def find_dates(text: str) -> list[dict[str, str]]:
    src = normalize_date_ocr_text(text)
    patterns = [
        r"\b20\d{2}[-./]\d{1,2}[-./]\d{1,2}\b",
        r"\b\d{1,2}[-./]\d{1,2}[-./]20\d{2}\b",
        r"\b[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th|rh|TH)?\s*,?\s*20\d{2}\b",
        r"\b\d{1,2}(?:st|nd|rd|th|rh)?\s+[A-Za-z]+\s*,?\s*20\d{2}\b",
        r"\b\d{2}[.]\d{1,2}[.]\d{1,2}\b",
    ]
    seen = set()
    rows = []
    for pat in patterns:
        for m in re.finditer(pat, src, re.I):
            raw = m.group(0)
            date = parse_date_text(raw)
            if not date:
                continue
            key = (date, raw)
            if key in seen:
                continue
            seen.add(key)
            rows.append({"date": date, "raw": raw})
    return rows


def extract_date_after_anchors(text: str, anchors: list[str], stop_before: list[str] | None = None, window: int = 650) -> tuple[str, str]:
    src = normalize_date_ocr_text(text)
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
                return dates[0]["date"], dates[0]["raw"]
            start = idx + len(anchor_u)
    return "", ""


def strip_inline_address_tail(value: str) -> str:
    text = clean_text(value)
    text = re.sub(
        r"\s+\d{1,6}\s+(?:[A-Z0-9'.#-]+\s+){0,6}(?:STREET|ST\.?|AVENUE|AVE\.?|ROAD|RD\.?|DRIVE|DR\.?|LANE|LN\.?|BOULEVARD|BLVD\.?|WAY|COURT|CT\.?|LOOP|PARKWAY|PKWY\.?)\b.*$",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\s+(?:NO\.?\s*)?\d{1,6}[, ]+.*$", "", text, flags=re.I)
    return clean_text(text).strip(" ,.-")


def cleanup_manufacturer(value: str) -> str:
    text = clean_text(value)
    text = re.sub(r"^(Company\s+Name\s*&\s*Address|Company\s+Name|Name\s+of\s+Company|Company|Manufacturer|Manufactured\s+by|For)\s*[:：]\s*", "", text, flags=re.I)
    return strip_inline_address_tail(text).strip(" ,.-")


def get_certificate_rule(record: dict[str, Any]) -> dict[str, Any]:
    rule = record.get("certificate_rule") or record.get("certificate_rule_current") or {}
    return rule if isinstance(rule, dict) else {}


def get_record_filename(record: dict[str, Any]) -> str:
    return str(record.get("filename") or record.get("source_filename") or "")


def get_record_raw_text(record: dict[str, Any]) -> str:
    return str(record.get("raw_text") or "")


def field_value(rule: dict[str, Any], field: str) -> str:
    value = rule.get(field)
    if value is None:
        return ""
    return value.strip() if isinstance(value, str) else str(value)


def is_empty_value(value: Any) -> bool:
    return str(value or "").strip() in {"", "-"}

def is_target_org_wildcard(target_org: str) -> bool:
    value = str(target_org or "").upper().strip()
    return value in {"", "ALL", "ANY", "*"}


def is_target_org_matched(target_org: str, current_org: str) -> bool:
    target = str(target_org or "").upper().strip()
    current = str(current_org or "").upper().strip()

    if is_target_org_wildcard(target):
        return True

    return target == current

def apply_candidate_to_rule_result(record: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    rule_before = get_certificate_rule(record)
    rule_after = deepcopy(rule_before)
    target_org = str(candidate.get("target_org") or "").upper().strip()
    target_field = str(candidate.get("target_field") or "").strip()
    rule_kind = str(candidate.get("rule_kind") or "").strip()
    proposed_rule = candidate.get("proposed_rule") or {}
    current_org = str(rule_before.get("cert_org") or "").upper().strip()
    if not is_target_org_matched(target_org, current_org):
        return rule_after

    raw_text = get_record_raw_text(record)
    filename = get_record_filename(record)

    if rule_kind == "date_anchor_rule" and target_field:
        date, raw = extract_date_after_anchors(
            raw_text,
            anchors=proposed_rule.get("anchors") or [],
            stop_before=proposed_rule.get("stop_before") or [],
            window=int(proposed_rule.get("window") or 650),
        )
        if not date and proposed_rule.get("allow_filename_fallback"):
            dates = find_dates(filename)
            if dates:
                date, raw = dates[-1]["date"], dates[-1]["raw"]
        if date:
            rule_after[target_field] = date
            candidates_key = "expiry_candidates" if target_field == "expiry_date" else f"{target_field}_candidates"
            rule_after[candidates_key] = [{"date": date, "raw": raw, "source": f"AI_RULE:{candidate.get('rule_candidate_id', '')}"}]

    elif rule_kind == "manufacturer_cleanup_rule":
        source_field = proposed_rule.get("source_field") or target_field or "manufacturer"
        output_field = target_field or "manufacturer"
        after = cleanup_manufacturer(field_value(rule_before, source_field))
        if after:
            rule_after[output_field] = after

    elif rule_kind == "cert_no_pattern_rule" and target_field:
        for pat in proposed_rule.get("patterns") or []:
            try:
                m = re.search(pat, raw_text, re.I)
            except re.error:
                continue
            if m:
                value = m.group(1) if m.groups() else m.group(0)
                value = re.sub(r"\s+", "", value.strip())
                if value:
                    rule_after[target_field] = value
                    rule_after["cert_no_candidates"] = [value]
                    break

    elif rule_kind == "non_certificate_doc_rule":
        markers = [str(x or "").upper() for x in proposed_rule.get("markers") or []]
        haystack = upper_text("\n".join([filename, raw_text]))
        if markers and any(marker in haystack for marker in markers):
            rule_after.update({
                "ok": True,
                "parse_status": "NON_CERTIFICATE_DOC",
                "cert_org": "UNKNOWN",
                "cert_country": "",
                "cert_no": "",
                "expiry_date": "",
                "manufacturer": "",
                "manufacturing_country": "",
                "products_count": 0,
                "source_rule": "AI_NON_CERTIFICATE_DOC_RULE",
                "confidence": "HIGH",
            })
    return rule_after

def is_present_rule_value(value: Any) -> bool:
    text = str(value or "").strip()

    if not text:
        return False

    if text in {"-", "—"}:
        return False

    if text.upper() in {"UNKNOWN", "NONE", "NULL"}:
        return False

    return True


def get_required_recognition_fields(rule: dict[str, Any]) -> list[str]:
    org = str(rule.get("cert_org") or "").upper().strip()
    parse_status = str(rule.get("parse_status") or "").upper().strip()

    if parse_status == "NON_CERTIFICATE_DOC":
        return []

    fields = [
        "cert_org",
        "cert_country",
        "manufacturer",
        "manufacturing_country",
        "cert_no",
        "expiry_date",
    ]

    # BPJPH는 expiry가 없는 유지확인형 문서가 많으므로 필수 필드에서 제외
    if org == "BPJPH":
        fields.remove("expiry_date")

    return fields


def calculate_rule_field_score(rule: dict[str, Any]) -> dict[str, Any]:
    fields = get_required_recognition_fields(rule)

    if not fields:
        return {
            "required_count": 0,
            "filled_count": 0,
            "rate": 0.0,
            "filled_fields": [],
            "missing_fields": [],
        }

    filled_fields = [field for field in fields if is_present_rule_value(rule.get(field))]
    missing_fields = [field for field in fields if field not in filled_fields]

    rate = round((len(filled_fields) / len(fields)) * 100, 1)

    return {
        "required_count": len(fields),
        "filled_count": len(filled_fields),
        "rate": rate,
        "filled_fields": filled_fields,
        "missing_fields": missing_fields,
    }


def get_org_stat_key(rule: dict[str, Any]) -> str:
    org = str(rule.get("cert_org") or "").strip()

    if not org:
        return "UNKNOWN"

    return org


def update_org_stats(
    org_stats_map: dict[str, dict[str, Any]],
    before_rule: dict[str, Any],
    after_rule: dict[str, Any],
    decision: str,
) -> None:
    org = get_org_stat_key(before_rule)
    before_score = calculate_rule_field_score(before_rule)
    after_score = calculate_rule_field_score(after_rule)

    row = org_stats_map.setdefault(
        org,
        {
            "cert_org": org,
            "total_records": 0,
            "before_score_sum": 0.0,
            "after_score_sum": 0.0,
            "improved_count": 0,
            "regression_count": 0,
            "changed_review_count": 0,
            "manual_review_count": 0,
            "unchanged_count": 0,
        },
    )

    row["total_records"] += 1
    row["before_score_sum"] += float(before_score["rate"])
    row["after_score_sum"] += float(after_score["rate"])

    if decision == "IMPROVED":
        row["improved_count"] += 1
    elif decision == "REGRESSION":
        row["regression_count"] += 1
    elif decision == "CHANGED_REVIEW":
        row["changed_review_count"] += 1
    elif decision == "MANUAL_REVIEW":
        row["manual_review_count"] += 1
    else:
        row["unchanged_count"] += 1


def finalize_org_stats(org_stats_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []

    for org, row in org_stats_map.items():
        total = max(1, int(row.get("total_records") or 0))
        before_rate = round(float(row.get("before_score_sum") or 0.0) / total, 1)
        after_rate = round(float(row.get("after_score_sum") or 0.0) / total, 1)

        rows.append({
            "cert_org": org,
            "total_records": row.get("total_records") or 0,
            "before_rate": before_rate,
            "after_rate": after_rate,
            "delta_rate": round(after_rate - before_rate, 1),
            "improved_count": row.get("improved_count") or 0,
            "regression_count": row.get("regression_count") or 0,
            "changed_review_count": row.get("changed_review_count") or 0,
            "manual_review_count": row.get("manual_review_count") or 0,
            "unchanged_count": row.get("unchanged_count") or 0,
        })

    return sorted(
        rows,
        key=lambda x: (x["delta_rate"], x["improved_count"], x["total_records"]),
        reverse=True,
    )

def classify_field_change(field: str, before_value: str, after_value: str, expected_values: set[str] | None = None) -> str:
    before = str(before_value or "").strip()
    after = str(after_value or "").strip()
    expected_values = expected_values or set()
    if before == after:
        return "UNCHANGED"
    if expected_values and after in expected_values:
        return "IMPROVED"
    if is_empty_value(before) and not is_empty_value(after):
        return "IMPROVED"
    if not is_empty_value(before) and is_empty_value(after):
        return "REGRESSION"
    if field == "expiry_date" and re.match(r"^\d{4}-\d{2}-\d{2}$", before) and re.match(r"^\d{4}-\d{2}-\d{2}$", after):
        if after < before:
            return "REGRESSION"
        if after > before:
            return "CHANGED_REVIEW"
    if field in {"cert_org", "cert_country"}:
        return "MANUAL_REVIEW"
    return "CHANGED_REVIEW"


def build_expected_values(candidate: dict[str, Any]) -> dict[str, set[str]]:
    expected_by_filename_keyword: dict[str, set[str]] = {}
    for case in candidate.get("expected_cases") or []:
        if not isinstance(case, dict):
            continue
        keyword = str(case.get("filename_keyword") or "").strip()
        expected_value = str(case.get("expected_value") or case.get("expected_expiry_date") or "").strip()
        if keyword and expected_value:
            expected_by_filename_keyword.setdefault(keyword, set()).add(expected_value)
    return expected_by_filename_keyword


def validate_rule_candidate(rule_candidate_id: str, export_path: str | Path | None = None, limit: int = 10000, save_report: bool = True) -> dict[str, Any]:
    candidate = get_rule_candidate(rule_candidate_id)
    if not candidate:
        raise ValueError(f"rule_candidate_id를 찾을 수 없습니다: {rule_candidate_id}")
    records = read_export_jsonl(export_path, limit=limit)
    target_field = str(candidate.get("target_field") or "").strip()
    if not target_field:
        raise ValueError("candidate.target_field가 비어 있습니다.")

    report_id = make_validation_report_id(rule_candidate_id)
    expected_by_keyword = build_expected_values(candidate)

    rows = []
    org_stats_map: dict[str, dict[str, Any]] = {}

    impacted_count = 0
    improved_count = 0
    unchanged_count = 0
    regression_count = 0
    changed_review_count = 0
    manual_review_count = 0

    for record in records:
        before_rule = get_certificate_rule(record)
        after_rule = apply_candidate_to_rule_result(record, candidate)
        before_value = field_value(before_rule, target_field)
        after_value = field_value(after_rule, target_field)
        filename = get_record_filename(record)
        expected_values = set()
        for keyword, values in expected_by_keyword.items():
            if keyword and keyword in filename:
                expected_values |= values
        decision = classify_field_change(
            target_field,
            before_value,
            after_value,
            expected_values=expected_values,
        )

        update_org_stats(
            org_stats_map,
            before_rule=before_rule,
            after_rule=after_rule,
            decision=decision,
        )

        if decision == "UNCHANGED":
            unchanged_count += 1
            continue
        impacted_count += 1
        if decision == "IMPROVED":
            improved_count += 1
        elif decision == "REGRESSION":
            regression_count += 1
        elif decision == "MANUAL_REVIEW":
            manual_review_count += 1
        else:
            changed_review_count += 1
        rows.append({
            "filename": filename,
            "source_type": record.get("source_type") or "",
            "source_id": record.get("source_id") or "",
            "ocr_job_id": record.get("ocr_job_id") or record.get("source_id") or "",
            "cert_org": before_rule.get("cert_org") or "",
            "field": target_field,
            "before_value": before_value,
            "after_value": after_value,
            "decision": decision,
            "parse_status_before": before_rule.get("parse_status") or "",
            "parse_status_after": after_rule.get("parse_status") or before_rule.get("parse_status") or "",
        })

    risk_level = str(candidate.get("risk_level") or "MEDIUM").upper()
    rule_kind = str(candidate.get("rule_kind") or "")
    candidate_target_org = str(candidate.get("target_org") or "").upper().strip()

    auto_apply_allowed = (
        regression_count == 0
        and improved_count > 0
        and risk_level in AUTO_APPLY_ALLOWED_RISK_LEVELS
        and target_field not in {"cert_org", "cert_country"}
        and rule_kind != "global_fallback_rule"
        and not is_target_org_wildcard(candidate_target_org)
    )
    org_stats = finalize_org_stats(org_stats_map)

    before_rate = 0.0
    after_rate = 0.0

    if org_stats:
        total_records_for_rate = sum(row["total_records"] for row in org_stats) or 1
        before_rate = round(
            sum(row["before_rate"] * row["total_records"] for row in org_stats) / total_records_for_rate,
            1,
        )
        after_rate = round(
            sum(row["after_rate"] * row["total_records"] for row in org_stats) / total_records_for_rate,
            1,
        )

    summary = {
        "total_records": len(records),
        "impacted_count": impacted_count,
        "improved_count": improved_count,
        "unchanged_count": unchanged_count,
        "regression_count": regression_count,
        "changed_review_count": changed_review_count,
        "manual_review_count": manual_review_count,
        "auto_apply_allowed": auto_apply_allowed,
        "before_recognition_rate": before_rate,
        "after_recognition_rate": after_rate,
        "delta_recognition_rate": round(after_rate - before_rate, 1),
    }
    report = {
        "ok": True,
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "validation_report_id": report_id,
        "rule_candidate_id": rule_candidate_id,
        "created_at": now_iso(),
        "export_path": str(export_path or get_default_export_jsonl_path()),
        "candidate": candidate,
        "summary": summary,
        "org_stats": org_stats,
        "rows": rows,
    }
    if save_report:
        save_validation_report(report)
        update_rule_candidate_status(rule_candidate_id, "VALIDATED", validation_report_id=report_id, validation_summary=summary)
    return report


def save_validation_report(report: dict[str, Any]) -> None:
    RULE_VALIDATION_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_id = report["validation_report_id"]
    json_path = RULE_VALIDATION_REPORT_DIR / f"{report_id}.json"
    csv_path = RULE_VALIDATION_REPORT_DIR / f"{report_id}.csv"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        fieldnames = ["filename", "source_type", "source_id", "ocr_job_id", "cert_org", "field", "before_value", "after_value", "decision", "parse_status_before", "parse_status_after"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.get("rows") or []:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def get_validation_report(validation_report_id: str) -> dict[str, Any]:
    report_id = str(validation_report_id or "").strip()
    path = RULE_VALIDATION_REPORT_DIR / f"{report_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"validation_report_id를 찾을 수 없습니다: {report_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_validation_reports(limit: int = 100) -> dict[str, Any]:
    RULE_VALIDATION_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    limit = max(1, min(int(limit), 500))
    paths = sorted(RULE_VALIDATION_REPORT_DIR.glob("VR_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    rows = []
    for path in paths[:limit]:
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append({
            "validation_report_id": report.get("validation_report_id"),
            "rule_candidate_id": report.get("rule_candidate_id"),
            "created_at": report.get("created_at"),
            "summary": report.get("summary") or {},
            "path": str(path),
        })
    return {"ok": True, "limit": limit, "rows": rows, "total": len(paths)}
