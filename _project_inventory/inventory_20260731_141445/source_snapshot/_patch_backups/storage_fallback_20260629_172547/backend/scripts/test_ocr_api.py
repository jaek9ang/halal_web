from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_RUNTIME_ROOT = Path(r"D:\halal_web_runtime")


def find_latest_test_file(runtime_root: Path) -> Path:
    roots = [
        runtime_root / "data" / "mail_downloads",
        runtime_root / "data" / "ocr_test_uploads",
        runtime_root / "output" / "received_certs",
    ]
    extensions = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
    candidates: list[Path] = []

    for root in roots:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower() in extensions
                and path.stat().st_size > 0
            ):
                candidates.append(path)

    if not candidates:
        raise FileNotFoundError(
            "OCR 테스트에 사용할 PDF/이미지를 D드라이브에서 찾지 못했습니다."
        )

    return max(candidates, key=lambda value: value.stat().st_mtime)


def get_json(response: requests.Response) -> dict[str, Any]:
    response.encoding = "utf-8"

    if not response.ok:
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        raise RuntimeError(
            f"API 실패 {response.status_code}: {response.url}\n{detail}"
        )

    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--lang", default="eng")
    parser.add_argument("--reuse-done", action="store_true")
    parser.add_argument("--runtime-root", default=str(DEFAULT_RUNTIME_ROOT))
    args = parser.parse_args()

    runtime_root = Path(args.runtime_root)
    source = Path(args.file) if args.file else find_latest_test_file(runtime_root)

    if not source.exists():
        raise FileNotFoundError(source)

    health = requests.get(f"{args.base_url}/health", timeout=10)
    health.raise_for_status()

    with source.open("rb") as file:
        upload = get_json(
            requests.post(
                f"{args.base_url}/ocr/test-upload",
                files={
                    "files": (
                        source.name,
                        file,
                        "application/octet-stream",
                    )
                },
                timeout=120,
            )
        )

    rows = upload.get("rows") or []
    if not rows:
        raise RuntimeError(f"업로드 결과가 없습니다: {upload}")

    uploaded = rows[0]
    file_id = uploaded.get("id")

    if not file_id:
        raise RuntimeError(f"OCR 테스트 파일 ID가 없습니다: {uploaded}")

    result = get_json(
        requests.post(
            f"{args.base_url}/ocr/test-files/{file_id}/run",
            json={
                "ocr_scanned_pages": True,
                "lang": args.lang,
                "skip_done": bool(args.reuse_done),
            },
            timeout=900,
        )
    )

    output_dir = runtime_root / "ocr_test_results"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / (
        f"ocr_test_{datetime.now():%Y%m%d_%H%M%S}_{file_id}.json"
    )
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )

    certificate = (
        result.get("certificate_rule")
        or (result.get("result") or {}).get("certificate_rule")
        or {}
    )
    status = str(result.get("status") or "")
    error = str(result.get("error_message") or "")

    print("=== OCR 테스트 결과 ===")
    print(f"파일       : {source}")
    print(f"파일 ID    : {file_id}")
    print(f"상태       : {status}")
    print(f"인증기관   : {certificate.get('cert_org', '')}")
    print(f"인증번호   : {certificate.get('cert_no', '')}")
    print(f"유효기간   : {certificate.get('expiry_date', '')}")
    print(f"제조사     : {certificate.get('manufacturer', '')}")
    print(f"신뢰도     : {certificate.get('confidence', '')}")
    print(f"결과 파일  : {output_path}")

    failed_statuses = {
        "ERROR",
        "TESSERACT_ERROR",
        "PDF_RENDER_ERROR",
        "IMAGE_READ_ERROR",
    }

    if status in failed_statuses or error:
        print(f"오류       : {error}")
        raise SystemExit(1)

    print("OCR_TEST_OK")


if __name__ == "__main__":
    main()
