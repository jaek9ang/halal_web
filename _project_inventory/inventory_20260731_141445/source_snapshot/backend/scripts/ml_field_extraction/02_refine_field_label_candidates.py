from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


SCHEMA_VERSION = "field_label_refinement_v1"
SINGLE_VALUE_FIELDS = {
    "cert_no",
    "manufacturer",
    "manufacturing_country",
    "expiry_date",
}

GENERIC_MANUFACTURER_VALUES = {
    "NAME",
    "COMPANY",
    "COMPANY NAME",
    "NAME OF COMPANY",
    "MANUFACTURER",
    "MANUFACTURED BY",
    "FACTORY",
    "FACTORY NAME",
    "APPLICANT",
    "CERTIFIED COMPANY",
}

PERSON_HINT_RE = re.compile(
    r"\b(PHD|PH\.D|M\.?D\.?|DR\.?|CHAIRMAN|PRESIDENT|DIRECTOR|SECRETARY|AUDITOR)\b",
    re.IGNORECASE,
)

COMPANY_HINT_RE = re.compile(
    r"\b("
    r"CO\.?|COMPANY|CORP\.?|CORPORATION|LTD\.?|LIMITED|LLC|INC\.?|"
    r"INDUSTRIES|INDUSTRY|SDN\.?\s*BHD\.?|PTE\.?\s*LTD\.?|PT\.?|"
    r"GMBH|AG|S\.?A\.?|A/S|BV|B\.V\.|PLC|LP|LLP"
    r")\b",
    re.IGNORECASE,
)

EXPLICIT_COMPANY_LABEL_RE = re.compile(
    r"\b(COMPANY\s+NAME|NAME\s+OF\s+COMPANY|MANUFACTURER|MANUFACTURED\s+BY|"
    r"PRODUCED\s+BY|FACTORY\s+NAME|APPLICANT)\b",
    re.IGNORECASE,
)

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CERT_GENERIC_RE = re.compile(
    r"^(CERTIFICATE|CERTIFICATE\s+NO|CERTIFICATE\s+NUMBER|CERT\s+NO|NO|NUMBER)$",
    re.IGNORECASE,
)


def clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).lower() in {"true", "1", "yes", "y"}


def parse_sources(value: Any) -> set[str]:
    return {
        item.strip()
        for item in clean(value).split("|")
        if item.strip()
    }


def parse_json_list(value: Any) -> list[str]:
    text = clean(value)
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except Exception:
        return [text]

    if isinstance(parsed, list):
        return [clean(item) for item in parsed if clean(item)]
    return [clean(parsed)] if clean(parsed) else []


def safe_int(value: Any) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except Exception:
        return 0


def safe_float(value: Any) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def should_promote(row: pd.Series) -> tuple[bool, str]:
    if clean(row.get("status")) != "REVIEW_REQUIRED":
        return False, ""

    field = clean(row.get("field"))
    candidate = clean(row.get("candidate_value"))
    evidence = clean(row.get("evidence_line"))
    evidence_score = safe_float(row.get("evidence_score"))
    evidence_found = parse_bool(row.get("evidence_found"))
    sources = parse_sources(row.get("agreeing_sources"))

    two_rule_agreement = {
        "full_rule",
        "conditional_rule",
    }.issubset(sources)

    if not candidate or not evidence_found or not two_rule_agreement:
        return False, ""

    # 인증번호: 두 추출 경로와 본문 근거가 동일하면 PMF의 구버전/접두어 차이는
    # 인증서 필드 학습 라벨을 막지 않는다.
    if field == "cert_no":
        if (
            evidence_score >= 0.95
            and len(candidate) >= 5
            and not CERT_GENERIC_RE.fullmatch(candidate)
        ):
            return True, (
                "두 규칙 경로와 인증서 본문 근거가 일치합니다. "
                "PMF 차이는 갱신본·접두어·운영값 차이로 분리했습니다."
            )
        return False, ""

    # 제조사: 라벨 문구 자체나 사람 이름은 제외한다.
    # 회사형 접미사 또는 명시적 회사 라벨 문맥이 있는 경우만 승격한다.
    if field == "manufacturer":
        upper_candidate = candidate.upper().strip(" .:-")
        if upper_candidate in GENERIC_MANUFACTURER_VALUES:
            return False, ""
        if PERSON_HINT_RE.search(candidate):
            return False, ""

        company_like = bool(COMPANY_HINT_RE.search(candidate))
        explicit_context = bool(EXPLICIT_COMPANY_LABEL_RE.search(evidence))

        if (
            evidence_score >= 0.90
            and len(candidate) >= 4
            and (company_like or explicit_context)
        ):
            return True, (
                "두 규칙 경로와 본문 제조사 근거가 일치하며 회사명 문맥을 확인했습니다. "
                "PMF의 약칭·사업장명 차이는 별도 운영값으로 유지합니다."
            )
        return False, ""

    # 만료일: 인증서 본문에 실제 근거가 있고 두 규칙 경로가 일치하면
    # PMF의 다른 갱신본 날짜보다 현재 PDF의 날짜를 학습 라벨로 우선한다.
    if field == "expiry_date":
        if evidence_score >= 0.95 and ISO_DATE_RE.fullmatch(candidate):
            return True, (
                "두 규칙 경로와 인증서 본문 날짜가 일치합니다. "
                "PMF의 다른 갱신본 날짜는 현재 PDF 라벨과 분리했습니다."
            )
        return False, ""

    # 제조국 충돌은 발급기관 국가와 제조국 혼동 위험이 있으므로 자동 승격 금지.
    # 제품 목록도 부속목록·다품목 구조 때문에 이 단계에서 자동 승격하지 않는다.
    return False, ""


def make_training_examples(
    refined: pd.DataFrame,
    group_map: dict[str, str],
) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []

    ready = refined[refined["status"] == "AUTO_READY"].copy()

    for _, row in ready.iterrows():
        field = clean(row.get("field"))
        sha256 = clean(row.get("sha256"))
        institution = clean(row.get("institution"))
        validation_group = group_map.get(
            sha256,
            f"{institution}::DOC::{sha256[:16]}",
        )

        common = {
            "schema_version": SCHEMA_VERSION,
            "sha256": sha256,
            "institution": institution,
            "validation_group": validation_group,
            "positive_page": safe_int(row.get("evidence_page")),
            "positive_line_no": safe_int(row.get("evidence_line_no")),
            "positive_line": clean(row.get("evidence_line")),
            "evidence_score": round(safe_float(row.get("evidence_score")), 4),
            "source": sorted(parse_sources(row.get("agreeing_sources"))),
            "label_origin": (
                "REFINED_PROMOTION"
                if clean(row.get("original_status")) == "REVIEW_REQUIRED"
                else "ORIGINAL_AUTO_READY"
            ),
        }

        if field == "products":
            for product in parse_json_list(row.get("candidate_value")):
                examples.append({
                    **common,
                    "field": "product",
                    "label_value": product,
                })
        elif field in SINGLE_VALUE_FIELDS:
            value = clean(row.get("candidate_value"))
            if value:
                examples.append({
                    **common,
                    "field": field,
                    "label_value": value,
                })

    return examples


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--source-report-root", default="")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    runtime_root = Path(args.runtime_root).resolve()

    if args.source_report_root:
        source_root = Path(args.source_report_root).resolve()
    else:
        pointer = runtime_root / "reports" / "latest_field_label_candidates.txt"
        source_root = Path(
            pointer.read_text(encoding="utf-8-sig").strip()
        ).resolve()

    field_csv = source_root / "02_field_candidates.csv"
    group_csv = source_root / "07_group_assignments.csv"

    if not field_csv.exists():
        raise FileNotFoundError(field_csv)
    if not group_csv.exists():
        raise FileNotFoundError(group_csv)

    fields = pd.read_csv(field_csv, encoding="utf-8-sig")
    groups = pd.read_csv(group_csv, encoding="utf-8-sig")

    required_columns = {
        "sha256",
        "institution",
        "file_name",
        "pdf_path",
        "field",
        "candidate_value",
        "status",
        "reason",
        "agreeing_sources",
        "evidence_found",
        "evidence_page",
        "evidence_line_no",
        "evidence_score",
        "evidence_line",
    }
    missing_columns = required_columns - set(fields.columns)
    if missing_columns:
        raise RuntimeError(
            "필수 열 누락: " + ", ".join(sorted(missing_columns))
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_root = (
        runtime_root
        / "reports"
        / f"field_label_refinement_{stamp}"
    )
    report_root.mkdir(parents=True, exist_ok=False)

    refined = fields.copy()
    refined["original_status"] = refined["status"]
    refined["refinement_action"] = ""
    refined["refinement_reason"] = ""

    promoted_indices: list[int] = []

    for index, row in refined.iterrows():
        promote, reason = should_promote(row)
        if not promote:
            continue

        refined.at[index, "status"] = "AUTO_READY"
        refined.at[index, "reason"] = reason
        refined.at[index, "refinement_action"] = "PROMOTED_TO_AUTO_READY"
        refined.at[index, "refinement_reason"] = reason
        promoted_indices.append(index)

    promoted = refined.loc[promoted_indices].copy()

    remaining_review = refined[
        ~refined["status"].isin(["AUTO_READY", "MISSING_ALLOWED"])
    ].copy()

    group_map = {
        clean(row["sha256"]): clean(row["validation_group"])
        for _, row in groups.iterrows()
        if clean(row.get("sha256"))
    }

    training_examples = make_training_examples(refined, group_map)

    coverage_rows: list[dict[str, Any]] = []
    for (institution, field), group in refined.groupby(
        ["institution", "field"],
        dropna=False,
    ):
        counts = Counter(clean(value) for value in group["status"])
        total = len(group)
        coverage_rows.append({
            "institution": institution,
            "field": field,
            "documents": total,
            "auto_ready": counts.get("AUTO_READY", 0),
            "candidate_only": counts.get("CANDIDATE_ONLY", 0),
            "review_required": counts.get("REVIEW_REQUIRED", 0),
            "missing_required": counts.get("MISSING_REQUIRED", 0),
            "missing_allowed": counts.get("MISSING_ALLOWED", 0),
            "auto_ready_rate": round(
                counts.get("AUTO_READY", 0) / total,
                4,
            ) if total else 0.0,
        })

    coverage = pd.DataFrame(coverage_rows).sort_values(
        ["institution", "field"]
    )

    field_summary_rows: list[dict[str, Any]] = []
    for field, group in refined.groupby("field"):
        counts = Counter(clean(value) for value in group["status"])
        total = len(group)
        field_summary_rows.append({
            "field": field,
            "total": total,
            "auto_ready": counts.get("AUTO_READY", 0),
            "candidate_only": counts.get("CANDIDATE_ONLY", 0),
            "review_required": counts.get("REVIEW_REQUIRED", 0),
            "missing_required": counts.get("MISSING_REQUIRED", 0),
            "missing_allowed": counts.get("MISSING_ALLOWED", 0),
            "auto_ready_rate": round(
                counts.get("AUTO_READY", 0) / total,
                4,
            ) if total else 0.0,
        })

    field_summary = pd.DataFrame(field_summary_rows).sort_values("field")

    original_counts = Counter(clean(value) for value in fields["status"])
    refined_counts = Counter(clean(value) for value in refined["status"])
    promoted_by_field = Counter(
        clean(value) for value in promoted["field"]
    )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "run_id": stamp,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(project_root),
        "runtime_root": str(runtime_root),
        "source_report_root": str(source_root),
        "report_root": str(report_root),
        "total_documents": int(refined["sha256"].nunique()),
        "institution_count": int(refined["institution"].nunique()),
        "field_row_count": int(len(refined)),
        "original_status_counts": dict(original_counts),
        "refined_status_counts": dict(refined_counts),
        "promoted_count": int(len(promoted)),
        "promoted_by_field": dict(promoted_by_field),
        "remaining_review_count": int(len(remaining_review)),
        "training_example_count": int(len(training_examples)),
        "training_examples_by_field": dict(
            Counter(row["field"] for row in training_examples)
        ),
        "policy": {
            "certificate_first": True,
            "pmf_role": "교차검증 및 운영 연결값. 현재 PDF 본문보다 우선하지 않음.",
            "country_conflict_auto_promotion": False,
            "product_auto_promotion": False,
            "validation_group_required": True,
        },
        "next_step": (
            "정제된 단일값 필드(cert_no, manufacturer, "
            "manufacturing_country, expiry_date)로 그룹 기반 후보순위 모델을 학습합니다. "
            "제품 목록은 별도 영역·행 분류 모델로 분리합니다."
        ),
    }

    refined.to_csv(
        report_root / "01_refined_field_candidates.csv",
        index=False,
        encoding="utf-8-sig",
    )
    promoted.to_csv(
        report_root / "02_auto_promoted.csv",
        index=False,
        encoding="utf-8-sig",
    )
    remaining_review.to_csv(
        report_root / "03_remaining_review.csv",
        index=False,
        encoding="utf-8-sig",
    )
    coverage.to_csv(
        report_root / "04_field_coverage_refined.csv",
        index=False,
        encoding="utf-8-sig",
    )
    field_summary.to_csv(
        report_root / "05_field_summary_refined.csv",
        index=False,
        encoding="utf-8-sig",
    )
    write_json(report_root / "06_summary.json", summary)
    write_jsonl(
        report_root / "07_training_ready_field_examples.jsonl",
        training_examples,
    )

    manual_review_columns = [
        column
        for column in [
            "sha256",
            "institution",
            "file_name",
            "pdf_path",
            "field",
            "candidate_value",
            "status",
            "reason",
            "agreeing_sources",
            "source_full_rule",
            "source_conditional_rule",
            "source_pmf",
            "source_filename",
            "conflicting_values",
            "evidence_page",
            "evidence_line_no",
            "evidence_score",
            "evidence_line",
            "review_decision",
            "reviewed_value",
            "review_note",
        ]
        if column in remaining_review.columns
    ]
    remaining_review[manual_review_columns].to_csv(
        report_root / "08_manual_review_template.csv",
        index=False,
        encoding="utf-8-sig",
    )

    rules = {
        "cert_no": {
            "requires": [
                "status=REVIEW_REQUIRED",
                "full_rule and conditional_rule agree",
                "evidence_found=true",
                "evidence_score>=0.95",
                "candidate length>=5",
            ],
            "pmf_conflict_policy": "현재 PDF 본문값 우선",
        },
        "manufacturer": {
            "requires": [
                "status=REVIEW_REQUIRED",
                "full_rule and conditional_rule agree",
                "evidence_found=true",
                "evidence_score>=0.90",
                "회사형 접미사 또는 명시적 회사 라벨 문맥",
                "라벨 문구 자체 및 사람 이름 제외",
            ],
            "pmf_conflict_policy": "약칭·사업장명 차이로 분리",
        },
        "expiry_date": {
            "requires": [
                "status=REVIEW_REQUIRED",
                "full_rule and conditional_rule agree",
                "evidence_found=true",
                "evidence_score>=0.95",
                "ISO 날짜",
            ],
            "pmf_conflict_policy": "현재 PDF의 갱신본 날짜 우선",
        },
        "manufacturing_country": {
            "auto_promote": False,
            "reason": "발급기관 국가와 제조국 혼동 가능성",
        },
        "products": {
            "auto_promote": False,
            "reason": "다품목·부속목록·제품행 구분은 별도 모델 대상",
        },
    }
    write_json(report_root / "09_refinement_rules.json", rules)

    pointer = (
        runtime_root
        / "reports"
        / "latest_field_label_refinement.txt"
    )
    pointer.write_text(str(report_root), encoding="utf-8")

    print("")
    print("필드 라벨 정제 완료")
    print(f"원본 AUTO_READY : {original_counts.get('AUTO_READY', 0)}")
    print(f"추가 승격       : {len(promoted)}")
    print(f"정제 AUTO_READY : {refined_counts.get('AUTO_READY', 0)}")
    print(f"남은 검토       : {len(remaining_review)}")
    print(f"학습 예제       : {len(training_examples)}")
    print(f"결과 폴더       : {report_root}")
    print("")
    print("다음 확인 파일")
    print(" - 06_summary.json")
    print(" - 02_auto_promoted.csv")
    print(" - 03_remaining_review.csv")
    print(" - 05_field_summary_refined.csv")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())