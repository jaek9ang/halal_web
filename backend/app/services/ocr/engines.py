"""OCR 엔진 호출. PDF 원본 텍스트를 먼저 보고, 없으면 이미지로 렌더해 OCR한다."""

from __future__ import annotations

import io
import os
import shutil
from pathlib import Path
from typing import Any


TESSERACT_DEFAULT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


TESSDATA_DEFAULT_DIR = r"C:\Program Files\Tesseract-OCR\tessdata"


# Tesseract는 없을 수도 있다. 없으면 TESSERACT_AVAILABLE=False로 두고
# 판독 시 사용자에게 보이는 오류 텍스트를 만든다.
try:
    import pytesseract
    from PIL import Image
except Exception as e:
    pytesseract = None
    Image = None
    TESSERACT_AVAILABLE = False
    TESSERACT_INFO = {
        "available": False,
        "import_ok": False,
        "cmd": "",
        "version": "",
        "tessdata_prefix": "",
        "error": str(e),
    }
else:
    cmd_candidates = [
        os.getenv("TESSERACT_CMD", "").strip(),
        TESSERACT_DEFAULT_CMD,
        shutil.which("tesseract") or "",
    ]

    selected_cmd = ""

    for candidate in cmd_candidates:
        if candidate and Path(candidate).exists():
            selected_cmd = str(Path(candidate))
            break

    if selected_cmd:
        pytesseract.pytesseract.tesseract_cmd = selected_cmd

    tessdata_prefix = (
        os.getenv("TESSDATA_PREFIX", "").strip()
        or TESSDATA_DEFAULT_DIR
    )

    if tessdata_prefix and Path(tessdata_prefix).exists():
        os.environ["TESSDATA_PREFIX"] = tessdata_prefix

    try:
        version_text = str(pytesseract.get_tesseract_version())
        TESSERACT_AVAILABLE = True
        TESSERACT_INFO = {
            "available": True,
            "import_ok": True,
            "cmd": selected_cmd or shutil.which("tesseract") or "",
            "version": version_text,
            "tessdata_prefix": os.environ.get("TESSDATA_PREFIX", ""),
            "error": "",
        }
    except Exception as e:
        TESSERACT_AVAILABLE = False
        TESSERACT_INFO = {
            "available": False,
            "import_ok": True,
            "cmd": selected_cmd or shutil.which("tesseract") or "",
            "version": "",
            "tessdata_prefix": os.environ.get("TESSDATA_PREFIX", ""),
            "error": str(e),
        }


def get_tesseract_runtime_info() -> dict[str, Any]:
    return dict(TESSERACT_INFO)


def build_tesseract_error_text() -> str:
    error = TESSERACT_INFO.get("error") or "Tesseract OCR 엔진을 실행할 수 없습니다."
    cmd = TESSERACT_INFO.get("cmd") or ""
    return f"[TESSERACT_ERROR] {error} / cmd={cmd}"


def is_tesseract_error_text(value: str) -> bool:
    text = str(value or "").lower()
    return (
        "[tesseract_error]" in text
        or "tesseract is not installed" in text
        or "not in your path" in text
        or "tesseractnotfounderror" in text
    )


def ocr_image_with_tesseract(image: Any, lang: str = "eng") -> str:
    if not TESSERACT_AVAILABLE:
        return build_tesseract_error_text()

    try:
        return pytesseract.image_to_string(image, lang=lang) or ""
    except Exception as e:
        return f"[TESSERACT_ERROR] {e}"


def extract_pdf_text(path: Path, ocr_scanned_pages: bool = True, lang: str = "eng") -> dict[str, Any]:
    doc = fitz.open(path)

    page_results = []
    full_text_parts = []

    try:
        for page_idx, page in enumerate(doc, start=1):
            native_text = page.get_text("text") or ""
            native_text = native_text.strip()

            method = "pdf_text"
            page_text = native_text

            if not page_text and ocr_scanned_pages and TESSERACT_AVAILABLE:
                method = "tesseract"
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                img_bytes = pix.tobytes("png")
                image = Image.open(io.BytesIO(img_bytes))
                page_text = ocr_image_with_tesseract(image, lang=lang).strip()

            elif not page_text and ocr_scanned_pages and not TESSERACT_AVAILABLE:
                method = "tesseract_unavailable"
                page_text = build_tesseract_error_text()

            page_results.append({
                "page": page_idx,
                "method": method,
                "text_length": len(page_text),
                "text_preview": page_text[:500],
            })

            if page_text:
                full_text_parts.append(f"\n\n--- PAGE {page_idx} ---\n{page_text}")

    finally:
        doc.close()

    return {
        "text": "\n".join(full_text_parts).strip(),
        "pages": page_results,
        "page_count": len(page_results),
    }


def extract_image_text(path: Path, lang: str = "eng") -> dict[str, Any]:
    if not TESSERACT_AVAILABLE:
        error_text = build_tesseract_error_text()

        return {
            "text": error_text,
            "pages": [{
                "page": 1,
                "method": "tesseract_unavailable",
                "text_length": len(error_text),
                "text_preview": error_text[:500],
            }],
            "page_count": 1,
        }

    image = Image.open(path)
    text = ocr_image_with_tesseract(image, lang=lang).strip()

    return {
        "text": text,
        "pages": [{
            "page": 1,
            "method": "tesseract",
            "text_length": len(text),
            "text_preview": text[:500],
        }],
        "page_count": 1,
    }
