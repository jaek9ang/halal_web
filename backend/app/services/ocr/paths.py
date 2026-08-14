"""판독 대상 파일 경로 검증.

허용된 루트 밖의 경로를 읽지 못하게 막는다."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import HALAL_DOC_ROOT, MAIL_RECEIVE_OUTPUT_DIR, OCR_OUTPUT_DIR

from app.services.ocr.engines import (
    TESSERACT_AVAILABLE,
    get_tesseract_runtime_info,
)


CERT_FILE_EXTS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
}


def is_allowed_cert_file(path: Path) -> bool:
    return path.suffix.lower() in CERT_FILE_EXTS


def safe_resolve_path(path_text: str) -> Path:
    """
    인증서 파일은 output/received_certs 하위 파일만 우선 허용.
    추후 업로드 폴더를 만들면 허용 경로를 추가하면 된다.
    """
    if not path_text:
        raise ValueError("파일 경로가 없습니다.")

    path = Path(path_text).resolve()

    allowed_roots = [
        MAIL_RECEIVE_OUTPUT_DIR.resolve(),
        OCR_OUTPUT_DIR.resolve(),
        HALAL_DOC_ROOT.resolve(),
    ]

    for root in allowed_roots:
        try:
            path.relative_to(root)
            return path
        except Exception:
            pass

    raise ValueError(f"허용되지 않은 파일 경로입니다: {path}")


def list_certificate_files(limit: int = 300) -> dict[str, Any]:
    MAIL_RECEIVE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []

    for path in MAIL_RECEIVE_OUTPUT_DIR.rglob("*"):
        if not path.is_file():
            continue

        if not is_allowed_cert_file(path):
            continue

        stat = path.stat()

        rows.append({
            "filename": path.name,
            "filepath": str(path),
            "file_ext": path.suffix.lower(),
            "size_bytes": int(stat.st_size),
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        })

    rows.sort(key=lambda x: x["modified_at"], reverse=True)

    limit = max(1, min(int(limit), 1000))

    return {
        "rows": rows[:limit],
        "total": len(rows),
        "tesseract_available": TESSERACT_AVAILABLE,
        "tesseract_info": get_tesseract_runtime_info(),
        "source_dir": str(MAIL_RECEIVE_OUTPUT_DIR),
    }


def resolve_allowed_ocr_source_path(source_path: str) -> Path:
    """
    OCR 대상 파일 경로를 검증한다.
    기존 OCR 업로드 폴더뿐 아니라 수신메일 다운로드 폴더도 허용한다.
    """
    if not source_path:
        raise ValueError("source_path가 없습니다.")

    backend_dir = Path(__file__).resolve().parents[2]
    raw_path = Path(str(source_path))

    candidates = []

    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        candidates.append(backend_dir / raw_path)
        candidates.append(Path.cwd() / raw_path)

    target = None

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            continue

        if resolved.exists():
            target = resolved
            break

    if target is None:
        raise ValueError(f"OCR 대상 파일이 존재하지 않습니다: {source_path}")

    allowed_roots = [
        MAIL_RECEIVE_OUTPUT_DIR,
        OCR_OUTPUT_DIR,
        HALAL_DOC_ROOT,
        backend_dir / "data",
        backend_dir / "data" / "ocr",
        backend_dir / "data" / "ocr_uploads",
        backend_dir / "data" / "mail_downloads",
        backend_dir / "data" / "ocr_test_uploads",
        backend_dir / "data" / "ocr_manual_uploads",
    ]

    is_allowed = False

    for root in allowed_roots:
        try:
            target.relative_to(root.resolve())
            is_allowed = True
            break
        except Exception:
            pass

    if not is_allowed:
        raise ValueError(f"허용되지 않은 파일 경로입니다: {target}")

    allowed_exts = {
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".tif",
        ".tiff",
        ".bmp",
    }

    if target.suffix.lower() not in allowed_exts:
        raise ValueError(f"OCR 지원 대상 확장자가 아닙니다: {target.suffix}")

    return target
