from __future__ import annotations

import os
from pathlib import Path
from typing import Final


DEFAULT_RUNTIME_ROOT: Final[Path] = Path(
    r"D:\halal_web_runtime\certificate_classifier"
)

RUNTIME_ENV_NAME: Final[str] = "HALAL_CERT_CLASSIFIER_RUNTIME"

MIN_NATIVE_TEXT_CHARS: Final[int] = 80
MIN_NATIVE_PAGE_CHARS: Final[int] = 20

TEXT_CACHE_VERSION: Final[int] = 1


def get_runtime_root() -> Path:
    configured = os.getenv(RUNTIME_ENV_NAME, "").strip()

    if configured:
        return Path(configured)

    return DEFAULT_RUNTIME_ROOT


def get_runtime_paths() -> dict[str, Path]:
    runtime_root = get_runtime_root()

    paths = {
        "runtime_root": runtime_root,
        "data_root": runtime_root / "data",
        "dataset_pointer": runtime_root / "data" / "current_dataset.txt",
        "text_cache_root": runtime_root / "text_cache",
        "native_cache_root": runtime_root / "text_cache" / "native",
        "reports_root": runtime_root / "reports",
        "models_root": runtime_root / "models",
        "logs_root": runtime_root / "logs",
    }

    for key, path in paths.items():
        if key == "dataset_pointer":
            continue

        path.mkdir(parents=True, exist_ok=True)

    return paths


def get_current_dataset_root() -> Path:
    paths = get_runtime_paths()
    pointer_path = paths["dataset_pointer"]

    if not pointer_path.exists():
        raise FileNotFoundError(
            f"현재 데이터셋 포인터가 없습니다: {pointer_path}"
        )

    dataset_text = pointer_path.read_text(
        encoding="utf-8-sig"
    ).strip()

    if not dataset_text:
        raise ValueError(
            f"현재 데이터셋 포인터가 비어 있습니다: {pointer_path}"
        )

    dataset_root = Path(dataset_text)

    if not dataset_root.exists():
        raise FileNotFoundError(
            f"현재 데이터셋 폴더가 없습니다: {dataset_root}"
        )

    raw_root = dataset_root / "raw"

    if not raw_root.exists():
        raise FileNotFoundError(
            f"현재 데이터셋의 raw 폴더가 없습니다: {raw_root}"
        )

    return dataset_root
