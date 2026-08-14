from __future__ import annotations

import html
import json
import math
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import matplotlib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

matplotlib.use("Agg")
import matplotlib.pyplot as plt


RUNTIME_ROOT = Path(
    r"D:\halal_web_runtime\certificate_classifier"
)
REPORTS_ROOT = RUNTIME_ROOT / "reports"
MODELS_ROOT = RUNTIME_ROOT / "models"
COMBINED_CACHE_ROOT = (
    RUNTIME_ROOT / "text_cache" / "combined"
)
LATEST_OCR_POINTER = (
    REPORTS_ROOT / "latest_ocr_run.txt"
)
LATEST_TRAINING_POINTER = (
    REPORTS_ROOT / "latest_model_training.txt"
)
CURRENT_MODEL_POINTER = (
    MODELS_ROOT / "current_model.txt"
)

RANDOM_STATE = 42
REQUESTED_SPLITS = 5
MODEL_VERSION = "char_tfidf_linear_svm_v1"
NEAR_DUPLICATE_THRESHOLD = 0.97

PAGE_MARKER_RE = re.compile(
    r"---\s*PAGE\s+\d+"
    r"(?:\s*\[[^\]]+\])?\s*---",
    re.IGNORECASE,
)
WHITESPACE_RE = re.compile(r"\s+")


def normalize_training_text(value: str) -> str:
    text = str(value or "").replace("\x00", " ")
    text = PAGE_MARKER_RE.sub(" ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def build_classification_text(value: str) -> str:
    # 기관 식별 정보는 첫 페이지에 집중되는 경우가 많습니다.
    # 첫 페이지를 세 번 반영하고 뒤쪽은 최대 네 페이지,
    # 각 800자까지만 반영해 긴 제품목록의 영향을 줄입니다.

    raw_text = str(value or "").replace("\x00", " ")

    page_parts = [
        WHITESPACE_RE.sub(" ", part).strip()
        for part in PAGE_MARKER_RE.split(raw_text)
    ]
    pages = [part for part in page_parts if part]

    if not pages:
        return normalize_training_text(raw_text)

    first_page = pages[0][:8000]
    appendix_parts = [
        page[:800]
        for page in pages[1:5]
    ]

    weighted_parts = [
        first_page,
        first_page,
        first_page,
        *appendix_parts,
    ]

    return WHITESPACE_RE.sub(
        " ",
        " ".join(weighted_parts),
    ).strip()


def load_latest_ocr_root() -> Path:
    if not LATEST_OCR_POINTER.exists():
        raise FileNotFoundError(
            f"2단계 OCR 포인터가 없습니다: "
            f"{LATEST_OCR_POINTER}"
        )

    root_text = LATEST_OCR_POINTER.read_text(
        encoding="utf-8-sig"
    ).strip()

    if not root_text:
        raise ValueError(
            f"2단계 OCR 포인터가 비어 있습니다: "
            f"{LATEST_OCR_POINTER}"
        )

    root = Path(root_text)
    manifest_path = root / "04_training_text_manifest.csv"

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"학습 텍스트 매니페스트가 없습니다: "
            f"{manifest_path}"
        )

    return root


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def load_training_frame(
    ocr_root: Path,
) -> pd.DataFrame:
    manifest_path = (
        ocr_root / "04_training_text_manifest.csv"
    )

    manifest = pd.read_csv(
        manifest_path,
        encoding="utf-8-sig",
    )

    required_columns = {
        "institution",
        "file_name",
        "pdf_path",
        "relative_path",
        "sha256",
        "source_audit_status",
        "final_status",
        "normalized_text_length",
    }

    missing_columns = sorted(
        required_columns.difference(manifest.columns)
    )

    if missing_columns:
        raise ValueError(
            "학습 매니페스트 필수 열이 없습니다: "
            + ", ".join(missing_columns)
        )

    manifest = manifest[
        manifest["final_status"].astype(str) == "READY"
    ].copy()

    rows: list[dict[str, Any]] = []
    load_errors: list[str] = []

    for row in manifest.itertuples(index=False):
        sha256 = str(row.sha256).strip()
        cache_path = (
            COMBINED_CACHE_ROOT / f"{sha256}.json"
        )

        try:
            payload = load_json(cache_path)
            text = build_classification_text(
                payload.get("combined_text") or ""
            )

            if len(text) < 80:
                raise ValueError(
                    f"학습 텍스트가 80자 미만입니다: "
                    f"{len(text)}자"
                )

            rows.append({
                "institution": str(
                    row.institution
                ).strip(),
                "file_name": str(row.file_name),
                "pdf_path": str(row.pdf_path),
                "relative_path": str(
                    row.relative_path
                ),
                "sha256": sha256,
                "source_audit_status": str(
                    row.source_audit_status
                ),
                "text_length": len(text),
                "text": text,
            })

        except Exception as exc:
            load_errors.append(
                f"{sha256} / {row.file_name}: {exc}"
            )

    if load_errors:
        preview = "\n".join(load_errors[:20])
        raise RuntimeError(
            "학습 텍스트 로드 오류가 발생했습니다.\n"
            f"{preview}"
        )

    frame = pd.DataFrame(rows)

    if frame.empty:
        raise RuntimeError(
            "학습 가능한 텍스트가 없습니다."
        )

    if frame["sha256"].duplicated().any():
        duplicates = frame[
            frame["sha256"].duplicated(
                keep=False
            )
        ]

        raise ValueError(
            "학습 데이터에 SHA256 중복이 있습니다: "
            f"{len(duplicates)}행"
        )

    class_counts = (
        frame["institution"]
        .value_counts()
        .sort_index()
    )

    if len(class_counts) < 2:
        raise ValueError(
            "기관 분류에는 2개 이상의 기관이 필요합니다."
        )

    if int(class_counts.min()) < 3:
        raise ValueError(
            "기관별 최소 문서 수가 3개 미만입니다."
        )

    return frame


def build_pipeline() -> Pipeline:
    return Pipeline([
        (
            "tfidf",
            TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(3, 5),
                min_df=2,
                max_df=0.995,
                sublinear_tf=True,
                lowercase=True,
                strip_accents=None,
                max_features=150_000,
                dtype=np.float32,
            ),
        ),
        (
            "classifier",
            LinearSVC(
                C=2.0,
                class_weight="balanced",
                max_iter=20_000,
                dual="auto",
                random_state=RANDOM_STATE,
            ),
        ),
    ])


def softmax_rows(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    shifted = values - np.max(
        values,
        axis=1,
        keepdims=True,
    )
    exponentials = np.exp(shifted)
    denominators = exponentials.sum(
        axis=1,
        keepdims=True,
    )
    denominators[denominators == 0] = 1.0
    return exponentials / denominators


def cross_validate(
    frame: pd.DataFrame,
    classes: np.ndarray,
    n_splits: int,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    texts = frame["text"].tolist()
    labels = frame["institution"].to_numpy(
        dtype=object
    )

    splitter = StratifiedKFold(
        n_splits=n_splits,
        shuffle=True,
        random_state=RANDOM_STATE,
    )

    predictions = np.empty(
        len(frame),
        dtype=object,
    )
    fold_numbers = np.zeros(
        len(frame),
        dtype=int,
    )
    score_matrix = np.full(
        (len(frame), len(classes)),
        -np.inf,
        dtype=float,
    )

    base_pipeline = build_pipeline()

    for fold_number, (
        train_index,
        test_index,
    ) in enumerate(
        splitter.split(texts, labels),
        start=1,
    ):
        print(
            f"[CV {fold_number}/{n_splits}] "
            f"train={len(train_index)}, "
            f"test={len(test_index)}"
        )

        model = clone(base_pipeline)
        train_texts = [
            texts[index]
            for index in train_index
        ]
        test_texts = [
            texts[index]
            for index in test_index
        ]

        model.fit(
            train_texts,
            labels[train_index],
        )

        fold_predictions = model.predict(
            test_texts
        )
        fold_scores = np.asarray(
            model.decision_function(test_texts)
        )

        if fold_scores.ndim == 1:
            fold_scores = fold_scores.reshape(
                -1,
                1,
            )

        fold_classes = np.asarray(
            model.named_steps[
                "classifier"
            ].classes_,
            dtype=object,
        )

        class_positions = {
            str(label): position
            for position, label in enumerate(classes)
        }

        for local_position, label in enumerate(
            fold_classes
        ):
            global_position = class_positions[
                str(label)
            ]

            score_matrix[
                test_index,
                global_position,
            ] = fold_scores[
                :,
                local_position,
            ]

        predictions[test_index] = (
            fold_predictions
        )
        fold_numbers[test_index] = fold_number

    if np.isneginf(score_matrix).any():
        raise RuntimeError(
            "교차검증 점수 행렬에 누락된 값이 있습니다."
        )

    return (
        predictions,
        score_matrix,
        fold_numbers,
    )


def build_metrics_frame(
    actual: np.ndarray,
    predicted: np.ndarray,
    classes: np.ndarray,
) -> pd.DataFrame:
    report = classification_report(
        actual,
        predicted,
        labels=classes,
        output_dict=True,
        zero_division=0,
    )

    rows = []

    for institution in classes:
        values = report[str(institution)]

        rows.append({
            "institution": str(institution),
            "precision": round(
                float(values["precision"]),
                6,
            ),
            "recall": round(
                float(values["recall"]),
                6,
            ),
            "f1_score": round(
                float(values["f1-score"]),
                6,
            ),
            "support": int(values["support"]),
        })

    return pd.DataFrame(rows)


def build_prediction_frame(
    frame: pd.DataFrame,
    actual: np.ndarray,
    predicted: np.ndarray,
    score_matrix: np.ndarray,
    fold_numbers: np.ndarray,
    classes: np.ndarray,
) -> pd.DataFrame:
    relative_confidence = softmax_rows(
        score_matrix
    )
    order = np.argsort(
        score_matrix,
        axis=1,
    )[:, ::-1]

    rows = []

    for index in range(len(frame)):
        first = int(order[index, 0])
        second = int(order[index, 1])
        third = int(order[index, 2])

        top_three = [
            str(classes[first]),
            str(classes[second]),
            str(classes[third]),
        ]

        rows.append({
            "fold": int(fold_numbers[index]),
            "institution_actual": str(actual[index]),
            "institution_predicted": str(
                predicted[index]
            ),
            "correct": bool(
                actual[index] == predicted[index]
            ),
            "top1_relative_confidence": round(
                float(
                    relative_confidence[
                        index,
                        first,
                    ]
                ),
                6,
            ),
            "decision_score_gap": round(
                float(
                    score_matrix[index, first]
                    - score_matrix[index, second]
                ),
                6,
            ),
            "top2_institution": str(
                classes[second]
            ),
            "top3_institution": str(
                classes[third]
            ),
            "top3_correct": bool(
                str(actual[index]) in top_three
            ),
            "file_name": frame.iloc[
                index
            ]["file_name"],
            "relative_path": frame.iloc[
                index
            ]["relative_path"],
            "pdf_path": frame.iloc[
                index
            ]["pdf_path"],
            "sha256": frame.iloc[
                index
            ]["sha256"],
            "source_audit_status": frame.iloc[
                index
            ]["source_audit_status"],
            "text_length": int(
                frame.iloc[index]["text_length"]
            ),
        })

    return pd.DataFrame(rows)


def save_confusion_csvs(
    actual: np.ndarray,
    predicted: np.ndarray,
    classes: np.ndarray,
    report_root: Path,
) -> tuple[np.ndarray, np.ndarray]:
    raw_matrix = confusion_matrix(
        actual,
        predicted,
        labels=classes,
    )
    normalized_matrix = confusion_matrix(
        actual,
        predicted,
        labels=classes,
        normalize="true",
    )

    raw_frame = pd.DataFrame(
        raw_matrix,
        index=classes,
        columns=classes,
    )
    normalized_frame = pd.DataFrame(
        normalized_matrix,
        index=classes,
        columns=classes,
    )

    raw_frame.index.name = "actual"
    normalized_frame.index.name = "actual"

    raw_frame.to_csv(
        report_root / "04_confusion_matrix.csv",
        encoding="utf-8-sig",
    )
    normalized_frame.to_csv(
        report_root
        / "05_confusion_matrix_normalized.csv",
        encoding="utf-8-sig",
    )

    return raw_matrix, normalized_matrix


def save_class_distribution_chart(
    frame: pd.DataFrame,
    report_root: Path,
) -> None:
    counts = (
        frame.groupby(
            [
                "institution",
                "source_audit_status",
            ]
        )
        .size()
        .unstack(fill_value=0)
    )

    total_order = (
        frame["institution"]
        .value_counts()
        .sort_values()
        .index
    )
    counts = counts.reindex(total_order)

    native_values = (
        counts["TEXT_DIRECT"]
        if "TEXT_DIRECT" in counts.columns
        else pd.Series(
            0,
            index=counts.index,
        )
    )
    ocr_values = (
        counts["OCR_REQUIRED"]
        if "OCR_REQUIRED" in counts.columns
        else pd.Series(
            0,
            index=counts.index,
        )
    )

    fig, ax = plt.subplots(figsize=(11, 8))
    ax.barh(
        counts.index,
        native_values,
        label="PDF native text",
    )
    ax.barh(
        counts.index,
        ocr_values,
        left=native_values,
        label="OCR text",
    )
    ax.set_title(
        "Training documents by institution"
    )
    ax.set_xlabel("Document count")
    ax.legend()
    fig.tight_layout()
    fig.savefig(
        report_root
        / "06_class_distribution.png",
        dpi=160,
    )
    plt.close(fig)


def save_confusion_chart(
    normalized_matrix: np.ndarray,
    classes: np.ndarray,
    report_root: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(14, 12))
    image = ax.imshow(
        normalized_matrix,
        aspect="auto",
        vmin=0,
        vmax=1,
    )
    ax.set_title(
        "5-fold cross-validation confusion matrix"
    )
    ax.set_xlabel("Predicted institution")
    ax.set_ylabel("Actual institution")
    ax.set_xticks(
        np.arange(len(classes))
    )
    ax.set_yticks(
        np.arange(len(classes))
    )
    ax.set_xticklabels(
        classes,
        rotation=70,
        ha="right",
    )
    ax.set_yticklabels(classes)

    for row in range(len(classes)):
        for column in range(len(classes)):
            value = float(
                normalized_matrix[
                    row,
                    column,
                ]
            )

            if value >= 0.01:
                ax.text(
                    column,
                    row,
                    f"{value:.2f}",
                    ha="center",
                    va="center",
                    fontsize=7,
                )

    fig.colorbar(
        image,
        ax=ax,
        label="Recall-normalized ratio",
    )
    fig.tight_layout()
    fig.savefig(
        report_root
        / "07_confusion_matrix.png",
        dpi=170,
    )
    plt.close(fig)


def save_f1_chart(
    metrics_frame: pd.DataFrame,
    report_root: Path,
) -> None:
    chart = metrics_frame.sort_values(
        "f1_score",
        ascending=True,
    )

    fig, ax = plt.subplots(figsize=(11, 8))
    bars = ax.barh(
        chart["institution"],
        chart["f1_score"],
    )
    ax.set_xlim(0, 1.05)
    ax.set_title(
        "Cross-validation F1 score by institution"
    )
    ax.set_xlabel("F1 score")

    for bar, value in zip(
        bars,
        chart["f1_score"],
    ):
        ax.text(
            min(float(value) + 0.01, 1.01),
            bar.get_y()
            + bar.get_height() / 2,
            f"{float(value):.3f}",
            va="center",
            fontsize=8,
        )

    fig.tight_layout()
    fig.savefig(
        report_root
        / "08_class_f1_scores.png",
        dpi=160,
    )
    plt.close(fig)


def save_confidence_chart(
    prediction_frame: pd.DataFrame,
    report_root: Path,
) -> None:
    correct_values = prediction_frame.loc[
        prediction_frame["correct"],
        "top1_relative_confidence",
    ]
    incorrect_values = prediction_frame.loc[
        ~prediction_frame["correct"],
        "top1_relative_confidence",
    ]

    fig, ax = plt.subplots(figsize=(10, 6))
    bins = np.linspace(0, 1, 21)

    ax.hist(
        correct_values,
        bins=bins,
        alpha=0.65,
        label="Correct",
    )

    if len(incorrect_values):
        ax.hist(
            incorrect_values,
            bins=bins,
            alpha=0.65,
            label="Incorrect",
        )

    ax.set_title(
        "Relative confidence distribution"
    )
    ax.set_xlabel(
        "Relative confidence "
        "(not calibrated probability)"
    )
    ax.set_ylabel("Document count")
    ax.legend()
    fig.tight_layout()
    fig.savefig(
        report_root
        / "09_confidence_distribution.png",
        dpi=160,
    )
    plt.close(fig)


def save_embedding_chart(
    tfidf_matrix: Any,
    frame: pd.DataFrame,
    report_root: Path,
) -> dict[str, float]:
    svd = TruncatedSVD(
        n_components=2,
        random_state=RANDOM_STATE,
    )
    coordinates = svd.fit_transform(
        tfidf_matrix
    )

    fig, ax = plt.subplots(figsize=(12, 9))

    institutions = sorted(
        frame["institution"].unique()
    )
    markers = [
        "o",
        "s",
        "^",
        "v",
        "D",
        "P",
        "X",
        "<",
        ">",
    ]

    for institution_index, institution in enumerate(
        institutions
    ):
        mask = (
            frame["institution"].to_numpy()
            == institution
        )

        ax.scatter(
            coordinates[mask, 0],
            coordinates[mask, 1],
            label=institution,
            marker=markers[
                institution_index
                % len(markers)
            ],
            s=34,
            alpha=0.72,
        )

    ax.set_title(
        "Certificate text embedding "
        "(TF-IDF + TruncatedSVD)"
    )
    ax.set_xlabel("SVD component 1")
    ax.set_ylabel("SVD component 2")
    ax.legend(
        bbox_to_anchor=(1.02, 1),
        loc="upper left",
        fontsize=8,
    )
    fig.tight_layout()
    fig.savefig(
        report_root
        / "10_document_embedding.png",
        dpi=170,
    )
    plt.close(fig)

    return {
        "component_1_explained_variance": round(
            float(
                svd.explained_variance_ratio_[0]
            ),
            6,
        ),
        "component_2_explained_variance": round(
            float(
                svd.explained_variance_ratio_[1]
            ),
            6,
        ),
        "total_explained_variance": round(
            float(
                svd.explained_variance_ratio_.sum()
            ),
            6,
        ),
    }


def find_near_duplicate_candidates(
    tfidf_matrix: Any,
    frame: pd.DataFrame,
) -> pd.DataFrame:
    rows = []

    for institution, group in frame.groupby(
        "institution",
        sort=True,
    ):
        indices = group.index.to_numpy()

        if len(indices) < 2:
            continue

        class_matrix = tfidf_matrix[indices]
        similarities = cosine_similarity(
            class_matrix
        )

        for left in range(len(indices)):
            for right in range(
                left + 1,
                len(indices),
            ):
                similarity = float(
                    similarities[left, right]
                )

                if (
                    similarity
                    < NEAR_DUPLICATE_THRESHOLD
                ):
                    continue

                left_row = frame.loc[
                    indices[left]
                ]
                right_row = frame.loc[
                    indices[right]
                ]

                rows.append({
                    "institution": institution,
                    "cosine_similarity": round(
                        similarity,
                        6,
                    ),
                    "file_name_a": (
                        left_row["file_name"]
                    ),
                    "sha256_a": left_row["sha256"],
                    "file_name_b": (
                        right_row["file_name"]
                    ),
                    "sha256_b": right_row["sha256"],
                })

    columns = [
        "institution",
        "cosine_similarity",
        "file_name_a",
        "sha256_a",
        "file_name_b",
        "sha256_b",
    ]

    return pd.DataFrame(
        rows,
        columns=columns,
    ).sort_values(
        [
            "institution",
            "cosine_similarity",
        ],
        ascending=[True, False],
        ignore_index=True,
    )


def build_top_confusions(
    raw_matrix: np.ndarray,
    classes: np.ndarray,
) -> pd.DataFrame:
    rows = []

    for actual_index, actual in enumerate(classes):
        for predicted_index, predicted in enumerate(
            classes
        ):
            if actual_index == predicted_index:
                continue

            count = int(
                raw_matrix[
                    actual_index,
                    predicted_index,
                ]
            )

            if count <= 0:
                continue

            rows.append({
                "actual_institution": str(actual),
                "predicted_institution": str(
                    predicted
                ),
                "count": count,
            })

    columns = [
        "actual_institution",
        "predicted_institution",
        "count",
    ]

    return pd.DataFrame(
        rows,
        columns=columns,
    ).sort_values(
        "count",
        ascending=False,
        ignore_index=True,
    )


def save_html_report(
    summary: dict[str, Any],
    metrics_frame: pd.DataFrame,
    top_confusions: pd.DataFrame,
    report_root: Path,
) -> None:
    metric_rows = []

    for row in metrics_frame.itertuples(
        index=False
    ):
        metric_rows.append(
            "<tr>"
            f"<td>{html.escape(row.institution)}</td>"
            f"<td>{row.precision:.3f}</td>"
            f"<td>{row.recall:.3f}</td>"
            f"<td>{row.f1_score:.3f}</td>"
            f"<td>{row.support}</td>"
            "</tr>"
        )

    confusion_rows = []

    for row in top_confusions.head(20).itertuples(
        index=False
    ):
        confusion_rows.append(
            "<tr>"
            f"<td>{html.escape(row.actual_institution)}</td>"
            f"<td>{html.escape(row.predicted_institution)}</td>"
            f"<td>{row.count}</td>"
            "</tr>"
        )

    if not confusion_rows:
        confusion_rows.append(
            "<tr><td colspan='3'>"
            "교차검증 오분류 없음"
            "</td></tr>"
        )

    report_html = f"""
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>할랄 인증기관 ML 학습 결과</title>
<style>
body {{
    font-family: Arial, "Malgun Gothic", sans-serif;
    margin: 28px;
    color: #1f2937;
    background: #f8fafc;
}}
h1, h2 {{
    margin-top: 0;
}}
.grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
    margin: 18px 0 26px;
}}
.card {{
    background: white;
    border: 1px solid #dbe3ec;
    border-radius: 10px;
    padding: 16px;
}}
.value {{
    font-size: 26px;
    font-weight: 700;
    margin-top: 6px;
}}
.section {{
    background: white;
    border: 1px solid #dbe3ec;
    border-radius: 10px;
    padding: 18px;
    margin: 16px 0;
}}
table {{
    border-collapse: collapse;
    width: 100%;
}}
th, td {{
    border-bottom: 1px solid #e5e7eb;
    padding: 8px;
    text-align: left;
}}
img {{
    width: 100%;
    max-width: 1200px;
    height: auto;
    border: 1px solid #e5e7eb;
}}
.note {{
    color: #64748b;
    font-size: 14px;
}}
</style>
</head>
<body>
<h1>할랄 인증기관 ML 학습 결과</h1>
<p class="note">
평가 방식: 층화 {summary["cv_splits"]}-Fold 교차검증.
동일 제조사 갱신본 등 유사 문서가 서로 다른 Fold에 포함될 수 있으므로
현재 결과는 1차 기준 성능입니다.
</p>

<div class="grid">
  <div class="card">
    <div>학습 문서</div>
    <div class="value">{summary["total_documents"]}</div>
  </div>
  <div class="card">
    <div>기관</div>
    <div class="value">{summary["institution_count"]}</div>
  </div>
  <div class="card">
    <div>정확도</div>
    <div class="value">{summary["accuracy"]:.3f}</div>
  </div>
  <div class="card">
    <div>Macro F1</div>
    <div class="value">{summary["macro_f1"]:.3f}</div>
  </div>
  <div class="card">
    <div>Top-3 정확도</div>
    <div class="value">{summary["top3_accuracy"]:.3f}</div>
  </div>
  <div class="card">
    <div>오분류</div>
    <div class="value">{summary["misclassified_count"]}</div>
  </div>
</div>

<div class="section">
<h2>기관별 F1</h2>
<img src="08_class_f1_scores.png" alt="기관별 F1 점수">
</div>

<div class="section">
<h2>혼동행렬</h2>
<img src="07_confusion_matrix.png" alt="교차검증 혼동행렬">
</div>

<div class="section">
<h2>문서 군집</h2>
<img src="10_document_embedding.png" alt="인증서 텍스트 군집도">
</div>

<div class="section">
<h2>상대 신뢰도 분포</h2>
<img src="09_confidence_distribution.png" alt="상대 신뢰도 분포">
<p class="note">
상대 신뢰도는 Linear SVM 결정점수를 비교하기 위해 변환한 값이며
보정된 확률이 아닙니다.
</p>
</div>

<div class="section">
<h2>기관별 성능</h2>
<table>
<thead>
<tr>
<th>기관</th>
<th>Precision</th>
<th>Recall</th>
<th>F1</th>
<th>문서 수</th>
</tr>
</thead>
<tbody>
{''.join(metric_rows)}
</tbody>
</table>
</div>

<div class="section">
<h2>주요 오분류 조합</h2>
<table>
<thead>
<tr>
<th>실제 기관</th>
<th>예측 기관</th>
<th>건수</th>
</tr>
</thead>
<tbody>
{''.join(confusion_rows)}
</tbody>
</table>
</div>

<div class="section">
<h2>생성 파일</h2>
<ul>
<li>02_cross_validation_predictions.csv</li>
<li>03_class_metrics.csv</li>
<li>04_confusion_matrix.csv</li>
<li>07_confusion_matrix.png</li>
<li>08_class_f1_scores.png</li>
<li>10_document_embedding.png</li>
<li>11_misclassified_documents.csv</li>
<li>12_model_summary.json</li>
<li>14_near_duplicate_candidates.csv</li>
</ul>
</div>
</body>
</html>
"""

    (
        report_root / "13_model_report.html"
    ).write_text(
        report_html,
        encoding="utf-8",
    )


def main() -> int:
    started = time.perf_counter()
    run_id = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    report_root = (
        REPORTS_ROOT
        / f"model_training_{run_id}"
    )
    model_root = (
        MODELS_ROOT
        / f"certificate_institution_{run_id}"
    )

    report_root.mkdir(
        parents=True,
        exist_ok=True,
    )
    model_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    ocr_root = load_latest_ocr_root()
    frame = load_training_frame(ocr_root)

    classes = np.array(
        sorted(
            frame["institution"].unique()
        ),
        dtype=object,
    )
    class_counts = (
        frame["institution"]
        .value_counts()
        .sort_index()
    )

    n_splits = min(
        REQUESTED_SPLITS,
        int(class_counts.min()),
    )

    if n_splits < 3:
        raise ValueError(
            "교차검증 Fold 수가 3 미만입니다."
        )

    print("")
    print("=" * 72)
    print("할랄 인증기관 ML 실제 학습")
    print("=" * 72)
    print(f"학습 문서: {len(frame)}")
    print(f"기관 수  : {len(classes)}")
    print(f"교차검증: {n_splits}-Fold")
    print(f"모델     : {MODEL_VERSION}")
    print("")

    actual = frame["institution"].to_numpy(
        dtype=object
    )

    (
        predicted,
        score_matrix,
        fold_numbers,
    ) = cross_validate(
        frame=frame,
        classes=classes,
        n_splits=n_splits,
    )

    prediction_frame = build_prediction_frame(
        frame=frame,
        actual=actual,
        predicted=predicted,
        score_matrix=score_matrix,
        fold_numbers=fold_numbers,
        classes=classes,
    )

    metrics_frame = build_metrics_frame(
        actual=actual,
        predicted=predicted,
        classes=classes,
    )

    (
        raw_matrix,
        normalized_matrix,
    ) = save_confusion_csvs(
        actual=actual,
        predicted=predicted,
        classes=classes,
        report_root=report_root,
    )

    accuracy = float(
        accuracy_score(actual, predicted)
    )
    balanced_accuracy = float(
        balanced_accuracy_score(
            actual,
            predicted,
        )
    )
    macro_f1 = float(
        f1_score(
            actual,
            predicted,
            average="macro",
        )
    )
    weighted_f1 = float(
        f1_score(
            actual,
            predicted,
            average="weighted",
        )
    )
    top3_accuracy = float(
        prediction_frame[
            "top3_correct"
        ].mean()
    )
    misclassified_count = int(
        (~prediction_frame["correct"]).sum()
    )

    training_manifest_output = frame[
        [
            "institution",
            "file_name",
            "pdf_path",
            "relative_path",
            "sha256",
            "source_audit_status",
            "text_length",
        ]
    ].copy()

    training_manifest_output.to_csv(
        report_root
        / "01_training_manifest.csv",
        index=False,
        encoding="utf-8-sig",
    )

    prediction_frame.to_csv(
        report_root
        / "02_cross_validation_predictions.csv",
        index=False,
        encoding="utf-8-sig",
    )

    metrics_frame.to_csv(
        report_root
        / "03_class_metrics.csv",
        index=False,
        encoding="utf-8-sig",
    )

    prediction_frame[
        ~prediction_frame["correct"]
    ].sort_values(
        [
            "institution_actual",
            "top1_relative_confidence",
        ],
        ascending=[True, False],
    ).to_csv(
        report_root
        / "11_misclassified_documents.csv",
        index=False,
        encoding="utf-8-sig",
    )

    top_confusions = build_top_confusions(
        raw_matrix=raw_matrix,
        classes=classes,
    )
    top_confusions.to_csv(
        report_root
        / "15_top_confusions.csv",
        index=False,
        encoding="utf-8-sig",
    )

    save_class_distribution_chart(
        frame=frame,
        report_root=report_root,
    )
    save_confusion_chart(
        normalized_matrix=normalized_matrix,
        classes=classes,
        report_root=report_root,
    )
    save_f1_chart(
        metrics_frame=metrics_frame,
        report_root=report_root,
    )
    save_confidence_chart(
        prediction_frame=prediction_frame,
        report_root=report_root,
    )

    print("")
    print("최종 모델 전체 학습 중...")

    final_pipeline = build_pipeline()
    final_pipeline.fit(
        frame["text"].tolist(),
        actual,
    )

    tfidf_matrix = final_pipeline.named_steps[
        "tfidf"
    ].transform(
        frame["text"].tolist()
    )

    embedding_summary = save_embedding_chart(
        tfidf_matrix=tfidf_matrix,
        frame=frame,
        report_root=report_root,
    )

    near_duplicates = (
        find_near_duplicate_candidates(
            tfidf_matrix=tfidf_matrix,
            frame=frame,
        )
    )
    near_duplicates.to_csv(
        report_root
        / "14_near_duplicate_candidates.csv",
        index=False,
        encoding="utf-8-sig",
    )

    vectorizer = final_pipeline.named_steps[
        "tfidf"
    ]
    classifier = final_pipeline.named_steps[
        "classifier"
    ]

    summary = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "model_version": MODEL_VERSION,
        "evaluation_type": (
            "StratifiedKFold baseline; "
            "not group-aware"
        ),
        "ocr_report_root": str(ocr_root),
        "report_root": str(report_root),
        "model_root": str(model_root),
        "total_documents": int(len(frame)),
        "institution_count": int(len(classes)),
        "classes": [
            str(value)
            for value in classes
        ],
        "class_counts": {
            str(key): int(value)
            for key, value in (
                class_counts.to_dict().items()
            )
        },
        "cv_splits": int(n_splits),
        "accuracy": round(accuracy, 6),
        "balanced_accuracy": round(
            balanced_accuracy,
            6,
        ),
        "macro_f1": round(macro_f1, 6),
        "weighted_f1": round(
            weighted_f1,
            6,
        ),
        "top3_accuracy": round(
            top3_accuracy,
            6,
        ),
        "misclassified_count": (
            misclassified_count
        ),
        "near_duplicate_pair_count": int(
            len(near_duplicates)
        ),
        "near_duplicate_threshold": (
            NEAR_DUPLICATE_THRESHOLD
        ),
        "feature_count": int(
            len(vectorizer.vocabulary_)
        ),
        "classifier_iterations": [
            int(value)
            for value in np.atleast_1d(
                classifier.n_iter_
            )
        ],
        "embedding": embedding_summary,
        "packages": {
            "python": sys.version,
            "scikit_learn": (
                sklearn.__version__
            ),
            "joblib": joblib.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "matplotlib": (
                matplotlib.__version__
            ),
        },
        "model_parameters": {
            "analyzer": "char_wb",
            "ngram_range": [3, 5],
            "min_df": 2,
            "max_df": 0.995,
            "max_features": 150000,
            "linear_svc_c": 2.0,
            "class_weight": "balanced",
            "random_state": RANDOM_STATE,
        },
        "confidence_note": (
            "relative_confidence는 "
            "Linear SVM 결정점수를 "
            "상대 비교용으로 변환한 값이며 "
            "보정된 확률이 아닙니다."
        ),
        "validation_warning": (
            "동일 제조사 갱신 인증서 등 "
            "유사 문서가 서로 다른 Fold에 "
            "포함될 수 있어 현재 교차검증 성능이 "
            "실운영 성능보다 높을 수 있습니다. "
            "14_near_duplicate_candidates.csv를 "
            "검토한 뒤 그룹 기반 재검증이 필요합니다."
        ),
        "elapsed_seconds": round(
            time.perf_counter() - started,
            2,
        ),
    }

    model_bundle = {
        "pipeline": final_pipeline,
        "metadata": summary,
    }

    joblib.dump(
        model_bundle,
        model_root
        / "certificate_institution_model.joblib",
        compress=3,
    )

    (
        model_root / "model_metadata.json"
    ).write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    (
        report_root / "12_model_summary.json"
    ).write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    save_html_report(
        summary=summary,
        metrics_frame=metrics_frame,
        top_confusions=top_confusions,
        report_root=report_root,
    )

    CURRENT_MODEL_POINTER.write_text(
        str(model_root),
        encoding="utf-8",
    )
    LATEST_TRAINING_POINTER.write_text(
        str(report_root),
        encoding="utf-8",
    )

    smoke_prediction = (
        final_pipeline.predict(
            [frame.iloc[0]["text"]]
        )[0]
    )

    smoke_payload = {
        "file_name": frame.iloc[0][
            "file_name"
        ],
        "actual_institution": (
            frame.iloc[0]["institution"]
        ),
        "predicted_institution": str(
            smoke_prediction
        ),
        "passed": bool(
            smoke_prediction
            == frame.iloc[0]["institution"]
        ),
    }

    (
        report_root / "16_smoke_test.json"
    ).write_text(
        json.dumps(
            smoke_payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("")
    print("=" * 72)
    print("3단계 실제 학습 완료")
    print("=" * 72)
    print(f"학습 문서       : {len(frame)}")
    print(f"기관 수         : {len(classes)}")
    print(f"정확도          : {accuracy:.4f}")
    print(f"Balanced 정확도 : {balanced_accuracy:.4f}")
    print(f"Macro F1        : {macro_f1:.4f}")
    print(f"Weighted F1     : {weighted_f1:.4f}")
    print(f"Top-3 정확도    : {top3_accuracy:.4f}")
    print(f"오분류 문서     : {misclassified_count}")
    print(
        "유사 문서 후보  : "
        f"{len(near_duplicates)}쌍"
    )
    print(f"모델 저장       : {model_root}")
    print(f"보고서 저장     : {report_root}")
    print("")
    print(metrics_frame.to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())