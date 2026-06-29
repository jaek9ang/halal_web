from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import tempfile
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
BACKEND_DIR = SCRIPT_PATH.parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.ocr_exporter import create_ocr_data_export_zip


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_text(value: Any) -> str:
    return "" if value is None else str(value)


def redact_text(value: str, *, backend_dir: Path, home_dir: Path) -> str:
    text = safe_text(value)
    replacements = [
        (str(backend_dir), "<BACKEND_DIR>"),
        (str(backend_dir.parent), "<PROJECT_ROOT>"),
        (str(home_dir), "<USER_HOME>"),
    ]

    for source, replacement in replacements:
        if source:
            text = text.replace(source, replacement)
            text = text.replace(source.replace("\\", "/"), replacement)

    return text


def redact_object(value: Any, *, backend_dir: Path, home_dir: Path) -> Any:
    if isinstance(value, dict):
        return {
            key: redact_object(item, backend_dir=backend_dir, home_dir=home_dir)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            redact_object(item, backend_dir=backend_dir, home_dir=home_dir)
            for item in value
        ]

    if isinstance(value, str):
        return redact_text(value, backend_dir=backend_dir, home_dir=home_dir)

    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    if not path.exists():
        return rows

    with path.open("r", encoding="utf-8-sig") as file:
        for line_no, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"export.jsonl {line_no}번째 줄을 읽지 못했습니다: {exc}"
                ) from exc

            if isinstance(value, dict):
                rows.append(value)

    return rows


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def get_rule(record: dict[str, Any]) -> dict[str, Any]:
    rule = (
        record.get("certificate_rule_current")
        or record.get("certificate_rule")
        or {}
    )
    return rule if isinstance(rule, dict) else {}


def get_saved_rule(record: dict[str, Any]) -> dict[str, Any]:
    rule = record.get("certificate_rule_saved") or {}
    return rule if isinstance(rule, dict) else {}


def build_issue_reasons(record: dict[str, Any]) -> list[str]:
    rule = get_rule(record)
    reasons: list[str] = []

    cert_org = safe_text(rule.get("cert_org")).strip().upper()
    cert_no = safe_text(
        rule.get("cert_no")
        or rule.get("certificate_no")
        or rule.get("certificate_number")
    ).strip()
    expiry_date = safe_text(
        rule.get("expiry_date")
        or rule.get("valid_until")
        or rule.get("expired_date")
    ).strip()
    manufacturer = safe_text(
        rule.get("manufacturer")
        or rule.get("company")
        or rule.get("company_name")
    ).strip()
    parse_status = safe_text(rule.get("parse_status")).strip().upper()
    confidence = safe_text(rule.get("confidence")).strip().upper()
    raw_text = safe_text(record.get("raw_text"))

    if cert_org in {"", "UNKNOWN", "UNCLASSIFIED", "NONE"}:
        reasons.append("기관 미판정")

    if parse_status in {
        "LOW_CONFIDENCE",
        "RULE_ERROR",
        "NO_TEXT",
        "ERROR",
        "UNKNOWN",
        "MANUAL_REVIEW",
    }:
        reasons.append(f"판독상태:{parse_status}")

    if confidence in {"", "LOW"}:
        reasons.append(f"신뢰도:{confidence or 'EMPTY'}")

    if cert_org not in {"BPJPH", "UNKNOWN", ""} and not cert_no:
        reasons.append("인증번호 누락")

    if cert_org not in {"BPJPH", "UNKNOWN", ""} and not expiry_date:
        reasons.append("유효기간 누락")

    if not manufacturer:
        reasons.append("제조사 누락")

    if len(raw_text.strip()) < 80:
        reasons.append("OCR 원문 부족")

    if record.get("certificate_rule_changed"):
        reasons.append("저장 당시 결과와 현재 규칙 결과 다름")

    image = record.get("image_classification_current") or record.get("image_classification") or {}
    if isinstance(image, dict) and image.get("text_image_conflict"):
        reasons.append("텍스트/이미지 기관 충돌")

    return reasons


def write_review_labels(records: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "review",
        "ocr_job_id",
        "filename",
        "source_category",
        "current_cert_org",
        "current_cert_no",
        "current_expiry_date",
        "current_manufacturer",
        "current_manufacturing_country",
        "current_parse_status",
        "current_confidence",
        "suspect_reasons",
        "expected_cert_org",
        "expected_cert_no",
        "expected_expiry_date",
        "expected_manufacturer",
        "expected_manufacturing_country",
        "expected_parse_status",
        "issue_note",
    ]

    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for record in records:
            rule = get_rule(record)
            reasons = build_issue_reasons(record)

            writer.writerow({
                "review": "Y" if reasons else "",
                "ocr_job_id": record.get("ocr_job_id") or "",
                "filename": record.get("filename") or "",
                "source_category": record.get("source_category") or "",
                "current_cert_org": rule.get("cert_org") or "",
                "current_cert_no": (
                    rule.get("cert_no")
                    or rule.get("certificate_no")
                    or rule.get("certificate_number")
                    or ""
                ),
                "current_expiry_date": (
                    rule.get("expiry_date")
                    or rule.get("valid_until")
                    or rule.get("expired_date")
                    or ""
                ),
                "current_manufacturer": (
                    rule.get("manufacturer")
                    or rule.get("company")
                    or rule.get("company_name")
                    or ""
                ),
                "current_manufacturing_country": (
                    rule.get("manufacturing_country")
                    or rule.get("mfg_country")
                    or ""
                ),
                "current_parse_status": rule.get("parse_status") or "",
                "current_confidence": rule.get("confidence") or "",
                "suspect_reasons": " | ".join(reasons),
                "expected_cert_org": "",
                "expected_cert_no": "",
                "expected_expiry_date": "",
                "expected_manufacturer": "",
                "expected_manufacturing_country": "",
                "expected_parse_status": "",
                "issue_note": "",
            })


def write_suspect_cases(records: list[dict[str, Any]], path: Path) -> int:
    fieldnames = [
        "ocr_job_id",
        "filename",
        "source_category",
        "cert_org",
        "cert_no",
        "expiry_date",
        "manufacturer",
        "parse_status",
        "confidence",
        "suspect_reasons",
        "raw_text_preview",
    ]

    count = 0

    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for record in records:
            reasons = build_issue_reasons(record)
            if not reasons:
                continue

            count += 1
            rule = get_rule(record)
            raw_text = safe_text(record.get("raw_text")).replace("\r", " ").replace("\n", " ")

            writer.writerow({
                "ocr_job_id": record.get("ocr_job_id") or "",
                "filename": record.get("filename") or "",
                "source_category": record.get("source_category") or "",
                "cert_org": rule.get("cert_org") or "",
                "cert_no": (
                    rule.get("cert_no")
                    or rule.get("certificate_no")
                    or rule.get("certificate_number")
                    or ""
                ),
                "expiry_date": (
                    rule.get("expiry_date")
                    or rule.get("valid_until")
                    or rule.get("expired_date")
                    or ""
                ),
                "manufacturer": (
                    rule.get("manufacturer")
                    or rule.get("company")
                    or rule.get("company_name")
                    or ""
                ),
                "parse_status": rule.get("parse_status") or "",
                "confidence": rule.get("confidence") or "",
                "suspect_reasons": " | ".join(reasons),
                "raw_text_preview": raw_text[:500],
            })

    return count


def build_diagnostics(records: list[dict[str, Any]]) -> dict[str, Any]:
    org_counts: Counter[str] = Counter()
    parse_status_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    source_rule_counts: Counter[str] = Counter()
    changed_count = 0
    suspect_count = 0

    for record in records:
        rule = get_rule(record)
        org_counts[safe_text(rule.get("cert_org") or "EMPTY")] += 1
        parse_status_counts[safe_text(rule.get("parse_status") or "EMPTY")] += 1
        confidence_counts[safe_text(rule.get("confidence") or "EMPTY")] += 1
        source_rule_counts[safe_text(rule.get("source_rule") or "EMPTY")] += 1

        if record.get("certificate_rule_changed"):
            changed_count += 1

        if build_issue_reasons(record):
            suspect_count += 1

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "record_count": len(records),
        "suspect_count": suspect_count,
        "certificate_rule_changed_count": changed_count,
        "counts_by_cert_org": dict(org_counts.most_common()),
        "counts_by_parse_status": dict(parse_status_counts.most_common()),
        "counts_by_confidence": dict(confidence_counts.most_common()),
        "counts_by_source_rule": dict(source_rule_counts.most_common()),
    }


def copy_current_code(target_dir: Path) -> list[str]:
    source_map = {
        BACKEND_DIR / "app" / "services" / "certificate_rule_service.py": "certificate_rule_service.py",
        BACKEND_DIR / "app" / "services" / "ocr_service.py": "ocr_service.py",
        BACKEND_DIR / "app" / "services" / "ocr_exporter.py": "ocr_exporter.py",
        BACKEND_DIR / "app" / "routers" / "ocr.py": "ocr_router.py",
    }

    target_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []

    for source, name in source_map.items():
        if not source.exists():
            continue

        target = target_dir / name
        shutil.copy2(source, target)
        copied.append(name)

    return copied


def write_readme(path: Path, diagnostics: dict[str, Any]) -> None:
    content = f"""# OCR 규칙 재검토 묶음

생성 시각: {diagnostics.get("generated_at")}
전체 OCR 레코드: {diagnostics.get("record_count")}
자동 의심 건수: {diagnostics.get("suspect_count")}

## 핵심 파일

- `export.jsonl`: OCR 원문 전체와 현재/과거 규칙 판독 결과
- `summary.csv`: 전체 결과 요약
- `combined_ocr_text.md`: OCR 원문을 파일별로 합친 문서
- `review_labels.csv`: 사람이 정답을 입력할 검토표
- `suspect_cases.csv`: 자동으로 의심 표시한 건
- `diagnostics.json`: 기관/상태/신뢰도별 통계
- `current_code/`: 현재 OCR 판독 관련 코드

## 정답 검토 방법

`review_labels.csv`에서 잘못 판독된 행만 아래 열을 작성하면 됩니다.

- expected_cert_org
- expected_cert_no
- expected_expiry_date
- expected_manufacturer
- expected_manufacturing_country
- expected_parse_status
- issue_note

원본 인증서 PDF는 이 ZIP에 포함하지 않습니다.
원문 확인이 꼭 필요한 대표 오판독 인증서만 별도로 추가하면 됩니다.
"""
    path.write_text(content, encoding="utf-8-sig")


def create_review_bundle(
    *,
    limit: int,
    include_ocr_jobs: bool,
    include_ocr_tests: bool,
    redact_paths: bool,
    output_dir: Path,
) -> Path:
    export_result = create_ocr_data_export_zip(
        limit=limit,
        include_ocr_jobs=include_ocr_jobs,
        include_ocr_tests=include_ocr_tests,
    )

    export_zip = Path(export_result["zip_path"])
    if not export_zip.exists():
        raise FileNotFoundError(f"OCR export ZIP이 없습니다: {export_zip}")

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = now_stamp()
    output_zip = output_dir / f"ocr_rule_review_bundle_{stamp}.zip"

    with tempfile.TemporaryDirectory(prefix="ocr_rule_review_") as temp_dir_text:
        temp_dir = Path(temp_dir_text)
        extracted_dir = temp_dir / "bundle"
        extracted_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(export_zip, "r") as source_zip:
            source_zip.extractall(extracted_dir)

        export_jsonl = extracted_dir / "export.jsonl"
        records = read_jsonl(export_jsonl)

        if redact_paths:
            home_dir = Path.home()
            records = [
                redact_object(
                    row,
                    backend_dir=BACKEND_DIR,
                    home_dir=home_dir,
                )
                for row in records
            ]
            write_jsonl(records, export_jsonl)

            combined_path = extracted_dir / "combined_ocr_text.md"
            if combined_path.exists():
                combined_text = combined_path.read_text(encoding="utf-8-sig")
                combined_path.write_text(
                    redact_text(
                        combined_text,
                        backend_dir=BACKEND_DIR,
                        home_dir=home_dir,
                    ),
                    encoding="utf-8-sig",
                )

            summary_path = extracted_dir / "summary.csv"
            if summary_path.exists():
                summary_text = summary_path.read_text(encoding="utf-8-sig")
                summary_path.write_text(
                    redact_text(
                        summary_text,
                        backend_dir=BACKEND_DIR,
                        home_dir=home_dir,
                    ),
                    encoding="utf-8-sig",
                )

        diagnostics = build_diagnostics(records)
        write_review_labels(records, extracted_dir / "review_labels.csv")
        suspect_count = write_suspect_cases(records, extracted_dir / "suspect_cases.csv")
        diagnostics["suspect_count"] = suspect_count

        (extracted_dir / "diagnostics.json").write_text(
            json.dumps(diagnostics, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )

        copied_code = copy_current_code(extracted_dir / "current_code")
        diagnostics["copied_code"] = copied_code

        write_readme(extracted_dir / "README.md", diagnostics)

        manifest = {
            "bundle_version": "ocr_rule_review_bundle_v1",
            "generated_at": diagnostics["generated_at"],
            "record_count": diagnostics["record_count"],
            "suspect_count": diagnostics["suspect_count"],
            "paths_redacted": redact_paths,
            "source_export_zip": str(export_zip),
            "copied_code": copied_code,
        }

        (extracted_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )

        with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for file_path in sorted(extracted_dir.rglob("*")):
                if file_path.is_file():
                    zip_file.write(file_path, file_path.relative_to(extracted_dir).as_posix())

    return output_zip


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OCR 원문·판독결과·현재 규칙 코드를 하나의 검토 ZIP으로 생성합니다."
    )
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--exclude-tests", action="store_true")
    parser.add_argument("--exclude-jobs", action="store_true")
    parser.add_argument(
        "--keep-paths",
        action="store_true",
        help="로컬 절대경로를 가리지 않습니다. 기본값은 경로 가림입니다.",
    )
    parser.add_argument(
        "--output-dir",
        default=r"C:\TEMP\halal_ocr_rule_review",
    )
    args = parser.parse_args()

    output_zip = create_review_bundle(
        limit=max(1, min(args.limit, 50000)),
        include_ocr_jobs=not args.exclude_jobs,
        include_ocr_tests=not args.exclude_tests,
        redact_paths=not args.keep_paths,
        output_dir=Path(args.output_dir),
    )

    print()
    print("OCR 규칙 재검토 ZIP 생성 완료")
    print(output_zip)
    print()
    print("이 ZIP을 업로드하면 OCR 원문과 현재 판독 결과를 기준으로 규칙을 다시 정리할 수 있습니다.")


if __name__ == "__main__":
    main()
