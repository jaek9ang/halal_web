from __future__ import annotations

import argparse
import html
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SCHEMA_VERSION = "product_ocr_bias_diagnostic_v1"
AUTO_STATUS = "AUTO_READY"
REVIEW_STATUSES = {"REVIEW_REQUIRED", "CANDIDATE_ONLY"}


def clean(value: Any) -> str:
    text = str(value or "").replace("\u00a0", " ").replace("\x00", " ")
    return " ".join(text.split()).strip()


def to_int(value: Any) -> int:
    try:
        return int(float(str(value or "0")))
    except (TypeError, ValueError):
        return 0


def to_float(value: Any) -> float:
    try:
        return float(str(value or "0"))
    except (TypeError, ValueError):
        return 0.0


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)

    return pd.read_csv(
        path,
        dtype=str,
        encoding="utf-8-sig",
    ).fillna("")


def load_cache_fallback(
    runtime_root: Path,
    sha256: str,
) -> dict[str, Any]:
    path = (
        runtime_root
        / "text_cache"
        / "combined"
        / f"{sha256}.json"
    )

    if not path.exists():
        return {}

    try:
        return json.loads(
            path.read_text(encoding="utf-8-sig")
        )
    except Exception:
        return {}


def derive_source_family(source_audit_status: str) -> str:
    status = clean(source_audit_status).upper()

    if status == "TEXT_DIRECT":
        return "NATIVE_TEXT"

    if status == "OCR_REQUIRED":
        return "OCR_REQUIRED"

    return "UNKNOWN"


def derive_source_subtype(row: pd.Series) -> str:
    family = clean(row.get("source_family"))

    if family == "NATIVE_TEXT":
        return "NATIVE_TEXT"

    if family != "OCR_REQUIRED":
        return "UNKNOWN"

    page_count = to_int(row.get("page_count"))
    native_pages = to_int(row.get("native_page_count"))
    ocr_pages = to_int(row.get("ocr_page_count"))

    if ocr_pages > 0 and native_pages > 0:
        return "HYBRID_OCR"

    if ocr_pages > 0 and (
        page_count == 0
        or ocr_pages >= page_count
    ):
        return "FULL_OCR"

    return "OCR_REQUIRED"


def derive_ocr_quality_bucket(row: pd.Series) -> str:
    family = clean(row.get("source_family"))

    if family == "NATIVE_TEXT":
        return "NATIVE_TEXT"

    if family != "OCR_REQUIRED":
        return "UNKNOWN"

    final_status = clean(row.get("final_status")).upper()
    ocr_pages = to_int(row.get("ocr_page_count"))
    success_pages = to_int(row.get("ocr_success_page_count"))
    failed_pages = to_int(row.get("ocr_failed_page_count"))
    confidence = to_float(row.get("mean_ocr_confidence"))

    if final_status != "READY":
        return "OCR_NOT_READY"

    if ocr_pages > 0 and success_pages == 0:
        return "OCR_FAILED"

    failed_ratio = (
        failed_pages / ocr_pages
        if ocr_pages
        else 0.0
    )

    if confidence >= 0.85 and failed_ratio == 0:
        return "OCR_HIGH"

    if confidence >= 0.65 and failed_ratio <= 0.20:
        return "OCR_MEDIUM"

    if confidence > 0:
        return "OCR_LOW"

    return "OCR_UNSCORED"


def enrich_ocr_manifest(
    ocr_frame: pd.DataFrame,
    runtime_root: Path,
    expected_sha: set[str],
) -> pd.DataFrame:
    frame = ocr_frame.copy()

    required_columns = [
        "sha256",
        "source_audit_status",
        "final_status",
        "page_count",
        "native_page_count",
        "ocr_page_count",
        "ocr_success_page_count",
        "ocr_failed_page_count",
        "normalized_text_length",
        "mean_ocr_confidence",
    ]

    for column in required_columns:
        if column not in frame.columns:
            frame[column] = ""

    known_sha = {
        clean(value)
        for value in frame["sha256"].tolist()
        if clean(value)
    }
    missing_sha = sorted(expected_sha - known_sha)

    fallback_rows: list[dict[str, Any]] = []

    for sha256 in missing_sha:
        payload = load_cache_fallback(
            runtime_root,
            sha256,
        )

        if not payload:
            continue

        fallback_rows.append({
            "sha256": sha256,
            "source_audit_status": clean(
                payload.get("source_audit_status")
            ),
            "final_status": clean(
                payload.get("final_status")
            ),
            "page_count": to_int(
                payload.get("page_count")
            ),
            "native_page_count": to_int(
                payload.get("native_page_count")
            ),
            "ocr_page_count": to_int(
                payload.get("ocr_page_count")
            ),
            "ocr_success_page_count": to_int(
                payload.get("ocr_success_page_count")
            ),
            "ocr_failed_page_count": to_int(
                payload.get("ocr_failed_page_count")
            ),
            "normalized_text_length": to_int(
                payload.get("normalized_text_length")
            ),
            "mean_ocr_confidence": to_float(
                payload.get("mean_ocr_confidence")
            ),
        })

    if fallback_rows:
        frame = pd.concat(
            [
                frame,
                pd.DataFrame(fallback_rows),
            ],
            ignore_index=True,
        )

    frame = frame.drop_duplicates(
        subset=["sha256"],
        keep="last",
    ).copy()

    frame["source_family"] = frame[
        "source_audit_status"
    ].map(derive_source_family)

    frame["source_subtype"] = frame.apply(
        derive_source_subtype,
        axis=1,
    )
    frame["ocr_quality_bucket"] = frame.apply(
        derive_ocr_quality_bucket,
        axis=1,
    )

    numeric_columns = [
        "page_count",
        "native_page_count",
        "ocr_page_count",
        "ocr_success_page_count",
        "ocr_failed_page_count",
        "normalized_text_length",
        "mean_ocr_confidence",
    ]

    for column in numeric_columns:
        frame[column] = pd.to_numeric(
            frame[column],
            errors="coerce",
        ).fillna(0)

    frame["ocr_page_ratio"] = np.where(
        frame["page_count"] > 0,
        frame["ocr_page_count"]
        / frame["page_count"],
        0.0,
    )
    frame["ocr_failed_page_ratio"] = np.where(
        frame["ocr_page_count"] > 0,
        frame["ocr_failed_page_count"]
        / frame["ocr_page_count"],
        0.0,
    )
    frame["text_length_per_page"] = np.where(
        frame["page_count"] > 0,
        frame["normalized_text_length"]
        / frame["page_count"],
        frame["normalized_text_length"],
    )

    return frame


def make_row_status_by_source(
    item_frame: pd.DataFrame,
) -> pd.DataFrame:
    grouped = (
        item_frame.groupby(
            ["source_family", "row_status"],
            dropna=False,
        )
        .size()
        .reset_index(name="row_count")
    )

    source_totals = (
        item_frame.groupby("source_family")
        .size()
        .to_dict()
    )
    status_totals = (
        item_frame.groupby("row_status")
        .size()
        .to_dict()
    )

    grouped["share_within_source"] = grouped.apply(
        lambda row: safe_rate(
            row["row_count"],
            source_totals.get(
                row["source_family"],
                0,
            ),
        ),
        axis=1,
    )
    grouped["share_of_status_total"] = grouped.apply(
        lambda row: safe_rate(
            row["row_count"],
            status_totals.get(
                row["row_status"],
                0,
            ),
        ),
        axis=1,
    )

    return grouped.sort_values(
        ["source_family", "row_status"]
    )


def make_document_summary(
    document_frame: pd.DataFrame,
    item_frame: pd.DataFrame,
) -> pd.DataFrame:
    item_aggregates = (
        item_frame.groupby("sha256")
        .agg(
            product_rows=("sha256", "size"),
            auto_ready_rows=(
                "row_status",
                lambda series: int(
                    (series == AUTO_STATUS).sum()
                ),
            ),
            review_rows=(
                "row_status",
                lambda series: int(
                    series.isin(REVIEW_STATUSES).sum()
                ),
            ),
            review_required_rows=(
                "row_status",
                lambda series: int(
                    (series == "REVIEW_REQUIRED").sum()
                ),
            ),
            candidate_only_rows=(
                "row_status",
                lambda series: int(
                    (series == "CANDIDATE_ONLY").sum()
                ),
            ),
        )
        .reset_index()
    )

    frame = document_frame.merge(
        item_aggregates,
        on="sha256",
        how="left",
    )

    count_columns = [
        "product_rows",
        "auto_ready_rows",
        "review_rows",
        "review_required_rows",
        "candidate_only_rows",
    ]

    for column in count_columns:
        frame[column] = pd.to_numeric(
            frame[column],
            errors="coerce",
        ).fillna(0).astype(int)

    frame["auto_ready_rate"] = np.where(
        frame["product_rows"] > 0,
        frame["auto_ready_rows"]
        / frame["product_rows"],
        0.0,
    )
    frame["review_rate"] = np.where(
        frame["product_rows"] > 0,
        frame["review_rows"]
        / frame["product_rows"],
        0.0,
    )
    frame["has_product_rows"] = (
        frame["product_rows"] > 0
    )
    frame["has_review_rows"] = (
        frame["review_rows"] > 0
    )

    return frame


def make_source_document_summary(
    document_frame: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for source_family, group in document_frame.groupby(
        "source_family",
        dropna=False,
    ):
        product_docs = group[
            group["has_product_rows"]
        ]

        rows.append({
            "source_family": source_family,
            "total_documents": int(
                group["sha256"].nunique()
            ),
            "documents_with_product_rows": int(
                product_docs["sha256"].nunique()
            ),
            "documents_with_auto_ready": int(
                group.loc[
                    group["auto_ready_rows"] > 0,
                    "sha256",
                ].nunique()
            ),
            "documents_with_review": int(
                group.loc[
                    group["review_rows"] > 0,
                    "sha256",
                ].nunique()
            ),
            "product_rows": int(
                group["product_rows"].sum()
            ),
            "auto_ready_rows": int(
                group["auto_ready_rows"].sum()
            ),
            "review_rows": int(
                group["review_rows"].sum()
            ),
            "auto_ready_rate": safe_rate(
                group["auto_ready_rows"].sum(),
                group["product_rows"].sum(),
            ),
            "review_rate": safe_rate(
                group["review_rows"].sum(),
                group["product_rows"].sum(),
            ),
            "mean_ocr_confidence": round(
                float(
                    pd.to_numeric(
                        group["mean_ocr_confidence"],
                        errors="coerce",
                    ).fillna(0).mean()
                ),
                4,
            ),
            "mean_text_length_per_page": round(
                float(
                    pd.to_numeric(
                        group["text_length_per_page"],
                        errors="coerce",
                    ).fillna(0).mean()
                ),
                1,
            ),
        })

    return pd.DataFrame(rows).sort_values(
        "source_family"
    )


def make_institution_bias(
    item_frame: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for (
        institution,
        source_family,
    ), group in item_frame.groupby(
        ["institution", "source_family"],
        dropna=False,
    ):
        rows.append({
            "institution": institution,
            "source_family": source_family,
            "documents": int(
                group["sha256"].nunique()
            ),
            "product_rows": int(len(group)),
            "auto_ready_rows": int(
                (group["row_status"] == AUTO_STATUS).sum()
            ),
            "review_required_rows": int(
                (
                    group["row_status"]
                    == "REVIEW_REQUIRED"
                ).sum()
            ),
            "candidate_only_rows": int(
                (
                    group["row_status"]
                    == "CANDIDATE_ONLY"
                ).sum()
            ),
            "auto_ready_rate": safe_rate(
                (group["row_status"] == AUTO_STATUS).sum(),
                len(group),
            ),
            "review_rate": safe_rate(
                group["row_status"].isin(
                    REVIEW_STATUSES
                ).sum(),
                len(group),
            ),
            "mean_ocr_confidence": round(
                float(
                    pd.to_numeric(
                        group["mean_ocr_confidence"],
                        errors="coerce",
                    ).fillna(0).mean()
                ),
                4,
            ),
        })

    return pd.DataFrame(rows).sort_values(
        ["institution", "source_family"]
    )


def make_quality_breakdown(
    item_frame: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for quality, group in item_frame.groupby(
        "ocr_quality_bucket",
        dropna=False,
    ):
        rows.append({
            "ocr_quality_bucket": quality,
            "documents": int(
                group["sha256"].nunique()
            ),
            "product_rows": int(len(group)),
            "auto_ready_rows": int(
                (group["row_status"] == AUTO_STATUS).sum()
            ),
            "review_rows": int(
                group["row_status"].isin(
                    REVIEW_STATUSES
                ).sum()
            ),
            "auto_ready_rate": safe_rate(
                (group["row_status"] == AUTO_STATUS).sum(),
                len(group),
            ),
            "review_rate": safe_rate(
                group["row_status"].isin(
                    REVIEW_STATUSES
                ).sum(),
                len(group),
            ),
            "mean_ocr_confidence": round(
                float(
                    pd.to_numeric(
                        group["mean_ocr_confidence"],
                        errors="coerce",
                    ).fillna(0).mean()
                ),
                4,
            ),
        })

    order = {
        "NATIVE_TEXT": 0,
        "OCR_HIGH": 1,
        "OCR_MEDIUM": 2,
        "OCR_LOW": 3,
        "OCR_UNSCORED": 4,
        "OCR_FAILED": 5,
        "OCR_NOT_READY": 6,
        "UNKNOWN": 7,
    }

    frame = pd.DataFrame(rows)
    frame["_order"] = frame[
        "ocr_quality_bucket"
    ].map(order).fillna(99)

    return frame.sort_values(
        "_order"
    ).drop(columns="_order")


def calculate_bias_diagnostic(
    item_frame: pd.DataFrame,
    document_frame: pd.DataFrame,
) -> dict[str, Any]:
    total_rows = int(len(item_frame))
    total_review = int(
        item_frame["row_status"].isin(
            REVIEW_STATUSES
        ).sum()
    )
    total_auto = int(
        (item_frame["row_status"] == AUTO_STATUS).sum()
    )

    ocr_rows = item_frame[
        item_frame["source_family"]
        == "OCR_REQUIRED"
    ]
    native_rows = item_frame[
        item_frame["source_family"]
        == "NATIVE_TEXT"
    ]

    ocr_review = int(
        ocr_rows["row_status"].isin(
            REVIEW_STATUSES
        ).sum()
    )
    native_review = int(
        native_rows["row_status"].isin(
            REVIEW_STATUSES
        ).sum()
    )
    ocr_auto = int(
        (ocr_rows["row_status"] == AUTO_STATUS).sum()
    )
    native_auto = int(
        (native_rows["row_status"] == AUTO_STATUS).sum()
    )

    ocr_auto_rate = safe_rate(
        ocr_auto,
        len(ocr_rows),
    )
    native_auto_rate = safe_rate(
        native_auto,
        len(native_rows),
    )
    auto_rate_gap = round(
        native_auto_rate - ocr_auto_rate,
        4,
    )

    ocr_review_share = safe_rate(
        ocr_review,
        total_review,
    )
    ocr_candidate_share = safe_rate(
        len(ocr_rows),
        total_rows,
    )
    ocr_document_share = safe_rate(
        document_frame.loc[
            document_frame["source_family"]
            == "OCR_REQUIRED",
            "sha256",
        ].nunique(),
        document_frame["sha256"].nunique(),
    )

    representation_gap = round(
        ocr_document_share
        - safe_rate(
            ocr_auto,
            total_auto,
        ),
        4,
    )

    if (
        ocr_review_share >= 0.65
        and auto_rate_gap >= 0.15
    ) or representation_gap >= 0.20:
        bias_level = "HIGH"
    elif (
        ocr_review_share >= 0.50
        or auto_rate_gap >= 0.10
        or representation_gap >= 0.10
    ):
        bias_level = "MEDIUM"
    else:
        bias_level = "LOW"

    if bias_level == "HIGH":
        recommendation = (
            "최종 제품행 모델 학습을 잠시 보류하고, "
            "OCR 대표 문서의 제품행 정답을 먼저 보강합니다."
        )
    elif bias_level == "MEDIUM":
        recommendation = (
            "기초 모델은 학습할 수 있으나 운영 확정 전 "
            "OCR 대표 문서 보강과 OCR 별도 성능 평가가 필요합니다."
        )
    else:
        recommendation = (
            "출처 편향이 크지 않습니다. "
            "출처를 고려한 GroupKFold로 실제 학습을 진행할 수 있습니다."
        )

    return {
        "total_product_rows": total_rows,
        "total_auto_ready_rows": total_auto,
        "total_review_rows": total_review,
        "native_product_rows": int(len(native_rows)),
        "ocr_product_rows": int(len(ocr_rows)),
        "native_auto_ready_rows": native_auto,
        "ocr_auto_ready_rows": ocr_auto,
        "native_review_rows": native_review,
        "ocr_review_rows": ocr_review,
        "native_auto_ready_rate": native_auto_rate,
        "ocr_auto_ready_rate": ocr_auto_rate,
        "auto_ready_rate_gap_native_minus_ocr": (
            auto_rate_gap
        ),
        "ocr_share_of_all_product_rows": (
            ocr_candidate_share
        ),
        "ocr_share_of_all_review_rows": (
            ocr_review_share
        ),
        "ocr_document_share": ocr_document_share,
        "ocr_share_of_all_auto_ready_rows": safe_rate(
            ocr_auto,
            total_auto,
        ),
        "ocr_training_representation_gap": (
            representation_gap
        ),
        "bias_level": bias_level,
        "recommendation": recommendation,
    }


def select_review_documents(
    document_frame: pd.DataFrame,
    max_per_institution: int = 5,
) -> pd.DataFrame:
    candidates = document_frame[
        (
            document_frame["source_family"]
            == "OCR_REQUIRED"
        )
        & (document_frame["review_rows"] > 0)
    ].copy()

    if candidates.empty:
        return candidates

    candidates["confidence_penalty"] = (
        1.0
        - pd.to_numeric(
            candidates["mean_ocr_confidence"],
            errors="coerce",
        ).fillna(0).clip(0, 1)
    )
    candidates["quality_penalty"] = candidates[
        "ocr_quality_bucket"
    ].map({
        "OCR_LOW": 3.0,
        "OCR_UNSCORED": 2.5,
        "OCR_MEDIUM": 1.5,
        "OCR_HIGH": 0.5,
        "OCR_FAILED": 4.0,
        "OCR_NOT_READY": 5.0,
    }).fillna(1.0)

    candidates["priority_score"] = (
        candidates["review_rows"] * 2.0
        + candidates["candidate_only_rows"] * 1.5
        + candidates["review_required_rows"] * 1.0
        + candidates["confidence_penalty"] * 5.0
        + candidates["quality_penalty"]
        + (1.0 - candidates["auto_ready_rate"]) * 4.0
    )

    candidates = candidates.sort_values(
        [
            "institution",
            "priority_score",
            "review_rows",
        ],
        ascending=[True, False, False],
    )

    selected_rows: list[pd.Series] = []

    for institution, group in candidates.groupby(
        "institution",
        sort=True,
    ):
        used_groups: set[str] = set()
        selected_count = 0

        for _, row in group.iterrows():
            validation_group = clean(
                row.get("validation_group")
            )

            if (
                validation_group
                and validation_group in used_groups
            ):
                continue

            selected_rows.append(row)
            used_groups.add(validation_group)
            selected_count += 1

            if selected_count >= max_per_institution:
                break

    selected = pd.DataFrame(selected_rows)

    if selected.empty:
        return selected

    selected = selected.sort_values(
        "priority_score",
        ascending=False,
    ).reset_index(drop=True)
    selected["overall_priority_rank"] = (
        selected.index + 1
    )
    selected["recommended_row_review_count"] = (
        selected["review_rows"]
        .clip(lower=1, upper=20)
        .astype(int)
    )
    selected["recommended_action"] = (
        "원본 PDF에서 제품명·품목별 인증번호 연결을 확인하고 "
        "대표 문서의 전체 제품행을 정답으로 확정"
    )
    selected["review_decision"] = ""
    selected["review_note"] = ""

    keep_columns = [
        "overall_priority_rank",
        "institution",
        "source_subtype",
        "ocr_quality_bucket",
        "file_name",
        "pdf_path",
        "sha256",
        "validation_group",
        "certificate_structure",
        "product_rows",
        "auto_ready_rows",
        "review_rows",
        "review_required_rows",
        "candidate_only_rows",
        "auto_ready_rate",
        "mean_ocr_confidence",
        "ocr_page_count",
        "page_count",
        "text_length_per_page",
        "priority_score",
        "recommended_row_review_count",
        "recommended_action",
        "review_decision",
        "review_note",
    ]

    return selected[
        [
            column
            for column in keep_columns
            if column in selected.columns
        ]
    ]


def select_priority_rows(
    item_frame: pd.DataFrame,
    selected_documents: pd.DataFrame,
) -> pd.DataFrame:
    if selected_documents.empty:
        return pd.DataFrame()

    selected_sha = set(
        selected_documents["sha256"].astype(str)
    )
    rows = item_frame[
        item_frame["sha256"].astype(str).isin(
            selected_sha
        )
        & item_frame["row_status"].isin(
            REVIEW_STATUSES
        )
    ].copy()

    if rows.empty:
        return rows

    rows["row_score_numeric"] = pd.to_numeric(
        rows["row_score"],
        errors="coerce",
    ).fillna(0)

    rows = rows.sort_values(
        [
            "institution",
            "sha256",
            "row_status",
            "row_score_numeric",
            "page",
            "row_anchor_line_no",
        ],
        ascending=[
            True,
            True,
            True,
            False,
            True,
            True,
        ],
    )

    rows["manual_decision"] = ""
    rows["corrected_product_name"] = ""
    rows["corrected_product_code"] = ""
    rows["corrected_halal_id"] = ""
    rows[
        "corrected_product_certificate_no"
    ] = ""
    rows["manual_note"] = ""

    return rows.drop(
        columns=["row_score_numeric"],
        errors="ignore",
    )


def save_charts(
    source_summary: pd.DataFrame,
    report_root: Path,
) -> None:
    if source_summary.empty:
        return

    chart = source_summary.set_index(
        "source_family"
    )

    plt.figure(figsize=(8, 5))
    plt.bar(
        chart.index,
        chart["auto_ready_rows"],
        label="AUTO_READY",
    )
    plt.bar(
        chart.index,
        chart["review_rows"],
        bottom=chart["auto_ready_rows"],
        label="Review",
    )
    plt.ylabel("Product row count")
    plt.title("Product row status by source type")
    plt.legend()
    plt.tight_layout()
    plt.savefig(
        report_root
        / "10_product_row_status_by_source.png",
        dpi=160,
    )
    plt.close()

    plt.figure(figsize=(8, 5))
    plt.bar(
        chart.index,
        chart["auto_ready_rate"],
    )
    plt.ylim(0, 1.05)
    plt.ylabel("AUTO_READY rate")
    plt.title("AUTO_READY rate by source type")

    for index, value in enumerate(
        chart["auto_ready_rate"].tolist()
    ):
        plt.text(
            index,
            min(1.01, float(value) + 0.02),
            f"{float(value):.1%}",
            ha="center",
        )

    plt.tight_layout()
    plt.savefig(
        report_root
        / "11_auto_ready_rate_by_source.png",
        dpi=160,
    )
    plt.close()


def create_html_report(
    summary: dict[str, Any],
    source_summary: pd.DataFrame,
    status_summary: pd.DataFrame,
    institution_bias: pd.DataFrame,
    quality_breakdown: pd.DataFrame,
    review_documents: pd.DataFrame,
    output_path: Path,
) -> None:
    diagnostic = summary["bias_diagnostic"]

    cards = [
        (
            "전체 제품행",
            diagnostic["total_product_rows"],
        ),
        (
            "OCR 제품행",
            diagnostic["ocr_product_rows"],
        ),
        (
            "검토 대상 중 OCR 비율",
            f"{diagnostic['ocr_share_of_all_review_rows']:.1%}",
        ),
        (
            "OCR 자동정답률",
            f"{diagnostic['ocr_auto_ready_rate']:.1%}",
        ),
        (
            "일반 PDF 자동정답률",
            f"{diagnostic['native_auto_ready_rate']:.1%}",
        ),
        (
            "편향 수준",
            diagnostic["bias_level"],
        ),
    ]

    card_html = "".join(
        "<div class='card'><div>"
        + html.escape(str(label))
        + "</div><div class='value'>"
        + html.escape(str(value))
        + "</div></div>"
        for label, value in cards
    )

    source_html = source_summary.to_html(
        index=False,
        escape=True,
    )
    status_html = status_summary.to_html(
        index=False,
        escape=True,
    )
    institution_html = institution_bias.to_html(
        index=False,
        escape=True,
    )
    quality_html = quality_breakdown.to_html(
        index=False,
        escape=True,
    )
    review_html = (
        review_documents.head(100).to_html(
            index=False,
            escape=True,
        )
        if not review_documents.empty
        else "<p>선정된 OCR 대표 검토 문서가 없습니다.</p>"
    )

    text = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>제품행 OCR 편향 진단</title>
<style>
body {{
    font-family: Arial, "Malgun Gothic", sans-serif;
    margin: 28px;
    color: #1f2937;
    background: #f8fafc;
}}
.grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(175px, 1fr));
    gap: 12px;
}}
.card, .section {{
    background: white;
    border: 1px solid #dbe3ec;
    border-radius: 10px;
    padding: 16px;
    margin: 14px 0;
}}
.value {{
    font-size: 24px;
    font-weight: 700;
    margin-top: 6px;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    font-size: 12px;
}}
th, td {{
    border-bottom: 1px solid #e5e7eb;
    padding: 7px;
    text-align: left;
    vertical-align: top;
}}
img {{
    width: 100%;
    max-width: 900px;
    height: auto;
}}
.note {{
    color: #64748b;
    font-size: 14px;
}}
.callout {{
    border-left: 4px solid #64748b;
    padding: 12px 16px;
    background: white;
}}
</style>
</head>
<body>
<h1>제품행 후보의 스캔본·OCR 편향 진단</h1>
<p class="note">
기존 4C 제품행 후보에 OCR 출처와 품질 정보를 연결하여,
검토 대상이 스캔본에 집중되는지 확인한 결과입니다.
</p>
<div class="grid">{card_html}</div>
<div class="callout">
<strong>판단:</strong>
{html.escape(diagnostic["recommendation"])}
</div>
<div class="section">
<h2>출처별 문서·제품행 현황</h2>
{source_html}
</div>
<div class="section">
<h2>출처별 상태 교차표</h2>
{status_html}
</div>
<div class="section">
<h2>출처별 AUTO_READY 비율</h2>
<img src="11_auto_ready_rate_by_source.png" alt="출처별 AUTO_READY 비율">
</div>
<div class="section">
<h2>OCR 품질별 제품행 결과</h2>
{quality_html}
</div>
<div class="section">
<h2>기관 × 출처 편향</h2>
{institution_html}
</div>
<div class="section">
<h2>우선 검토할 OCR 대표 문서</h2>
{review_html}
</div>
</body>
</html>"""

    output_path.write_text(
        text,
        encoding="utf-8",
    )


def write_json(
    path: Path,
    payload: Any,
) -> None:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root",
        required=True,
    )
    parser.add_argument(
        "--runtime-root",
        required=True,
    )
    parser.add_argument(
        "--product-report-root",
        required=True,
    )
    parser.add_argument(
        "--ocr-report-root",
        required=True,
    )
    args = parser.parse_args()

    project_root = Path(
        args.project_root
    ).resolve()
    runtime_root = Path(
        args.runtime_root
    ).resolve()
    product_report_root = Path(
        args.product_report_root
    ).resolve()
    ocr_report_root = Path(
        args.ocr_report_root
    ).resolve()

    document_path = (
        product_report_root
        / "01_document_structure_candidates.csv"
    )
    item_path = (
        product_report_root
        / "02_product_item_candidates.csv"
    )
    ocr_path = (
        ocr_report_root
        / "01_ocr_document_results.csv"
    )

    document_frame = read_csv(document_path)
    item_frame = read_csv(item_path)
    ocr_frame = read_csv(ocr_path)

    expected_sha = set(
        document_frame["sha256"].astype(str)
    )
    ocr_manifest = enrich_ocr_manifest(
        ocr_frame,
        runtime_root,
        expected_sha,
    )

    ocr_columns = [
        "sha256",
        "source_audit_status",
        "source_family",
        "source_subtype",
        "ocr_quality_bucket",
        "final_status",
        "page_count",
        "native_page_count",
        "ocr_page_count",
        "ocr_success_page_count",
        "ocr_failed_page_count",
        "normalized_text_length",
        "mean_ocr_confidence",
        "ocr_page_ratio",
        "ocr_failed_page_ratio",
        "text_length_per_page",
    ]

    document_enriched = document_frame.merge(
        ocr_manifest[ocr_columns],
        on="sha256",
        how="left",
    )
    item_enriched = item_frame.merge(
        ocr_manifest[ocr_columns],
        on="sha256",
        how="left",
    )

    for frame in (
        document_enriched,
        item_enriched,
    ):
        frame["source_family"] = frame[
            "source_family"
        ].fillna("UNKNOWN")
        frame["source_subtype"] = frame[
            "source_subtype"
        ].fillna("UNKNOWN")
        frame["ocr_quality_bucket"] = frame[
            "ocr_quality_bucket"
        ].fillna("UNKNOWN")

    document_enriched = make_document_summary(
        document_enriched,
        item_enriched,
    )
    source_document_summary = (
        make_source_document_summary(
            document_enriched
        )
    )
    row_status_by_source = (
        make_row_status_by_source(
            item_enriched
        )
    )
    institution_bias = make_institution_bias(
        item_enriched
    )
    quality_breakdown = make_quality_breakdown(
        item_enriched
    )
    bias_diagnostic = calculate_bias_diagnostic(
        item_enriched,
        document_enriched,
    )
    review_documents = select_review_documents(
        document_enriched
    )
    priority_rows = select_priority_rows(
        item_enriched,
        review_documents,
    )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    report_root = (
        runtime_root
        / "reports"
        / f"product_ocr_bias_diagnostic_{stamp}"
    )
    report_root.mkdir(
        parents=True,
        exist_ok=False,
    )

    document_enriched.to_csv(
        report_root
        / "01_documents_with_ocr_source.csv",
        index=False,
        encoding="utf-8-sig",
    )
    item_enriched.to_csv(
        report_root
        / "02_product_items_with_ocr_source.csv",
        index=False,
        encoding="utf-8-sig",
    )
    row_status_by_source.to_csv(
        report_root
        / "03_row_status_by_source.csv",
        index=False,
        encoding="utf-8-sig",
    )
    source_document_summary.to_csv(
        report_root
        / "04_source_document_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    institution_bias.to_csv(
        report_root
        / "05_institution_source_bias.csv",
        index=False,
        encoding="utf-8-sig",
    )
    quality_breakdown.to_csv(
        report_root
        / "06_ocr_quality_breakdown.csv",
        index=False,
        encoding="utf-8-sig",
    )
    review_documents.to_csv(
        report_root
        / "07_priority_ocr_review_documents.csv",
        index=False,
        encoding="utf-8-sig",
    )
    priority_rows.to_csv(
        report_root
        / "08_priority_ocr_review_rows.csv",
        index=False,
        encoding="utf-8-sig",
    )

    source_counts = Counter(
        document_enriched[
            "source_family"
        ].astype(str)
    )
    source_subtype_counts = Counter(
        document_enriched[
            "source_subtype"
        ].astype(str)
    )
    quality_counts = Counter(
        document_enriched[
            "ocr_quality_bucket"
        ].astype(str)
    )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "run_id": stamp,
        "created_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "project_root": str(project_root),
        "runtime_root": str(runtime_root),
        "product_report_root": str(
            product_report_root
        ),
        "ocr_report_root": str(
            ocr_report_root
        ),
        "report_root": str(report_root),
        "total_documents": int(
            document_enriched[
                "sha256"
            ].nunique()
        ),
        "total_product_rows": int(
            len(item_enriched)
        ),
        "source_document_counts": dict(
            source_counts
        ),
        "source_subtype_document_counts": dict(
            source_subtype_counts
        ),
        "ocr_quality_document_counts": dict(
            quality_counts
        ),
        "bias_diagnostic": bias_diagnostic,
        "priority_review_document_count": int(
            len(review_documents)
        ),
        "priority_review_row_count": int(
            len(priority_rows)
        ),
        "training_policy": {
            "positive": (
                "AUTO_READY만 양성 학습 후보로 사용"
            ),
            "negative": (
                "명백한 비제품 문장만 음성으로 사용"
            ),
            "unknown": (
                "REVIEW_REQUIRED와 CANDIDATE_ONLY는 "
                "확인 전까지 학습에서 제외"
            ),
            "validation": (
                "validation_group 유지 + 기관 및 "
                "NATIVE_TEXT/OCR_REQUIRED 분포를 고려한 분할"
            ),
            "reporting": (
                "전체, NATIVE_TEXT, OCR_REQUIRED, 기관별 성능을 별도 보고"
            ),
        },
        "next_step": (
            "07_priority_ocr_review_documents.csv에서 대표 OCR 문서를 확인하고, "
            "편향 수준이 LOW이면 4C-2 실제 학습으로 진행합니다. "
            "MEDIUM/HIGH이면 대표 문서의 제품행 정답을 보강한 뒤 학습합니다."
        ),
    }

    write_json(
        report_root
        / "09_bias_diagnostic_summary.json",
        summary,
    )

    save_charts(
        source_document_summary,
        report_root,
    )
    create_html_report(
        summary,
        source_document_summary,
        row_status_by_source,
        institution_bias,
        quality_breakdown,
        review_documents,
        report_root
        / "12_ocr_bias_report.html",
    )

    latest_pointer = (
        runtime_root
        / "reports"
        / "latest_product_ocr_bias_diagnostic.txt"
    )
    latest_pointer.write_text(
        str(report_root),
        encoding="utf-8",
    )

    diagnostic = bias_diagnostic

    print("")
    print("4C-1 스캔본/OCR 편향 진단 완료")
    print(
        f"전체 제품행             : "
        f"{diagnostic['total_product_rows']}"
    )
    print(
        f"OCR 제품행              : "
        f"{diagnostic['ocr_product_rows']}"
    )
    print(
        f"OCR AUTO_READY          : "
        f"{diagnostic['ocr_auto_ready_rows']}"
    )
    print(
        f"OCR 검토 대상           : "
        f"{diagnostic['ocr_review_rows']}"
    )
    print(
        f"검토 대상 중 OCR 비율   : "
        f"{diagnostic['ocr_share_of_all_review_rows']:.1%}"
    )
    print(
        f"일반 PDF AUTO_READY율   : "
        f"{diagnostic['native_auto_ready_rate']:.1%}"
    )
    print(
        f"OCR AUTO_READY율        : "
        f"{diagnostic['ocr_auto_ready_rate']:.1%}"
    )
    print(
        f"편향 수준               : "
        f"{diagnostic['bias_level']}"
    )
    print(
        f"판단                    : "
        f"{diagnostic['recommendation']}"
    )
    print(f"보고서                  : {report_root}")
    print("")
    print("확인 파일")
    print(" - 09_bias_diagnostic_summary.json")
    print(" - 03_row_status_by_source.csv")
    print(" - 04_source_document_summary.csv")
    print(" - 05_institution_source_bias.csv")
    print(" - 07_priority_ocr_review_documents.csv")
    print(" - 08_priority_ocr_review_rows.csv")
    print(" - 12_ocr_bias_report.html")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())