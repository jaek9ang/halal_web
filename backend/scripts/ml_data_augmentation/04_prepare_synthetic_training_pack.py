from __future__ import annotations

import argparse
import html
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


SCHEMA_VERSION = "synthetic_training_pack_v1"

FIELD_RULES = {
    "certificate_no": {
        "label_ko": "문서·인증번호",
        "admit_threshold": 0.88,
        "review_threshold": 0.65,
    },
    "manufacturer": {
        "label_ko": "제조사명",
        "admit_threshold": 0.80,
        "review_threshold": 0.65,
    },
    "expiry_date": {
        "label_ko": "유효기간",
        "admit_threshold": 0.90,
        "review_threshold": 0.70,
    },
    "product_name": {
        "label_ko": "제품명",
        "admit_threshold": 0.80,
        "review_threshold": 0.65,
    },
    "product_code": {
        "label_ko": "제품코드",
        "admit_threshold": 0.88,
        "review_threshold": 0.65,
    },
    "halal_id": {
        "label_ko": "Halal-ID",
        "admit_threshold": 0.88,
        "review_threshold": 0.65,
    },
    "product_certificate_no": {
        "label_ko": "품목별 인증번호",
        "admit_threshold": 0.88,
        "review_threshold": 0.65,
    },
}


def clean(value: Any) -> str:
    if pd.isna(value):
        return ""
    return " ".join(str(value or "").split()).strip()


def safe_float(value: Any) -> float | None:
    if pd.isna(value) or clean(value) == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def status_ko(status: str) -> str:
    return {
        "ADMIT": "편입",
        "REVIEW": "검토",
        "REJECT": "제외",
        "NOT_EVALUABLE": "평가자료 없음",
    }.get(status, status)


def find_ocr_text_path(
    report_root: Path,
    synthetic_sha256: str,
) -> str:
    path = (
        report_root
        / "ocr_text"
        / f"{synthetic_sha256}.txt"
    )
    return str(path) if path.exists() else ""


def aggregate_expected_values(
    detail_frame: pd.DataFrame,
) -> dict[tuple[str, str], list[str]]:
    result: dict[tuple[str, str], list[str]] = {}

    if detail_frame.empty:
        return result

    required = {
        "synthetic_sha256",
        "field_name",
        "expected_value",
    }

    if not required.issubset(detail_frame.columns):
        return result

    for (sha256, field_name), group in detail_frame.groupby(
        ["synthetic_sha256", "field_name"],
        dropna=False,
    ):
        values: list[str] = []
        seen: set[str] = set()

        for value in group["expected_value"]:
            value = clean(value)

            if not value:
                continue

            key = value.upper()

            if key in seen:
                continue

            seen.add(key)
            values.append(value)

        result[
            (clean(sha256), clean(field_name))
        ] = values

    return result


def evaluate_field(
    expected_count: int,
    score: float | None,
    page_success_rate: float,
    rule: dict[str, Any],
) -> tuple[str, str]:
    if expected_count <= 0 or score is None:
        return (
            "NOT_EVALUABLE",
            "원본문서에서 평가용 항목 후보를 확보하지 못함",
        )

    if page_success_rate < 0.90:
        return (
            "REJECT",
            "OCR 페이지 처리 성공률이 90% 미만",
        )

    if score >= float(
        rule["admit_threshold"]
    ):
        return (
            "ADMIT",
            "항목 유지점수가 편입 기준 이상",
        )

    if score >= float(
        rule["review_threshold"]
    ):
        return (
            "REVIEW",
            "항목은 일부 유지됐으나 확인 필요",
        )

    return (
        "REJECT",
        "항목 유지점수가 최소 기준 미만",
    )


def make_easy_html(
    summary: dict[str, Any],
    field_summary: pd.DataFrame,
    profile_summary: pd.DataFrame,
    institution_summary: pd.DataFrame,
    review_rows: pd.DataFrame,
    output_path: Path,
) -> None:
    cards = [
        (
            "합성 스캔본",
            summary["total_documents"],
        ),
        (
            "항목 1개 이상 편입 가능",
            summary["documents_with_admitted_fields"],
        ),
        (
            "평가자료 없는 문서",
            summary["not_evaluable_document_count"],
        ),
        (
            "편입 가능한 항목",
            summary["admitted_field_rows"],
        ),
        (
            "검토 항목",
            summary["review_field_rows"],
        ),
        (
            "제외 항목",
            summary["rejected_field_rows"],
        ),
    ]

    card_html = "".join(
        "<div class='card'><div class='caption'>"
        + html.escape(str(label))
        + "</div><div class='number'>"
        + html.escape(str(value))
        + "</div></div>"
        for label, value in cards
    )

    field_table = field_summary.to_html(
        index=False,
        escape=True,
        classes="data",
    )
    profile_table = profile_summary.to_html(
        index=False,
        escape=True,
        classes="data",
    )
    institution_table = institution_summary.to_html(
        index=False,
        escape=True,
        classes="data",
    )

    review_columns = [
        "기관",
        "변형",
        "항목",
        "판정",
        "점수",
        "사유",
        "파일",
    ]

    if review_rows.empty:
        review_table = (
            "<p>검토 또는 제외할 항목이 없습니다.</p>"
        )
    else:
        review_table = review_rows[
            review_columns
        ].head(100).to_html(
            index=False,
            escape=True,
            classes="data",
        )

    body = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>합성 스캔 학습 편입 판단</title>
<style>
body {{
    font-family: Arial, "Malgun Gothic", sans-serif;
    background: #f4f6f8;
    color: #1f2937;
    margin: 0;
    padding: 24px;
}}
.wrap {{
    max-width: 1200px;
    margin: auto;
}}
.section {{
    background: white;
    border: 1px solid #dde4eb;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 16px;
}}
.verdict {{
    border-left: 5px solid #475569;
    background: #eef2f7;
    padding: 15px;
    font-size: 20px;
    font-weight: 700;
}}
.cards {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
    gap: 10px;
    margin-top: 16px;
}}
.card {{
    border: 1px solid #e1e7ed;
    border-radius: 10px;
    padding: 13px;
}}
.caption {{
    color: #64748b;
    font-size: 13px;
}}
.number {{
    font-size: 25px;
    font-weight: 700;
    margin-top: 5px;
}}
.data {{
    border-collapse: collapse;
    width: 100%;
    font-size: 13px;
}}
.data th, .data td {{
    border-bottom: 1px solid #e5e7eb;
    padding: 8px;
    text-align: left;
    vertical-align: top;
}}
.data th {{
    background: #f8fafc;
}}
.note {{
    color: #64748b;
    font-size: 13px;
}}
</style>
</head>
<body>
<div class="wrap">
<div class="section">
<h1>합성 스캔 학습 편입 판단</h1>
<div class="verdict">
{html.escape(summary["final_decision"])}
</div>
<p>{html.escape(summary["reason"])}</p>
<div class="cards">{card_html}</div>
</div>

<div class="section">
<h2>중요한 해석</h2>
<p>
기존 보고서에서 핵심항목 후보가 없었던 문서는 점수 0으로 계산됐습니다.
이번 보고서는 이를 <strong>OCR 실패가 아닌 평가자료 없음</strong>으로 분리합니다.
</p>
<p>
합성 PDF 전체를 한 번에 넣지 않고,
정상적으로 유지된 항목만 항목별 학습자료로 편입합니다.
</p>
</div>

<div class="section">
<h2>항목별 편입 결과</h2>
{field_table}
</div>

<div class="section">
<h2>스캔 변형별 결과</h2>
{profile_table}
</div>

<div class="section">
<h2>기관별 결과</h2>
{institution_table}
</div>

<div class="section">
<h2>검토·제외 항목</h2>
{review_table}
</div>

<div class="section">
<h2>다음 학습 적용 규칙</h2>
<p>
1. ADMIT 항목만 증강 학습자료로 사용<br>
2. REVIEW 항목은 자동 편입하지 않음<br>
3. NOT_EVALUABLE은 OCR 실패가 아니며 라벨 보강 대상<br>
4. 원본과 합성본은 항상 동일 Fold 사용<br>
5. 원본과 합성본 한 가족의 가중치 합계를 1로 제한<br>
6. 합성본은 최종 독립 테스트에서 제외
</p>
<p class="note">
이 단계에서는 기존 데이터셋에 파일을 자동 복사하거나 모델을 학습하지 않습니다.
</p>
</div>
</div>
</body>
</html>"""

    output_path.write_text(
        body,
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runtime-root",
        required=True,
    )
    parser.add_argument(
        "--core-eval-report-root",
        required=True,
    )
    args = parser.parse_args()

    runtime_root = Path(
        args.runtime_root
    ).resolve()
    core_report_root = Path(
        args.core_eval_report_root
    ).resolve()

    document_path = (
        core_report_root
        / "01_document_core_field_results.csv"
    )
    detail_path = (
        core_report_root
        / "02_value_match_details.csv"
    )

    documents = pd.read_csv(
        document_path,
        dtype=str,
        encoding="utf-8-sig",
    ).fillna("")
    details = pd.read_csv(
        detail_path,
        dtype=str,
        encoding="utf-8-sig",
    ).fillna("")

    expected_values = aggregate_expected_values(
        details
    )

    run_id = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    output_root = (
        runtime_root
        / "reports"
        / f"synthetic_training_pack_{run_id}"
    )
    output_root.mkdir(
        parents=True,
        exist_ok=False,
    )

    field_rows: list[dict[str, Any]] = []

    for _, row in documents.iterrows():
        synthetic_sha = clean(
            row.get("synthetic_sha256")
        )
        page_success_rate = (
            safe_float(
                row.get("page_success_rate")
            )
            or 0.0
        )

        for field_name, rule in FIELD_RULES.items():
            expected_count = safe_int(
                row.get(
                    f"{field_name}_expected_count"
                )
            )
            score = safe_float(
                row.get(
                    f"{field_name}_score"
                )
            )
            status, reason = evaluate_field(
                expected_count,
                score,
                page_success_rate,
                rule,
            )

            values = expected_values.get(
                (synthetic_sha, field_name),
                [],
            )

            field_rows.append({
                "institution": clean(
                    row.get("institution")
                ),
                "augmentation_profile": clean(
                    row.get(
                        "augmentation_profile"
                    )
                ),
                "source_path": clean(
                    row.get("source_path")
                ),
                "synthetic_path": clean(
                    row.get("synthetic_path")
                ),
                "ocr_text_path": (
                    find_ocr_text_path(
                        core_report_root,
                        synthetic_sha,
                    )
                ),
                "source_sha256": clean(
                    row.get("source_sha256")
                ),
                "synthetic_sha256": synthetic_sha,
                "source_document_id": clean(
                    row.get("source_sha256")
                ),
                "validation_group": clean(
                    row.get("validation_group")
                ),
                "field_name": field_name,
                "field_name_ko": rule[
                    "label_ko"
                ],
                "expected_count": expected_count,
                "expected_values_json": json.dumps(
                    values,
                    ensure_ascii=False,
                ),
                "score": score,
                "admit_threshold": rule[
                    "admit_threshold"
                ],
                "review_threshold": rule[
                    "review_threshold"
                ],
                "field_status": status,
                "field_status_ko": status_ko(
                    status
                ),
                "status_reason": reason,
                "page_success_rate": (
                    page_success_rate
                ),
                "mean_ocr_confidence": (
                    safe_float(
                        row.get(
                            "mean_ocr_confidence"
                        )
                    )
                ),
                "label_origin": (
                    "SOURCE_PDF_DERIVED"
                    if field_name in {
                        "certificate_no",
                        "manufacturer",
                        "expiry_date",
                    }
                    else "4C_AUTO_READY_INHERITED"
                ),
                "is_synthetic": True,
                "use_for_final_test": False,
            })

    fields = pd.DataFrame(field_rows)

    admitted = fields[
        fields["field_status"] == "ADMIT"
    ].copy()
    review_reject = fields[
        fields["field_status"].isin(
            ["REVIEW", "REJECT"]
        )
    ].copy()
    not_evaluable = fields[
        fields["field_status"]
        == "NOT_EVALUABLE"
    ].copy()

    family_counts = (
        admitted.groupby(
            [
                "source_sha256",
                "field_name",
            ]
        )
        .size()
        .rename(
            "admitted_synthetic_count"
        )
        .reset_index()
    )

    admitted = admitted.merge(
        family_counts,
        on=[
            "source_sha256",
            "field_name",
        ],
        how="left",
    )

    admitted[
        "recommended_family_member_weight"
    ] = (
        1.0
        / (
            1.0
            + admitted[
                "admitted_synthetic_count"
            ].astype(float)
        )
    ).round(6)

    admitted[
        "recommended_original_weight"
    ] = admitted[
        "recommended_family_member_weight"
    ]
    admitted[
        "recommended_synthetic_weight"
    ] = admitted[
        "recommended_family_member_weight"
    ]

    admitted[
        "fold_lock_key"
    ] = admitted[
        "source_sha256"
    ]

    admitted[
        "training_use"
    ] = "AUGMENT_TRAIN_ONLY"

    document_status = (
        fields.groupby(
            [
                "institution",
                "augmentation_profile",
                "source_path",
                "synthetic_path",
                "source_sha256",
                "synthetic_sha256",
                "validation_group",
            ],
            dropna=False,
        )["field_status"]
        .apply(list)
        .reset_index()
    )

    def make_document_status(
        statuses: list[str],
    ) -> str:
        if "ADMIT" in statuses:
            return "HAS_ADMITTED_FIELDS"

        if (
            "REVIEW" in statuses
            or "REJECT" in statuses
        ):
            return "REVIEW_REQUIRED"

        return "NOT_EVALUABLE"

    document_status[
        "document_pack_status"
    ] = document_status[
        "field_status"
    ].apply(make_document_status)
    document_status[
        "admitted_field_count"
    ] = document_status[
        "field_status"
    ].apply(
        lambda values: values.count("ADMIT")
    )
    document_status[
        "review_field_count"
    ] = document_status[
        "field_status"
    ].apply(
        lambda values: values.count("REVIEW")
    )
    document_status[
        "rejected_field_count"
    ] = document_status[
        "field_status"
    ].apply(
        lambda values: values.count("REJECT")
    )
    document_status[
        "not_evaluable_field_count"
    ] = document_status[
        "field_status"
    ].apply(
        lambda values: values.count(
            "NOT_EVALUABLE"
        )
    )
    document_status = document_status.drop(
        columns=["field_status"]
    )

    field_summary_rows: list[dict[str, Any]] = []

    for field_name, rule in FIELD_RULES.items():
        group = fields[
            fields["field_name"] == field_name
        ]

        field_summary_rows.append({
            "항목": rule["label_ko"],
            "전체합성본": int(len(group)),
            "평가가능": int(
                (
                    group["field_status"]
                    != "NOT_EVALUABLE"
                ).sum()
            ),
            "편입": int(
                (
                    group["field_status"]
                    == "ADMIT"
                ).sum()
            ),
            "검토": int(
                (
                    group["field_status"]
                    == "REVIEW"
                ).sum()
            ),
            "제외": int(
                (
                    group["field_status"]
                    == "REJECT"
                ).sum()
            ),
            "평가자료없음": int(
                (
                    group["field_status"]
                    == "NOT_EVALUABLE"
                ).sum()
            ),
            "평가가능중편입률": safe_rate(
                (
                    group["field_status"]
                    == "ADMIT"
                ).sum(),
                (
                    group["field_status"]
                    != "NOT_EVALUABLE"
                ).sum(),
            ),
            "평균점수": round(
                float(
                    group["score"]
                    .dropna()
                    .astype(float)
                    .mean()
                ),
                4,
            )
            if group["score"].replace(
                "",
                pd.NA,
            ).notna().any()
            else None,
        })

    field_summary = pd.DataFrame(
        field_summary_rows
    )

    def compact_summary(
        group_columns: list[str],
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []

        for key, group in fields.groupby(
            group_columns,
            dropna=False,
        ):
            if not isinstance(key, tuple):
                key = (key,)

            row = {
                column: key[index]
                for index, column in enumerate(
                    group_columns
                )
            }
            documents_in_group = group[
                "synthetic_sha256"
            ].nunique()
            documents_with_admit = group[
                group["field_status"] == "ADMIT"
            ]["synthetic_sha256"].nunique()

            row.update({
                "합성본": int(documents_in_group),
                "항목1개이상편입가능": int(
                    documents_with_admit
                ),
                "편입항목": int(
                    (
                        group["field_status"]
                        == "ADMIT"
                    ).sum()
                ),
                "검토항목": int(
                    (
                        group["field_status"]
                        == "REVIEW"
                    ).sum()
                ),
                "제외항목": int(
                    (
                        group["field_status"]
                        == "REJECT"
                    ).sum()
                ),
                "평가자료없는항목": int(
                    (
                        group["field_status"]
                        == "NOT_EVALUABLE"
                    ).sum()
                ),
            })
            rows.append(row)

        return pd.DataFrame(rows).sort_values(
            group_columns
        )

    profile_summary = compact_summary(
        ["augmentation_profile"]
    )
    institution_summary = compact_summary(
        ["institution"]
    )

    total_documents = int(
        fields["synthetic_sha256"].nunique()
    )
    documents_with_admitted_fields = int(
        admitted[
            "synthetic_sha256"
        ].nunique()
    )
    not_evaluable_documents = int(
        (
            document_status[
                "document_pack_status"
            ]
            == "NOT_EVALUABLE"
        ).sum()
    )

    if len(admitted) > 0:
        final_decision = (
            "전체 일괄 병합은 금지하고, "
            "편입 판정을 받은 항목만 학습 증강자료로 사용합니다."
        )
        reason = (
            "평가 가능한 항목은 대체로 잘 유지됐지만, "
            "평가용 라벨이 없는 문서가 있어 항목별 선별이 필요합니다."
        )
        machine_decision = "FIELD_LEVEL_ADMISSION"
    else:
        final_decision = (
            "현재 합성본은 학습 증강자료로 편입하지 않습니다."
        )
        reason = (
            "편입 기준을 충족한 핵심항목이 없습니다."
        )
        machine_decision = "NO_ADMISSION"

    summary = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "source_core_evaluation_report": str(
            core_report_root
        ),
        "output_root": str(output_root),
        "total_documents": total_documents,
        "documents_with_admitted_fields": (
            documents_with_admitted_fields
        ),
        "not_evaluable_document_count": (
            not_evaluable_documents
        ),
        "admitted_field_rows": int(
            len(admitted)
        ),
        "review_field_rows": int(
            (
                fields["field_status"]
                == "REVIEW"
            ).sum()
        ),
        "rejected_field_rows": int(
            (
                fields["field_status"]
                == "REJECT"
            ).sum()
        ),
        "not_evaluable_field_rows": int(
            len(not_evaluable)
        ),
        "final_decision": final_decision,
        "reason": reason,
        "machine_decision": (
            machine_decision
        ),
        "critical_correction": (
            "평가용 항목 후보가 없는 문서는 OCR 실패가 아니라 "
            "NOT_EVALUABLE로 분리했습니다."
        ),
        "training_policy": {
            "admit_only": (
                "field_status=ADMIT 항목만 증강 학습에 사용"
            ),
            "fold_lock": (
                "source_sha256 기준으로 원본과 합성본을 같은 Fold에 고정"
            ),
            "family_weight": (
                "원본과 편입 합성본 한 가족의 가중치 합을 1로 제한"
            ),
            "final_test": (
                "합성본은 최종 독립 테스트에서 제외"
            ),
            "automatic_merge": False,
        },
        "next_model_stage": (
            "4C-2 페이지/행/역할 분류 모델은 "
            "제품행 라벨 보강 후 실행"
        ),
    }

    fields.to_csv(
        output_root
        / "01_all_field_admission_results.csv",
        index=False,
        encoding="utf-8-sig",
    )
    admitted.to_csv(
        output_root
        / "02_admitted_training_fields.csv",
        index=False,
        encoding="utf-8-sig",
    )
    document_status.to_csv(
        output_root
        / "03_document_pack_status.csv",
        index=False,
        encoding="utf-8-sig",
    )
    review_reject.to_csv(
        output_root
        / "04_review_reject_fields.csv",
        index=False,
        encoding="utf-8-sig",
    )
    not_evaluable.to_csv(
        output_root
        / "05_not_evaluable_fields.csv",
        index=False,
        encoding="utf-8-sig",
    )
    field_summary.to_csv(
        output_root
        / "06_field_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    profile_summary.to_csv(
        output_root
        / "07_profile_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    institution_summary.to_csv(
        output_root
        / "08_institution_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    (
        output_root
        / "09_summary.json"
    ).write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    review_html = review_reject.copy()

    if not review_html.empty:
        review_html["기관"] = review_html[
            "institution"
        ]
        review_html["변형"] = review_html[
            "augmentation_profile"
        ]
        review_html["항목"] = review_html[
            "field_name_ko"
        ]
        review_html["판정"] = review_html[
            "field_status_ko"
        ]
        review_html["점수"] = review_html[
            "score"
        ]
        review_html["사유"] = review_html[
            "status_reason"
        ]
        review_html["파일"] = review_html[
            "synthetic_path"
        ].apply(
            lambda value: Path(value).name
        )

    make_easy_html(
        summary,
        field_summary,
        profile_summary,
        institution_summary,
        review_html,
        output_root
        / "10_easy_report.html",
    )

    (
        runtime_root
        / "reports"
        / "latest_synthetic_training_pack.txt"
    ).write_text(
        str(output_root),
        encoding="utf-8",
    )

    print("")
    print("합성 스캔 안전 편입 패키지 생성 완료")
    print(
        f"합성 스캔본              : "
        f"{total_documents}"
    )
    print(
        f"항목 1개 이상 편입 가능 : "
        f"{documents_with_admitted_fields}"
    )
    print(
        f"평가자료 없는 문서       : "
        f"{not_evaluable_documents}"
    )
    print(
        f"편입 항목                : "
        f"{len(admitted)}"
    )
    print(
        f"검토 항목                : "
        f"{summary['review_field_rows']}"
    )
    print(
        f"제외 항목                : "
        f"{summary['rejected_field_rows']}"
    )
    print(
        f"판단                     : "
        f"{final_decision}"
    )
    print(f"결과 폴더                : {output_root}")
    print("보기 쉬운 보고서         : 10_easy_report.html")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())