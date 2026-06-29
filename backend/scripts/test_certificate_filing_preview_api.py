from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests


BASE_URL = "http://127.0.0.1:8000"
OUTPUT_PATH = Path(r"C:\TEMP\certificate_filing_preview_utf8.json")


def get_json(url: str, *, timeout: int = 60) -> dict[str, Any]:
    response = requests.get(url, timeout=timeout)
    response.encoding = "utf-8"
    response.raise_for_status()
    return response.json()


def post_json(url: str, payload: dict[str, Any], *, timeout: int = 60) -> dict[str, Any]:
    response = requests.post(url, json=payload, timeout=timeout)
    response.encoding = "utf-8"

    if not response.ok:
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        raise RuntimeError(
            f"POST 실패: {response.status_code}\n"
            f"URL: {url}\n"
            f"응답: {detail}"
        )

    return response.json()


def select_safe_candidate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in rows:
        if not row.get("auto_match"):
            continue

        blockers = row.get("auto_match_blockers") or []
        if blockers:
            continue

        top_match = row.get("top_pmf_match") or {}
        if top_match.get("row_pos") is None:
            continue

        return row

    raise RuntimeError(
        "자동매칭 가능한 안전 후보를 찾지 못했습니다. "
        "candidates 결과의 auto_match 및 auto_match_blockers를 확인하세요."
    )


def main() -> None:
    candidates = get_json(f"{BASE_URL}/certificate-filing/candidates?limit=100")
    rows = candidates.get("rows") or []

    if not rows:
        raise RuntimeError("파일자동분류 후보가 0건입니다.")

    selected = select_safe_candidate(rows)
    top_match = selected["top_pmf_match"]

    payload = {
        "ocr_job_id": int(selected["ocr_job_id"]),
        "pmf_row_pos": int(top_match["row_pos"]),
        "pmf_depth": int(top_match.get("depth") or 0),
    }

    print("=== 선택 후보 ===")
    print(f"OCR Job ID : {payload['ocr_job_id']}")
    print(f"파일명     : {selected.get('filename', '')}")
    print(f"원료번호   : {top_match.get('material_no', '')}")
    print(f"영문명     : {top_match.get('english_name', '')}")
    print(f"제조사     : {top_match.get('maker', '')}")
    print(f"공급사     : {top_match.get('supplier', '')}")
    print(f"PMF 위치   : row={payload['pmf_row_pos']}, depth={payload['pmf_depth']}")

    preview = post_json(
        f"{BASE_URL}/certificate-filing/preview",
        payload,
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(preview, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )

    print()
    print("=== 미리보기 결과 ===")
    print(f"ok            : {preview.get('ok')}")
    print(f"warnings      : {len(preview.get('warnings') or [])}")
    print(f"blockers      : {len(preview.get('blockers') or [])}")
    print(f"hard_blockers : {len(preview.get('hard_blockers') or [])}")

    filing = preview.get("filing_preview") or {}
    pmf_update = preview.get("pmf_update_preview") or {}

    print(f"대상 폴더     : {filing.get('target_folder', filing.get('target_dir', ''))}")
    print(f"대상 파일     : {filing.get('target_path', '')}")
    print(f"PMF 변경예정  : {pmf_update}")

    if preview.get("blockers"):
        print()
        print("=== 차단 사유 ===")
        for item in preview["blockers"]:
            print(f"- {item}")

    print()
    print(f"저장 파일: {OUTPUT_PATH}")
    print("이 스크립트는 /confirm을 호출하지 않으므로 실제 파일 및 PMF를 수정하지 않습니다.")


if __name__ == "__main__":
    main()
