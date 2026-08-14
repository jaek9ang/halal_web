from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np


RUNTIME_ROOT = Path(
    r"D:\halal_web_runtime\certificate_classifier"
)
CURRENT_MODEL_POINTER = (
    RUNTIME_ROOT / "models" / "current_model.txt"
)


def _softmax(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    shifted = values - np.max(values)
    exponentials = np.exp(shifted)
    denominator = float(exponentials.sum())

    if denominator <= 0:
        return np.zeros_like(exponentials)

    return exponentials / denominator


def get_current_model_root() -> Path:
    if not CURRENT_MODEL_POINTER.exists():
        raise FileNotFoundError(
            "현재 모델 포인터가 없습니다: "
            f"{CURRENT_MODEL_POINTER}"
        )

    model_root_text = CURRENT_MODEL_POINTER.read_text(
        encoding="utf-8-sig"
    ).strip()

    if not model_root_text:
        raise ValueError(
            "현재 모델 포인터가 비어 있습니다: "
            f"{CURRENT_MODEL_POINTER}"
        )

    model_root = Path(model_root_text)

    if not model_root.exists():
        raise FileNotFoundError(
            f"현재 모델 폴더가 없습니다: {model_root}"
        )

    return model_root


@lru_cache(maxsize=4)
def _load_bundle(model_path_text: str) -> dict[str, Any]:
    bundle = joblib.load(model_path_text)

    if not isinstance(bundle, dict):
        raise TypeError("모델 번들 형식이 올바르지 않습니다.")

    if "pipeline" not in bundle:
        raise KeyError("모델 번들에 pipeline이 없습니다.")

    return bundle


def load_current_model() -> dict[str, Any]:
    model_root = get_current_model_root()
    model_path = model_root / "certificate_institution_model.joblib"

    if not model_path.exists():
        raise FileNotFoundError(
            f"모델 파일이 없습니다: {model_path}"
        )

    return _load_bundle(str(model_path))


def predict_institution(
    text: str,
    top_k: int = 3,
) -> dict[str, Any]:
    normalized_text = " ".join(str(text or "").split())

    if len(normalized_text) < 20:
        raise ValueError(
            "분류할 텍스트가 너무 짧습니다. "
            "20자 이상이 필요합니다."
        )

    bundle = load_current_model()
    pipeline = bundle["pipeline"]
    metadata = dict(bundle.get("metadata") or {})

    predicted = str(
        pipeline.predict([normalized_text])[0]
    )

    raw_scores = np.asarray(
        pipeline.decision_function([normalized_text])
    )

    if raw_scores.ndim == 1:
        raw_scores = raw_scores.reshape(1, -1)

    classes = np.asarray(
        pipeline.named_steps["classifier"].classes_,
        dtype=object,
    )

    scores = raw_scores[0]
    relative_confidence = _softmax(scores)

    order = np.argsort(scores)[::-1]
    top_k = max(1, min(int(top_k), len(order)))

    candidates = []

    for class_index in order[:top_k]:
        candidates.append({
            "institution": str(classes[class_index]),
            "decision_score": round(
                float(scores[class_index]),
                6,
            ),
            "relative_confidence": round(
                float(relative_confidence[class_index]),
                6,
            ),
        })

    score_gap = 0.0

    if len(order) >= 2:
        score_gap = float(
            scores[order[0]] - scores[order[1]]
        )

    return {
        "predicted_institution": predicted,
        "relative_confidence": (
            candidates[0]["relative_confidence"]
        ),
        "decision_score_gap": round(score_gap, 6),
        "candidates": candidates,
        "model_run_id": metadata.get("run_id"),
        "model_version": metadata.get("model_version"),
        "confidence_note": (
            "relative_confidence는 Linear SVM 점수를 "
            "상대 비교용으로 변환한 값이며 확률은 아닙니다."
        ),
    }


def get_current_model_metadata() -> dict[str, Any]:
    model_root = get_current_model_root()
    metadata_path = model_root / "model_metadata.json"

    if not metadata_path.exists():
        return {}

    return json.loads(
        metadata_path.read_text(encoding="utf-8-sig")
    )