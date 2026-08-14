from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


BACKEND_DIR = Path(__file__).resolve().parents[2]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


from app.ml.certificate_classifier.config import (  # noqa: E402
    MIN_NATIVE_PAGE_CHARS,
    MIN_NATIVE_TEXT_CHARS,
    get_current_dataset_root,
    get_runtime_paths,
)
from app.ml.certificate_classifier.text_extractor import (  # noqa: E402
    inspect_pdf_native_text,
)


AUDIT_COLUMNS = [
    "institution",
    "file_name",
    "pdf_path",
    "relative_path",
    "sha256",
    "file_size_bytes",
    "page_count",
    "text_page_count",
    "usable_text_page_count",
    "native_text_length",
    "normalized_text_length",
    "status",
    "cache_hit",
    "error",
    "text_preview",
]


def build_institution_summary(
    audit_frame: pd.DataFrame,
) -> pd.DataFrame:
    summary_rows: list[dict[str, object]] = []

    institutions = sorted(
        audit_frame["institution"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    for institution in institutions:
        institution_frame = audit_frame[
            audit_frame["institution"] == institution
        ]

        summary_rows.append({
            "institution": institution,
            "total_pdf": int(len(institution_frame)),
            "text_direct": int(
                (
                    institution_frame["status"]
                    == "TEXT_DIRECT"
                ).sum()
            ),
            "ocr_required": int(
                (
                    institution_frame["status"]
                    == "OCR_REQUIRED"
                ).sum()
            ),
            "extraction_error": int(
                (
                    institution_frame["status"]
                    == "EXTRACTION_ERROR"
                ).sum()
            ),
            "mean_native_text_length": round(
                float(
                    institution_frame[
                        "normalized_text_length"
                    ].mean()
                ),
                1,
            ),
            "min_native_text_length": int(
                institution_frame[
                    "normalized_text_length"
                ].min()
            ),
            "max_native_text_length": int(
                institution_frame[
                    "normalized_text_length"
                ].max()
            ),
        })

    return pd.DataFrame(summary_rows)


def main() -> int:
    runtime_paths = get_runtime_paths()
    dataset_root = get_current_dataset_root()
    raw_root = dataset_root / "raw"

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_root = (
        runtime_paths["reports_root"]
        / f"dataset_audit_{run_id}"
    )
    report_root.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(
        raw_root.glob("*/*.pdf"),
        key=lambda path: (
            path.parent.name.upper(),
            path.name.upper(),
        ),
    )

    if not pdf_files:
        raise RuntimeError(
            f"학습 PDF를 찾지 못했습니다: {raw_root}"
        )

    print("")
    print("=" * 70)
    print("할랄 인증기관 ML 데이터셋 내장 텍스트 점검")
    print("=" * 70)
    print(f"데이터셋: {dataset_root}")
    print(f"PDF 수  : {len(pdf_files)}")
    print(
        f"TEXT_DIRECT 기준: "
        f"{MIN_NATIVE_TEXT_CHARS}자 이상"
    )
    print("")

    audit_rows: list[dict[str, object]] = []

    for index, pdf_path in enumerate(
        pdf_files,
        start=1,
    ):
        institution = pdf_path.parent.name

        print(
            f"[{index:03d}/{len(pdf_files):03d}] "
            f"{institution} / {pdf_path.name}"
        )

        result = inspect_pdf_native_text(
            pdf_path=pdf_path,
            institution=institution,
            dataset_root=dataset_root,
        )

        audit_rows.append({
            column: result.get(column)
            for column in AUDIT_COLUMNS
        })

    audit_frame = pd.DataFrame(
        audit_rows,
        columns=AUDIT_COLUMNS,
    )

    institution_summary = build_institution_summary(
        audit_frame
    )

    ocr_required_frame = audit_frame[
        audit_frame["status"] == "OCR_REQUIRED"
    ].copy()

    error_frame = audit_frame[
        audit_frame["status"] == "EXTRACTION_ERROR"
    ].copy()

    direct_frame = audit_frame[
        audit_frame["status"] == "TEXT_DIRECT"
    ].copy()

    audit_frame.to_csv(
        report_root / "01_document_audit.csv",
        index=False,
        encoding="utf-8-sig",
    )

    institution_summary.to_csv(
        report_root / "02_institution_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    ocr_required_frame.to_csv(
        report_root / "03_ocr_required.csv",
        index=False,
        encoding="utf-8-sig",
    )

    error_frame.to_csv(
        report_root / "04_extraction_errors.csv",
        index=False,
        encoding="utf-8-sig",
    )

    direct_frame.to_csv(
        report_root / "05_text_direct.csv",
        index=False,
        encoding="utf-8-sig",
    )

    status_counts = {
        status: int(count)
        for status, count in (
            audit_frame["status"]
            .value_counts()
            .to_dict()
            .items()
        )
    }

    summary_payload = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "dataset_root": str(dataset_root),
        "raw_root": str(raw_root),
        "report_root": str(report_root),
        "total_pdf": int(len(audit_frame)),
        "institution_count": int(
            audit_frame["institution"].nunique()
        ),
        "status_counts": status_counts,
        "cache_hit_count": int(
            audit_frame["cache_hit"]
            .fillna(False)
            .astype(bool)
            .sum()
        ),
        "thresholds": {
            "min_native_text_chars": (
                MIN_NATIVE_TEXT_CHARS
            ),
            "min_native_page_chars": (
                MIN_NATIVE_PAGE_CHARS
            ),
        },
    }

    (
        report_root / "06_audit_summary.json"
    ).write_text(
        json.dumps(
            summary_payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    latest_pointer = (
        runtime_paths["reports_root"]
        / "latest_audit.txt"
    )

    latest_pointer.write_text(
        str(report_root),
        encoding="utf-8",
    )

    print("")
    print("=" * 70)
    print("점검 완료")
    print("=" * 70)
    print(f"전체 PDF        : {len(audit_frame)}")
    print(
        "TEXT_DIRECT     : "
        f"{status_counts.get('TEXT_DIRECT', 0)}"
    )
    print(
        "OCR_REQUIRED    : "
        f"{status_counts.get('OCR_REQUIRED', 0)}"
    )
    print(
        "EXTRACTION_ERROR: "
        f"{status_counts.get('EXTRACTION_ERROR', 0)}"
    )
    print(f"결과 폴더       : {report_root}")
    print("")
    print(institution_summary.to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
