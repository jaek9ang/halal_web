import hashlib
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from app.core.path_utils import to_backend_storage_path
from typing import Any

from fastapi import UploadFile

from app.services.ocr_service import create_ocr_job, get_ocr_job
from app.core.db import connect as db_connect

# backend 폴더 기준 경로
BACKEND_DIR = Path(__file__).resolve().parents[2]

# OCR 테스트 파일 저장 / DB 경로
DATA_DIR = BACKEND_DIR / "data"
DB_DIR = BACKEND_DIR / "db"

OCR_TEST_UPLOAD_DIR = DATA_DIR / "ocr_test_uploads"
OCR_TEST_DB_PATH = DB_DIR / "ocr_test.db"

OCR_TEST_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_DIR.mkdir(parents=True, exist_ok=True)



ALLOWED_OCR_TEST_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
IMAGE_OCR_TEST_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}

def classify_ocr_error(error: Exception) -> tuple[str, str]:
    message = str(error) or ""
    lower = message.lower()

    if (
        "tesseract is not installed" in lower
        or "not in your path" in lower
        or "tesseractnotfounderror" in lower
    ):
        return (
            "TESSERACT_ERROR",
            "[TESSERACT_ERROR] Tesseract OCR 엔진이 설치되어 있지 않거나 PATH에 등록되어 있지 않습니다.",
        )

    if "unable to get page count" in lower or "pdfinfo" in lower:
        return (
            "PDF_RENDER_ERROR",
            f"[PDF_RENDER_ERROR] PDF 페이지 렌더링 실패: {message}",
        )

    if "cannot identify image file" in lower:
        return (
            "IMAGE_READ_ERROR",
            f"[IMAGE_READ_ERROR] 이미지 파일 판독 실패: {message}",
        )

    return (
        "ERROR",
        message,
    )

def detect_ocr_error_status(message: str) -> tuple[str | None, str]:
    text = str(message or "")
    lower = text.lower()

    if (
        "tesseract is not installed" in lower
        or "not in your path" in lower
        or "tesseractnotfounderror" in lower
        or "[tesseract_error]" in lower
    ):
        return (
            "TESSERACT_ERROR",
            "[TESSERACT_ERROR] Tesseract OCR 엔진이 설치되어 있지 않거나 PATH에 등록되어 있지 않습니다.",
        )

    if "pdfinfo" in lower or "unable to get page count" in lower:
        return (
            "PDF_RENDER_ERROR",
            f"[PDF_RENDER_ERROR] PDF 렌더링 실패: {text}",
        )

    if "cannot identify image file" in lower:
        return (
            "IMAGE_READ_ERROR",
            f"[IMAGE_READ_ERROR] 이미지 판독 실패: {text}",
        )

    return None, text

def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect_db():
    return db_connect(OCR_TEST_DB_PATH)


def init_ocr_test_db():
    conn = connect_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ocr_test_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_hash TEXT NOT NULL UNIQUE,
            original_filename TEXT,
            saved_filename TEXT,
            saved_path TEXT,
            size_bytes INTEGER DEFAULT 0,
            status TEXT DEFAULT 'READY',
            ocr_job_id INTEGER,
            raw_text_preview TEXT,
            error_message TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ocr_test_status
        ON ocr_test_files(status)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ocr_test_filename
        ON ocr_test_files(original_filename)
    """)

    conn.commit()
    conn.close()


def row_to_dict(row) -> dict[str, Any] | None:
    if row is None:
        return None

    return dict(row)


def safe_filename(name: str, fallback: str = "uploaded_file") -> str:
    value = Path(name or fallback).name
    value = re.sub(r'[\\/:*?"<>|]+', "_", value).strip()
    return value or fallback


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
      for chunk in iter(lambda: f.read(1024 * 1024), b""):
          if not chunk:
              break
          h.update(chunk)

    return h.hexdigest()


def get_test_file_by_hash(file_hash: str) -> dict[str, Any] | None:
    init_ocr_test_db()

    conn = connect_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM ocr_test_files
        WHERE file_hash = ?
    """, (file_hash,))

    row = row_to_dict(cur.fetchone())
    conn.close()
    return row


def get_test_file(file_id: int) -> dict[str, Any] | None:
    init_ocr_test_db()

    conn = connect_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM ocr_test_files
        WHERE id = ?
    """, (file_id,))

    row = row_to_dict(cur.fetchone())
    conn.close()
    return row


def attach_ocr_job_detail(row: dict[str, Any] | None, include_text: bool = False) -> dict[str, Any] | None:
    if not row:
        return row

    job_id = row.get("ocr_job_id")
    if not job_id:
        return row

    try:
        job = get_ocr_job(int(job_id))
    except Exception:
        return row

    rule = (
        job.get("certificate_rule")
        or job.get("result", {}).get("certificate_rule")
        or job.get("result", {}).get("field_guess", {}).get("certificate_rule")
        or None
    )

    row["certificate_rule"] = rule
    row["result"] = job.get("result") or {}

    if include_text:
        row["raw_text"] = job.get("raw_text") or job.get("raw_text_preview") or ""

    if not row.get("raw_text_preview"):
        row["raw_text_preview"] = job.get("raw_text_preview") or ""

    return row


def list_ocr_test_files(limit: int = 300) -> dict[str, Any]:
    init_ocr_test_db()

    conn = connect_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM ocr_test_files
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
    """, (limit,))

    rows = [attach_ocr_job_detail(row_to_dict(row), include_text=False) for row in cur.fetchall()]
    conn.close()

    return {
        "ok": True,
        "rows": rows,
        "count": len(rows),
    }


def save_ocr_test_uploads(files: list[UploadFile]) -> dict[str, Any]:
    init_ocr_test_db()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target_dir = OCR_TEST_UPLOAD_DIR / stamp
    target_dir.mkdir(parents=True, exist_ok=True)

    rows = []

    for idx, upload in enumerate(files, start=1):
        original = upload.filename or f"upload_{idx}"
        saved_name = safe_filename(original, f"upload_{idx}")
        ext = Path(saved_name).suffix.lower()

        if ext not in ALLOWED_OCR_TEST_EXTS:
            rows.append({
                "ok": False,
                "original_filename": original,
                "message": f"지원하지 않는 확장자입니다: {ext}",
            })
            continue

        temp_path = target_dir / saved_name

        with temp_path.open("wb") as out:
            shutil.copyfileobj(upload.file, out)

        size_bytes = temp_path.stat().st_size

        if size_bytes <= 0:
            temp_path.unlink(missing_ok=True)
            rows.append({
                "ok": False,
                "original_filename": original,
                "message": "빈 파일입니다.",
            })
            continue

        file_hash = sha256_file(temp_path)
        existing = get_test_file_by_hash(file_hash)

        if existing:
            temp_path.unlink(missing_ok=True)
            existing = attach_ocr_job_detail(existing, include_text=False) or existing
            existing["ok"] = True
            existing["duplicated"] = True
            rows.append(existing)
            continue

        rel_path = to_backend_storage_path(temp_path)
        now = now_text()

        conn = connect_db()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO ocr_test_files (
                file_hash,
                original_filename,
                saved_filename,
                saved_path,
                size_bytes,
                status,
                ocr_job_id,
                raw_text_preview,
                error_message,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'READY', NULL, '', '', ?, ?)
        """, (
            file_hash,
            original,
            saved_name,
            rel_path,
            size_bytes,
            now,
            now,
        ))

        file_id = cur.lastrowid
        conn.commit()
        conn.close()

        row = get_test_file(file_id)
        row["ok"] = True
        row["duplicated"] = False
        rows.append(row)

    return {
        "ok": True,
        "rows": rows,
        "count": len(rows),
    }


def update_test_file_status(
    file_id: int,
    status: str,
    ocr_job_id: int | None = None,
    raw_text_preview: str = "",
    error_message: str = "",
) -> dict[str, Any] | None:
    init_ocr_test_db()

    conn = connect_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE ocr_test_files
        SET
            status = ?,
            ocr_job_id = COALESCE(?, ocr_job_id),
            raw_text_preview = ?,
            error_message = ?,
            updated_at = ?
        WHERE id = ?
    """, (
        status,
        ocr_job_id,
        raw_text_preview[:3000] if raw_text_preview else "",
        error_message or "",
        now_text(),
        file_id,
    ))

    conn.commit()
    conn.close()

    return get_test_file(file_id)


def run_ocr_test_file(
    file_id: int,
    ocr_scanned_pages: bool = True,
    lang: str = "eng",
    skip_done: bool = True,
) -> dict[str, Any]:
    row = get_test_file(file_id)

    if not row:
        return {
            "ok": False,
            "id": file_id,
            "status": "ERROR",
            "message": "OCR 테스트 파일을 찾지 못했습니다.",
        }
    
    saved_path = str(row.get("saved_path") or row.get("saved_filename") or "")
    file_ext = Path(saved_path).suffix.lower()

    # OCR 테스트는 기본적으로 "텍스트 추출 가능 여부"만 빠르게 확인한다.
    # 이미지 파일은 곧바로 스캔본으로 분류한다. 여기서 Tesseract를 돌리면 화면이 멈춘다.
    if not ocr_scanned_pages and file_ext in IMAGE_OCR_TEST_EXTS:
        saved = update_test_file_status(
            file_id=file_id,
            status="SCANNED_NEED_OCR",
            raw_text_preview="",
            error_message="이미지/스캔본 파일입니다. OCR 엔진 단계에서 별도 처리해야 합니다.",
        ) or row

        saved["ok"] = True
        saved["raw_text"] = ""
        saved["raw_text_preview"] = ""
        saved["message"] = "이미지/스캔본 파일입니다. OCR 엔진 단계에서 별도 처리해야 합니다."
        return saved
    
    if skip_done and row.get("status") == "DONE" and row.get("ocr_job_id"):
        try:
            job = get_ocr_job(int(row["ocr_job_id"]))

            row["raw_text"] = job.get("raw_text") or job.get("raw_text_preview") or ""
            row["raw_text_preview"] = job.get("raw_text_preview") or row.get("raw_text_preview") or ""

            row["certificate_rule"] = (
                job.get("certificate_rule")
                or job.get("result", {}).get("certificate_rule")
                or job.get("result", {}).get("field_guess", {}).get("certificate_rule")
                or {}
            )

            row["result"] = job.get("result") or {}
        except Exception:
            pass

        row["ok"] = True
        row["skipped"] = True
        return row

    update_test_file_status(file_id, "RUNNING")

    try:
        job = create_ocr_job(
            source_path=row["saved_path"],
            ocr_scanned_pages=ocr_scanned_pages,
            lang=lang,
        )

        job_id = int(job.get("id"))
        detail = get_ocr_job(job_id)

        status = detail.get("status") or job.get("status") or "DONE"
        raw_text = detail.get("raw_text") or detail.get("raw_text_preview") or ""
        error_message = detail.get("error_message") or ""
        # 빠른 OCR 테스트 모드에서 텍스트가 없으면 실패가 아니라 스캔본 대기 상태로 분류한다.
        
        if not ocr_scanned_pages and status in {"NO_TEXT", "DONE"} and not str(raw_text or "").strip():
            status = "SCANNED_NEED_OCR"
            error_message = "텍스트 레이어가 없는 스캔본으로 보입니다. 스캔 OCR 엔진 단계에서 처리해야 합니다."

        # OCR 서비스가 DONE으로 반환했더라도, 실제 내용에 Tesseract 오류가 있으면 상태를 보정한다.
        detected_status, detected_message = detect_ocr_error_status(
            "\n".join([
                str(error_message or ""),
                str(raw_text or "")[:1000],
            ])
        )

        if detected_status:
            status = detected_status
            error_message = detected_message
        elif status == "DONE" and error_message:
            status = "ERROR"
            
        saved = update_test_file_status(
            file_id=file_id,
            status=status,
            ocr_job_id=job_id,
            raw_text_preview=raw_text,
            error_message=error_message,
        )

        certificate_rule = (
            detail.get("certificate_rule")
            or detail.get("result", {}).get("certificate_rule")
            or detail.get("result", {}).get("field_guess", {}).get("certificate_rule")
            or {}
        )

        saved["ok"] = True
        saved["raw_text"] = raw_text
        saved["raw_text_preview"] = raw_text[:3000]
        saved["certificate_rule"] = certificate_rule
        saved["result"] = detail.get("result") or {}
        return saved

    except Exception as e:
        error_status, error_message = classify_ocr_error(e)

        saved = update_test_file_status(
            file_id=file_id,
            status=error_status,
            error_message=error_message,
        )

        saved["ok"] = False
        saved["status"] = error_status
        saved["message"] = error_message
        return saved