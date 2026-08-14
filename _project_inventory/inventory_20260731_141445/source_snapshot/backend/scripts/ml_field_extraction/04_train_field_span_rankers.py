from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC


SCHEMA_VERSION = "field_span_ranker_v1"
MODEL_VERSION = "char_tfidf_linear_svm_field_span_ranker_v1"
FIELDS = ("cert_no", "manufacturer", "expiry_date")
FIELD_CONFIGS = {
    "cert_no": {
        "max_negatives_per_document": 70,
        "max_features": 130000,
    },
    "manufacturer": {
        "max_negatives_per_document": 90,
        "max_features": 150000,
    },
    "expiry_date": {
        "max_negatives_per_document": 60,
        "max_features": 110000,
    },
}

PAGE_MARKER_RE = re.compile(
    r"---\s*PAGE\s+(\d+)(?:\s*\[[^\]]*\])?\s*---",
    re.IGNORECASE,
)
WHITESPACE_RE = re.compile(r"\s+")
DATE_NUMERIC_RE = re.compile(
    r"\b(20\d{2})[-./](\d{1,2})[-./](\d{1,2})\b"
)
DATE_DMY_RE = re.compile(
    r"\b(\d{1,2})[-./](\d{1,2})[-./](20\d{2})\b"
)
DATE_MONTH_FIRST_RE = re.compile(
    r"\b("
    r"JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|"
    r"SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER"
    r")\s+(\d{1,2})(?:ST|ND|RD|TH)?[,.]?\s+(20\d{2})\b",
    re.IGNORECASE,
)
DATE_DAY_FIRST_RE = re.compile(
    r"\b(\d{1,2})(?:ST|ND|RD|TH)?\s+("
    r"JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|"
    r"SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER"
    r")[,.]?\s+(20\d{2})\b",
    re.IGNORECASE,
)
COMPANY_SUFFIX_RE = re.compile(
    r"\b(?:CO\.?|COMPANY|CORP\.?|CORPORATION|INC\.?|LTD\.?|LIMITED|"
    r"LLC|PTE\.?\s*LTD\.?|SDN\.?\s*BHD\.?|GMBH|B\.?V\.?|"
    r"S\.?A\.?|PLC|AG|INDUSTRIES?|PRIVATE\s+LIMITED)\b",
    re.IGNORECASE,
)
GENERIC_LINE_RE = re.compile(
    r"^\s*(?:COMPANY|COMPANY\s+NAME|NAME\s+OF\s+COMPANY|"
    r"MANUFACTURER|MANUFACTURED\s+BY|FACTORY|FACILITY\s+NAME|"
    r"PLANT\s+NAME(?:\s*&\s*ADDRESS)?|CERTIFICATE\s+(?:NO|NUMBER)|"
    r"VALID\s+UNTIL|EXPIRY\s+DATE|EXPIRATION\s+DATE|"
    r"CO\.?\s*,?\s*LTD\.?|LTD\.?|PRIVATE\s+LIMITED)\s*[:：-]*\s*$",
    re.IGNORECASE,
)

MONTHS = {
    "JANUARY": 1,
    "FEBRUARY": 2,
    "MARCH": 3,
    "APRIL": 4,
    "MAY": 5,
    "JUNE": 6,
    "JULY": 7,
    "AUGUST": 8,
    "SEPTEMBER": 9,
    "OCTOBER": 10,
    "NOVEMBER": 11,
    "DECEMBER": 12,
}


def clean(value: Any) -> str:
    text = str(value or "").replace("\u00a0", " ").replace("\x00", " ")
    return WHITESPACE_RE.sub(" ", text).strip()


def norm_key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9가-힣]+", "", clean(value).upper())


def normalize_cert(value: Any) -> str:
    text = norm_key(value)
    if text.startswith("LPPOM"):
        text = text[5:]
    if re.fullmatch(r"ID\d{10,}", text):
        text = text[2:]
    return text


def manufacturer_tokens(value: Any) -> list[str]:
    text = clean(value).upper()
    text = COMPANY_SUFFIX_RE.sub(" ", text)
    text = re.sub(r"[^A-Z0-9가-힣]+", " ", text)
    stop_words = {
        "THE",
        "OF",
        "AND",
        "GROUP",
        "HOLDING",
        "HOLDINGS",
    }
    return [
        token
        for token in text.split()
        if token and token not in stop_words
    ]


def manufacturer_similarity(left: Any, right: Any) -> float:
    left_set = set(manufacturer_tokens(left))
    right_set = set(manufacturer_tokens(right))
    if not left_set or not right_set:
        return 0.0
    intersection = len(left_set & right_set)
    containment = intersection / max(1, min(len(left_set), len(right_set)))
    jaccard = intersection / max(1, len(left_set | right_set))
    return max(containment, jaccard)


def extract_dates(text: str) -> list[str]:
    results: list[str] = []

    for match in DATE_NUMERIC_RE.finditer(text):
        year, month, day = map(int, match.groups())
        if 1 <= month <= 12 and 1 <= day <= 31:
            results.append(f"{year:04d}-{month:02d}-{day:02d}")

    for match in DATE_DMY_RE.finditer(text):
        day, month, year = map(int, match.groups())
        if 1 <= month <= 12 and 1 <= day <= 31:
            results.append(f"{year:04d}-{month:02d}-{day:02d}")

    for match in DATE_MONTH_FIRST_RE.finditer(text.upper()):
        month_name, day, year = match.groups()
        results.append(
            f"{int(year):04d}-{MONTHS[month_name]:02d}-{int(day):02d}"
        )

    for match in DATE_DAY_FIRST_RE.finditer(text.upper()):
        day, month_name, year = match.groups()
        results.append(
            f"{int(year):04d}-{MONTHS[month_name]:02d}-{int(day):02d}"
        )

    return list(dict.fromkeys(results))


def split_pages(text: str) -> list[dict[str, Any]]:
    raw = str(text or "")
    matches = list(PAGE_MARKER_RE.finditer(raw))
    chunks: list[tuple[int, str]] = []

    if matches:
        for index, match in enumerate(matches):
            page = int(match.group(1))
            start = match.end()
            end = (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(raw)
            )
            chunks.append((page, raw[start:end]))
    else:
        chunks.append((1, raw))

    rows: list[dict[str, Any]] = []
    for page, chunk in chunks:
        page_lines = [
            clean(line)
            for line in chunk.splitlines()
            if clean(line)
            and not PAGE_MARKER_RE.fullmatch(clean(line))
        ]
        for line_no, line in enumerate(page_lines, start=1):
            rows.append({
                "page": page,
                "line_no": line_no,
                "line": line,
            })

    return rows


def build_spans(
    field: str,
    institution: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []

    for start in range(len(rows)):
        if rows[start]["page"] > 4:
            continue

        for length in (1, 2, 3):
            end = start + length
            if end > len(rows):
                break

            selected = rows[start:end]
            if len({row["page"] for row in selected}) != 1:
                break

            span_text = " | ".join(row["line"] for row in selected)
            upper = span_text.upper()

            if len(span_text) > 500:
                continue

            if field == "cert_no":
                eligible = bool(
                    re.search(r"\d", span_text)
                    and (
                        length > 1
                        or "CERT" in upper
                        or "REGISTRATION" in upper
                        or len(norm_key(span_text)) >= 5
                    )
                )
            elif field == "manufacturer":
                eligible = bool(
                    re.search(r"[A-Za-z가-힣]", span_text)
                    and len(norm_key(span_text)) >= 4
                )
            elif field == "expiry_date":
                eligible = bool(
                    extract_dates(span_text)
                    or any(
                        token in upper
                        for token in (
                            "VALID",
                            "EXPIR",
                            "UNTIL",
                            "PERIOD",
                            "DATE",
                        )
                    )
                )
            else:
                eligible = False

            if not eligible:
                continue

            previous = rows[start - 1]["line"] if start > 0 else ""
            following = rows[end]["line"] if end < len(rows) else ""
            page = int(selected[0]["page"])
            position_bucket = min(9, int(selected[0]["line_no"]) // 5)
            org_token = re.sub(
                r"[^A-Z0-9]+",
                "_",
                institution.upper(),
            ).strip("_")

            tokens = [
                f"__FIELD_{field.upper()}__",
                f"__ORG_{org_token}__",
                f"__PAGE_{page}__",
                f"__POS_{position_bucket}__",
                f"__SPAN_{length}__",
            ]

            if page == 1:
                tokens.append("__FIRST_PAGE__")
            if extract_dates(span_text):
                tokens.append("__HAS_DATE__")
            if COMPANY_SUFFIX_RE.search(span_text):
                tokens.append("__HAS_COMPANY_SUFFIX__")
            if GENERIC_LINE_RE.fullmatch(clean(selected[0]["line"])):
                tokens.append("__STARTS_WITH_LABEL_ONLY__")
            if any(token in upper for token in ("CERT", "REGISTRATION", "LICENSE")):
                tokens.append("__CERT_CONTEXT__")
            if any(token in upper for token in ("VALID", "EXPIR", "UNTIL")):
                tokens.append("__EXPIRY_CONTEXT__")
            if any(
                token in upper
                for token in (
                    "MANUFACTURER",
                    "MANUFACTURED BY",
                    "COMPANY NAME",
                    "NAME OF COMPANY",
                    "FACTORY",
                    "FACILITY",
                    "APPLICANT",
                )
            ):
                tokens.append("__MAKER_CONTEXT__")

            feature_text = (
                " ".join(tokens)
                + "\nPREV: "
                + previous
                + "\nSPAN: "
                + span_text
                + "\nNEXT: "
                + following
            )

            spans.append({
                "page": page,
                "start_line_no": int(selected[0]["line_no"]),
                "end_line_no": int(selected[-1]["line_no"]),
                "span_length": length,
                "span_text": span_text,
                "feature_text": feature_text,
            })

    return spans


def span_match_score(
    field: str,
    span_text: str,
    label_value: str,
    positive_line: str,
) -> float:
    scores: list[float] = []
    span_key = norm_key(span_text)
    positive_key = norm_key(positive_line)
    label_key = norm_key(label_value)

    if positive_key:
        if positive_key in span_key:
            scores.append(1.0)
        else:
            scores.append(
                SequenceMatcher(None, positive_key, span_key).ratio()
            )

    if field == "cert_no":
        target = normalize_cert(label_value)
        current = normalize_cert(span_text)
        if target and target in current:
            scores.append(1.0)

    elif field == "manufacturer":
        scores.append(
            manufacturer_similarity(label_value, span_text)
        )
        if label_key and label_key in span_key:
            scores.append(1.0)

    elif field == "expiry_date":
        if clean(label_value) in extract_dates(span_text):
            scores.append(1.0)

    return max(scores or [0.0])


def hard_negative_score(field: str, span: dict[str, Any]) -> float:
    text = span["span_text"]
    upper = text.upper()
    score = 0.0

    if int(span["page"]) == 1:
        score += 0.5
    if int(span["span_length"]) > 1:
        score += 0.3

    if field == "cert_no":
        score += min(
            3.0,
            sum(character.isdigit() for character in text) / 4.0,
        )
        if any(token in upper for token in ("CERT", "NO", "NUMBER", "ID")):
            score += 4.0

    elif field == "manufacturer":
        if COMPANY_SUFFIX_RE.search(text):
            score += 4.0
        if any(
            token in upper
            for token in (
                "MANUFACTURER",
                "COMPANY",
                "FACTORY",
                "FACILITY",
                "APPLICANT",
            )
        ):
            score += 4.0
        if GENERIC_LINE_RE.fullmatch(clean(text)):
            score -= 2.0

    elif field == "expiry_date":
        if extract_dates(text):
            score += 5.0
        if any(token in upper for token in ("VALID", "EXPIR", "UNTIL", "DATE")):
            score += 4.0

    return score


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_cache(runtime_root: Path, sha256: str) -> dict[str, Any]:
    path = runtime_root / "text_cache" / "combined" / f"{sha256}.json"
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_dataset(
    field: str,
    examples: list[dict[str, Any]],
    runtime_root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    deduped: dict[str, dict[str, Any]] = {}

    for example in examples:
        if clean(example.get("field")) != field:
            continue
        sha256 = clean(example.get("sha256"))
        if sha256 and sha256 not in deduped:
            deduped[sha256] = example

    candidate_rows: list[dict[str, Any]] = []
    document_rows: list[dict[str, Any]] = []

    for example in deduped.values():
        sha256 = clean(example.get("sha256"))
        institution = clean(example.get("institution"))
        label_value = clean(example.get("label_value"))
        positive_line = clean(example.get("positive_line"))
        validation_group = clean(example.get("validation_group"))

        payload = load_cache(runtime_root, sha256)
        rows = split_pages(str(payload.get("combined_text") or ""))
        spans = build_spans(field, institution, rows)

        if not spans:
            document_rows.append({
                "field": field,
                "sha256": sha256,
                "institution": institution,
                "validation_group": validation_group,
                "label_value": label_value,
                "status": "NO_CANDIDATE_SPANS",
                "candidate_count": 0,
                "positive_count": 0,
            })
            continue

        match_scores = [
            span_match_score(
                field,
                span["span_text"],
                label_value,
                positive_line,
            )
            for span in spans
        ]

        positive_indices = {
            index
            for index, score in enumerate(match_scores)
            if score >= 0.92
        }

        if not positive_indices:
            best_index = int(np.argmax(match_scores))
            if match_scores[best_index] >= 0.65:
                positive_indices.add(best_index)

        if not positive_indices:
            document_rows.append({
                "field": field,
                "sha256": sha256,
                "institution": institution,
                "validation_group": validation_group,
                "label_value": label_value,
                "status": "POSITIVE_SPAN_NOT_FOUND",
                "candidate_count": len(spans),
                "positive_count": 0,
            })
            continue

        negative_indices = [
            index
            for index in range(len(spans))
            if index not in positive_indices
        ]
        negative_indices.sort(
            key=lambda index: hard_negative_score(field, spans[index]),
            reverse=True,
        )

        max_negatives = int(
            FIELD_CONFIGS[field]["max_negatives_per_document"]
        )
        selected_negatives = negative_indices[:max_negatives]
        remaining = negative_indices[max_negatives:]

        if remaining:
            step = max(1, len(remaining) // 10)
            selected_negatives.extend(remaining[::step][:10])

        selected_indices = sorted(
            positive_indices | set(selected_negatives)
        )

        for index in selected_indices:
            span = spans[index]
            candidate_rows.append({
                "field": field,
                "sha256": sha256,
                "institution": institution,
                "validation_group": validation_group,
                "label_value": label_value,
                "page": int(span["page"]),
                "start_line_no": int(span["start_line_no"]),
                "end_line_no": int(span["end_line_no"]),
                "span_length": int(span["span_length"]),
                "span_text": span["span_text"],
                "feature_text": span["feature_text"],
                "is_positive": int(index in positive_indices),
                "match_score": round(float(match_scores[index]), 6),
            })

        document_rows.append({
            "field": field,
            "sha256": sha256,
            "institution": institution,
            "validation_group": validation_group,
            "label_value": label_value,
            "status": "READY",
            "candidate_count": len(selected_indices),
            "positive_count": len(positive_indices),
        })

    return pd.DataFrame(candidate_rows), pd.DataFrame(document_rows)


def build_pipeline(field: str) -> Pipeline:
    return Pipeline([
        (
            "tfidf",
            TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(2, 5),
                min_df=2,
                max_df=0.995,
                sublinear_tf=True,
                lowercase=True,
                max_features=int(
                    FIELD_CONFIGS[field]["max_features"]
                ),
                dtype=np.float32,
            ),
        ),
        (
            "classifier",
            LinearSVC(
                C=1.0,
                class_weight="balanced",
                max_iter=20000,
                dual="auto",
                random_state=42,
            ),
        ),
    ])


def evaluate(
    field: str,
    frame: pd.DataFrame,
    model_root: Path,
) -> tuple[dict[str, Any], pd.DataFrame]:
    groups = frame["validation_group"].astype(str).to_numpy()
    unique_groups = int(pd.Series(groups).nunique())
    n_splits = min(5, unique_groups)

    splitter = GroupKFold(n_splits=n_splits)
    X = frame["feature_text"].astype(str).to_numpy()
    y = frame["is_positive"].astype(int).to_numpy()
    oof_scores = np.full(len(frame), np.nan, dtype=float)
    folds = np.full(len(frame), -1, dtype=int)

    for fold, (train_index, test_index) in enumerate(
        splitter.split(X, y, groups),
        start=1,
    ):
        pipeline = build_pipeline(field)
        pipeline.fit(X[train_index], y[train_index])
        scores = np.asarray(
            pipeline.decision_function(X[test_index]),
            dtype=float,
        ).reshape(-1)

        oof_scores[test_index] = scores
        folds[test_index] = fold

        print(
            f"[{field}] Fold {fold}/{n_splits} "
            f"train={len(train_index)} test={len(test_index)}"
        )

    evaluated = frame.copy()
    evaluated["oof_score"] = oof_scores
    evaluated["fold"] = folds

    predictions: list[dict[str, Any]] = []

    for sha256, group in evaluated.groupby("sha256"):
        ranked = group.sort_values(
            "oof_score",
            ascending=False,
        ).reset_index(drop=True)

        positive_ranks = [
            index + 1
            for index, value in enumerate(ranked["is_positive"].tolist())
            if int(value) == 1
        ]
        best_rank = min(positive_ranks)
        top1_score = float(ranked.iloc[0]["oof_score"])
        second_score = (
            float(ranked.iloc[1]["oof_score"])
            if len(ranked) > 1
            else top1_score
        )

        predictions.append({
            "field": field,
            "sha256": sha256,
            "institution": ranked.iloc[0]["institution"],
            "validation_group": ranked.iloc[0]["validation_group"],
            "label_value": ranked.iloc[0]["label_value"],
            "top1_page": int(ranked.iloc[0]["page"]),
            "top1_start_line_no": int(ranked.iloc[0]["start_line_no"]),
            "top1_end_line_no": int(ranked.iloc[0]["end_line_no"]),
            "top1_span_length": int(ranked.iloc[0]["span_length"]),
            "top1_span_text": ranked.iloc[0]["span_text"],
            "top1_score": round(top1_score, 6),
            "score_gap": round(top1_score - second_score, 6),
            "top1_correct": int(best_rank == 1),
            "top3_correct": int(best_rank <= 3),
            "positive_rank": int(best_rank),
            "reciprocal_rank": round(1.0 / best_rank, 6),
            "candidate_count": int(len(ranked)),
            "fold": int(ranked.iloc[0]["fold"]),
        })

    prediction_frame = pd.DataFrame(predictions)

    correct_gaps = prediction_frame.loc[
        prediction_frame["top1_correct"] == 1,
        "score_gap",
    ].to_numpy(dtype=float)

    review_threshold = (
        float(np.quantile(correct_gaps, 0.10))
        if len(correct_gaps)
        else 0.0
    )

    try:
        ap = float(
            average_precision_score(
                evaluated["is_positive"],
                evaluated["oof_score"],
            )
        )
    except Exception:
        ap = 0.0

    try:
        roc_auc = float(
            roc_auc_score(
                evaluated["is_positive"],
                evaluated["oof_score"],
            )
        )
    except Exception:
        roc_auc = 0.0

    metrics = {
        "field": field,
        "documents": int(prediction_frame["sha256"].nunique()),
        "candidate_spans": int(len(evaluated)),
        "positive_spans": int(evaluated["is_positive"].sum()),
        "validation_groups": unique_groups,
        "cv_splits": n_splits,
        "top1_accuracy": round(
            float(prediction_frame["top1_correct"].mean()),
            6,
        ),
        "top3_accuracy": round(
            float(prediction_frame["top3_correct"].mean()),
            6,
        ),
        "mrr": round(
            float(prediction_frame["reciprocal_rank"].mean()),
            6,
        ),
        "candidate_average_precision": round(ap, 6),
        "candidate_roc_auc": round(roc_auc, 6),
        "recommended_review_gap_threshold": round(
            review_threshold,
            6,
        ),
    }

    final_pipeline = build_pipeline(field)
    final_pipeline.fit(X, y)

    joblib.dump(
        {
            "schema_version": SCHEMA_VERSION,
            "model_version": MODEL_VERSION,
            "field": field,
            "pipeline": final_pipeline,
            "metadata": metrics,
        },
        model_root / f"{field}_span_ranker.joblib",
        compress=3,
    )

    return metrics, prediction_frame


def suspected_label_issue(row: pd.Series) -> tuple[bool, str]:
    field = clean(row["field"])
    label = clean(row["label_value"])
    top1 = clean(row["top1_span_text"])

    if field == "expiry_date":
        top_dates = extract_dates(top1)
        if top_dates and label not in top_dates:
            upper = top1.upper()
            if any(token in upper for token in ("VALID UNTIL", "EXPIR", "VALIDITY")):
                return True, (
                    "Top-1 Span에 유효기간 표현과 다른 날짜가 함께 있어 "
                    "약지도 라벨의 과거·다른 날짜 가능성 검토 필요"
                )

    if field == "manufacturer":
        if GENERIC_LINE_RE.fullmatch(label):
            return True, "제조사 라벨값이 일반 라벨 또는 법인접미사만으로 구성됨"
        if len(manufacturer_tokens(label)) <= 1:
            return True, "제조사 라벨의 핵심 토큰이 1개 이하임"

    if field == "cert_no":
        if len(normalize_cert(label)) < 5:
            return True, "인증번호 라벨이 지나치게 짧음"

    return False, ""


def save_chart(
    metrics: pd.DataFrame,
    column: str,
    title: str,
    output: Path,
) -> None:
    frame = metrics.sort_values(column, ascending=True)
    plt.figure(figsize=(8, 4.5))
    plt.barh(frame["field"], frame[column])
    plt.xlim(0, 1.05)
    plt.xlabel(column)
    plt.title(title)

    for index, value in enumerate(frame[column].tolist()):
        plt.text(
            min(1.01, float(value) + 0.01),
            index,
            f"{float(value):.3f}",
            va="center",
        )

    plt.tight_layout()
    plt.savefig(output, dpi=160)
    plt.close()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create_html(
    summary: dict[str, Any],
    metrics: pd.DataFrame,
    errors: pd.DataFrame,
    suspected: pd.DataFrame,
    output: Path,
) -> None:
    metrics_html = metrics.to_html(index=False, escape=True)
    errors_html = (
        errors.head(100).to_html(index=False, escape=True)
        if not errors.empty
        else "<p>Top-1 오류 없음</p>"
    )
    suspected_html = (
        suspected.head(100).to_html(index=False, escape=True)
        if not suspected.empty
        else "<p>자동 탐지된 라벨 의심 없음</p>"
    )

    text = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>할랄 인증서 필드 Span 모델 결과</title>
<style>
body {{
    font-family: Arial, "Malgun Gothic", sans-serif;
    margin: 28px;
    color: #1f2937;
    background: #f8fafc;
}}
.section {{
    background: white;
    border: 1px solid #dbe3ec;
    border-radius: 10px;
    padding: 16px;
    margin: 16px 0;
    overflow: auto;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    font-size: 13px;
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
</style>
</head>
<body>
<h1>할랄 인증서 필드 Span 모델 결과</h1>
<p class="note">
1~3개 인접 줄을 하나의 후보로 묶어 인증번호·제조사·유효기간을
찾는 실제 지도학습 모델입니다. GroupKFold를 사용했습니다.
</p>
<div class="section">
<h2>요약</h2>
<p>학습 문서-필드: {summary["training_document_field_count"]}</p>
<p>후보 Span: {summary["candidate_span_count"]}</p>
</div>
<div class="section">
<h2>필드별 성능</h2>
{metrics_html}
</div>
<div class="section">
<h2>Top-1 정확도</h2>
<img src="08_top1_accuracy.png" alt="Top-1 정확도">
</div>
<div class="section">
<h2>Top-3 정확도</h2>
<img src="09_top3_accuracy.png" alt="Top-3 정확도">
</div>
<div class="section">
<h2>Top-1 오류</h2>
{errors_html}
</div>
<div class="section">
<h2>약지도 라벨 의심</h2>
{suspected_html}
</div>
</body>
</html>"""

    output.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--refinement-root", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    runtime_root = Path(args.runtime_root).resolve()
    refinement_root = Path(args.refinement_root).resolve()

    label_path = (
        refinement_root
        / "07_training_ready_field_examples.jsonl"
    )
    examples = read_jsonl(label_path)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_root = (
        runtime_root
        / "models"
        / f"field_span_extraction_{stamp}"
    )
    report_root = (
        runtime_root
        / "reports"
        / f"field_span_model_training_{stamp}"
    )

    model_root.mkdir(parents=True, exist_ok=False)
    report_root.mkdir(parents=True, exist_ok=False)

    candidate_frames: list[pd.DataFrame] = []
    document_frames: list[pd.DataFrame] = []
    prediction_frames: list[pd.DataFrame] = []
    metrics_rows: list[dict[str, Any]] = []

    print("")
    print("4B-2 Span 기반 실제 머신러닝 학습 시작")
    print("")

    for field in FIELDS:
        candidates, documents = build_dataset(
            field,
            examples,
            runtime_root,
        )

        ready_sha = set(
            documents.loc[
                documents["status"] == "READY",
                "sha256",
            ].astype(str)
        )
        candidates = candidates[
            candidates["sha256"].astype(str).isin(ready_sha)
        ].reset_index(drop=True)

        if candidates.empty:
            raise RuntimeError(f"{field}: 학습 후보 없음")

        print(
            f"{field}: 문서={len(ready_sha)}, "
            f"Span={len(candidates)}, "
            f"양성={int(candidates['is_positive'].sum())}"
        )

        metrics, predictions = evaluate(
            field,
            candidates,
            model_root,
        )

        candidate_frames.append(candidates)
        document_frames.append(documents)
        prediction_frames.append(predictions)
        metrics_rows.append(metrics)

    candidate_frame = pd.concat(candidate_frames, ignore_index=True)
    document_frame = pd.concat(document_frames, ignore_index=True)
    prediction_frame = pd.concat(prediction_frames, ignore_index=True)
    metrics_frame = pd.DataFrame(metrics_rows)

    top1_errors = prediction_frame[
        prediction_frame["top1_correct"] == 0
    ].copy()
    top3_failures = prediction_frame[
        prediction_frame["top3_correct"] == 0
    ].copy()

    suspicion_rows: list[dict[str, Any]] = []
    for _, row in top1_errors.iterrows():
        is_suspect, reason = suspected_label_issue(row)
        if is_suspect:
            payload = row.to_dict()
            payload["suspicion_reason"] = reason
            suspicion_rows.append(payload)

    suspected_frame = pd.DataFrame(suspicion_rows)

    candidate_frame.to_csv(
        report_root / "01_span_training_rows.csv",
        index=False,
        encoding="utf-8-sig",
    )
    document_frame.to_csv(
        report_root / "02_training_documents.csv",
        index=False,
        encoding="utf-8-sig",
    )
    metrics_frame.to_csv(
        report_root / "03_field_metrics.csv",
        index=False,
        encoding="utf-8-sig",
    )
    prediction_frame.to_csv(
        report_root / "04_oof_predictions.csv",
        index=False,
        encoding="utf-8-sig",
    )
    top1_errors.to_csv(
        report_root / "05_top1_errors.csv",
        index=False,
        encoding="utf-8-sig",
    )
    top3_failures.to_csv(
        report_root / "06_top3_failures.csv",
        index=False,
        encoding="utf-8-sig",
    )
    suspected_frame.to_csv(
        report_root / "07_suspected_label_issues.csv",
        index=False,
        encoding="utf-8-sig",
    )

    save_chart(
        metrics_frame,
        "top1_accuracy",
        "Span 모델 GroupKFold Top-1 정확도",
        report_root / "08_top1_accuracy.png",
    )
    save_chart(
        metrics_frame,
        "top3_accuracy",
        "Span 모델 GroupKFold Top-3 정확도",
        report_root / "09_top3_accuracy.png",
    )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "run_id": stamp,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(project_root),
        "runtime_root": str(runtime_root),
        "refinement_root": str(refinement_root),
        "model_root": str(model_root),
        "report_root": str(report_root),
        "evaluation_type": "GroupKFold by validation_group",
        "fields": list(FIELDS),
        "training_document_field_count": int(
            document_frame.loc[
                document_frame["status"] == "READY",
                ["field", "sha256"],
            ].drop_duplicates().shape[0]
        ),
        "candidate_span_count": int(len(candidate_frame)),
        "positive_span_count": int(
            candidate_frame["is_positive"].sum()
        ),
        "top1_error_count": int(len(top1_errors)),
        "top3_failure_count": int(len(top3_failures)),
        "suspected_label_issue_count": int(len(suspected_frame)),
        "field_metrics": metrics_rows,
        "improvements": [
            "1~3개 인접 줄을 하나의 후보로 사용",
            "페이지 마커 제외",
            "Company Name/Valid until 라벨과 다음 줄 결합",
            "영문 월 날짜 형식 추가",
            "제조국 운영 모델 제외",
        ],
        "important_warning": (
            "약지도 라벨 기반이므로 07_suspected_label_issues.csv의 "
            "원본 확인이 최종 운영 전 필요합니다."
        ),
        "next_step": (
            "성능 확인 후 cert_no/manufacturer/expiry_date Span 모델을 "
            "운영 후보로 확정하고, 제품 목록 페이지·행 분류 모델을 학습합니다."
        ),
        "packages": {
            "python": sys.version,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    }

    write_json(report_root / "10_summary.json", summary)
    write_json(model_root / "model_metadata.json", summary)

    create_html(
        summary,
        metrics_frame,
        top1_errors,
        suspected_frame,
        report_root / "11_model_report.html",
    )

    smoke = {
        "model_root": str(model_root),
        "model_files": sorted(
            path.name for path in model_root.glob("*.joblib")
        ),
        "all_models_exist": all(
            (
                model_root
                / f"{field}_span_ranker.joblib"
            ).exists()
            for field in FIELDS
        ),
    }
    write_json(report_root / "12_smoke_test.json", smoke)

    current_pointer = (
        runtime_root
        / "models"
        / "current_field_span_model.txt"
    )
    latest_pointer = (
        runtime_root
        / "reports"
        / "latest_field_span_model_training.txt"
    )

    current_pointer.write_text(str(model_root), encoding="utf-8")
    latest_pointer.write_text(str(report_root), encoding="utf-8")

    print("")
    print("4B-2 완료")
    print(metrics_frame[
        [
            "field",
            "documents",
            "top1_accuracy",
            "top3_accuracy",
            "mrr",
        ]
    ].to_string(index=False))
    print("")
    print(f"모델: {model_root}")
    print(f"보고서: {report_root}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())