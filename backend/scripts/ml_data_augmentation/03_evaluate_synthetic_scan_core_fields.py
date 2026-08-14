from __future__ import annotations

import argparse
import csv
import html
import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import fitz
import numpy as np
import pandas as pd
from PIL import Image


SCHEMA_VERSION = "synthetic_scan_core_field_evaluation_v1"

FIELD_LABELS_KO = {
    "certificate_no": "문서·인증번호",
    "manufacturer": "제조사명",
    "expiry_date": "유효기간",
    "product_name": "제품명",
    "product_code": "제품코드",
    "halal_id": "Halal-ID",
    "product_certificate_no": "품목별 인증번호",
}

DOCUMENT_ID_LABELS = re.compile(
    r"(?i)\b("
    r"certificate\s*(?:no|number|#)|"
    r"document\s*(?:no|number|#)|"
    r"registration\s*(?:no|number|#)|"
    r"reference\s*(?:no|number|#)|"
    r"cert(?:ificate)?\s*id|"
    r"halal\s*certificate\s*(?:no|number|#)"
    r")\b"
)

MANUFACTURER_LABELS = re.compile(
    r"(?i)^\s*("
    r"manufacturer|"
    r"manufactured\s+by|"
    r"company\s+name(?:\s*&\s*address)?|"
    r"name\s+of\s+(?:the\s+)?company|"
    r"certificate\s+holder|"
    r"certified\s+company|"
    r"applicant"
    r")\s*[:\-]?\s*(.*)$"
)

EXPIRY_LABELS = re.compile(
    r"(?i)\b("
    r"valid\s+until|"
    r"valid\s+through|"
    r"expiry(?:\s+date)?|"
    r"expiration(?:\s+date)?|"
    r"validity"
    r")\b"
)

STOP_LABELS = re.compile(
    r"(?i)^\s*("
    r"address|country|product|scope|issue|issued|date|"
    r"valid|expiry|certificate|registration|document|"
    r"signature|authorized|approved|plant|site"
    r")\b"
)

CODE_PATTERN = re.compile(
    r"\b(?=[A-Z0-9./#()_-]{5,}\b)"
    r"(?=[A-Z0-9./#()_-]*[A-Z])"
    r"(?=[A-Z0-9./#()_-]*\d)"
    r"[A-Z0-9][A-Z0-9./#()_-]*\b",
    flags=re.I,
)

DATE_PATTERNS = [
    re.compile(r"\b\d{4}[-./]\d{1,2}[-./]\d{1,2}\b"),
    re.compile(r"\b\d{1,2}[-./]\d{1,2}[-./]\d{2,4}\b"),
    re.compile(
        r"(?i)\b(?:JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|"
        r"MAY|JUN(?:E)?|JUL(?:Y)?|AUG(?:UST)?|SEP(?:TEMBER)?|"
        r"OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?)"
        r"\s+\d{1,2}(?:ST|ND|RD|TH)?[,]?\s+\d{4}\b"
    ),
    re.compile(
        r"(?i)\b\d{1,2}(?:ST|ND|RD|TH)?\s+"
        r"(?:JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|"
        r"MAY|JUN(?:E)?|JUL(?:Y)?|AUG(?:UST)?|SEP(?:TEMBER)?|"
        r"OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?)"
        r"[,]?\s+\d{4}\b"
    ),
]

COMPANY_SUFFIXES = {
    "CO", "COMPANY", "LTD", "LIMITED", "INC", "INCORPORATED",
    "CORP", "CORPORATION", "LLC", "PLC", "PTE", "PT", "BV",
    "NV", "SA", "SPA", "GMBH", "AG", "SDN", "BHD", "PRIVATE",
}


def clean(value: Any) -> str:
    return " ".join(
        str(value or "")
        .replace("\u00a0", " ")
        .replace("\x00", " ")
        .split()
    ).strip()


def normalize_compact(value: Any) -> str:
    return re.sub(
        r"[^A-Z0-9]",
        "",
        clean(value).upper(),
    )


def normalize_words(value: Any) -> list[str]:
    return [
        token
        for token in re.findall(
            r"[A-Z0-9]+",
            clean(value).upper(),
        )
        if token
    ]


def unique_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        value = clean(value)

        if not value:
            continue

        key = value.upper()

        if key in seen:
            continue

        seen.add(key)
        result.append(value)

    return result


def safe_rate(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def read_native_pdf_text(path: Path) -> str:
    pages: list[str] = []

    with fitz.open(path) as document:
        for page in document:
            pages.append(page.get_text("text"))

    return "\n".join(pages)


def load_rapidocr() -> tuple[Any, str]:
    errors: list[str] = []

    try:
        from rapidocr_onnxruntime import RapidOCR

        return RapidOCR(), "rapidocr_onnxruntime"
    except Exception as exc:
        errors.append(f"rapidocr_onnxruntime={exc!r}")

    try:
        from rapidocr import RapidOCR

        return RapidOCR(), "rapidocr"
    except Exception as exc:
        errors.append(f"rapidocr={exc!r}")

    raise RuntimeError(
        "RapidOCR 로드 실패: " + " | ".join(errors)
    )


def parse_ocr_result(raw_result: Any) -> list[tuple[str, float]]:
    payload = raw_result

    if isinstance(payload, tuple):
        payload = payload[0]

    if hasattr(payload, "txts"):
        texts = list(getattr(payload, "txts") or [])
        scores = list(getattr(payload, "scores") or [])

        return [
            (
                clean(text),
                float(scores[index])
                if index < len(scores)
                else 0.0,
            )
            for index, text in enumerate(texts)
            if clean(text)
        ]

    if isinstance(payload, dict):
        texts = (
            payload.get("txts")
            or payload.get("texts")
            or payload.get("text")
            or []
        )
        scores = payload.get("scores") or []

        if isinstance(texts, str):
            texts = [texts]

        return [
            (
                clean(text),
                float(scores[index])
                if index < len(scores)
                else 0.0,
            )
            for index, text in enumerate(texts)
            if clean(text)
        ]

    rows: list[tuple[str, float]] = []

    if isinstance(payload, (list, tuple)):
        for item in payload:
            if not isinstance(item, (list, tuple)):
                continue

            if len(item) >= 3:
                text = clean(item[1])
                score = float(item[2] or 0)
            elif len(item) >= 2:
                text = clean(item[0])
                score = float(item[1] or 0)
            else:
                continue

            if text:
                rows.append((text, score))

    return rows


def ocr_pdf(
    engine: Any,
    path: Path,
    dpi: int,
) -> tuple[str, float, int, int]:
    page_texts: list[str] = []
    scores: list[float] = []
    page_count = 0
    success_count = 0

    with fitz.open(path) as document:
        for page in document:
            page_count += 1
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
            result = parse_ocr_result(
                engine(np.asarray(image))
            )
            page_text = "\n".join(
                text for text, _score in result
            )

            if page_text:
                success_count += 1

            page_texts.append(page_text)
            scores.extend(
                score
                for _text, score in result
                if score > 0
            )

    return (
        "\n".join(page_texts),
        round(statistics.mean(scores), 4)
        if scores
        else 0.0,
        page_count,
        success_count,
    )


def extract_document_numbers(text: str) -> list[str]:
    lines = [clean(line) for line in text.splitlines()]
    values: list[str] = []

    for index, line in enumerate(lines):
        if not DOCUMENT_ID_LABELS.search(line):
            continue

        window = " ".join(
            lines[index:index + 3]
        )

        for match in CODE_PATTERN.findall(window):
            normalized = normalize_compact(match)

            if len(normalized) >= 5:
                values.append(match)

    return unique_keep_order(values)[:20]


def extract_manufacturers(text: str) -> list[str]:
    lines = [clean(line) for line in text.splitlines()]
    values: list[str] = []

    for index, line in enumerate(lines):
        match = MANUFACTURER_LABELS.match(line)

        if not match:
            continue

        parts: list[str] = []
        inline_value = clean(match.group(2))

        if inline_value:
            parts.append(inline_value)

        for next_line in lines[index + 1:index + 4]:
            if not next_line:
                continue

            if STOP_LABELS.match(next_line):
                break

            parts.append(next_line)

            if any(
                suffix in normalize_words(next_line)
                for suffix in COMPANY_SUFFIXES
            ):
                break

        value = clean(" ".join(parts))

        if len(normalize_words(value)) >= 2:
            values.append(value)

    return unique_keep_order(values)[:10]


def extract_expiry_dates(text: str) -> list[str]:
    lines = [clean(line) for line in text.splitlines()]
    values: list[str] = []

    for index, line in enumerate(lines):
        if not EXPIRY_LABELS.search(line):
            continue

        window = " ".join(lines[index:index + 3])

        for pattern in DATE_PATTERNS:
            values.extend(pattern.findall(window))

    return unique_keep_order(values)[:10]


def locate_latest_product_candidates(
    runtime_root: Path,
) -> Path | None:
    pointer = (
        runtime_root
        / "reports"
        / "latest_product_item_labels.txt"
    )

    if pointer.exists():
        report_root = Path(
            pointer.read_text(
                encoding="utf-8-sig"
            ).strip()
        )
        candidate = (
            report_root
            / "02_product_item_candidates.csv"
        )

        if candidate.exists():
            return candidate

    candidates = sorted(
        (
            runtime_root
            / "reports"
        ).glob(
            "product_item_labels_*/02_product_item_candidates.csv"
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    return candidates[0] if candidates else None


def load_product_values(
    runtime_root: Path,
) -> dict[str, dict[str, list[str]]]:
    path = locate_latest_product_candidates(
        runtime_root
    )

    if path is None:
        return {}

    frame = pd.read_csv(
        path,
        dtype=str,
        encoding="utf-8-sig",
    ).fillna("")

    sha_column = next(
        (
            column
            for column in [
                "sha256",
                "source_sha256",
                "document_sha256",
            ]
            if column in frame.columns
        ),
        None,
    )

    if sha_column is None:
        return {}

    if "row_status" in frame.columns:
        frame = frame[
            frame["row_status"] == "AUTO_READY"
        ].copy()

    column_aliases = {
        "product_name": [
            "product_name",
            "candidate_product_name",
            "item_name",
        ],
        "product_code": [
            "product_code",
            "candidate_product_code",
            "item_code",
        ],
        "halal_id": [
            "halal_id",
            "candidate_halal_id",
        ],
        "product_certificate_no": [
            "product_certificate_no",
            "candidate_product_certificate_no",
            "product_cert_no",
        ],
    }

    resolved: dict[str, str] = {}

    for field_name, aliases in column_aliases.items():
        for alias in aliases:
            if alias in frame.columns:
                resolved[field_name] = alias
                break

    result: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for _, row in frame.iterrows():
        sha256 = clean(row[sha_column]).upper()

        if not sha256:
            continue

        for field_name, column in resolved.items():
            value = clean(row[column])

            if value:
                result[sha256][field_name].append(value)

    normalized: dict[str, dict[str, list[str]]] = {}

    for sha256, fields in result.items():
        normalized[sha256] = {
            field_name: unique_keep_order(values)
            for field_name, values in fields.items()
        }

    return normalized


def code_match_score(
    expected: str,
    observed_text: str,
) -> float:
    expected_normalized = normalize_compact(expected)
    observed_normalized = normalize_compact(
        observed_text
    )

    if not expected_normalized:
        return 0.0

    if expected_normalized in observed_normalized:
        return 1.0

    candidates = [
        normalize_compact(candidate)
        for candidate in CODE_PATTERN.findall(
            observed_text
        )
    ]

    best = 0.0

    for candidate in candidates:
        if not candidate:
            continue

        ratio = SequenceMatcher(
            None,
            expected_normalized,
            candidate,
            autojunk=False,
        ).ratio()
        best = max(best, ratio)

    return round(best, 4)


def text_match_score(
    expected: str,
    observed_text: str,
) -> float:
    expected_tokens = normalize_words(expected)

    if not expected_tokens:
        return 0.0

    observed_tokens = normalize_words(
        observed_text
    )
    observed_counter = Counter(
        observed_tokens
    )
    expected_counter = Counter(
        expected_tokens
    )

    exact_matched = sum(
        (
            observed_counter
            & expected_counter
        ).values()
    )

    exact_recall = (
        exact_matched
        / sum(expected_counter.values())
    )

    fuzzy_matched = 0

    for expected_token in expected_tokens:
        if expected_token in observed_counter:
            fuzzy_matched += 1
            continue

        best = max(
            (
                SequenceMatcher(
                    None,
                    expected_token,
                    observed_token,
                    autojunk=False,
                ).ratio()
                for observed_token in observed_tokens
                if abs(
                    len(expected_token)
                    - len(observed_token)
                ) <= 3
            ),
            default=0.0,
        )

        if best >= 0.86:
            fuzzy_matched += 1

    fuzzy_recall = fuzzy_matched / len(
        expected_tokens
    )

    return round(
        max(exact_recall, fuzzy_recall),
        4,
    )


def date_match_score(
    expected: str,
    observed_text: str,
) -> float:
    compact_expected = normalize_compact(expected)

    if compact_expected in normalize_compact(
        observed_text
    ):
        return 1.0

    expected_numbers = re.findall(
        r"\d+",
        expected,
    )

    if not expected_numbers:
        return 0.0

    observed_upper = observed_text.upper()

    matched = sum(
        number in observed_upper
        for number in expected_numbers
    )

    return round(
        matched / len(expected_numbers),
        4,
    )


def aggregate_values(
    field_name: str,
    expected_values: list[str],
    observed_text: str,
) -> tuple[float | None, list[dict[str, Any]]]:
    expected_values = unique_keep_order(
        expected_values
    )

    if not expected_values:
        return None, []

    details: list[dict[str, Any]] = []

    for value in expected_values:
        if field_name in {
            "certificate_no",
            "product_code",
            "halal_id",
            "product_certificate_no",
        }:
            score = code_match_score(
                value,
                observed_text,
            )
        elif field_name == "expiry_date":
            score = date_match_score(
                value,
                observed_text,
            )
        else:
            score = text_match_score(
                value,
                observed_text,
            )

        details.append({
            "expected_value": value,
            "score": score,
            "matched": score >= (
                0.88
                if field_name in {
                    "certificate_no",
                    "product_code",
                    "halal_id",
                    "product_certificate_no",
                }
                else 0.80
            ),
        })

    return (
        round(
            statistics.mean(
                detail["score"]
                for detail in details
            ),
            4,
        ),
        details,
    )


def assess_document(
    field_scores: dict[str, float | None],
    page_success_rate: float,
) -> tuple[str, str]:
    available = [
        score
        for score in field_scores.values()
        if score is not None
    ]

    if not available:
        return (
            "REVIEW",
            "평가 가능한 핵심 항목 후보가 없음",
        )

    average = statistics.mean(available)
    minimum = min(available)

    document_core = [
        field_scores.get("certificate_no"),
        field_scores.get("manufacturer"),
        field_scores.get("expiry_date"),
    ]
    available_core = [
        score
        for score in document_core
        if score is not None
    ]

    core_average = (
        statistics.mean(available_core)
        if available_core
        else average
    )

    if (
        page_success_rate == 1.0
        and average >= 0.85
        and core_average >= 0.85
        and minimum >= 0.65
    ):
        return (
            "사용 가능",
            "핵심 항목이 안정적으로 유지됨",
        )

    if (
        page_success_rate >= 0.90
        and average >= 0.65
        and core_average >= 0.65
    ):
        return (
            "검토 후 사용",
            "일부 항목 손실 또는 표현 차이 확인 필요",
        )

    return (
        "제외",
        "핵심 번호·회사명·날짜 중 손실이 큼",
    )


def group_summary(
    frame: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for key, group in frame.groupby(
        columns,
        dropna=False,
    ):
        if not isinstance(key, tuple):
            key = (key,)

        row = {
            column: key[index]
            for index, column in enumerate(columns)
        }

        row.update({
            "합성본수": int(len(group)),
            "원본문서수": int(
                group["source_sha256"].nunique()
            ),
            "사용가능": int(
                (group["document_decision"] == "사용 가능").sum()
            ),
            "검토후사용": int(
                (group["document_decision"] == "검토 후 사용").sum()
            ),
            "제외": int(
                (group["document_decision"] == "제외").sum()
            ),
            "사용가능비율": safe_rate(
                (group["document_decision"] == "사용 가능").sum(),
                len(group),
            ),
            "평균핵심항목점수": round(
                float(
                    group["average_field_score"].mean()
                ),
                4,
            ),
        })

        for field_name, label in FIELD_LABELS_KO.items():
            column = f"{field_name}_score"
            available = group[column].dropna()

            row[label] = (
                round(float(available.mean()), 4)
                if len(available)
                else None
            )

        rows.append(row)

    return pd.DataFrame(rows).sort_values(columns)


def make_field_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for field_name, label in FIELD_LABELS_KO.items():
        score_column = f"{field_name}_score"
        available = frame[score_column].dropna()

        rows.append({
            "항목": label,
            "평가가능문서": int(len(available)),
            "평균유지점수": (
                round(float(available.mean()), 4)
                if len(available)
                else None
            ),
            "80점이상": int(
                (available >= 0.80).sum()
            ),
            "80점이상비율": safe_rate(
                (available >= 0.80).sum(),
                len(available),
            ),
        })

    return pd.DataFrame(rows)


def status_badge(value: str) -> str:
    css = {
        "사용 가능": "good",
        "검토 후 사용": "review",
        "제외": "bad",
    }.get(value, "neutral")

    return (
        f"<span class='badge {css}'>"
        f"{html.escape(value)}</span>"
    )


def create_easy_html(
    summary: dict[str, Any],
    field_summary: pd.DataFrame,
    profile_summary: pd.DataFrame,
    institution_summary: pd.DataFrame,
    review_frame: pd.DataFrame,
    output_path: Path,
) -> None:
    decision = summary["final_decision"]

    cards = [
        ("합성 스캔본", summary["total_documents"]),
        ("바로 사용", summary["usable_count"]),
        ("검토 후 사용", summary["review_count"]),
        ("제외", summary["exclude_count"]),
        (
            "평균 핵심항목 유지",
            f"{summary['mean_field_score']:.1%}",
        ),
    ]

    cards_html = "".join(
        "<div class='card'><div class='small'>"
        + html.escape(str(label))
        + "</div><div class='number'>"
        + html.escape(str(value))
        + "</div></div>"
        for label, value in cards
    )

    field_rows = ""

    for _, row in field_summary.iterrows():
        score = row["평균유지점수"]
        score_text = (
            f"{float(score):.1%}"
            if pd.notna(score)
            else "평가자료 없음"
        )
        rate = row["80점이상비율"]
        rate_text = (
            f"{float(rate):.1%}"
            if pd.notna(rate)
            else "-"
        )

        field_rows += (
            "<tr>"
            f"<td>{html.escape(str(row['항목']))}</td>"
            f"<td>{int(row['평가가능문서'])}</td>"
            f"<td><strong>{score_text}</strong></td>"
            f"<td>{rate_text}</td>"
            "</tr>"
        )

    profile_rows = ""

    for _, row in profile_summary.iterrows():
        profile_rows += (
            "<tr>"
            f"<td>{html.escape(str(row['augmentation_profile']))}</td>"
            f"<td>{int(row['합성본수'])}</td>"
            f"<td>{int(row['사용가능'])}</td>"
            f"<td>{int(row['검토후사용'])}</td>"
            f"<td>{int(row['제외'])}</td>"
            f"<td>{float(row['평균핵심항목점수']):.1%}</td>"
            "</tr>"
        )

    institution_rows = ""

    for _, row in institution_summary.iterrows():
        usable = int(row["사용가능"])
        review = int(row["검토후사용"])
        excluded = int(row["제외"])

        if excluded > 0:
            action = "제외 문서의 손실 항목 확인"
        elif review > 0:
            action = "검토 문서만 확인"
        else:
            action = "그대로 사용 가능"

        institution_rows += (
            "<tr>"
            f"<td>{html.escape(str(row['institution']))}</td>"
            f"<td>{int(row['합성본수'])}</td>"
            f"<td>{usable}</td>"
            f"<td>{review}</td>"
            f"<td>{excluded}</td>"
            f"<td>{float(row['평균핵심항목점수']):.1%}</td>"
            f"<td>{html.escape(action)}</td>"
            "</tr>"
        )

    review_rows = ""

    for _, row in review_frame.head(50).iterrows():
        review_rows += (
            "<tr>"
            f"<td>{html.escape(str(row['institution']))}</td>"
            f"<td>{html.escape(str(row['augmentation_profile']))}</td>"
            f"<td>{status_badge(str(row['document_decision']))}</td>"
            f"<td>{html.escape(str(row['weak_fields_ko']))}</td>"
            f"<td>{html.escape(Path(str(row['synthetic_path'])).name)}</td>"
            "</tr>"
        )

    if not review_rows:
        review_rows = (
            "<tr><td colspan='5'>"
            "확인할 문서가 없습니다."
            "</td></tr>"
        )

    body = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>합성 스캔 핵심항목 평가</title>
<style>
body {{
    font-family: Arial, "Malgun Gothic", sans-serif;
    background: #f4f6f8;
    color: #1f2937;
    margin: 0;
    padding: 24px;
}}
.wrap {{
    max-width: 1180px;
    margin: auto;
}}
.hero, .section {{
    background: white;
    border: 1px solid #dfe5eb;
    border-radius: 12px;
    padding: 22px;
    margin-bottom: 16px;
}}
.hero h1 {{
    margin-top: 0;
    font-size: 26px;
}}
.verdict {{
    font-size: 21px;
    font-weight: 700;
    padding: 14px;
    background: #eef2f7;
    border-left: 5px solid #475569;
    margin: 16px 0;
}}
.cards {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(155px, 1fr));
    gap: 10px;
}}
.card {{
    border: 1px solid #e3e8ee;
    border-radius: 10px;
    padding: 14px;
}}
.small {{
    font-size: 13px;
    color: #64748b;
}}
.number {{
    margin-top: 5px;
    font-size: 25px;
    font-weight: 700;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    font-size: 13px;
}}
th, td {{
    border-bottom: 1px solid #e5e7eb;
    padding: 9px;
    text-align: left;
    vertical-align: top;
}}
th {{
    background: #f8fafc;
}}
.badge {{
    display: inline-block;
    padding: 3px 8px;
    border-radius: 10px;
    font-weight: 700;
}}
.good {{
    background: #dcfce7;
}}
.review {{
    background: #fef3c7;
}}
.bad {{
    background: #fee2e2;
}}
.note {{
    color: #64748b;
    font-size: 13px;
}}
</style>
</head>
<body>
<div class="wrap">
<div class="hero">
<h1>합성 스캔본 핵심항목 평가</h1>
<div class="verdict">{html.escape(decision)}</div>
<p>{html.escape(summary["reason"])}</p>
<div class="cards">{cards_html}</div>
</div>

<div class="section">
<h2>1. 실제 업무 항목이 얼마나 유지됐나</h2>
<table>
<thead>
<tr>
<th>항목</th>
<th>평가 문서</th>
<th>평균 유지점수</th>
<th>80점 이상 비율</th>
</tr>
</thead>
<tbody>{field_rows}</tbody>
</table>
<p class="note">
공백, 하이픈, 슬래시, 대소문자 차이는 같은 값으로 최대한 정규화했습니다.
</p>
</div>

<div class="section">
<h2>2. 스캔 변형별 비교</h2>
<table>
<thead>
<tr>
<th>변형</th>
<th>합성본</th>
<th>사용 가능</th>
<th>검토</th>
<th>제외</th>
<th>평균 점수</th>
</tr>
</thead>
<tbody>{profile_rows}</tbody>
</table>
</div>

<div class="section">
<h2>3. 기관별 결과와 조치</h2>
<table>
<thead>
<tr>
<th>기관</th>
<th>합성본</th>
<th>사용 가능</th>
<th>검토</th>
<th>제외</th>
<th>평균 점수</th>
<th>조치</th>
</tr>
</thead>
<tbody>{institution_rows}</tbody>
</table>
</div>

<div class="section">
<h2>4. 확인이 필요한 문서</h2>
<table>
<thead>
<tr>
<th>기관</th>
<th>변형</th>
<th>판정</th>
<th>약한 항목</th>
<th>파일</th>
</tr>
</thead>
<tbody>{review_rows}</tbody>
</table>
</div>

<div class="section">
<h2>판정 기준</h2>
<p>
<strong>사용 가능:</strong> 핵심항목 평균 85% 이상이며 큰 손실이 없는 문서<br>
<strong>검토 후 사용:</strong> 평균 65% 이상이지만 일부 항목 확인이 필요한 문서<br>
<strong>제외:</strong> 번호·회사명·날짜 등 핵심항목 손실이 큰 문서
</p>
<p class="note">
제품 항목은 기존 4C AUTO_READY 후보가 있는 원본문서만 평가됩니다.
이 결과는 합성 스캔의 OCR 보존성 평가이며 인증서 실제 정답 확정 결과는 아닙니다.
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
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--synthetic-root", required=True)
    parser.add_argument("--render-dpi", type=int, default=220)
    args = parser.parse_args()

    runtime_root = Path(args.runtime_root).resolve()
    synthetic_root = Path(args.synthetic_root).resolve()
    manifest_path = (
        synthetic_root
        / "synthetic_scan_manifest.csv"
    )

    manifest = pd.read_csv(
        manifest_path,
        dtype=str,
        encoding="utf-8-sig",
    ).fillna("")

    engine, engine_name = load_rapidocr()
    product_values = load_product_values(
        runtime_root
    )

    run_id = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    report_root = (
        runtime_root
        / "reports"
        / f"synthetic_scan_core_field_eval_{run_id}"
    )
    report_root.mkdir(
        parents=True,
        exist_ok=False,
    )
    cache_root = report_root / "ocr_text"
    cache_root.mkdir(parents=True)

    source_cache: dict[str, str] = {}
    result_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []

    total = len(manifest)

    for index, row in manifest.iterrows():
        source_path = Path(row["source_path"])
        synthetic_path = Path(row["synthetic_path"])
        source_sha = clean(
            row["source_sha256"]
        ).upper()

        print(
            f"[{index + 1}/{total}] "
            f"{row['institution']} | "
            f"{row['augmentation_profile']} | "
            f"{synthetic_path.name}"
        )

        if str(source_path) not in source_cache:
            source_cache[str(source_path)] = (
                read_native_pdf_text(source_path)
            )

        source_text = source_cache[
            str(source_path)
        ]
        ocr_text, confidence, pages, success_pages = (
            ocr_pdf(
                engine,
                synthetic_path,
                args.render_dpi,
            )
        )

        (
            cache_root
            / f"{clean(row['synthetic_sha256'])}.txt"
        ).write_text(
            ocr_text,
            encoding="utf-8",
        )

        expected: dict[str, list[str]] = {
            "certificate_no": extract_document_numbers(
                source_text
            ),
            "manufacturer": extract_manufacturers(
                source_text
            ),
            "expiry_date": extract_expiry_dates(
                source_text
            ),
            "product_name": [],
            "product_code": [],
            "halal_id": [],
            "product_certificate_no": [],
        }

        if source_sha in product_values:
            for field_name in [
                "product_name",
                "product_code",
                "halal_id",
                "product_certificate_no",
            ]:
                expected[field_name] = (
                    product_values[source_sha].get(
                        field_name,
                        [],
                    )
                )

        field_scores: dict[str, float | None] = {}
        weak_fields: list[str] = []

        for field_name in FIELD_LABELS_KO:
            score, details = aggregate_values(
                field_name,
                expected[field_name],
                ocr_text,
            )
            field_scores[field_name] = score

            if score is not None and score < 0.80:
                weak_fields.append(
                    FIELD_LABELS_KO[field_name]
                )

            for detail in details:
                detail_rows.append({
                    "institution": row["institution"],
                    "augmentation_profile": row[
                        "augmentation_profile"
                    ],
                    "source_sha256": source_sha,
                    "synthetic_sha256": row[
                        "synthetic_sha256"
                    ],
                    "synthetic_path": str(
                        synthetic_path
                    ),
                    "field_name": field_name,
                    "field_name_ko": (
                        FIELD_LABELS_KO[field_name]
                    ),
                    **detail,
                })

        available_scores = [
            score
            for score in field_scores.values()
            if score is not None
        ]
        average_score = (
            statistics.mean(available_scores)
            if available_scores
            else 0.0
        )
        page_success_rate = safe_rate(
            success_pages,
            pages,
        )
        decision, reason = assess_document(
            field_scores,
            page_success_rate,
        )

        result_row = {
            "institution": row["institution"],
            "augmentation_profile": row[
                "augmentation_profile"
            ],
            "source_path": str(source_path),
            "synthetic_path": str(
                synthetic_path
            ),
            "source_sha256": source_sha,
            "synthetic_sha256": row[
                "synthetic_sha256"
            ],
            "validation_group": row[
                "validation_group"
            ],
            "ocr_engine": engine_name,
            "render_dpi": args.render_dpi,
            "page_count": pages,
            "successful_pages": success_pages,
            "page_success_rate": (
                page_success_rate
            ),
            "mean_ocr_confidence": confidence,
            "available_field_count": len(
                available_scores
            ),
            "average_field_score": round(
                average_score,
                4,
            ),
            "document_decision": decision,
            "decision_reason": reason,
            "weak_fields_ko": ", ".join(
                weak_fields
            ),
        }

        for field_name in FIELD_LABELS_KO:
            result_row[
                f"{field_name}_expected_count"
            ] = len(expected[field_name])
            result_row[
                f"{field_name}_score"
            ] = field_scores[field_name]

        result_rows.append(result_row)

    results = pd.DataFrame(result_rows)
    details = pd.DataFrame(detail_rows)

    score_columns = [
        f"{field_name}_score"
        for field_name in FIELD_LABELS_KO
    ] + ["average_field_score"]

    for column in score_columns:
        results[column] = pd.to_numeric(
            results[column],
            errors="coerce",
        )

    field_summary = make_field_summary(
        results
    )
    profile_summary = group_summary(
        results,
        ["augmentation_profile"],
    )
    institution_summary = group_summary(
        results,
        ["institution"],
    )

    review_frame = results[
        results["document_decision"].isin(
            ["검토 후 사용", "제외"]
        )
    ].sort_values(
        [
            "document_decision",
            "average_field_score",
        ],
        ascending=[True, True],
    )

    usable_count = int(
        (
            results["document_decision"]
            == "사용 가능"
        ).sum()
    )
    review_count = int(
        (
            results["document_decision"]
            == "검토 후 사용"
        ).sum()
    )
    exclude_count = int(
        (
            results["document_decision"]
            == "제외"
        ).sum()
    )
    total_documents = int(len(results))
    usable_or_review = (
        usable_count + review_count
    )
    acceptable_rate = safe_rate(
        usable_or_review,
        total_documents,
    )
    mean_score = float(
        results["average_field_score"].mean()
    )

    if (
        exclude_count == 0
        and acceptable_rate >= 0.90
        and mean_score >= 0.85
    ):
        final_decision = (
            "두 변형 모두 학습 증강용으로 사용할 수 있습니다."
        )
        reason = (
            "핵심 번호·회사명·날짜·제품 항목이 "
            "대부분 안정적으로 유지됐습니다."
        )
        machine_decision = "KEEP_BOTH"
    elif (
        acceptable_rate >= 0.75
        and mean_score >= 0.70
    ):
        final_decision = (
            "검토 문서만 제외하거나 수정한 뒤 학습에 사용할 수 있습니다."
        )
        reason = (
            "전체적으로 사용할 수 있으나 일부 문서의 "
            "핵심 항목 손실을 확인해야 합니다."
        )
        machine_decision = "KEEP_AFTER_REVIEW"
    else:
        final_decision = (
            "현재 합성본을 바로 학습에 넣지 않습니다."
        )
        reason = (
            "핵심 항목 유지율이 낮아 변형 강도 또는 "
            "OCR 설정을 조정해야 합니다."
        )
        machine_decision = "DO_NOT_MERGE"

    summary = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "report_root": str(report_root),
        "synthetic_root": str(
            synthetic_root
        ),
        "ocr_engine": engine_name,
        "render_dpi": args.render_dpi,
        "total_documents": total_documents,
        "source_document_count": int(
            results["source_sha256"].nunique()
        ),
        "usable_count": usable_count,
        "review_count": review_count,
        "exclude_count": exclude_count,
        "acceptable_rate": acceptable_rate,
        "mean_field_score": round(
            mean_score,
            4,
        ),
        "final_decision": final_decision,
        "reason": reason,
        "machine_decision": machine_decision,
        "product_candidate_source": (
            str(
                locate_latest_product_candidates(
                    runtime_root
                )
            )
            if locate_latest_product_candidates(
                runtime_root
            )
            else None
        ),
        "important_note": (
            "이 평가는 원본 PDF에서 추출한 핵심 항목 후보가 "
            "합성 OCR 텍스트에 유지되는지 확인합니다. "
            "인증서 운영 정답 확정과는 별도입니다."
        ),
    }

    results.to_csv(
        report_root
        / "01_document_core_field_results.csv",
        index=False,
        encoding="utf-8-sig",
    )
    details.to_csv(
        report_root
        / "02_value_match_details.csv",
        index=False,
        encoding="utf-8-sig",
    )
    field_summary.to_csv(
        report_root
        / "03_field_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    profile_summary.to_csv(
        report_root
        / "04_profile_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    institution_summary.to_csv(
        report_root
        / "05_institution_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    review_frame.to_csv(
        report_root
        / "06_review_documents.csv",
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
    create_easy_html(
        summary,
        field_summary,
        profile_summary,
        institution_summary,
        review_frame,
        report_root
        / "08_easy_report.html",
    )

    (
        runtime_root
        / "reports"
        / "latest_synthetic_scan_core_field_eval.txt"
    ).write_text(
        str(report_root),
        encoding="utf-8",
    )

    print("")
    print("핵심 항목 기준 합성 스캔 평가 완료")
    print(
        f"합성 스캔본     : {total_documents}"
    )
    print(
        f"바로 사용       : {usable_count}"
    )
    print(
        f"검토 후 사용    : {review_count}"
    )
    print(
        f"제외            : {exclude_count}"
    )
    print(
        f"평균 핵심항목 유지: {mean_score:.1%}"
    )
    print(
        f"최종 판단       : {final_decision}"
    )
    print(f"보고서          : {report_root}")
    print("보기 쉬운 보고서: 08_easy_report.html")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())