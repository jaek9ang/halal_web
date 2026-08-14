from __future__ import annotations

import argparse
import html
import json
import math
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


SCHEMA_VERSION = "field_ranker_v1"
MODEL_VERSION = "char_tfidf_linear_svm_field_ranker_v1"
FIELD_CONFIGS = {
    "cert_no": {
        "max_negatives_per_document": 45,
        "max_features": 100000,
        "experimental": False,
        "activation_note": (
            "인증번호 원문을 찾는 모델입니다. LPPOM- 등 접두어 제거는 "
            "PMF 비교용 정규화에서만 수행합니다."
        ),
    },
    "manufacturer": {
        "max_negatives_per_document": 55,
        "max_features": 120000,
        "experimental": False,
        "activation_note": (
            "제조사 원문을 찾는 모델입니다. ANHUI 같은 지역명은 원문에서 "
            "삭제하지 않고 PMF 비교 시 핵심 회사명 토큰으로 비교합니다."
        ),
    },
    "expiry_date": {
        "max_negatives_per_document": 45,
        "max_features": 90000,
        "experimental": False,
        "activation_note": (
            "현재 PDF에 적힌 유효기간을 학습합니다. PMF 날짜와의 일치는 "
            "학습 조건으로 사용하지 않습니다."
        ),
    },
    "manufacturing_country": {
        "max_negatives_per_document": 55,
        "max_features": 100000,
        "experimental": True,
        "activation_note": (
            "발급기관 국가와 제조국 혼동 가능성이 있어 실험용으로만 학습하며 "
            "운영 자동확정에 사용하지 않습니다."
        ),
    },
}

PAGE_MARKER_RE = re.compile(
    r"---\s*PAGE\s+(\d+)\s*\[[^\]]*\]\s*---",
    re.IGNORECASE,
)
DATE_NUMERIC_RE = re.compile(
    r"\b(20\d{2})[-./](\d{1,2})[-./](\d{1,2})\b"
)
DATE_DMY_RE = re.compile(
    r"\b(\d{1,2})[-./](\d{1,2})[-./](20\d{2})\b"
)
MONTH_RE = re.compile(
    r"\b(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|"
    r"SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\b",
    re.IGNORECASE,
)
COMPANY_SUFFIX_RE = re.compile(
    r"\b(?:CO\.?|COMPANY|CORP\.?|CORPORATION|INC\.?|LTD\.?|LIMITED|"
    r"LLC|PTE\.?\s*LTD\.?|SDN\.?\s*BHD\.?|GMBH|B\.?V\.?|"
    r"S\.?A\.?|PLC|AG|INDUSTRIES?)\b",
    re.IGNORECASE,
)
WHITESPACE_RE = re.compile(r"\s+")


def clean(value: Any) -> str:
    text = str(value or "").replace("\u00a0", " ").replace("\x00", " ")
    return WHITESPACE_RE.sub(" ", text).strip()


def norm_key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9가-힣]+", "", clean(value).upper())


def normalize_cert_match(value: Any) -> str:
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
    left_tokens = set(manufacturer_tokens(left))
    right_tokens = set(manufacturer_tokens(right))

    if not left_tokens or not right_tokens:
        return 0.0

    intersection = len(left_tokens & right_tokens)
    containment = intersection / max(
        1,
        min(len(left_tokens), len(right_tokens)),
    )
    jaccard = intersection / max(
        1,
        len(left_tokens | right_tokens),
    )
    return max(containment, jaccard)


def contains_date(line: str) -> bool:
    return bool(
        DATE_NUMERIC_RE.search(line)
        or DATE_DMY_RE.search(line)
        or MONTH_RE.search(line)
    )


def extract_dates(line: str) -> list[str]:
    results: list[str] = []

    for match in DATE_NUMERIC_RE.finditer(line):
        year, month, day = map(int, match.groups())
        try:
            results.append(
                f"{year:04d}-{month:02d}-{day:02d}"
            )
        except ValueError:
            continue

    for match in DATE_DMY_RE.finditer(line):
        day, month, year = map(int, match.groups())
        try:
            results.append(
                f"{year:04d}-{month:02d}-{day:02d}"
            )
        except ValueError:
            continue

    return list(dict.fromkeys(results))


def split_pages_and_lines(text: str) -> list[dict[str, Any]]:
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
    global_index = 0

    for page, chunk in chunks:
        for line_no, line in enumerate(chunk.splitlines(), start=1):
            current = clean(line)
            if not current:
                continue
            rows.append({
                "global_index": global_index,
                "page": page,
                "line_no": line_no,
                "line": current,
            })
            global_index += 1

    return rows


def eligible(field: str, row: dict[str, Any]) -> bool:
    line = row["line"]
    upper = line.upper()
    page = int(row["page"])

    if len(line) < 2 or len(line) > 280:
        return False

    if field == "cert_no":
        return bool(
            page <= 3
            and (
                re.search(r"\d", line)
                or "CERT" in upper
                or "REGISTRATION" in upper
            )
        )

    if field == "expiry_date":
        return bool(
            page <= 4
            and (
                contains_date(line)
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
        )

    if field == "manufacturer":
        return bool(
            page <= 4
            and re.search(r"[A-Za-z가-힣]", line)
            and len(norm_key(line)) >= 3
        )

    if field == "manufacturing_country":
        return bool(
            page <= 4
            and re.search(r"[A-Za-z가-힣]", line)
            and len(norm_key(line)) >= 3
        )

    return False


def feature_text(
    field: str,
    institution: str,
    rows: list[dict[str, Any]],
    index: int,
) -> str:
    row = rows[index]
    current = row["line"]
    previous = rows[index - 1]["line"] if index > 0 else ""
    following = rows[index + 1]["line"] if index + 1 < len(rows) else ""
    upper = current.upper()

    page = int(row["page"])
    line_no = int(row["line_no"])
    position_bucket = min(9, line_no // 5)

    org_token = re.sub(
        r"[^A-Z0-9]+",
        "_",
        institution.upper(),
    ).strip("_")

    tokens = [
        f"__FIELD_{field.upper()}__",
        f"__ORG_{org_token}__",
        f"__PAGE_{min(page, 9)}__",
        f"__POS_{position_bucket}__",
    ]

    if page == 1:
        tokens.append("__FIRST_PAGE__")
    if re.search(r"\d", current):
        tokens.append("__HAS_DIGIT__")
    if contains_date(current):
        tokens.append("__HAS_DATE__")
    if COMPANY_SUFFIX_RE.search(current):
        tokens.append("__HAS_COMPANY_SUFFIX__")
    if any(token in upper for token in ("CERT", "REGISTRATION", "LICENSE")):
        tokens.append("__CERT_KEYWORD__")
    if any(token in upper for token in ("VALID", "EXPIR", "UNTIL")):
        tokens.append("__EXPIRY_KEYWORD__")
    if any(
        token in upper
        for token in (
            "MANUFACTURER",
            "MANUFACTURED BY",
            "COMPANY NAME",
            "FACTORY",
            "APPLICANT",
        )
    ):
        tokens.append("__MAKER_KEYWORD__")
    if any(token in upper for token in ("COUNTRY", "ADDRESS", "SITE", "PLANT")):
        tokens.append("__COUNTRY_CONTEXT__")

    return (
        " ".join(tokens)
        + "\nPREV: "
        + previous
        + "\nCUR: "
        + current
        + "\nNEXT: "
        + following
    )


def line_match_score(
    field: str,
    line: str,
    label_value: str,
    positive_line: str,
) -> float:
    line_key = norm_key(line)
    label_key = norm_key(label_value)
    positive_key = norm_key(positive_line)

    scores: list[float] = []

    if positive_key:
        if positive_key == line_key:
            scores.append(1.0)
        elif positive_key in line_key or line_key in positive_key:
            ratio = min(
                len(positive_key),
                len(line_key),
            ) / max(
                1,
                max(len(positive_key), len(line_key)),
            )
            scores.append(0.85 + 0.14 * ratio)
        else:
            scores.append(
                SequenceMatcher(
                    None,
                    positive_key,
                    line_key,
                ).ratio()
            )

    if field == "cert_no":
        target = normalize_cert_match(label_value)
        current = normalize_cert_match(line)
        if target and target in current:
            scores.append(1.0)

    elif field == "manufacturer":
        scores.append(
            manufacturer_similarity(label_value, line)
        )
        if label_key and label_key in line_key:
            scores.append(1.0)

    elif field == "expiry_date":
        if clean(label_value) in extract_dates(line):
            scores.append(1.0)

    elif field == "manufacturing_country":
        if label_key and label_key in line_key:
            scores.append(1.0)

    return max(scores or [0.0])


def hard_negative_score(
    field: str,
    row: dict[str, Any],
    known_countries: set[str],
) -> float:
    line = row["line"]
    upper = line.upper()
    score = 0.0

    if int(row["page"]) == 1:
        score += 0.4

    if field == "cert_no":
        score += min(
            3.0,
            sum(character.isdigit() for character in line) / 4.0,
        )
        if any(token in upper for token in ("CERT", "NO", "NUMBER", "ID")):
            score += 3.0

    elif field == "manufacturer":
        if COMPANY_SUFFIX_RE.search(line):
            score += 4.0
        if any(
            token in upper
            for token in (
                "MANUFACTURER",
                "COMPANY",
                "FACTORY",
                "APPLICANT",
            )
        ):
            score += 3.0
        score += min(2.0, len(line) / 80.0)

    elif field == "expiry_date":
        if contains_date(line):
            score += 4.0
        if any(token in upper for token in ("VALID", "EXPIR", "UNTIL", "DATE")):
            score += 3.0

    elif field == "manufacturing_country":
        line_key = norm_key(line)
        if any(
            norm_key(country) in line_key
            for country in known_countries
            if norm_key(country)
        ):
            score += 4.0
        if any(
            token in upper
            for token in (
                "COUNTRY",
                "ADDRESS",
                "FACTORY",
                "PLANT",
                "SITE",
            )
        ):
            score += 3.0

    return score


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if not line.strip():
                continue
            rows.append(json.loads(line))

    return rows


def load_cache(
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
        raise FileNotFoundError(path)

    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def build_field_dataset(
    *,
    field: str,
    examples: list[dict[str, Any]],
    runtime_root: Path,
    known_countries: set[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    config = FIELD_CONFIGS[field]
    candidate_rows: list[dict[str, Any]] = []
    document_rows: list[dict[str, Any]] = []

    deduped: dict[str, dict[str, Any]] = {}
    for example in examples:
        if clean(example.get("field")) != field:
            continue
        sha256 = clean(example.get("sha256"))
        if sha256 and sha256 not in deduped:
            deduped[sha256] = example

    for document_index, example in enumerate(deduped.values()):
        sha256 = clean(example.get("sha256"))
        institution = clean(example.get("institution"))
        label_value = clean(example.get("label_value"))
        positive_line = clean(example.get("positive_line"))
        positive_page = int(example.get("positive_page") or 0)
        positive_line_no = int(example.get("positive_line_no") or 0)
        validation_group = clean(example.get("validation_group"))

        payload = load_cache(runtime_root, sha256)
        rows = split_pages_and_lines(
            str(payload.get("combined_text") or "")
        )

        eligible_indices = [
            index
            for index, row in enumerate(rows)
            if eligible(field, row)
        ]

        if not eligible_indices:
            continue

        match_scores: dict[int, float] = {}
        positive_indices: set[int] = set()

        for index in eligible_indices:
            row = rows[index]
            score = line_match_score(
                field,
                row["line"],
                label_value,
                positive_line,
            )
            match_scores[index] = score

            exact_position = bool(
                positive_page > 0
                and positive_line_no > 0
                and int(row["page"]) == positive_page
                and int(row["line_no"]) == positive_line_no
            )

            if exact_position or score >= 0.90:
                positive_indices.add(index)

        if not positive_indices:
            best_index = max(
                eligible_indices,
                key=lambda index: match_scores.get(index, 0.0),
            )
            if match_scores.get(best_index, 0.0) >= 0.55:
                positive_indices.add(best_index)

        if not positive_indices:
            document_rows.append({
                "sha256": sha256,
                "institution": institution,
                "field": field,
                "validation_group": validation_group,
                "label_value": label_value,
                "candidate_count": len(eligible_indices),
                "positive_count": 0,
                "status": "POSITIVE_LINE_NOT_FOUND",
            })
            continue

        negative_indices = [
            index
            for index in eligible_indices
            if index not in positive_indices
        ]
        negative_indices.sort(
            key=lambda index: (
                hard_negative_score(
                    field,
                    rows[index],
                    known_countries,
                ),
                -abs(index - min(positive_indices)),
            ),
            reverse=True,
        )

        max_negatives = int(
            config["max_negatives_per_document"]
        )
        selected_negatives = negative_indices[:max_negatives]

        # 문서 전체 위치를 조금씩 반영하기 위한 결정적 분산 샘플
        remaining = negative_indices[max_negatives:]
        if remaining:
            step = max(1, len(remaining) // 8)
            selected_negatives.extend(
                remaining[::step][:8]
            )

        selected_indices = sorted(
            positive_indices | set(selected_negatives)
        )

        for index in selected_indices:
            row = rows[index]
            candidate_rows.append({
                "field": field,
                "sha256": sha256,
                "institution": institution,
                "validation_group": validation_group,
                "label_value": label_value,
                "page": int(row["page"]),
                "line_no": int(row["line_no"]),
                "line": row["line"],
                "feature_text": feature_text(
                    field,
                    institution,
                    rows,
                    index,
                ),
                "is_positive": int(
                    index in positive_indices
                ),
                "match_score": round(
                    float(match_scores.get(index, 0.0)),
                    6,
                ),
                "document_index": document_index,
            })

        document_rows.append({
            "sha256": sha256,
            "institution": institution,
            "field": field,
            "validation_group": validation_group,
            "label_value": label_value,
            "candidate_count": len(selected_indices),
            "positive_count": len(positive_indices),
            "status": "READY",
        })

    return (
        pd.DataFrame(candidate_rows),
        pd.DataFrame(document_rows),
    )


def build_pipeline(max_features: int) -> Pipeline:
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
                max_features=max_features,
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


def evaluate_field(
    *,
    field: str,
    frame: pd.DataFrame,
    model_root: Path,
    known_countries: list[str],
) -> tuple[dict[str, Any], pd.DataFrame]:
    ready = frame.copy()
    unique_groups = int(
        ready["validation_group"].nunique()
    )

    if unique_groups < 2:
        raise RuntimeError(
            f"{field}: validation_group이 2개 미만입니다."
        )

    n_splits = min(5, unique_groups)
    splitter = GroupKFold(n_splits=n_splits)
    oof_scores = np.full(len(ready), np.nan, dtype=float)
    fold_values = np.full(len(ready), -1, dtype=int)

    X = ready["feature_text"].astype(str).to_numpy()
    y = ready["is_positive"].astype(int).to_numpy()
    groups = ready["validation_group"].astype(str).to_numpy()

    for fold, (train_index, test_index) in enumerate(
        splitter.split(X, y, groups),
        start=1,
    ):
        pipeline = build_pipeline(
            int(FIELD_CONFIGS[field]["max_features"])
        )
        pipeline.fit(X[train_index], y[train_index])
        scores = np.asarray(
            pipeline.decision_function(X[test_index]),
            dtype=float,
        ).reshape(-1)

        oof_scores[test_index] = scores
        fold_values[test_index] = fold

        print(
            f"[{field}] Fold {fold}/{n_splits} "
            f"train={len(train_index)} test={len(test_index)}"
        )

    ready["oof_score"] = oof_scores
    ready["fold"] = fold_values

    document_predictions: list[dict[str, Any]] = []

    for sha256, group in ready.groupby("sha256"):
        ranked = group.sort_values(
            "oof_score",
            ascending=False,
        ).reset_index(drop=True)

        positive_ranks = [
            index + 1
            for index, value in enumerate(
                ranked["is_positive"].tolist()
            )
            if int(value) == 1
        ]
        best_rank = min(positive_ranks)
        top1_correct = int(best_rank == 1)
        top3_correct = int(best_rank <= 3)

        top_score = float(ranked.iloc[0]["oof_score"])
        second_score = (
            float(ranked.iloc[1]["oof_score"])
            if len(ranked) > 1
            else top_score
        )
        score_gap = top_score - second_score

        document_predictions.append({
            "field": field,
            "sha256": sha256,
            "institution": ranked.iloc[0]["institution"],
            "validation_group": ranked.iloc[0]["validation_group"],
            "label_value": ranked.iloc[0]["label_value"],
            "top1_page": int(ranked.iloc[0]["page"]),
            "top1_line_no": int(ranked.iloc[0]["line_no"]),
            "top1_line": ranked.iloc[0]["line"],
            "top1_score": round(top_score, 6),
            "score_gap": round(score_gap, 6),
            "top1_correct": top1_correct,
            "top3_correct": top3_correct,
            "positive_rank": int(best_rank),
            "reciprocal_rank": round(1.0 / best_rank, 6),
            "candidate_count": int(len(ranked)),
            "fold": int(ranked.iloc[0]["fold"]),
        })

    predictions = pd.DataFrame(document_predictions)
    correct_gaps = predictions.loc[
        predictions["top1_correct"] == 1,
        "score_gap",
    ].to_numpy(dtype=float)

    if len(correct_gaps):
        review_threshold = float(
            np.quantile(correct_gaps, 0.10)
        )
    else:
        review_threshold = 0.0

    try:
        candidate_ap = float(
            average_precision_score(
                ready["is_positive"],
                ready["oof_score"],
            )
        )
    except Exception:
        candidate_ap = 0.0

    try:
        candidate_roc_auc = float(
            roc_auc_score(
                ready["is_positive"],
                ready["oof_score"],
            )
        )
    except Exception:
        candidate_roc_auc = 0.0

    metrics = {
        "field": field,
        "documents": int(
            predictions["sha256"].nunique()
        ),
        "candidate_rows": int(len(ready)),
        "positive_rows": int(
            ready["is_positive"].sum()
        ),
        "validation_groups": unique_groups,
        "cv_splits": n_splits,
        "top1_accuracy": round(
            float(predictions["top1_correct"].mean()),
            6,
        ),
        "top3_accuracy": round(
            float(predictions["top3_correct"].mean()),
            6,
        ),
        "mrr": round(
            float(predictions["reciprocal_rank"].mean()),
            6,
        ),
        "candidate_average_precision": round(
            candidate_ap,
            6,
        ),
        "candidate_roc_auc": round(
            candidate_roc_auc,
            6,
        ),
        "recommended_review_gap_threshold": round(
            review_threshold,
            6,
        ),
        "experimental": bool(
            FIELD_CONFIGS[field]["experimental"]
        ),
        "activation_note": FIELD_CONFIGS[field][
            "activation_note"
        ],
    }

    final_pipeline = build_pipeline(
        int(FIELD_CONFIGS[field]["max_features"])
    )
    final_pipeline.fit(X, y)

    model_payload = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "field": field,
        "pipeline": final_pipeline,
        "metadata": {
            **metrics,
            "known_countries": known_countries,
            "confidence_note": (
                "SVM 결정점수와 후보 간 점수 차이는 "
                "보정된 확률이 아닙니다."
            ),
        },
    }

    joblib.dump(
        model_payload,
        model_root / f"{field}_ranker.joblib",
        compress=3,
    )

    return metrics, predictions


def save_metric_chart(
    metrics_frame: pd.DataFrame,
    value_column: str,
    title: str,
    output_path: Path,
) -> None:
    plot_frame = metrics_frame.sort_values(
        value_column,
        ascending=True,
    )

    plt.figure(figsize=(9, 5))
    plt.barh(
        plot_frame["field"],
        plot_frame[value_column],
    )
    plt.xlim(0, 1.05)
    plt.xlabel(value_column)
    plt.title(title)

    for index, value in enumerate(
        plot_frame[value_column].tolist()
    ):
        plt.text(
            min(1.01, float(value) + 0.01),
            index,
            f"{float(value):.3f}",
            va="center",
        )

    plt.tight_layout()
    plt.savefig(output_path, dpi=160)
    plt.close()


def create_html_report(
    *,
    summary: dict[str, Any],
    metrics: pd.DataFrame,
    errors: pd.DataFrame,
    output_path: Path,
) -> None:
    cards = [
        ("학습 필드", summary["field_count"]),
        ("학습 문서-필드", summary["training_document_field_count"]),
        ("후보 줄", summary["candidate_row_count"]),
        ("검증 방식", "GroupKFold"),
        ("운영 후보 필드", summary["production_candidate_field_count"]),
        ("실험 필드", summary["experimental_field_count"]),
    ]

    card_html = "".join(
        "<div class='card'><div>"
        + html.escape(str(label))
        + "</div><div class='value'>"
        + html.escape(str(value))
        + "</div></div>"
        for label, value in cards
    )

    metrics_html = metrics.to_html(
        index=False,
        escape=True,
    )
    errors_html = (
        errors.head(100).to_html(
            index=False,
            escape=True,
        )
        if not errors.empty
        else "<p>Top-1 오류 없음</p>"
    )

    html_text = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>할랄 인증서 필드 순위 모델 학습 결과</title>
<style>
body {{
    font-family: Arial, "Malgun Gothic", sans-serif;
    margin: 28px;
    color: #1f2937;
    background: #f8fafc;
}}
.grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
    margin: 18px 0 26px;
}}
.card, .section {{
    background: white;
    border: 1px solid #dbe3ec;
    border-radius: 10px;
    padding: 16px;
}}
.section {{
    margin: 16px 0;
    overflow: auto;
}}
.value {{
    font-size: 25px;
    font-weight: 700;
    margin-top: 6px;
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
    max-width: 1000px;
    height: auto;
}}
.note {{
    color: #64748b;
    font-size: 14px;
}}
.warning {{
    border-left: 4px solid #64748b;
    padding-left: 12px;
}}
</style>
</head>
<body>
<h1>할랄 인증서 필드 순위 모델 학습 결과</h1>
<p class="note">
기관, 페이지, 줄 위치, 앞뒤 문장과 형식 특징으로
정답 필드가 있는 줄을 찾는 실제 지도학습 모델입니다.
동일 제조사·갱신본·유사 문서는 validation_group 기준으로
같은 Fold에 배치했습니다.
</p>
<div class="grid">{card_html}</div>
<div class="section">
<h2>필드별 그룹 교차검증</h2>
{metrics_html}
</div>
<div class="section">
<h2>Top-1 정확도</h2>
<img src="07_top1_accuracy.png" alt="필드별 Top-1 정확도">
</div>
<div class="section">
<h2>Top-3 정확도</h2>
<img src="08_top3_accuracy.png" alt="필드별 Top-3 정확도">
</div>
<div class="section">
<h2>Top-1 오류</h2>
{errors_html}
</div>
<div class="section warning">
<h2>운영 적용 제한</h2>
<p>
manufacturing_country는 REPUBLIK INDONESIA 같은 발급기관 국가를
제조국으로 오인할 수 있어 실험용입니다.
제품 목록은 이번 모델에 포함하지 않았으며 별도 영역·행 분류 모델로 학습합니다.
</p>
</div>
</body>
</html>"""

    output_path.write_text(
        html_text,
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

    single_value_examples = [
        example
        for example in examples
        if clean(example.get("field")) in FIELD_CONFIGS
    ]

    known_countries = sorted({
        clean(example.get("label_value")).upper()
        for example in single_value_examples
        if clean(example.get("field"))
        == "manufacturing_country"
        and clean(example.get("label_value"))
    })

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_root = (
        runtime_root
        / "models"
        / f"field_extraction_{stamp}"
    )
    report_root = (
        runtime_root
        / "reports"
        / f"field_model_training_{stamp}"
    )

    model_root.mkdir(parents=True, exist_ok=False)
    report_root.mkdir(parents=True, exist_ok=False)

    all_candidates: list[pd.DataFrame] = []
    all_documents: list[pd.DataFrame] = []
    field_metrics: list[dict[str, Any]] = []
    all_predictions: list[pd.DataFrame] = []

    print("")
    print("실제 필드 후보 순위 모델 학습을 시작합니다.")
    print(f"학습 라벨: {label_path}")
    print("")

    for field in FIELD_CONFIGS:
        field_frame, document_frame = build_field_dataset(
            field=field,
            examples=single_value_examples,
            runtime_root=runtime_root,
            known_countries=set(known_countries),
        )

        ready_documents = document_frame[
            document_frame["status"] == "READY"
        ].copy()
        ready_sha = set(
            ready_documents["sha256"].astype(str)
        )
        field_frame = field_frame[
            field_frame["sha256"].astype(str).isin(
                ready_sha
            )
        ].reset_index(drop=True)

        if field_frame.empty:
            raise RuntimeError(
                f"{field}: 학습 후보 줄이 없습니다."
            )
        if int(field_frame["is_positive"].sum()) == 0:
            raise RuntimeError(
                f"{field}: 양성 학습 줄이 없습니다."
            )

        print(
            f"{field}: 문서={len(ready_documents)}, "
            f"후보줄={len(field_frame)}, "
            f"양성줄={int(field_frame['is_positive'].sum())}"
        )

        metrics, predictions = evaluate_field(
            field=field,
            frame=field_frame,
            model_root=model_root,
            known_countries=known_countries,
        )

        field_metrics.append(metrics)
        all_predictions.append(predictions)
        all_candidates.append(field_frame)
        all_documents.append(document_frame)

    candidate_frame = pd.concat(
        all_candidates,
        ignore_index=True,
    )
    document_frame = pd.concat(
        all_documents,
        ignore_index=True,
    )
    predictions_frame = pd.concat(
        all_predictions,
        ignore_index=True,
    )
    metrics_frame = pd.DataFrame(field_metrics)

    errors = predictions_frame[
        predictions_frame["top1_correct"] == 0
    ].copy()

    candidate_frame.to_csv(
        report_root / "01_candidate_training_rows.csv",
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
    predictions_frame.to_csv(
        report_root / "04_oof_document_predictions.csv",
        index=False,
        encoding="utf-8-sig",
    )
    errors.to_csv(
        report_root / "05_top1_errors.csv",
        index=False,
        encoding="utf-8-sig",
    )

    country_review = predictions_frame[
        predictions_frame["field"]
        == "manufacturing_country"
    ].copy()
    country_review.to_csv(
        report_root / "06_country_predictions_review.csv",
        index=False,
        encoding="utf-8-sig",
    )

    save_metric_chart(
        metrics_frame,
        "top1_accuracy",
        "필드별 GroupKFold Top-1 정확도",
        report_root / "07_top1_accuracy.png",
    )
    save_metric_chart(
        metrics_frame,
        "top3_accuracy",
        "필드별 GroupKFold Top-3 정확도",
        report_root / "08_top3_accuracy.png",
    )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "run_id": stamp,
        "created_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "project_root": str(project_root),
        "runtime_root": str(runtime_root),
        "refinement_root": str(refinement_root),
        "model_root": str(model_root),
        "report_root": str(report_root),
        "evaluation_type": (
            "GroupKFold by validation_group; "
            "same manufacturer/renewal/near-duplicate group kept together"
        ),
        "field_count": int(len(metrics_frame)),
        "training_document_field_count": int(
            document_frame.loc[
                document_frame["status"] == "READY",
                ["field", "sha256"],
            ].drop_duplicates().shape[0]
        ),
        "candidate_row_count": int(
            len(candidate_frame)
        ),
        "positive_row_count": int(
            candidate_frame["is_positive"].sum()
        ),
        "production_candidate_fields": [
            field
            for field, config in FIELD_CONFIGS.items()
            if not config["experimental"]
        ],
        "experimental_fields": [
            field
            for field, config in FIELD_CONFIGS.items()
            if config["experimental"]
        ],
        "production_candidate_field_count": sum(
            not config["experimental"]
            for config in FIELD_CONFIGS.values()
        ),
        "experimental_field_count": sum(
            bool(config["experimental"])
            for config in FIELD_CONFIGS.values()
        ),
        "field_metrics": field_metrics,
        "known_country_label_count": len(
            known_countries
        ),
        "normalization_policy": {
            "cert_no": (
                "원문 보존. PMF 비교 시 LPPOM- 및 "
                "ID+장문숫자 접두어를 비교용으로만 제거."
            ),
            "manufacturer": (
                "원문 보존. 대소문자·문장부호·법인접미사를 정리하고 "
                "핵심 토큰 포함도로 비교. 앞 지역명 한 단어 차이를 허용."
            ),
            "expiry_date": (
                "현재 PDF 본문값을 정답으로 사용. PMF 날짜는 학습 조건에서 제외."
            ),
            "manufacturing_country": (
                "실험용. 발급기관 국가와 제조국 구분 검토 필요."
            ),
        },
        "important_warning": (
            "현재 라벨은 4A-2 약지도 후보입니다. GroupKFold로 템플릿 누출을 "
            "줄였지만 신규 기관 양식의 완전한 독립 테스트를 대체하지 않습니다."
        ),
        "next_step": (
            "03_field_metrics.csv와 05_top1_errors.csv를 검토한 후 "
            "cert_no/manufacturer/expiry_date 운영 후보를 확정하고, "
            "products는 별도 페이지·행 분류 모델로 학습합니다."
        ),
        "packages": {
            "python": sys.version,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    }

    write_json(
        report_root / "09_summary.json",
        summary,
    )
    write_json(
        model_root / "model_metadata.json",
        summary,
    )

    create_html_report(
        summary=summary,
        metrics=metrics_frame,
        errors=errors,
        output_path=report_root / "10_model_report.html",
    )

    smoke_payload = {
        "model_root": str(model_root),
        "files": sorted(
            path.name
            for path in model_root.glob("*.joblib")
        ),
        "all_model_files_exist": all(
            (
                model_root
                / f"{field}_ranker.joblib"
            ).exists()
            for field in FIELD_CONFIGS
        ),
    }
    write_json(
        report_root / "11_smoke_test.json",
        smoke_payload,
    )

    current_pointer = (
        runtime_root
        / "models"
        / "current_field_model.txt"
    )
    latest_report_pointer = (
        runtime_root
        / "reports"
        / "latest_field_model_training.txt"
    )

    current_pointer.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    latest_report_pointer.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    current_pointer.write_text(
        str(model_root),
        encoding="utf-8",
    )
    latest_report_pointer.write_text(
        str(report_root),
        encoding="utf-8",
    )

    print("")
    print("4B 실제 머신러닝 학습 완료")
    print(f"모델 폴더 : {model_root}")
    print(f"보고서 폴더: {report_root}")
    print("")
    print(metrics_frame[
        [
            "field",
            "documents",
            "top1_accuracy",
            "top3_accuracy",
            "mrr",
            "experimental",
        ]
    ].to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())