"""OCR 실행.

원래 ocr_service.py 한 파일(1,473줄)이었다.

의존 방향:
    engines -> store -> paths -> templates -> jobs -> failures"""

from __future__ import annotations

from app.services.ocr.engines import (
    TESSDATA_DEFAULT_DIR,
    TESSERACT_DEFAULT_CMD,
    build_tesseract_error_text,
    extract_image_text,
    extract_pdf_text,
    get_tesseract_runtime_info,
    is_tesseract_error_text,
    ocr_image_with_tesseract,
)
from app.services.ocr.store import (
    ensure_ocr_db,
    get_ocr_conn,
)
from app.services.ocr.paths import (
    CERT_FILE_EXTS,
    is_allowed_cert_file,
    list_certificate_files,
    resolve_allowed_ocr_source_path,
    safe_resolve_path,
)
from app.services.ocr.templates import (
    ADMIN_TEMPLATE_DECISIONS,
    IMAGE_TEMPLATE_DECISIONS,
    build_template_classification_for_ocr,
    reconcile_template_classification_with_rule,
)
from app.services.ocr.jobs import (
    create_ocr_job,
    delete_ocr_jobs,
    get_ocr_job,
    guess_certificate_fields,
    list_ocr_jobs,
    normalize_ocr_result_for_response,
)
from app.services.ocr.failures import (
    OCR_FAILURE_STATUSES,
    delete_stale_tesseract_ocr_jobs,
    get_ocr_failure_summary,
)

__all__ = [
    "ADMIN_TEMPLATE_DECISIONS",
    "CERT_FILE_EXTS",
    "IMAGE_TEMPLATE_DECISIONS",
    "OCR_FAILURE_STATUSES",
    "TESSDATA_DEFAULT_DIR",
    "TESSERACT_DEFAULT_CMD",
    "build_template_classification_for_ocr",
    "build_tesseract_error_text",
    "create_ocr_job",
    "delete_ocr_jobs",
    "delete_stale_tesseract_ocr_jobs",
    "ensure_ocr_db",
    "extract_image_text",
    "extract_pdf_text",
    "get_ocr_conn",
    "get_ocr_failure_summary",
    "get_ocr_job",
    "get_tesseract_runtime_info",
    "guess_certificate_fields",
    "is_allowed_cert_file",
    "is_tesseract_error_text",
    "list_certificate_files",
    "list_ocr_jobs",
    "normalize_ocr_result_for_response",
    "ocr_image_with_tesseract",
    "reconcile_template_classification_with_rule",
    "resolve_allowed_ocr_source_path",
    "safe_resolve_path",
]
