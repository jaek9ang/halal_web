import io
import json
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from app.services.certificate_rule_service import parse_certificate_rule
from app.services.ocr_context_service import parse_certificate_with_linked_context
import re

import fitz

from app.core.config import (
    MAIL_RECEIVE_OUTPUT_DIR,
    OCR_OUTPUT_DIR,
    PMF_APP_DB_PATH,
    HALAL_DOC_ROOT,
)

TESSERACT_DEFAULT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA_DEFAULT_DIR = r"C:\Program Files\Tesseract-OCR\tessdata"


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


CERT_FILE_EXTS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
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

def ensure_ocr_db() -> None:
    PMF_APP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    OCR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(PMF_APP_DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ocr_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_path TEXT,
        filename TEXT,
        file_ext TEXT,
        status TEXT,
        raw_text TEXT,
        result_json TEXT,
        error_message TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """)

    conn.commit()
    conn.close()


def get_ocr_conn():
    ensure_ocr_db()
    conn = sqlite3.connect(PMF_APP_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


IMAGE_TEMPLATE_DECISIONS = {"AUTO_IMAGE", "REVIEW", "MANUAL_REVIEW", "NO_REFERENCE", "ERROR"}
ADMIN_TEMPLATE_DECISIONS = {
    "AUTO_CONFIRMED",
    "MANUAL_CONFIRMED",
    "MANUAL_CORRECTED",
    "EXCLUDED",
    "RESTORED",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _upper_text(value: Any) -> str:
    return str(value or "").strip().upper()


def build_template_classification_for_ocr(path: Path) -> dict[str, Any]:
    """
    OCR 실행 전에 인증서 양식 DB로 기관 후보를 먼저 판정한다.
    관리자 확정/정정/제외값이 저장되어 있으면 classify_file_path 내부에서 우선 적용된다.
    이 함수는 실패해도 OCR 자체를 막지 않고 error 정보를 result_json에 남긴다.
    """
    try:
        # Lazy import: cert_template_service <-> ocr_service circular import 방지
        from app.services.cert_template_service import classify_file_path

        row = classify_file_path(
            str(path),
            enhanced_retry=True,
            max_pages=1,
        )

        manual = row.get("manual_decision") or {}
        manual_type = _upper_text(manual.get("decision_type"))
        raw_decision = _upper_text(row.get("decision"))
        is_excluded = (
            raw_decision == "EXCLUDED"
            or manual_type == "EXCLUDED"
            or int(manual.get("is_excluded") or 0) == 1
        )

        image_decision = _upper_text(
            manual.get("original_decision")
            or row.get("image_decision")
            or row.get("original_decision")
            or row.get("decision")
        )

        if image_decision not in IMAGE_TEMPLATE_DECISIONS:
            # 관리자 판정값이 decision에 들어온 경우에는 원본 이미지 판정값이 없을 수 있다.
            score = _safe_float(row.get("score"))
            margin = _safe_float(row.get("margin"))
            if score >= 0.82 and margin >= 0.07:
                image_decision = "AUTO_IMAGE"
            elif score < 0.70 or margin < 0.04:
                image_decision = "MANUAL_REVIEW"
            else:
                image_decision = "REVIEW"

        predicted_org = str(
            manual.get("predicted_org")
            or row.get("predicted_org")
            or "-"
        ).strip() or "-"

        final_org = str(
            manual.get("final_org")
            or row.get("final_org")
            or row.get("predicted_org")
            or "-"
        ).strip() or "-"

        if is_excluded:
            final_org = "-"

        top_candidates = row.get("top_candidates") or []
        top_candidates = top_candidates[:5] if isinstance(top_candidates, list) else []

        return {
            "ok": True,
            "file_hash": row.get("file_hash") or "",
            "filename": path.name,
            "file_path": str(path),
            "predicted_org": predicted_org,
            "final_org": final_org,
            "image_decision": image_decision,
            "decision": raw_decision or image_decision,
            "admin_decision": manual_type if manual_type in ADMIN_TEMPLATE_DECISIONS else "",
            "is_excluded": bool(is_excluded),
            "score": _safe_float(row.get("score")),
            "second_org": row.get("second_org") or "-",
            "second_score": _safe_float(row.get("second_score")),
            "margin": _safe_float(row.get("margin")),
            "feature_kind": row.get("feature_kind") or "-",
            "top_candidates": top_candidates,
            "top_evidence": row.get("top_evidence") or {},
            "manual_decision": manual or None,
        }

    except Exception as e:
        return {
            "ok": False,
            "filename": path.name,
            "file_path": str(path),
            "predicted_org": "-",
            "final_org": "-",
            "image_decision": "ERROR",
            "decision": "ERROR",
            "admin_decision": "",
            "is_excluded": False,
            "score": 0.0,
            "second_org": "-",
            "second_score": 0.0,
            "margin": 0.0,
            "feature_kind": "-",
            "top_candidates": [],
            "error": str(e),
        }


def reconcile_template_classification_with_rule(
    image_classification: dict[str, Any],
    certificate_rule: dict[str, Any],
) -> dict[str, Any]:
    """
    이미지 양식 분류와 OCR 텍스트 규칙 결과가 충돌할 때 최종기관을 보정한다.

    원칙:
    1. 관리자 확정/정정/제외값은 최우선으로 유지한다.
    2. 이미지 판정이 AUTO_IMAGE면 이미지기관을 유지하되, 텍스트기관과 다르면 conflict만 표시한다.
    3. 이미지 판정이 REVIEW/MANUAL_REVIEW이고 텍스트 규칙기관이 명확하면 최종기관은 텍스트 규칙기관으로 보정한다.
    4. 텍스트 규칙기관이 없으면 이미지기관을 후보로만 유지한다.
    """
    info = dict(image_classification or {})
    rule = certificate_rule or {}

    if not info:
        return info

    if info.get("is_excluded"):
        info["final_org"] = "-"
        info["final_org_source"] = "ADMIN_EXCLUDED"
        return info

    manual_obj = info.get("manual_decision") if isinstance(info.get("manual_decision"), dict) else {}
    admin_type = _upper_text(info.get("admin_decision") or manual_obj.get("decision_type"))
    image_decision = _upper_text(info.get("image_decision") or info.get("decision"))
    predicted_org = str(info.get("predicted_org") or "-").strip() or "-"

    rule_org = str(rule.get("cert_org") or "").strip().upper()
    if not rule_org or rule_org == "UNKNOWN":
        rule_org = ""

    if admin_type in {"AUTO_CONFIRMED", "MANUAL_CONFIRMED", "MANUAL_CORRECTED"}:
        info["final_org"] = str(info.get("final_org") or predicted_org or "-").strip() or "-"
        info["final_org_source"] = "ADMIN"
        if rule_org:
            info["text_rule_org"] = rule_org
            info["text_image_conflict"] = predicted_org.upper() != rule_org
        return info

    if image_decision == "AUTO_IMAGE":
        info["final_org"] = str(info.get("final_org") or predicted_org or "-").strip() or "-"
        info["final_org_source"] = "IMAGE_AUTO"
        if rule_org:
            info["text_rule_org"] = rule_org
            info["text_image_conflict"] = predicted_org.upper() != rule_org
        return info

    if rule_org:
        info["final_org"] = rule_org
        info["final_org_source"] = "TEXT_RULE"
        info["text_rule_org"] = rule_org
        info["text_image_conflict"] = predicted_org.upper() != rule_org
        return info

    info["final_org"] = predicted_org
    info["final_org_source"] = "IMAGE_REVIEW_CANDIDATE"
    info["text_image_conflict"] = False
    return info


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

def guess_certificate_fields(
    raw_text: str,
    filename: str = "",
    source_path: str = "",
    ocr_job_id: int | None = None,
) -> dict[str, Any]:
    """
    OCR 기본 규칙을 실행한 뒤, 메일 관리번호와 PMF 연결이 확인되는 경우에만
    제품명·제조사 문맥으로 교차검증한다.
    """
    if source_path:
        parsed = parse_certificate_with_linked_context(
            raw_text=raw_text,
            filename=filename,
            source_path=source_path,
            ocr_job_id=ocr_job_id,
        )
    else:
        parsed = parse_certificate_rule(
            raw_text=raw_text,
            filename=filename,
        )

    org = parsed.get("cert_org")
    org_candidates = []

    if org and org != "UNKNOWN":
        org_candidates.append(org)

    return {
        "org_candidates": org_candidates,
        "has_text": bool((raw_text or "").strip()),
        "text_length": len(raw_text or ""),
        "certificate_rule": parsed,
    }

def create_ocr_job(
    source_path: str,
    ocr_scanned_pages: bool = True,
    lang: str = "eng",
) -> dict[str, Any]:
    ensure_ocr_db()

    path = resolve_allowed_ocr_source_path(source_path)

    if not path.exists():
        raise FileNotFoundError(f"파일을 찾지 못했습니다: {path}")

    if not is_allowed_cert_file(path):
        raise ValueError(f"지원하지 않는 파일 형식입니다: {path.suffix}")
    
    if path.stat().st_size <= 0:
        raise ValueError(f"OCR 대상 파일이 비어 있습니다: {path}")
    
    now_ts = datetime.now().isoformat(timespec="seconds")

    conn = get_ocr_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO ocr_jobs (
        source_path,
        filename,
        file_ext,
        status,
        raw_text,
        result_json,
        error_message,
        created_at,
        updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(path),
        path.name,
        path.suffix.lower(),
        "RUNNING",
        "",
        "{}",
        "",
        now_ts,
        now_ts,
    ))

    job_id = cur.lastrowid
    conn.commit()
    conn.close()

    image_classification = build_template_classification_for_ocr(path)

    if image_classification.get("is_excluded"):
        result = {
            "source_path": str(path),
            "filename": path.name,
            "file_ext": path.suffix.lower(),
            "page_count": 0,
            "pages": [],
            "field_guess": {
                "org_candidates": [],
                "has_text": False,
                "text_length": 0,
                "certificate_rule": {},
                "image_classification": image_classification,
            },
            "certificate_rule": {},
            "image_classification": image_classification,
            "tesseract_available": TESSERACT_AVAILABLE,
            "tesseract_info": get_tesseract_runtime_info(),
            "ocr_lang": lang,
            "message": "관리자 판정값이 EXCLUDED라서 OCR을 실행하지 않았습니다.",
        }

        conn = get_ocr_conn()
        conn.execute("""
        UPDATE ocr_jobs
        SET status = ?,
            raw_text = ?,
            result_json = ?,
            error_message = ?,
            updated_at = ?
        WHERE id = ?
        """, (
            "EXCLUDED",
            "",
            json.dumps(result, ensure_ascii=False),
            "관리자 판정값이 EXCLUDED라서 OCR을 실행하지 않았습니다.",
            datetime.now().isoformat(timespec="seconds"),
            job_id,
        ))
        conn.commit()
        conn.close()

        return get_ocr_job(job_id)

    try:
        ext = path.suffix.lower()

        if ext == ".pdf":
            extracted = extract_pdf_text(
                path=path,
                ocr_scanned_pages=ocr_scanned_pages,
                lang=lang,
            )
        else:
            extracted = extract_image_text(
                path=path,
                lang=lang,
            )

        raw_text = extracted.get("text", "")
        field_guess = guess_certificate_fields(
            raw_text,
            filename=path.name,
            source_path=str(path),
            ocr_job_id=job_id,
        )
        certificate_rule = field_guess.get("certificate_rule") or {}

        # 이미지 양식 DB 분류와 OCR 텍스트 규칙 결과를 병합한다.
        # REVIEW/MANUAL_REVIEW에서 이미지 후보를 최종기관으로 오인하지 않도록 한다.
        image_classification = reconcile_template_classification_with_rule(
            image_classification,
            certificate_rule,
        )

        field_guess["image_classification"] = image_classification

        result = {
            "source_path": str(path),
            "filename": path.name,
            "file_ext": ext,
            "page_count": extracted.get("page_count", 0),
            "pages": extracted.get("pages", []),
            "field_guess": field_guess,
            "certificate_rule": certificate_rule,
            "image_classification": image_classification,
            "tesseract_available": TESSERACT_AVAILABLE,
            "tesseract_info": get_tesseract_runtime_info(),
            "ocr_lang": lang,
        }

        if is_tesseract_error_text(raw_text):
            status = "TESSERACT_ERROR"
            error_message = raw_text[:1000]
        elif raw_text.strip():
            status = "DONE"
            error_message = ""
        else:
            status = "NO_TEXT"
            error_message = ""

        conn = get_ocr_conn()
        conn.execute("""
        UPDATE ocr_jobs
        SET status = ?,
            raw_text = ?,
            result_json = ?,
            error_message = ?,
            updated_at = ?
        WHERE id = ?
        """, (
            status,
            raw_text,
            json.dumps(result, ensure_ascii=False),
            error_message,
            datetime.now().isoformat(timespec="seconds"),
            job_id,
        ))
        conn.commit()
        conn.close()

        return get_ocr_job(job_id)

    except Exception as e:
        error_result = {
            "source_path": str(path),
            "filename": path.name,
            "file_ext": path.suffix.lower(),
            "image_classification": image_classification,
            "error": str(e),
            "tesseract_available": TESSERACT_AVAILABLE,
            "tesseract_info": get_tesseract_runtime_info(),
            "ocr_lang": lang,
        }
        conn = get_ocr_conn()
        conn.execute("""
        UPDATE ocr_jobs
        SET status = ?,
            result_json = ?,
            error_message = ?,
            updated_at = ?
        WHERE id = ?
        """, (
            "ERROR",
            json.dumps(error_result, ensure_ascii=False),
            str(e),
            datetime.now().isoformat(timespec="seconds"),
            job_id,
        ))
        conn.commit()
        conn.close()

        return get_ocr_job(job_id)

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

def normalize_ocr_result_for_response(data: dict[str, Any]) -> dict[str, Any]:
    """
    DB에 이미 저장된 과거 OCR job도 응답 시점에
    image_classification + certificate_rule을 다시 reconcile한다.

    목적:
    - 기존 result_json에 final_org_source/text_rule_org가 없어도 화면에서는 보정값 표시
    - REVIEW/MANUAL_REVIEW 이미지 후보가 OCR 텍스트 규칙기관보다 우선되는 문제 방지
    """
    result = data.get("result") or {}

    if not isinstance(result, dict):
        result = {}

    rule = (
        result.get("certificate_rule")
        or result.get("field_guess", {}).get("certificate_rule")
    )

    if not rule:
        try:
            filename = data.get("filename") or Path(data.get("source_path") or "").name
            rule = parse_certificate_rule(
                raw_text=data.get("raw_text") or "",
                filename=filename,
            )
        except Exception as e:
            rule = {
                "ok": False,
                "parse_status": "RULE_ERROR",
                "message": str(e),
            }

    image_classification = (
        result.get("image_classification")
        or result.get("field_guess", {}).get("image_classification")
        or {}
    )

    if isinstance(image_classification, dict) and image_classification:
        image_classification = reconcile_template_classification_with_rule(
            image_classification,
            rule or {},
        )

    result["certificate_rule"] = rule
    result["image_classification"] = image_classification

    if isinstance(result.get("field_guess"), dict):
        result["field_guess"]["certificate_rule"] = rule
        result["field_guess"]["image_classification"] = image_classification

    data["result"] = result
    data["certificate_rule"] = rule
    data["image_classification"] = image_classification

    return data

def get_ocr_job(job_id: int) -> dict[str, Any]:
    ensure_ocr_db()

    conn = get_ocr_conn()
    row = conn.execute("""
        SELECT *
        FROM ocr_jobs
        WHERE id = ?
    """, (int(job_id),)).fetchone()
    conn.close()

    if not row:
        raise ValueError(f"OCR job을 찾지 못했습니다: {job_id}")

    data = dict(row)

    try:
        data["result"] = json.loads(data.get("result_json") or "{}")
    except Exception:
        data["result"] = {}

    data["raw_text_preview"] = (data.get("raw_text") or "")[:3000]

    return normalize_ocr_result_for_response(data)

def list_ocr_jobs(
    limit: int = 100,
    status: str = "",
    org: str = "",
    keyword: str = "",
    include_test: bool = False,
) -> dict[str, Any]:
    ensure_ocr_db()

    limit = max(1, min(int(limit), 500))

    where = []
    params = []

    if not include_test:
        where.append("""
            COALESCE(source_path, '') NOT LIKE '%ocr_test_uploads%'
            AND COALESCE(source_path, '') NOT LIKE '%data/ocr_test_uploads%'
        """)

    if status:
        where.append("UPPER(COALESCE(status, '')) = ?")
        params.append(status.upper())

    if keyword:
        like = f"%{keyword}%"
        where.append("""
            (
                COALESCE(filename, '') LIKE ?
                OR COALESCE(source_path, '') LIKE ?
                OR COALESCE(raw_text, '') LIKE ?
                OR COALESCE(result_json, '') LIKE ?
                OR COALESCE(error_message, '') LIKE ?
            )
        """)
        params.extend([like, like, like, like, like])

    sql = """
        SELECT
            id,
            source_path,
            filename,
            file_ext,
            status,
            raw_text,
            result_json,
            error_message,
            created_at,
            updated_at,
            LENGTH(COALESCE(raw_text, '')) AS text_length
        FROM ocr_jobs
    """

    if where:
        sql += " WHERE " + " AND ".join(f"({x})" for x in where)

    sql += """
        ORDER BY id DESC
        LIMIT ?
    """
    params.append(limit)

    conn = get_ocr_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    result_rows = []

    for row in rows:
        data = dict(row)

        try:
            parsed_result = json.loads(data.get("result_json") or "{}")
        except Exception:
            parsed_result = {}

        data["result"] = parsed_result
        data = normalize_ocr_result_for_response(data)

        rule = data.get("certificate_rule") or {}
        image_classification = data.get("image_classification") or {}

        if org:
            target_org = org.upper()
            rule_org = str(rule.get("cert_org") or "").upper()
            image_orgs = {
                str(image_classification.get("predicted_org") or "").upper(),
                str(image_classification.get("final_org") or "").upper(),
            }

            if rule_org != target_org and target_org not in image_orgs:
                continue

        data["raw_text_preview"] = (data.get("raw_text") or "")[:500]

        # 목록 응답이 너무 커지는 것 방지
        data.pop("raw_text", None)
        data.pop("result_json", None)

        result_rows.append(data)

    return {
        "ok": True,
        "rows": result_rows,
        "count": len(result_rows),
    }

OCR_FAILURE_STATUSES = {
    "TESSERACT_ERROR",
    "SCANNED_NEED_OCR",
    "NO_TEXT",
    "PDF_RENDER_ERROR",
    "IMAGE_READ_ERROR",
    "ERROR",
}


def _resolve_ocr_failure_status(data: dict[str, Any]) -> str:
    status = str(data.get("status") or "").upper()
    error_message = str(data.get("error_message") or "")
    raw_text = str(data.get("raw_text") or "")
    result = data.get("result") or {}

    rule = (
        data.get("certificate_rule")
        or result.get("certificate_rule")
        or result.get("field_guess", {}).get("certificate_rule")
        or {}
    )

    blob = "\n".join([
        status,
        error_message,
        raw_text[:1500],
        str(result.get("error") or ""),
        str(result.get("message") or ""),
        str(rule.get("parse_status") or ""),
        str(rule.get("message") or ""),
    ]).lower()

    if (
        "tesseract is not installed" in blob
        or "not in your path" in blob
        or "tesseractnotfounderror" in blob
        or "[tesseract_error]" in blob
        or str(rule.get("parse_status") or "").upper() == "TESSERACT_ERROR"
    ):
        return "TESSERACT_ERROR"

    if (
        "pdfinfo" in blob
        or "unable to get page count" in blob
        or "[pdf_render_error]" in blob
    ):
        return "PDF_RENDER_ERROR"

    if (
        "cannot identify image file" in blob
        or "[image_read_error]" in blob
    ):
        return "IMAGE_READ_ERROR"

    if (
        "scanned_need_ocr" in blob
        or "[scanned_need_ocr]" in blob
        or "text layer is empty" in blob
        or "텍스트 레이어" in blob
    ):
        return "SCANNED_NEED_OCR"

    if (
        status == "NO_TEXT"
        or "[no_text]" in blob
        or "no text" in blob
        or "추출된 텍스트가 없습니다" in blob
    ):
        return "NO_TEXT"

    if status == "ERROR":
        return "ERROR"

    return status

def _ocr_history_key(data: dict[str, Any]) -> str:
    # ?? ?? ??? key.
    # junction/symlink/????? ?? ??? ?????.
    source_value = str(data.get("source_path") or "").strip()
    filename = str(data.get("filename") or "").strip()

    if source_value:
        backend_dir = Path(__file__).resolve().parents[2]
        raw_path = Path(source_value)

        candidates = (
            [raw_path]
            if raw_path.is_absolute()
            else [
                backend_dir / raw_path,
                Path.cwd() / raw_path,
            ]
        )

        for candidate in candidates:
            try:
                canonical = Path(
                    os.path.realpath(str(candidate))
                ).resolve(strict=False)

                if canonical.exists():
                    value = str(canonical)
                    value = value.replace("\\", "/").lower()
                    value = re.sub(r"/+", "/", value)
                    return value
            except Exception:
                continue

        value = source_value.replace("\\", "/").lower()
        value = re.sub(r"/+", "/", value)
        return value

    value = filename.replace("\\", "/").lower()
    value = re.sub(r"/+", "/", value)
    return value



def _hydrate_ocr_failure_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)

    try:
        data["result"] = json.loads(data.get("result_json") or "{}")
    except Exception:
        data["result"] = {}

    try:
        data = normalize_ocr_result_for_response(data)
    except Exception:
        pass

    return data


def _is_successful_ocr_job(data: dict[str, Any]) -> bool:
    """
    현재 기준 정상 OCR job인지 판단.
    DONE이어도 raw_text 안에 과거 Tesseract 오류문구가 있으면 성공으로 보지 않는다.
    """
    status = str(data.get("status") or "").upper()

    if status != "DONE":
        return False

    failure_status = _resolve_ocr_failure_status(data)

    if failure_status in OCR_FAILURE_STATUSES:
        return False

    raw_text = str(data.get("raw_text") or "")
    error_message = str(data.get("error_message") or "")

    if is_tesseract_error_text(raw_text) or is_tesseract_error_text(error_message):
        return False

    return True


def _build_latest_maps(rows: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, int]]:
    """
    latest_job_id_by_key: 파일별 최신 job id
    latest_success_id_by_key: 파일별 최신 정상 DONE job id
    """
    latest_job_id_by_key: dict[str, int] = {}
    latest_success_id_by_key: dict[str, int] = {}

    for data in rows:
        key = _ocr_history_key(data)

        if not key:
            continue

        try:
            job_id = int(data.get("id") or 0)
        except Exception:
            job_id = 0

        if job_id <= 0:
            continue

        if job_id > latest_job_id_by_key.get(key, 0):
            latest_job_id_by_key[key] = job_id

        if _is_successful_ocr_job(data) and job_id > latest_success_id_by_key.get(key, 0):
            latest_success_id_by_key[key] = job_id

    return latest_job_id_by_key, latest_success_id_by_key


def _is_stale_tesseract_history(
    data: dict[str, Any],
    latest_success_id_by_key: dict[str, int],
) -> bool:
    """
    과거 Tesseract 실패 이력 여부.
    같은 파일에 더 최신 정상 DONE job이 있으면 stale로 판단한다.
    """
    failure_status = _resolve_ocr_failure_status(data)

    if failure_status != "TESSERACT_ERROR":
        return False

    key = _ocr_history_key(data)

    if not key:
        return False

    try:
        job_id = int(data.get("id") or 0)
    except Exception:
        job_id = 0

    return latest_success_id_by_key.get(key, 0) > job_id


def get_ocr_failure_summary(
    limit: int = 300,
    keyword: str = "",
    include_test: bool = True,
    hide_stale_tesseract: bool = True,
    latest_only: bool = False,
) -> dict[str, Any]:
    """
    관리 > 데이터 추출 > OCR 오류 모니터링 패널용.
    현재 오류와 과거 Tesseract 실패 이력을 분리한다.
    """
    ensure_ocr_db()

    limit = max(1, min(int(limit), 1000))
    keyword = str(keyword or "").strip()

    where = []
    params: list[Any] = []

    if not include_test:
        where.append("""
            COALESCE(source_path, '') NOT LIKE '%ocr_test_uploads%'
            AND COALESCE(source_path, '') NOT LIKE '%data/ocr_test_uploads%'
        """)

    sql = """
        SELECT
            id,
            source_path,
            filename,
            file_ext,
            status,
            raw_text,
            result_json,
            error_message,
            created_at,
            updated_at,
            LENGTH(COALESCE(raw_text, '')) AS text_length
        FROM ocr_jobs
    """

    if where:
        sql += " WHERE " + " AND ".join(f"({x})" for x in where)

    sql += """
        ORDER BY id DESC
        LIMIT 5000
    """

    conn = get_ocr_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    hydrated_rows = [_hydrate_ocr_failure_row(row) for row in rows]
    latest_job_id_by_key, latest_success_id_by_key = _build_latest_maps(hydrated_rows)

    result_rows = []

    counts = {
        "TESSERACT_ERROR": 0,
        "STALE_TESSERACT_HISTORY": 0,
        "SCANNED_NEED_OCR": 0,
        "NO_TEXT": 0,
        "PDF_RENDER_ERROR": 0,
        "IMAGE_READ_ERROR": 0,
        "ERROR": 0,
        "DONE": 0,
        "OTHER": 0,
    }

    for data in hydrated_rows:
        key = _ocr_history_key(data)

        try:
            job_id = int(data.get("id") or 0)
        except Exception:
            job_id = 0

        if latest_only and key and latest_job_id_by_key.get(key) != job_id:
            continue

        if keyword:
            haystack = "\n".join([
                str(data.get("filename") or ""),
                str(data.get("source_path") or ""),
                str(data.get("error_message") or ""),
                str(data.get("raw_text") or "")[:2000],
                str(data.get("result_json") or "")[:2000],
            ]).lower()

            if keyword.lower() not in haystack:
                continue

        failure_status = _resolve_ocr_failure_status(data)
        is_stale_tesseract = _is_stale_tesseract_history(
            data,
            latest_success_id_by_key,
        )

        if is_stale_tesseract:
            bucket = "STALE_TESSERACT_HISTORY"
        elif failure_status in OCR_FAILURE_STATUSES:
            bucket = failure_status
        elif str(data.get("status") or "").upper() == "DONE":
            bucket = "DONE"
        else:
            bucket = "OTHER"

        counts[bucket] = counts.get(bucket, 0) + 1

        if is_stale_tesseract and hide_stale_tesseract:
            continue

        if bucket in OCR_FAILURE_STATUSES or bucket == "STALE_TESSERACT_HISTORY":
            rule = data.get("certificate_rule") or {}
            image = data.get("image_classification") or {}

            result_rows.append({
                "id": data.get("id"),
                "filename": data.get("filename") or "",
                "source_path": data.get("source_path") or "",
                "file_ext": data.get("file_ext") or "",
                "status": data.get("status") or "",
                "failure_status": bucket,
                "is_stale_tesseract": bool(is_stale_tesseract),
                "error_message": data.get("error_message") or "",
                "text_length": data.get("text_length") or len(data.get("raw_text") or ""),
                "raw_text_preview": (data.get("raw_text") or "")[:500],
                "created_at": data.get("created_at") or "",
                "updated_at": data.get("updated_at") or "",
                "cert_org": rule.get("cert_org") or "",
                "parse_status": rule.get("parse_status") or "",
                "image_final_org": image.get("final_org") or "",
                "image_decision": image.get("image_decision") or image.get("decision") or "",
                "tesseract_available": bool((data.get("result") or {}).get("tesseract_available")),
                "current_tesseract_available": TESSERACT_AVAILABLE,
                "current_tesseract_info": get_tesseract_runtime_info(),
            })

        if len(result_rows) >= limit:
            break

    active_failure_count = sum(
        counts.get(k, 0)
        for k in OCR_FAILURE_STATUSES
    )

    return {
        "ok": True,
        "limit": limit,
        "keyword": keyword,
        "include_test": include_test,
        "hide_stale_tesseract": hide_stale_tesseract,
        "latest_only": latest_only,
        "counts": counts,
        "failure_count": len(result_rows),
        "active_failure_count": active_failure_count,
        "stale_tesseract_count": counts.get("STALE_TESSERACT_HISTORY", 0),
        "rows": result_rows,
    }


def delete_stale_tesseract_ocr_jobs(
    include_test: bool = True,
) -> dict[str, Any]:
    """
    같은 source_path/filename에 더 최신 정상 DONE job이 존재하는
    과거 Tesseract 실패 OCR job만 삭제한다.
    """
    ensure_ocr_db()

    where = []
    params: list[Any] = []

    if not include_test:
        where.append("""
            COALESCE(source_path, '') NOT LIKE '%ocr_test_uploads%'
            AND COALESCE(source_path, '') NOT LIKE '%data/ocr_test_uploads%'
        """)

    sql = """
        SELECT
            id,
            source_path,
            filename,
            file_ext,
            status,
            raw_text,
            result_json,
            error_message,
            created_at,
            updated_at,
            LENGTH(COALESCE(raw_text, '')) AS text_length
        FROM ocr_jobs
    """

    if where:
        sql += " WHERE " + " AND ".join(f"({x})" for x in where)

    sql += " ORDER BY id DESC"

    conn = get_ocr_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    hydrated_rows = [_hydrate_ocr_failure_row(row) for row in rows]
    _, latest_success_id_by_key = _build_latest_maps(hydrated_rows)

    stale_ids = []

    for data in hydrated_rows:
        if _is_stale_tesseract_history(data, latest_success_id_by_key):
            try:
                stale_ids.append(int(data.get("id") or 0))
            except Exception:
                pass

    stale_ids = sorted({x for x in stale_ids if x > 0})

    if not stale_ids:
        return {
            "ok": True,
            "deleted": 0,
            "job_ids": [],
            "message": "삭제할 과거 Tesseract 오류 이력이 없습니다.",
        }

    return delete_ocr_jobs(stale_ids)

def delete_ocr_jobs(job_ids: list[int]) -> dict[str, Any]:
    ensure_ocr_db()

    ids = []
    for value in job_ids or []:
        try:
            ids.append(int(value))
        except Exception:
            pass

    ids = sorted(set(ids))

    if not ids:
        return {
            "ok": False,
            "deleted": 0,
            "message": "삭제할 OCR 작업 ID가 없습니다.",
        }

    placeholders = ",".join(["?"] * len(ids))

    conn = get_ocr_conn()
    cur = conn.cursor()

    cur.execute(
        f"DELETE FROM ocr_jobs WHERE id IN ({placeholders})",
        ids,
    )

    deleted = cur.rowcount
    conn.commit()
    conn.close()

    return {
        "ok": True,
        "deleted": deleted,
        "job_ids": ids,
    }