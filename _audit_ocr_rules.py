from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


EXPORT_DIR = Path("backend/data/ocr_exports")
EXPORT_PATTERN = "tesseract_rerun_batch_*.json"

ORG_ALIASES = {
    "JAKIM": ["JAKIM"],
    "MUIS": ["MUIS"],
    "HFFIA": ["HFFIA"],
    "HFCE": ["HFCE"],
    "TQHCC": ["TQHCC"],
    "HALAL CONTROL": [
        "HALAL CONTROL",
        "HALALCONTROL",
    ],
    "JMA": ["JMA"],
    "BPJPH": ["BPJPH"],
    "IFANCA": ["IFANCA"],
    "CICOT": ["CICOT"],
}

DATE_PATTERN = re.compile(
    r"(?<!\d)"
    r"(20\d{2})[-_.](0[1-9]|1[0-2])"
    r"[-_.](0[1-9]|[12]\d|3[01])"
    r"(?!\d)"
)


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_org(value: Any) -> str:
    text = normalize_text(value).upper()
    compact = re.sub(r"[^A-Z0-9]", "", text)

    for standard, aliases in ORG_ALIASES.items():
        for alias in aliases:
            alias_compact = re.sub(
                r"[^A-Z0-9]",
                "",
                alias.upper(),
            )
            if compact == alias_compact:
                return standard

    return text


def expected_org_from_filename(
    filename: str,
) -> str:
    upper_name = filename.upper()
    compact_name = re.sub(
        r"[^A-Z0-9]",
        "",
        upper_name,
    )

    candidates: list[
        tuple[int, str]
    ] = []

    for standard, aliases in ORG_ALIASES.items():
        for alias in aliases:
            alias_compact = re.sub(
                r"[^A-Z0-9]",
                "",
                alias.upper(),
            )

            if alias_compact in compact_name:
                candidates.append(
                    (
                        len(alias_compact),
                        standard,
                    )
                )

    if not candidates:
        return ""

    candidates.sort(reverse=True)
    return candidates[0][1]


def expected_date_from_filename(
    filename: str,
) -> str:
    matches = list(
        DATE_PATTERN.finditer(filename)
    )

    if not matches:
        return ""

    match = matches[-1]

    return (
        f"{match.group(1)}-"
        f"{match.group(2)}-"
        f"{match.group(3)}"
    )


def load_latest_results() -> list[dict[str, Any]]:
    files = sorted(
        EXPORT_DIR.glob(EXPORT_PATTERN),
        key=lambda path: path.stat().st_mtime,
    )

    if not files:
        raise FileNotFoundError(
            "재처리 결과 JSON을 찾지 못했습니다: "
            f"{EXPORT_DIR / EXPORT_PATTERN}"
        )

    latest_by_source: dict[
        str,
        dict[str, Any],
    ] = {}

    for path in files:
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )

        for result in payload.get(
            "results",
            [],
        ):
            source_path = normalize_text(
                result.get("source_path")
            )

            filename = normalize_text(
                result.get("filename")
            )

            key = (
                source_path.lower()
                if source_path
                else filename.lower()
            )

            current = dict(result)
            current["_export_file"] = str(path)
            current["_export_mtime"] = (
                path.stat().st_mtime
            )

            previous = latest_by_source.get(key)

            if previous is None:
                latest_by_source[key] = current
                continue

            current_job_id = int(
                current.get("new_job_id") or 0
            )

            previous_job_id = int(
                previous.get("new_job_id") or 0
            )

            if current_job_id >= previous_job_id:
                latest_by_source[key] = current

    return list(latest_by_source.values())


def audit_result(
    result: dict[str, Any],
) -> dict[str, Any]:
    filename = normalize_text(
        result.get("filename")
    )

    status = normalize_text(
        result.get("new_status")
    ).upper()

    parse_status = normalize_text(
        result.get("parse_status")
    ).upper()

    cert_org = normalize_org(
        result.get("cert_org")
    )

    expected_org = expected_org_from_filename(
        filename
    )

    expiry_date = normalize_text(
        result.get("expiry_date")
    )

    expected_expiry = (
        expected_date_from_filename(filename)
    )

    cert_no = normalize_text(
        result.get("cert_no")
    )

    manufacturer = normalize_text(
        result.get("manufacturer")
    )

    quality_flags = [
        normalize_text(flag)
        for flag in (
            result.get("quality_flags")
            or []
        )
        if normalize_text(flag)
    ]

    blocking_flags = [
        normalize_text(flag)
        for flag in (
            result.get(
                "blocking_quality_flags"
            )
            or []
        )
        if normalize_text(flag)
    ]

    hard_issues: list[str] = []
    review_issues: list[str] = []

    if status != "DONE":
        hard_issues.append(
            f"STATUS_{status or 'EMPTY'}"
        )

    if not cert_org:
        hard_issues.append("CERT_ORG_MISSING")

    if not cert_no:
        hard_issues.append("CERT_NO_MISSING")

    if not expiry_date:
        hard_issues.append("EXPIRY_MISSING")

    if not manufacturer:
        hard_issues.append(
            "MANUFACTURER_MISSING"
        )

    if expected_org and cert_org:
        if expected_org != cert_org:
            hard_issues.append("ORG_MISMATCH")

    if expected_expiry and expiry_date:
        if expected_expiry != expiry_date:
            hard_issues.append(
                "EXPIRY_MISMATCH"
            )

    if manufacturer.startswith("@"):
        hard_issues.append(
            "MANUFACTURER_SUSPICIOUS"
        )

    for flag in blocking_flags:
        if flag not in hard_issues:
            hard_issues.append(flag)

    if parse_status == "FILENAME_ONLY":
        review_issues.append("FILENAME_ONLY")

    elif parse_status == "LOW_CONFIDENCE":
        review_issues.append("LOW_CONFIDENCE")

    elif not parse_status:
        review_issues.append(
            "PARSE_STATUS_MISSING"
        )

    for flag in quality_flags:
        if (
            flag not in hard_issues
            and flag not in review_issues
        ):
            review_issues.append(flag)

    if hard_issues:
        audit_status = "BLOCKED"
    elif review_issues:
        audit_status = "CONDITIONAL_PASS"
    else:
        audit_status = "PASS"

    return {
        "old_job_id": result.get(
            "old_job_id"
        ),
        "new_job_id": result.get(
            "new_job_id"
        ),
        "filename": filename,
        "source_path": normalize_text(
            result.get("source_path")
        ),
        "ocr_status": status,
        "parse_status": parse_status,
        "cert_org": cert_org,
        "expected_org": expected_org,
        "cert_no": cert_no,
        "expiry_date": expiry_date,
        "expected_expiry": expected_expiry,
        "manufacturer": manufacturer,
        "quality_flags": "|".join(
            quality_flags
        ),
        "blocking_quality_flags": "|".join(
            blocking_flags
        ),
        "hard_issues": "|".join(
            hard_issues
        ),
        "review_issues": "|".join(
            review_issues
        ),
        "audit_status": audit_status,
        "ready_for_classification": (
            audit_status != "BLOCKED"
        ),
        "export_file": result.get(
            "_export_file"
        ),
    }


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0].keys()),
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    results = load_latest_results()

    audited = [
        audit_result(result)
        for result in results
    ]

    audited.sort(
        key=lambda row: (
            row["audit_status"],
            row["filename"],
        )
    )

    status_counts = Counter(
        row["audit_status"]
        for row in audited
    )

    parse_counts = Counter(
        row["parse_status"] or "EMPTY"
        for row in audited
    )

    hard_issue_counts: Counter[str] = Counter()
    review_issue_counts: Counter[str] = Counter()

    for row in audited:
        for issue in str(
            row["hard_issues"]
        ).split("|"):
            if issue:
                hard_issue_counts[issue] += 1

        for issue in str(
            row["review_issues"]
        ).split("|"):
            if issue:
                review_issue_counts[issue] += 1

    duplicate_cert_numbers: dict[
        str,
        list[str],
    ] = defaultdict(list)

    for row in audited:
        cert_no = normalize_text(
            row["cert_no"]
        )

        if cert_no:
            duplicate_cert_numbers[
                cert_no
            ].append(row["filename"])

    duplicate_cert_numbers = {
        cert_no: filenames
        for cert_no, filenames
        in duplicate_cert_numbers.items()
        if len(filenames) > 1
    }

    ready_rows = [
        row
        for row in audited
        if row["ready_for_classification"]
    ]

    blocked_rows = [
        row
        for row in audited
        if not row[
            "ready_for_classification"
        ]
    ]

    now = datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M%S")

    audit_csv = EXPORT_DIR / (
        f"ocr_rule_audit_{stamp}.csv"
    )

    ready_csv = EXPORT_DIR / (
        f"classification_ready_{stamp}.csv"
    )

    blocked_csv = EXPORT_DIR / (
        f"ocr_manual_review_{stamp}.csv"
    )

    summary_json = EXPORT_DIR / (
        f"ocr_rule_audit_{stamp}.json"
    )

    write_csv(audit_csv, audited)
    write_csv(ready_csv, ready_rows)
    write_csv(blocked_csv, blocked_rows)

    total = len(audited)
    blocked_count = len(blocked_rows)

    mismatch_count = (
        hard_issue_counts.get(
            "ORG_MISMATCH",
            0,
        )
        + hard_issue_counts.get(
            "EXPIRY_MISMATCH",
            0,
        )
    )

    mismatch_rate = (
        mismatch_count / total
        if total
        else 1.0
    )

    if total == 0:
        next_step_gate = "NO_DATA"

    elif mismatch_rate > 0.10:
        next_step_gate = (
            "FIX_OCR_RULES_FIRST"
        )

    else:
        next_step_gate = (
            "GO_CLASSIFICATION_DRY_RUN"
        )

    summary = {
        "created_at": now.isoformat(
            timespec="seconds"
        ),
        "total_latest_results": total,
        "audit_status_counts": dict(
            status_counts
        ),
        "parse_status_counts": dict(
            parse_counts
        ),
        "hard_issue_counts": dict(
            hard_issue_counts
        ),
        "review_issue_counts": dict(
            review_issue_counts
        ),
        "ready_for_classification": (
            len(ready_rows)
        ),
        "blocked_for_manual_review": (
            blocked_count
        ),
        "rule_mismatch_count": (
            mismatch_count
        ),
        "rule_mismatch_rate": round(
            mismatch_rate,
            4,
        ),
        "duplicate_cert_numbers": (
            duplicate_cert_numbers
        ),
        "next_step_gate": next_step_gate,
        "files": {
            "audit_csv": str(audit_csv),
            "classification_ready_csv": (
                str(ready_csv)
            ),
            "manual_review_csv": str(
                blocked_csv
            ),
        },
    }

    summary_json.write_text(
        json.dumps(
            {
                "summary": summary,
                "results": audited,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print()
    print("TOTAL_LATEST_RESULTS:", total)
    print(
        "AUDIT_STATUS_COUNTS:",
        dict(status_counts),
    )
    print(
        "PARSE_STATUS_COUNTS:",
        dict(parse_counts),
    )
    print(
        "HARD_ISSUE_COUNTS:",
        dict(hard_issue_counts),
    )
    print(
        "REVIEW_ISSUE_COUNTS:",
        dict(review_issue_counts),
    )
    print(
        "READY_FOR_CLASSIFICATION:",
        len(ready_rows),
    )
    print(
        "BLOCKED_FOR_MANUAL_REVIEW:",
        blocked_count,
    )
    print(
        "RULE_MISMATCH_RATE:",
        f"{mismatch_rate:.1%}",
    )
    print(
        "NEXT_STEP_GATE:",
        next_step_gate,
    )
    print("AUDIT_CSV:", audit_csv)
    print("READY_CSV:", ready_csv)
    print("MANUAL_REVIEW_CSV:", blocked_csv)
    print("SUMMARY_JSON:", summary_json)
    print("OCR_RULE_AUDIT_OK")


if __name__ == "__main__":
    main()
