from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import fitz

from .config import (
    MIN_NATIVE_PAGE_CHARS,
    MIN_NATIVE_TEXT_CHARS,
    TEXT_CACHE_VERSION,
    get_runtime_paths,
)


_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", str(value or "")).strip()


def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file_obj:
        while True:
            chunk = file_obj.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest().upper()


def _cache_paths(sha256: str) -> tuple[Path, Path]:
    runtime_paths = get_runtime_paths()
    cache_root = runtime_paths["native_cache_root"]

    json_path = cache_root / f"{sha256}.json"
    text_path = cache_root / f"{sha256}.txt"

    return json_path, text_path


def _load_cached_result(
    json_path: Path,
    sha256: str,
) -> dict[str, Any] | None:
    if not json_path.exists():
        return None

    try:
        payload = json.loads(
            json_path.read_text(encoding="utf-8")
        )
    except Exception:
        return None

    if payload.get("cache_version") != TEXT_CACHE_VERSION:
        return None

    if payload.get("sha256") != sha256:
        return None

    result = dict(payload)
    result["cache_hit"] = True

    return result


def _save_cache(
    json_path: Path,
    text_path: Path,
    result: dict[str, Any],
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    text_path.write_text(
        str(result.get("native_text") or ""),
        encoding="utf-8",
    )


def inspect_pdf_native_text(
    pdf_path: Path,
    institution: str,
    dataset_root: Path,
) -> dict[str, Any]:
    pdf_path = Path(pdf_path)
    institution = str(institution or "").strip()

    try:
        sha256 = calculate_sha256(pdf_path)
    except Exception as exc:
        return {
            "institution": institution,
            "file_name": pdf_path.name,
            "pdf_path": str(pdf_path),
            "relative_path": "",
            "sha256": "",
            "file_size_bytes": 0,
            "page_count": 0,
            "text_page_count": 0,
            "usable_text_page_count": 0,
            "native_text_length": 0,
            "normalized_text_length": 0,
            "status": "EXTRACTION_ERROR",
            "cache_hit": False,
            "error": f"SHA256_ERROR: {exc}",
            "text_preview": "",
            "page_details": [],
            "native_text": "",
            "cache_version": TEXT_CACHE_VERSION,
        }

    json_cache_path, text_cache_path = _cache_paths(sha256)

    cached_result = _load_cached_result(
        json_cache_path,
        sha256,
    )

    if cached_result is not None:
        cached_result["institution"] = institution
        cached_result["pdf_path"] = str(pdf_path)
        cached_result["file_name"] = pdf_path.name

        try:
            cached_result["relative_path"] = str(
                pdf_path.relative_to(dataset_root)
            )
        except ValueError:
            cached_result["relative_path"] = str(pdf_path)

        return cached_result

    try:
        file_size_bytes = int(pdf_path.stat().st_size)
        document = fitz.open(pdf_path)

        page_details: list[dict[str, Any]] = []
        native_text_parts: list[str] = []

        try:
            if document.needs_pass:
                raise ValueError("암호가 설정된 PDF입니다.")

            for page_index, page in enumerate(
                document,
                start=1,
            ):
                raw_page_text = page.get_text("text") or ""
                normalized_page_text = normalize_text(
                    raw_page_text
                )

                page_details.append({
                    "page": page_index,
                    "raw_text_length": len(raw_page_text),
                    "normalized_text_length": len(
                        normalized_page_text
                    ),
                    "has_text": bool(normalized_page_text),
                    "usable_text": (
                        len(normalized_page_text)
                        >= MIN_NATIVE_PAGE_CHARS
                    ),
                    "text_preview": normalized_page_text[:300],
                })

                if normalized_page_text:
                    native_text_parts.append(
                        f"--- PAGE {page_index} ---\n"
                        f"{raw_page_text.strip()}"
                    )

        finally:
            document.close()

        native_text = "\n\n".join(native_text_parts).strip()
        normalized_text = normalize_text(native_text)

        text_page_count = sum(
            1
            for row in page_details
            if row["has_text"]
        )

        usable_text_page_count = sum(
            1
            for row in page_details
            if row["usable_text"]
        )

        status = (
            "TEXT_DIRECT"
            if (
                len(normalized_text)
                >= MIN_NATIVE_TEXT_CHARS
                and text_page_count >= 1
            )
            else "OCR_REQUIRED"
        )

        try:
            relative_path = str(
                pdf_path.relative_to(dataset_root)
            )
        except ValueError:
            relative_path = str(pdf_path)

        result = {
            "institution": institution,
            "file_name": pdf_path.name,
            "pdf_path": str(pdf_path),
            "relative_path": relative_path,
            "sha256": sha256,
            "file_size_bytes": file_size_bytes,
            "page_count": len(page_details),
            "text_page_count": text_page_count,
            "usable_text_page_count": usable_text_page_count,
            "native_text_length": len(native_text),
            "normalized_text_length": len(normalized_text),
            "status": status,
            "cache_hit": False,
            "error": "",
            "text_preview": normalized_text[:500],
            "page_details": page_details,
            "native_text": native_text,
            "cache_version": TEXT_CACHE_VERSION,
        }

        _save_cache(
            json_cache_path,
            text_cache_path,
            result,
        )

        return result

    except Exception as exc:
        try:
            relative_path = str(
                pdf_path.relative_to(dataset_root)
            )
        except ValueError:
            relative_path = str(pdf_path)

        return {
            "institution": institution,
            "file_name": pdf_path.name,
            "pdf_path": str(pdf_path),
            "relative_path": relative_path,
            "sha256": sha256,
            "file_size_bytes": (
                int(pdf_path.stat().st_size)
                if pdf_path.exists()
                else 0
            ),
            "page_count": 0,
            "text_page_count": 0,
            "usable_text_page_count": 0,
            "native_text_length": 0,
            "normalized_text_length": 0,
            "status": "EXTRACTION_ERROR",
            "cache_hit": False,
            "error": str(exc),
            "text_preview": "",
            "page_details": [],
            "native_text": "",
            "cache_version": TEXT_CACHE_VERSION,
        }
