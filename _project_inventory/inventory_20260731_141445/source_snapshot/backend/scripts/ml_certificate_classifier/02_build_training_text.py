from __future__ import annotations

import html
import importlib.metadata
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

import cv2
import fitz
import matplotlib
import numpy as np
import pandas as pd
from rapidocr import RapidOCR

matplotlib.use("Agg")
import matplotlib.pyplot as plt


RUNTIME_ROOT = Path(r"D:\halal_web_runtime\certificate_classifier")
DATASET_POINTER = RUNTIME_ROOT / "data" / "current_dataset.txt"
REPORTS_ROOT = RUNTIME_ROOT / "reports"
NATIVE_CACHE_ROOT = RUNTIME_ROOT / "text_cache" / "native"
COMBINED_CACHE_ROOT = RUNTIME_ROOT / "text_cache" / "combined"
MIN_PAGE_TEXT_CHARS = 20
MIN_DOCUMENT_TEXT_CHARS = 80
CACHE_VERSION = 1
ZOOM = 2.0

WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    return WHITESPACE_RE.sub(" ", str(value or "")).strip()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def get_dataset_root() -> Path:
    if not DATASET_POINTER.exists():
        raise FileNotFoundError(f"데이터셋 포인터가 없습니다: {DATASET_POINTER}")

    dataset_root = Path(
        DATASET_POINTER.read_text(encoding="utf-8-sig").strip()
    )

    if not (dataset_root / "raw").exists():
        raise FileNotFoundError(f"데이터셋 raw 폴더가 없습니다: {dataset_root / 'raw'}")

    return dataset_root


def get_latest_audit_root() -> Path:
    pointer = REPORTS_ROOT / "latest_audit.txt"

    if not pointer.exists():
        raise FileNotFoundError(f"1단계 점검 포인터가 없습니다: {pointer}")

    audit_root = Path(pointer.read_text(encoding="utf-8-sig").strip())

    if not (audit_root / "01_document_audit.csv").exists():
        raise FileNotFoundError(
            f"1단계 점검 CSV가 없습니다: {audit_root / '01_document_audit.csv'}"
        )

    return audit_root


def page_to_bgr(page: fitz.Page) -> np.ndarray:
    pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), alpha=False)
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height,
        pix.width,
        pix.n,
    )

    if pix.n == 1:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if pix.n == 4:
        return cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
    return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)


def rapidocr_page(engine: RapidOCR, page: fitz.Page) -> dict[str, Any]:
    result = engine(page_to_bgr(page))

    if result is None:
        return {"text": "", "line_count": 0, "confidence": 0.0}

    texts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)

    if texts is None:
        texts = []
    if scores is None:
        scores = []

    clean_texts = []
    for value in texts:
        clean = normalize_text(str(value))
        if clean:
            clean_texts.append(clean)

    clean_scores = []
    for value in scores:
        try:
            clean_scores.append(float(value))
        except (TypeError, ValueError):
            continue

    return {
        "text": "\n".join(clean_texts).strip(),
        "line_count": len(clean_texts),
        "confidence": round(mean(clean_scores), 6) if clean_scores else 0.0,
    }


def combined_cache_paths(sha256: str) -> tuple[Path, Path]:
    COMBINED_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    return (
        COMBINED_CACHE_ROOT / f"{sha256}.json",
        COMBINED_CACHE_ROOT / f"{sha256}.txt",
    )


def read_combined_cache(sha256: str) -> dict[str, Any] | None:
    json_path, _ = combined_cache_paths(sha256)

    if not json_path.exists():
        return None

    try:
        payload = load_json(json_path)
    except Exception:
        return None

    if payload.get("cache_version") != CACHE_VERSION:
        return None
    if payload.get("sha256") != sha256:
        return None

    payload["cache_hit"] = True
    return payload


def save_combined_cache(payload: dict[str, Any]) -> None:
    json_path, text_path = combined_cache_paths(str(payload["sha256"]))
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    text_path.write_text(
        str(payload.get("combined_text") or ""),
        encoding="utf-8",
    )


def build_native_result(
    audit_row: pd.Series,
    dataset_root: Path,
) -> dict[str, Any]:
    sha256 = str(audit_row["sha256"])
    cached = read_combined_cache(sha256)
    if cached is not None:
        return cached

    native_path = NATIVE_CACHE_ROOT / f"{sha256}.json"
    if not native_path.exists():
        raise FileNotFoundError(f"내장 텍스트 캐시가 없습니다: {native_path}")

    native = load_json(native_path)
    combined_text = str(native.get("native_text") or "").strip()
    normalized_length = len(normalize_text(combined_text))

    payload = {
        "cache_version": CACHE_VERSION,
        "sha256": sha256,
        "institution": str(audit_row["institution"]),
        "file_name": str(audit_row["file_name"]),
        "pdf_path": str(audit_row["pdf_path"]),
        "relative_path": str(audit_row.get("relative_path") or ""),
        "source_audit_status": "TEXT_DIRECT",
        "final_status": "READY" if normalized_length >= MIN_DOCUMENT_TEXT_CHARS else "LOW_TEXT",
        "page_count": int(native.get("page_count") or 0),
        "native_page_count": int(native.get("text_page_count") or 0),
        "ocr_page_count": 0,
        "ocr_success_page_count": 0,
        "ocr_failed_page_count": 0,
        "normalized_text_length": normalized_length,
        "mean_ocr_confidence": 0.0,
        "combined_text": combined_text,
        "pages": native.get("page_details") or [],
        "errors": [],
        "cache_hit": False,
    }
    save_combined_cache(payload)
    return payload


def build_hybrid_result(
    engine: RapidOCR,
    audit_row: pd.Series,
) -> dict[str, Any]:
    sha256 = str(audit_row["sha256"])
    cached = read_combined_cache(sha256)
    if cached is not None:
        return cached

    pdf_path = Path(str(audit_row["pdf_path"]))
    page_rows = []
    text_parts = []
    errors = []
    confidence_values = []

    document = fitz.open(pdf_path)
    try:
        if document.needs_pass:
            raise ValueError("암호가 설정된 PDF입니다.")

        for page_number, page in enumerate(document, start=1):
            native_text = (page.get_text("text") or "").strip()
            native_normalized = normalize_text(native_text)
            method = "PDF_TEXT"
            selected_text = native_text
            confidence = 0.0
            line_count = 0
            error_text = ""

            if len(native_normalized) < MIN_PAGE_TEXT_CHARS:
                method = "RAPIDOCR"
                try:
                    ocr = rapidocr_page(engine, page)
                    selected_text = str(ocr["text"] or "").strip()
                    confidence = float(ocr["confidence"] or 0.0)
                    line_count = int(ocr["line_count"] or 0)
                    if confidence > 0:
                        confidence_values.append(confidence)
                except Exception as exc:
                    selected_text = ""
                    error_text = f"PAGE_{page_number}: {exc}"
                    errors.append(error_text)

            selected_normalized = normalize_text(selected_text)
            if selected_normalized:
                text_parts.append(
                    f"--- PAGE {page_number} [{method}] ---\n{selected_text}"
                )

            page_rows.append({
                "page": page_number,
                "method": method,
                "native_text_length": len(native_text),
                "selected_text_length": len(selected_text),
                "normalized_text_length": len(selected_normalized),
                "ocr_line_count": line_count,
                "ocr_mean_confidence": round(confidence, 6),
                "error": error_text,
                "text_preview": selected_normalized[:300],
            })
    finally:
        document.close()

    combined_text = "\n\n".join(text_parts).strip()
    normalized_length = len(normalize_text(combined_text))
    ocr_pages = [row for row in page_rows if row["method"] == "RAPIDOCR"]

    if normalized_length >= MIN_DOCUMENT_TEXT_CHARS:
        final_status = "READY"
    elif normalized_length > 0:
        final_status = "LOW_TEXT"
    elif errors:
        final_status = "OCR_ERROR"
    else:
        final_status = "NO_TEXT"

    payload = {
        "cache_version": CACHE_VERSION,
        "sha256": sha256,
        "institution": str(audit_row["institution"]),
        "file_name": str(audit_row["file_name"]),
        "pdf_path": str(pdf_path),
        "relative_path": str(audit_row.get("relative_path") or ""),
        "source_audit_status": "OCR_REQUIRED",
        "final_status": final_status,
        "page_count": len(page_rows),
        "native_page_count": sum(row["method"] == "PDF_TEXT" for row in page_rows),
        "ocr_page_count": len(ocr_pages),
        "ocr_success_page_count": sum(row["normalized_text_length"] > 0 for row in ocr_pages),
        "ocr_failed_page_count": sum(row["normalized_text_length"] == 0 for row in ocr_pages),
        "normalized_text_length": normalized_length,
        "mean_ocr_confidence": round(mean(confidence_values), 6) if confidence_values else 0.0,
        "combined_text": combined_text,
        "pages": page_rows,
        "errors": errors,
        "cache_hit": False,
    }
    save_combined_cache(payload)
    return payload


def result_row(payload: dict[str, Any]) -> dict[str, Any]:
    errors = payload.get("errors") or []
    return {
        "institution": payload.get("institution") or "",
        "file_name": payload.get("file_name") or "",
        "pdf_path": payload.get("pdf_path") or "",
        "relative_path": payload.get("relative_path") or "",
        "sha256": payload.get("sha256") or "",
        "source_audit_status": payload.get("source_audit_status") or "",
        "final_status": payload.get("final_status") or "",
        "page_count": int(payload.get("page_count") or 0),
        "native_page_count": int(payload.get("native_page_count") or 0),
        "ocr_page_count": int(payload.get("ocr_page_count") or 0),
        "ocr_success_page_count": int(payload.get("ocr_success_page_count") or 0),
        "ocr_failed_page_count": int(payload.get("ocr_failed_page_count") or 0),
        "normalized_text_length": int(payload.get("normalized_text_length") or 0),
        "mean_ocr_confidence": float(payload.get("mean_ocr_confidence") or 0.0),
        "cache_hit": bool(payload.get("cache_hit")),
        "error_count": len(errors),
        "error_text": " | ".join(str(value) for value in errors),
    }


def institution_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for institution, group in frame.groupby("institution", sort=True):
        ocr_group = group[group["ocr_page_count"] > 0]
        rows.append({
            "institution": institution,
            "total_pdf": int(len(group)),
            "native_direct": int((group["source_audit_status"] == "TEXT_DIRECT").sum()),
            "ocr_target": int((group["source_audit_status"] == "OCR_REQUIRED").sum()),
            "ready": int((group["final_status"] == "READY").sum()),
            "review_needed": int((group["final_status"] != "READY").sum()),
            "mean_text_length": round(float(group["normalized_text_length"].mean()), 1),
            "mean_ocr_confidence": round(float(ocr_group["mean_ocr_confidence"].mean()), 4) if len(ocr_group) else 0.0,
        })
    return pd.DataFrame(rows)


def save_charts(summary: pd.DataFrame, report_root: Path) -> None:
    chart = summary.sort_values("total_pdf", ascending=True)
    ocr_ready = chart["ready"] - chart["native_direct"]

    fig, ax = plt.subplots(figsize=(11, 8))
    ax.barh(chart["institution"], chart["native_direct"], label="Native text")
    ax.barh(chart["institution"], ocr_ready, left=chart["native_direct"], label="OCR ready")
    ax.barh(chart["institution"], chart["review_needed"], left=chart["ready"], label="Review needed")
    ax.set_title("Training text readiness by institution")
    ax.set_xlabel("PDF count")
    ax.legend()
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(report_root / "05_training_text_readiness.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    chart = summary.sort_values("mean_text_length", ascending=True)
    fig, ax = plt.subplots(figsize=(11, 8))
    ax.barh(chart["institution"], chart["mean_text_length"])
    ax.set_title("Average extracted text length by institution")
    ax.set_xlabel("Normalized character count")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(report_root / "06_average_text_length.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def save_html(summary: pd.DataFrame, payload: dict[str, Any], report_root: Path) -> None:
    rows = []
    for row in summary.to_dict(orient="records"):
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(row['institution']))}</td>"
            f"<td>{row['total_pdf']}</td>"
            f"<td>{row['native_direct']}</td>"
            f"<td>{row['ocr_target']}</td>"
            f"<td>{row['ready']}</td>"
            f"<td>{row['review_needed']}</td>"
            f"<td>{row['mean_text_length']}</td>"
            f"<td>{row['mean_ocr_confidence']}</td>"
            "</tr>"
        )

    report = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>OCR 학습데이터 보고서</title>
<style>body{{font-family:Arial,sans-serif;margin:28px;color:#1f2937}}.cards{{display:flex;gap:12px;flex-wrap:wrap}}.card{{border:1px solid #d1d5db;border-radius:10px;padding:14px;min-width:150px}}.value{{font-size:24px;font-weight:700}}img{{max-width:100%;border:1px solid #e5e7eb;margin:12px 0 24px}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border:1px solid #d1d5db;padding:7px}}th{{background:#f3f4f6}}</style></head>
<body><h1>할랄 인증서 OCR 학습데이터 보고서</h1>
<div class="cards"><div class="card">전체 PDF<div class="value">{payload['total_pdf']}</div></div><div class="card">학습 준비 완료<div class="value">{payload['ready_count']}</div></div><div class="card">OCR 대상<div class="value">{payload['ocr_target_count']}</div></div><div class="card">검토 필요<div class="value">{payload['review_count']}</div></div></div>
<h2>기관별 학습 텍스트 준비 상태</h2><img src="05_training_text_readiness.png" alt="기관별 준비 상태">
<h2>기관별 평균 텍스트 길이</h2><img src="06_average_text_length.png" alt="기관별 평균 텍스트 길이">
<h2>기관별 결과</h2><table><thead><tr><th>기관</th><th>전체</th><th>내장텍스트</th><th>OCR대상</th><th>준비완료</th><th>검토필요</th><th>평균길이</th><th>OCR신뢰도</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</body></html>"""
    (report_root / "08_ocr_report.html").write_text(report, encoding="utf-8")


def main() -> int:
    dataset_root = get_dataset_root()
    audit_root = get_latest_audit_root()
    audit = pd.read_csv(audit_root / "01_document_audit.csv", dtype={"sha256": str})

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_root = REPORTS_ROOT / f"ocr_training_text_{run_id}"
    report_root.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("할랄 인증기관 ML 2단계 - RapidOCR 학습 텍스트 생성")
    print("=" * 72)
    print(f"전체 PDF: {len(audit)}")
    print(f"OCR 대상: {int((audit['status'] == 'OCR_REQUIRED').sum())}")
    print("RapidOCR 엔진 초기화 중...")
    engine = RapidOCR()
    print("RapidOCR 엔진 정상")

    rows = []
    started = time.perf_counter()

    for index, audit_row in audit.iterrows():
        sequence = index + 1
        print(f"[{sequence:03d}/{len(audit):03d}] {audit_row['institution']} / {audit_row['file_name']}")
        try:
            if str(audit_row["status"]) == "TEXT_DIRECT":
                payload = build_native_result(audit_row, dataset_root)
            else:
                payload = build_hybrid_result(engine, audit_row)
        except Exception as exc:
            payload = {
                "institution": str(audit_row["institution"]),
                "file_name": str(audit_row["file_name"]),
                "pdf_path": str(audit_row["pdf_path"]),
                "relative_path": str(audit_row.get("relative_path") or ""),
                "sha256": str(audit_row["sha256"]),
                "source_audit_status": str(audit_row["status"]),
                "final_status": "OCR_ERROR",
                "page_count": 0,
                "native_page_count": 0,
                "ocr_page_count": 0,
                "ocr_success_page_count": 0,
                "ocr_failed_page_count": 0,
                "normalized_text_length": 0,
                "mean_ocr_confidence": 0.0,
                "cache_hit": False,
                "errors": [str(exc)],
            }
        rows.append(result_row(payload))

        if sequence % 10 == 0 or sequence == len(audit):
            elapsed = time.perf_counter() - started
            remaining = (elapsed / sequence) * (len(audit) - sequence)
            print(f"    경과 {elapsed / 60:.1f}분 / 예상 잔여 {remaining / 60:.1f}분")

    results = pd.DataFrame(rows)
    summary = institution_summary(results)
    review = results[results["final_status"] != "READY"].copy()
    ready = results[results["final_status"] == "READY"].copy()

    results.to_csv(report_root / "01_ocr_document_results.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(report_root / "02_institution_ocr_summary.csv", index=False, encoding="utf-8-sig")
    review.to_csv(report_root / "03_review_required.csv", index=False, encoding="utf-8-sig")
    ready.to_csv(report_root / "04_training_text_manifest.csv", index=False, encoding="utf-8-sig")
    save_charts(summary, report_root)

    summary_payload = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "dataset_root": str(dataset_root),
        "audit_root": str(audit_root),
        "report_root": str(report_root),
        "total_pdf": int(len(results)),
        "institution_count": int(results["institution"].nunique()),
        "ocr_target_count": int((results["source_audit_status"] == "OCR_REQUIRED").sum()),
        "ready_count": int(len(ready)),
        "review_count": int(len(review)),
        "cache_hit_count": int(results["cache_hit"].astype(bool).sum()),
        "status_counts": {str(k): int(v) for k, v in results["final_status"].value_counts().to_dict().items()},
        "rapidocr_version": importlib.metadata.version("rapidocr"),
        "onnxruntime_version": importlib.metadata.version("onnxruntime"),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
    }
    (report_root / "07_ocr_summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    save_html(summary, summary_payload, report_root)
    (REPORTS_ROOT / "latest_ocr_run.txt").write_text(str(report_root), encoding="utf-8")

    print("=" * 72)
    print("2단계 완료")
    print(f"학습 준비 완료: {len(ready)}")
    print(f"검토 필요: {len(review)}")
    print(f"결과 폴더: {report_root}")
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
