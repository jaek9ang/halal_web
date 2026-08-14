from __future__ import annotations

import argparse
import csv
import html
import io
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

import fitz
import numpy as np
import pandas as pd
from PIL import Image


SCHEMA_VERSION = "synthetic_scan_ocr_evaluation_v1"

TOKEN_PATTERN = re.compile(
    r"[^\W_][\w./#()+:@&-]*",
    flags=re.UNICODE,
)
CRITICAL_TOKEN_PATTERN = re.compile(
    r"(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9][A-Za-z0-9./#()+:@&_-]*"
)
DATE_TOKEN_PATTERN = re.compile(
    r"(?:\d{1,4}[-./]\d{1,2}[-./]\d{1,4})"
)


def clean(value: Any) -> str:
    return " ".join(
        str(value or "")
        .replace("\u00a0", " ")
        .replace("\x00", " ")
        .split()
    ).strip()


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_rate(
    numerator: int | float,
    denominator: int | float,
) -> float:
    if not denominator:
        return 0.0
    return round(
        float(numerator) / float(denominator),
        4,
    )


def normalize_text(text: str) -> str:
    text = str(text or "").upper()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    return [
        token.upper()
        for token in TOKEN_PATTERN.findall(
            str(text or "")
        )
        if len(token.strip()) >= 2
    ]


def multiset_recall(
    expected: Iterable[str],
    observed: Iterable[str],
) -> float:
    expected_counter = Counter(expected)
    observed_counter = Counter(observed)

    expected_total = sum(
        expected_counter.values()
    )

    if expected_total == 0:
        return 1.0

    matched = sum(
        (
            expected_counter
            & observed_counter
        ).values()
    )

    return matched / expected_total


def multiset_precision(
    expected: Iterable[str],
    observed: Iterable[str],
) -> float:
    expected_counter = Counter(expected)
    observed_counter = Counter(observed)

    observed_total = sum(
        observed_counter.values()
    )

    if observed_total == 0:
        return 0.0

    matched = sum(
        (
            expected_counter
            & observed_counter
        ).values()
    )

    return matched / observed_total


def f1_score(
    precision: float,
    recall: float,
) -> float:
    if precision + recall == 0:
        return 0.0

    return (
        2.0
        * precision
        * recall
        / (precision + recall)
    )


def extract_critical_tokens(
    tokens: Iterable[str],
) -> list[str]:
    result: list[str] = []

    for token in tokens:
        if CRITICAL_TOKEN_PATTERN.fullmatch(
            token
        ):
            result.append(token)
            continue

        if DATE_TOKEN_PATTERN.fullmatch(
            token
        ):
            result.append(token)

    return result


def extract_number_like_tokens(
    tokens: Iterable[str],
) -> list[str]:
    return [
        token
        for token in tokens
        if any(character.isdigit() for character in token)
    ]


def load_rapidocr() -> tuple[Any, str]:
    errors: list[str] = []

    try:
        from rapidocr_onnxruntime import RapidOCR

        return RapidOCR(), "rapidocr_onnxruntime"
    except Exception as exc:
        errors.append(
            f"rapidocr_onnxruntime: {exc!r}"
        )

    try:
        from rapidocr import RapidOCR

        return RapidOCR(), "rapidocr"
    except Exception as exc:
        errors.append(
            f"rapidocr: {exc!r}"
        )

    raise RuntimeError(
        "RapidOCR 로드 실패: "
        + " | ".join(errors)
    )


def parse_rapidocr_result(
    raw_result: Any,
) -> list[tuple[str, float]]:
    payload = raw_result

    if isinstance(payload, tuple):
        payload = payload[0]

    if hasattr(payload, "txts"):
        texts = list(
            getattr(payload, "txts") or []
        )
        scores = list(
            getattr(payload, "scores") or []
        )

        return [
            (
                clean(text),
                safe_float(
                    scores[index]
                    if index < len(scores)
                    else 0.0
                ),
            )
            for index, text in enumerate(texts)
            if clean(text)
        ]

    if hasattr(payload, "text"):
        text_value = clean(
            getattr(payload, "text")
        )
        score_value = safe_float(
            getattr(payload, "score", 0.0)
        )

        return (
            [(text_value, score_value)]
            if text_value
            else []
        )

    if isinstance(payload, dict):
        texts = (
            payload.get("txts")
            or payload.get("texts")
            or payload.get("text")
            or []
        )
        scores = (
            payload.get("scores")
            or payload.get("confidence")
            or []
        )

        if isinstance(texts, str):
            texts = [texts]

        if not isinstance(scores, list):
            scores = [scores]

        return [
            (
                clean(text),
                safe_float(
                    scores[index]
                    if index < len(scores)
                    else 0.0
                ),
            )
            for index, text in enumerate(texts)
            if clean(text)
        ]

    results: list[tuple[str, float]] = []

    if isinstance(payload, (list, tuple)):
        for item in payload:
            if not isinstance(
                item,
                (list, tuple),
            ):
                continue

            if len(item) >= 3:
                text = clean(item[1])
                score = safe_float(item[2])
            elif len(item) >= 2:
                text = clean(item[0])
                score = safe_float(item[1])
            else:
                continue

            if text:
                results.append(
                    (text, score)
                )

    return results


def read_native_pdf_text(
    pdf_path: Path,
) -> tuple[str, int]:
    pages: list[str] = []

    with fitz.open(pdf_path) as document:
        for page in document:
            pages.append(
                page.get_text("text")
            )

    return "\n".join(pages), len(pages)


def render_page(
    page: fitz.Page,
    dpi: int,
) -> np.ndarray:
    pixmap = page.get_pixmap(
        dpi=dpi,
        colorspace=fitz.csRGB,
        alpha=False,
        annots=True,
    )
    image = Image.frombytes(
        "RGB",
        (pixmap.width, pixmap.height),
        pixmap.samples,
    )
    return np.asarray(image)


def run_ocr_on_pdf(
    engine: Any,
    pdf_path: Path,
    render_dpi: int,
) -> dict[str, Any]:
    page_texts: list[str] = []
    page_rows: list[dict[str, Any]] = []
    all_scores: list[float] = []

    with fitz.open(pdf_path) as document:
        for page_index, page in enumerate(
            document,
            start=1,
        ):
            try:
                image_array = render_page(
                    page,
                    render_dpi,
                )
                raw_result = engine(
                    image_array
                )
                items = parse_rapidocr_result(
                    raw_result
                )
                page_text = "\n".join(
                    text
                    for text, _score in items
                )
                scores = [
                    score
                    for _text, score in items
                    if score > 0
                ]

                page_texts.append(page_text)
                all_scores.extend(scores)
                page_rows.append({
                    "page": page_index,
                    "status": (
                        "READY"
                        if page_text
                        else "EMPTY"
                    ),
                    "line_count": len(items),
                    "text_length": len(page_text),
                    "mean_confidence": round(
                        statistics.mean(scores),
                        4,
                    ) if scores else 0.0,
                    "error": "",
                })
            except Exception as exc:
                page_texts.append("")
                page_rows.append({
                    "page": page_index,
                    "status": "ERROR",
                    "line_count": 0,
                    "text_length": 0,
                    "mean_confidence": 0.0,
                    "error": repr(exc),
                })

    successful_pages = sum(
        row["status"] == "READY"
        for row in page_rows
    )
    error_pages = sum(
        row["status"] == "ERROR"
        for row in page_rows
    )

    return {
        "text": "\n".join(page_texts),
        "page_count": len(page_rows),
        "successful_pages": successful_pages,
        "empty_pages": sum(
            row["status"] == "EMPTY"
            for row in page_rows
        ),
        "error_pages": error_pages,
        "page_success_rate": safe_rate(
            successful_pages,
            len(page_rows),
        ),
        "mean_confidence": round(
            statistics.mean(all_scores),
            4,
        ) if all_scores else 0.0,
        "page_details": page_rows,
    }


def assess_row(
    token_recall: float,
    critical_recall: float,
    number_recall: float,
    page_success_rate: float,
    mean_confidence: float,
) -> tuple[str, list[str]]:
    reasons: list[str] = []

    if token_recall < 0.80:
        reasons.append(
            f"token_recall={token_recall:.3f}"
        )

    if critical_recall < 0.85:
        reasons.append(
            f"critical_recall={critical_recall:.3f}"
        )

    if number_recall < 0.85:
        reasons.append(
            f"number_recall={number_recall:.3f}"
        )

    if page_success_rate < 1.0:
        reasons.append(
            f"page_success_rate={page_success_rate:.3f}"
        )

    if mean_confidence < 0.85:
        reasons.append(
            f"mean_confidence={mean_confidence:.3f}"
        )

    if (
        token_recall >= 0.85
        and critical_recall >= 0.90
        and number_recall >= 0.90
        and page_success_rate == 1.0
        and mean_confidence >= 0.90
    ):
        return "PASS", reasons

    if (
        token_recall >= 0.70
        and critical_recall >= 0.75
        and number_recall >= 0.75
        and page_success_rate >= 0.90
        and mean_confidence >= 0.80
    ):
        return "REVIEW", reasons

    return "FAIL", reasons


def summarize_group(
    frame: pd.DataFrame,
    group_columns: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for group_key, group in frame.groupby(
        group_columns,
        dropna=False,
    ):
        if not isinstance(
            group_key,
            tuple,
        ):
            group_key = (group_key,)

        row = {
            column: group_key[index]
            for index, column in enumerate(
                group_columns
            )
        }

        row.update({
            "documents": int(len(group)),
            "source_documents": int(
                group["source_sha256"].nunique()
            ),
            "pass_count": int(
                (group["evaluation_status"] == "PASS").sum()
            ),
            "review_count": int(
                (group["evaluation_status"] == "REVIEW").sum()
            ),
            "fail_count": int(
                (group["evaluation_status"] == "FAIL").sum()
            ),
            "pass_rate": safe_rate(
                (
                    group["evaluation_status"]
                    == "PASS"
                ).sum(),
                len(group),
            ),
            "mean_token_recall": round(
                float(
                    group["token_recall"].mean()
                ),
                4,
            ),
            "mean_critical_token_recall": round(
                float(
                    group[
                        "critical_token_recall"
                    ].mean()
                ),
                4,
            ),
            "mean_number_token_recall": round(
                float(
                    group[
                        "number_token_recall"
                    ].mean()
                ),
                4,
            ),
            "mean_token_f1": round(
                float(
                    group["token_f1"].mean()
                ),
                4,
            ),
            "mean_ocr_confidence": round(
                float(
                    group[
                        "mean_ocr_confidence"
                    ].mean()
                ),
                4,
            ),
            "mean_page_success_rate": round(
                float(
                    group[
                        "page_success_rate"
                    ].mean()
                ),
                4,
            ),
        })

        rows.append(row)

    return pd.DataFrame(rows).sort_values(
        group_columns
    )


def create_html_report(
    summary: dict[str, Any],
    profile_summary: pd.DataFrame,
    institution_summary: pd.DataFrame,
    low_quality: pd.DataFrame,
    output_path: Path,
) -> None:
    decision = summary[
        "overall_training_decision"
    ]

    cards = [
        (
            "합성 PDF",
            summary["total_synthetic_pdfs"],
        ),
        (
            "PASS",
            summary["pass_count"],
        ),
        (
            "REVIEW",
            summary["review_count"],
        ),
        (
            "FAIL",
            summary["fail_count"],
        ),
        (
            "평균 Token Recall",
            f"{summary['mean_token_recall']:.1%}",
        ),
        (
            "학습 판단",
            decision,
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

    profile_html = profile_summary.to_html(
        index=False,
        escape=True,
    )
    institution_html = institution_summary.to_html(
        index=False,
        escape=True,
    )
    low_quality_html = (
        low_quality.head(100).to_html(
            index=False,
            escape=True,
        )
        if not low_quality.empty
        else "<p>REVIEW 또는 FAIL 문서가 없습니다.</p>"
    )

    text = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>합성 스캔 OCR 평가</title>
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
.callout {{
    border-left: 4px solid #64748b;
    padding: 12px 16px;
    background: white;
}}
.note {{
    color: #64748b;
    font-size: 14px;
}}
</style>
</head>
<body>
<h1>합성 스캔 PDF OCR 품질 평가</h1>
<p class="note">
원본 텍스트 PDF와 합성 이미지 PDF의 RapidOCR 결과를 비교했습니다.
</p>
<div class="grid">{card_html}</div>
<div class="callout">
<strong>판단:</strong>
{html.escape(summary["recommendation"])}
</div>
<div class="section">
<h2>변형 프로필별 결과</h2>
{profile_html}
</div>
<div class="section">
<h2>기관별 결과</h2>
{institution_html}
</div>
<div class="section">
<h2>REVIEW / FAIL 문서</h2>
{low_quality_html}
</div>
</body>
</html>"""

    output_path.write_text(
        text,
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runtime-root",
        required=True,
    )
    parser.add_argument(
        "--synthetic-root",
        required=True,
    )
    parser.add_argument(
        "--render-dpi",
        type=int,
        default=220,
    )
    args = parser.parse_args()

    runtime_root = Path(
        args.runtime_root
    ).resolve()
    synthetic_root = Path(
        args.synthetic_root
    ).resolve()
    manifest_path = (
        synthetic_root
        / "synthetic_scan_manifest.csv"
    )

    manifest = pd.read_csv(
        manifest_path,
        dtype=str,
        encoding="utf-8-sig",
    ).fillna("")

    required_columns = {
        "institution",
        "source_path",
        "synthetic_path",
        "source_sha256",
        "synthetic_sha256",
        "validation_group",
        "augmentation_profile",
    }
    missing_columns = (
        required_columns
        - set(manifest.columns)
    )

    if missing_columns:
        raise RuntimeError(
            "manifest 필수 열 누락: "
            + ", ".join(
                sorted(missing_columns)
            )
        )

    engine, engine_name = load_rapidocr()

    run_stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    report_root = (
        runtime_root
        / "reports"
        / f"synthetic_scan_ocr_eval_{run_stamp}"
    )
    report_root.mkdir(
        parents=True,
        exist_ok=False,
    )

    result_rows: list[dict[str, Any]] = []
    page_rows: list[dict[str, Any]] = []
    source_cache: dict[str, tuple[str, int]] = {}

    total = len(manifest)

    for index, row in manifest.iterrows():
        institution = clean(
            row["institution"]
        )
        source_path = Path(
            row["source_path"]
        )
        synthetic_path = Path(
            row["synthetic_path"]
        )
        profile = clean(
            row["augmentation_profile"]
        )

        print(
            f"[{index + 1}/{total}] "
            f"{institution} | "
            f"{profile} | "
            f"{synthetic_path.name}"
        )

        if not source_path.exists():
            raise FileNotFoundError(
                source_path
            )

        if not synthetic_path.exists():
            raise FileNotFoundError(
                synthetic_path
            )

        source_key = str(source_path)

        if source_key not in source_cache:
            source_cache[source_key] = (
                read_native_pdf_text(
                    source_path
                )
            )

        source_text, source_pages = (
            source_cache[source_key]
        )
        ocr_result = run_ocr_on_pdf(
            engine,
            synthetic_path,
            args.render_dpi,
        )
        observed_text = ocr_result["text"]

        source_normalized = normalize_text(
            source_text
        )
        observed_normalized = normalize_text(
            observed_text
        )

        source_tokens = tokenize(
            source_text
        )
        observed_tokens = tokenize(
            observed_text
        )
        source_critical = extract_critical_tokens(
            source_tokens
        )
        observed_critical = extract_critical_tokens(
            observed_tokens
        )
        source_numbers = extract_number_like_tokens(
            source_tokens
        )
        observed_numbers = extract_number_like_tokens(
            observed_tokens
        )

        token_recall = multiset_recall(
            source_tokens,
            observed_tokens,
        )
        token_precision = multiset_precision(
            source_tokens,
            observed_tokens,
        )
        token_f1 = f1_score(
            token_precision,
            token_recall,
        )
        critical_recall = multiset_recall(
            source_critical,
            observed_critical,
        )
        number_recall = multiset_recall(
            source_numbers,
            observed_numbers,
        )

        char_similarity = SequenceMatcher(
            None,
            source_normalized[:100000],
            observed_normalized[:100000],
            autojunk=False,
        ).ratio()

        status, reasons = assess_row(
            token_recall,
            critical_recall,
            number_recall,
            ocr_result[
                "page_success_rate"
            ],
            ocr_result[
                "mean_confidence"
            ],
        )

        result_rows.append({
            "institution": institution,
            "augmentation_profile": profile,
            "source_path": str(source_path),
            "synthetic_path": str(
                synthetic_path
            ),
            "source_sha256": clean(
                row["source_sha256"]
            ),
            "synthetic_sha256": clean(
                row["synthetic_sha256"]
            ),
            "validation_group": clean(
                row["validation_group"]
            ),
            "source_page_count": source_pages,
            "synthetic_page_count": (
                ocr_result["page_count"]
            ),
            "successful_pages": (
                ocr_result[
                    "successful_pages"
                ]
            ),
            "empty_pages": (
                ocr_result["empty_pages"]
            ),
            "error_pages": (
                ocr_result["error_pages"]
            ),
            "page_success_rate": (
                ocr_result[
                    "page_success_rate"
                ]
            ),
            "mean_ocr_confidence": (
                ocr_result[
                    "mean_confidence"
                ]
            ),
            "source_text_length": len(
                source_text
            ),
            "ocr_text_length": len(
                observed_text
            ),
            "text_length_ratio": safe_rate(
                len(observed_text),
                len(source_text),
            ),
            "char_similarity": round(
                char_similarity,
                4,
            ),
            "source_token_count": len(
                source_tokens
            ),
            "ocr_token_count": len(
                observed_tokens
            ),
            "token_precision": round(
                token_precision,
                4,
            ),
            "token_recall": round(
                token_recall,
                4,
            ),
            "token_f1": round(
                token_f1,
                4,
            ),
            "critical_source_token_count": len(
                source_critical
            ),
            "critical_token_recall": round(
                critical_recall,
                4,
            ),
            "number_source_token_count": len(
                source_numbers
            ),
            "number_token_recall": round(
                number_recall,
                4,
            ),
            "evaluation_status": status,
            "evaluation_reasons": " | ".join(
                reasons
            ),
            "ocr_engine": engine_name,
            "render_dpi": args.render_dpi,
        })

        for page_detail in ocr_result[
            "page_details"
        ]:
            page_rows.append({
                "institution": institution,
                "augmentation_profile": profile,
                "source_sha256": clean(
                    row["source_sha256"]
                ),
                "synthetic_sha256": clean(
                    row["synthetic_sha256"]
                ),
                "synthetic_path": str(
                    synthetic_path
                ),
                **page_detail,
            })

    results = pd.DataFrame(
        result_rows
    )
    pages = pd.DataFrame(
        page_rows
    )

    numeric_columns = [
        "page_success_rate",
        "mean_ocr_confidence",
        "text_length_ratio",
        "char_similarity",
        "token_precision",
        "token_recall",
        "token_f1",
        "critical_token_recall",
        "number_token_recall",
    ]

    for column in numeric_columns:
        results[column] = pd.to_numeric(
            results[column],
            errors="coerce",
        ).fillna(0)

    profile_summary = summarize_group(
        results,
        ["augmentation_profile"],
    )
    institution_summary = summarize_group(
        results,
        ["institution"],
    )
    institution_profile_summary = (
        summarize_group(
            results,
            [
                "institution",
                "augmentation_profile",
            ],
        )
    )

    low_quality = results[
        results["evaluation_status"]
        .isin(["REVIEW", "FAIL"])
    ].sort_values(
        [
            "evaluation_status",
            "token_recall",
            "critical_token_recall",
        ],
        ascending=[
            True,
            True,
            True,
        ],
    )

    pass_count = int(
        (
            results["evaluation_status"]
            == "PASS"
        ).sum()
    )
    review_count = int(
        (
            results["evaluation_status"]
            == "REVIEW"
        ).sum()
    )
    fail_count = int(
        (
            results["evaluation_status"]
            == "FAIL"
        ).sum()
    )
    pass_rate = safe_rate(
        pass_count,
        len(results),
    )

    if (
        fail_count == 0
        and pass_rate >= 0.90
    ):
        overall_decision = (
            "KEEP_BOTH_PROFILES"
        )
        recommendation = (
            "SCAN_A_CLEAN과 SCAN_B_OFFICE를 모두 "
            "학습 증강 후보로 사용할 수 있습니다."
        )
    elif (
        fail_count <= max(
            2,
            math.ceil(
                len(results) * 0.10
            ),
        )
        and pass_rate >= 0.70
    ):
        overall_decision = (
            "KEEP_AFTER_REVIEW"
        )
        recommendation = (
            "대부분 사용할 수 있으나 REVIEW/FAIL 문서를 제외하거나 "
            "변형 강도를 조정한 뒤 학습에 편입합니다."
        )
    else:
        overall_decision = (
            "DO_NOT_MERGE_YET"
        )
        recommendation = (
            "합성 변형이 OCR 텍스트를 지나치게 훼손했습니다. "
            "변형 강도를 낮추고 다시 생성해야 합니다."
        )

    profile_decisions: dict[str, Any] = {}

    for _, row in profile_summary.iterrows():
        profile_name = clean(
            row["augmentation_profile"]
        )
        profile_pass_rate = safe_float(
            row["pass_rate"]
        )
        profile_fail_count = int(
            row["fail_count"]
        )

        profile_decisions[profile_name] = {
            "pass_rate": profile_pass_rate,
            "fail_count": profile_fail_count,
            "decision": (
                "KEEP"
                if (
                    profile_fail_count == 0
                    and profile_pass_rate
                    >= 0.85
                )
                else "REVIEW"
                if profile_pass_rate >= 0.65
                else "DROP_OR_REGENERATE"
            ),
        }

    summary = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_stamp,
        "created_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "runtime_root": str(
            runtime_root
        ),
        "synthetic_root": str(
            synthetic_root
        ),
        "report_root": str(
            report_root
        ),
        "ocr_engine": engine_name,
        "render_dpi": args.render_dpi,
        "total_synthetic_pdfs": int(
            len(results)
        ),
        "source_document_count": int(
            results[
                "source_sha256"
            ].nunique()
        ),
        "pass_count": pass_count,
        "review_count": review_count,
        "fail_count": fail_count,
        "pass_rate": pass_rate,
        "mean_token_recall": round(
            float(
                results[
                    "token_recall"
                ].mean()
            ),
            4,
        ),
        "mean_critical_token_recall": round(
            float(
                results[
                    "critical_token_recall"
                ].mean()
            ),
            4,
        ),
        "mean_number_token_recall": round(
            float(
                results[
                    "number_token_recall"
                ].mean()
            ),
            4,
        ),
        "mean_token_f1": round(
            float(
                results[
                    "token_f1"
                ].mean()
            ),
            4,
        ),
        "mean_ocr_confidence": round(
            float(
                results[
                    "mean_ocr_confidence"
                ].mean()
            ),
            4,
        ),
        "overall_training_decision": (
            overall_decision
        ),
        "recommendation": recommendation,
        "profile_decisions": (
            profile_decisions
        ),
        "thresholds": {
            "PASS": {
                "token_recall": ">= 0.85",
                "critical_token_recall": ">= 0.90",
                "number_token_recall": ">= 0.90",
                "page_success_rate": "1.0",
                "mean_ocr_confidence": ">= 0.90",
            },
            "REVIEW": {
                "token_recall": ">= 0.70",
                "critical_token_recall": ">= 0.75",
                "number_token_recall": ">= 0.75",
                "page_success_rate": ">= 0.90",
                "mean_ocr_confidence": ">= 0.80",
            },
        },
        "training_policy": {
            "grouping": (
                "원본과 합성본은 source_sha256 기준으로 "
                "동일 Fold에 고정"
            ),
            "training": (
                "PASS 우선 사용, REVIEW는 문서 확인 후 사용, "
                "FAIL은 제외"
            ),
            "testing": (
                "합성본은 최종 독립 테스트에서 제외"
            ),
        },
    }

    results.to_csv(
        report_root
        / "01_synthetic_ocr_document_results.csv",
        index=False,
        encoding="utf-8-sig",
    )
    pages.to_csv(
        report_root
        / "02_synthetic_ocr_page_results.csv",
        index=False,
        encoding="utf-8-sig",
    )
    profile_summary.to_csv(
        report_root
        / "03_profile_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    institution_summary.to_csv(
        report_root
        / "04_institution_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    institution_profile_summary.to_csv(
        report_root
        / "05_institution_profile_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    low_quality.to_csv(
        report_root
        / "06_review_fail_documents.csv",
        index=False,
        encoding="utf-8-sig",
    )
    (
        report_root
        / "07_summary.json"
    ).write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    create_html_report(
        summary,
        profile_summary,
        institution_summary,
        low_quality,
        report_root
        / "08_synthetic_ocr_report.html",
    )

    latest_pointer = (
        runtime_root
        / "reports"
        / "latest_synthetic_scan_ocr_eval.txt"
    )
    latest_pointer.write_text(
        str(report_root),
        encoding="utf-8",
    )

    print("")
    print("합성 스캔 OCR 평가 완료")
    print(
        f"합성 PDF        : "
        f"{summary['total_synthetic_pdfs']}"
    )
    print(
        f"원본 문서       : "
        f"{summary['source_document_count']}"
    )
    print(
        f"PASS            : "
        f"{summary['pass_count']}"
    )
    print(
        f"REVIEW          : "
        f"{summary['review_count']}"
    )
    print(
        f"FAIL            : "
        f"{summary['fail_count']}"
    )
    print(
        f"평균 Token Recall: "
        f"{summary['mean_token_recall']:.1%}"
    )
    print(
        f"평균 중요값 Recall: "
        f"{summary['mean_critical_token_recall']:.1%}"
    )
    print(
        f"평균 숫자 Recall: "
        f"{summary['mean_number_token_recall']:.1%}"
    )
    print(
        f"학습 판단       : "
        f"{summary['overall_training_decision']}"
    )
    print(
        f"보고서          : "
        f"{report_root}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())