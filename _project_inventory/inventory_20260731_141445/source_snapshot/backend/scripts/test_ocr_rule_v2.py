from __future__ import annotations

import argparse
import ast
import json
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.certificate_rule_service import (
    parse_certificate_rule,
    parse_certificate_rule_with_context,
)
from app.services.ocr_context_service import assemble_ocr_context


def load_records(bundle_path: Path) -> list[dict[str, Any]]:
    if not bundle_path.exists():
        raise FileNotFoundError(bundle_path)

    if bundle_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(bundle_path, "r") as archive:
            name = next(
                (item for item in archive.namelist() if item.endswith("export.jsonl")),
                None,
            )
            if not name:
                raise RuntimeError("ZIP 안에서 export.jsonl을 찾지 못했습니다.")
            text = archive.read(name).decode("utf-8-sig")
    else:
        text = bundle_path.read_text(encoding="utf-8-sig")

    return [json.loads(line) for line in text.splitlines() if line.strip()]


def unique_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for record in records:
        key = (record.get("filename"), record.get("raw_text"))
        if key in seen:
            continue
        seen.add(key)
        output.append(record)
    return output


def find_job(records: list[dict[str, Any]], job_id: int) -> dict[str, Any]:
    for record in records:
        if int(record.get("ocr_job_id") or -1) == job_id:
            return record
    raise AssertionError(f"OCR Job {job_id}를 export.jsonl에서 찾지 못했습니다.")


def assert_field(result: dict[str, Any], field: str, expected: Any, label: str) -> None:
    actual = result.get(field)
    if actual != expected:
        raise AssertionError(f"{label}: {field} expected={expected!r}, actual={actual!r}")


def test_targeted_regressions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases = {
        509: {"cert_no": "ARA-504254310625-1", "expiry_date": "2028-05-17"},
        499: {"cert_no": "JUHF-0409-0240", "expiry_date": "2028-04-04"},
        438: {"expiry_date": "2029-05-15"},
        429: {"cert_no": "284-TSRU/24"},
        227: {"expiry_date": "2025-10-14"},
    }
    report = []
    for job_id, expected_fields in cases.items():
        record = find_job(records, job_id)
        result = parse_certificate_rule(record.get("raw_text", ""), record.get("filename", ""))
        for field, expected in expected_fields.items():
            assert_field(result, field, expected, f"OCR Job {job_id}")
        report.append({
            "ocr_job_id": job_id,
            "filename": record.get("filename"),
            "passed": True,
            "checked": expected_fields,
        })
    return report


def test_context_assist(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    report = []

    # 정상 연결: 메일/PMF 표준 제조사와 제품명이 OCR 원문에서 확인된다.
    record = find_job(records, 515)
    result = parse_certificate_rule_with_context(
        record.get("raw_text", ""),
        record.get("filename", ""),
        {
            "reliability": "HIGH",
            "selection_reason": "ATTACHMENT_INDEX",
            "request_id": "HALAL-REQ-TEST",
            "item_index": 1,
            "org": "IFANCA",
            "english_name": "Beef Type Flavour",
            "material_name": "Beef Type Flavour",
            "maker": "Givaudan Flavors Corporation",
            "maker_country": "USA",
            "cert_no": "HC-OLD",
            "current_expiry": "2026-05-31",
        },
    )
    assert result.get("auto_confirm_eligible") is True
    assert_field(result, "context_status", "VERIFIED", "context good")
    assert_field(result, "manufacturer", "Givaudan Flavors Corporation", "context good")
    report.append({"case": "verified_mail_pmf_context", "passed": True})

    # 잘못 연결된 메일기관은 자동확정을 막고 OCR 원값을 보존한다.
    record = find_job(records, 510)
    base = parse_certificate_rule(record.get("raw_text", ""), record.get("filename", ""))
    result = parse_certificate_rule_with_context(
        record.get("raw_text", ""),
        record.get("filename", ""),
        {
            "reliability": "HIGH",
            "selection_reason": "ATTACHMENT_INDEX",
            "request_id": "HALAL-REQ-CONFLICT",
            "item_index": 1,
            "org": "MUI",
            "english_name": "Onion flavor oil",
            "maker": "SHIN YANG Poseung branch Co.,Ltd.",
            "maker_country": "KOREA",
        },
    )
    assert_field(result, "parse_status", "MANUAL_REVIEW", "context conflict")
    assert_field(result, "context_status", "CONFLICT", "context conflict")
    assert result.get("auto_confirm_eligible") is False
    assert_field(result, "manufacturer", base.get("manufacturer"), "context conflict preserve")
    assert_field(result, "expiry_date", "", "BPJPH expiry must stay empty")
    report.append({"case": "org_conflict_blocks_and_preserves_ocr", "passed": True})

    # OCR 제조사가 잘린 경우 원문에 실제 회사명이 있으면 PMF 표준명으로 정규화한다.
    record = find_job(records, 435)
    result = parse_certificate_rule_with_context(
        record.get("raw_text", ""),
        record.get("filename", ""),
        {
            "reliability": "HIGH",
            "selection_reason": "ATTACHMENT_INDEX",
            "request_id": "HALAL-REQ-HFFIA",
            "item_index": 1,
            "org": "HFFIA",
            "english_name": "VITACEL",
            "material_name": "VITACEL",
            "maker": "J. Rettenmaier & Söhne GmbH + Co. KG",
            "maker_country": "GERMANY",
            "current_expiry": "2024-01-01",
        },
    )
    assert_field(
        result,
        "manufacturer",
        "J. Rettenmaier & Söhne GmbH + Co. KG",
        "context canonical maker",
    )
    assert result.get("auto_confirm_eligible") is False  # 날짜 역행 안전장치
    report.append({"case": "canonical_maker_with_date_regression_block", "passed": True})

    # PMF 후보 신뢰도 산정 순수 함수 테스트
    context = assemble_ocr_context(
        {"request_id": "REQ-1", "mail_log": {"supplier": "공급사"}},
        {
            "selected_mail_item": {
                "item_index": 1,
                "english_name": "Sample Product",
                "maker": "Sample Maker Co., Ltd.",
                "org": "IFANCA",
                "cert_no": "OLD-1",
                "current_expiry": "2026-01-01",
            },
            "selection_reason": "ATTACHMENT_INDEX",
            "attachment_index": 1,
            "auto_selectable": True,
            "warnings": [],
            "hard_blockers": [],
        },
        [{
            "row_pos": 10,
            "depth": 1,
            "material_no": "81",
            "material_name": "샘플",
            "english_name": "Sample Product",
            "maker": "Sample Maker Co., Ltd.",
            "maker_country": "USA",
            "org": "IFANCA",
            "score": 260,
            "reasons": ["english_name:exact", "maker:exact", "org:exact"],
        }],
    )
    assert_field(context, "reliability", "HIGH", "context assembly")
    assert_field(context, "pmf_material_no", "81", "context assembly")
    report.append({"case": "context_reliability_high", "passed": True})

    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, help="OCR rule review ZIP 또는 export.jsonl")
    parser.add_argument(
        "--report",
        default=r"C:\TEMP\halal_ocr_rule_review\ocr_rule_v2_test_report.json",
    )
    args = parser.parse_args()

    records = load_records(Path(args.bundle))
    unique = unique_records(records)

    service_path = BACKEND_DIR / "app" / "services" / "certificate_rule_service.py"
    tree = ast.parse(service_path.read_text(encoding="utf-8-sig"))
    names = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    duplicates = {name: count for name, count in Counter(names).items() if count > 1}
    if duplicates:
        raise AssertionError(f"중복 함수 정의가 남아 있습니다: {duplicates}")

    parse_errors = []
    status_counts: Counter[str] = Counter()
    for record in records:
        try:
            result = parse_certificate_rule(
                record.get("raw_text", ""),
                record.get("filename", ""),
            )
            status_counts[str(result.get("parse_status") or "EMPTY")] += 1
        except Exception as exc:
            parse_errors.append({
                "ocr_job_id": record.get("ocr_job_id"),
                "filename": record.get("filename"),
                "error": repr(exc),
            })

    if parse_errors:
        raise AssertionError(f"전체 회귀 테스트 오류 {len(parse_errors)}건")

    targeted = test_targeted_regressions(records)
    context_tests = test_context_assist(records)

    report = {
        "ok": True,
        "records_tested": len(records),
        "unique_documents": len(unique),
        "runtime_errors": len(parse_errors),
        "duplicate_function_definitions": duplicates,
        "status_counts": dict(status_counts),
        "targeted_regressions": targeted,
        "context_tests": context_tests,
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n테스트 보고서: {report_path}")


if __name__ == "__main__":
    main()
