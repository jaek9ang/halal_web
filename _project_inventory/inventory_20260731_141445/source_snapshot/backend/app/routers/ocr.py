from pathlib import Path
from app.core.path_utils import to_backend_storage_path
from datetime import datetime
import re
import shutil
import zipfile
import json
from pydantic import BaseModel
from fastapi import APIRouter, Query, UploadFile, File
from fastapi.responses import FileResponse

from app.services.ocr_service import (
    list_certificate_files,
    create_ocr_job,
    get_ocr_job,
    list_ocr_jobs,
    delete_ocr_jobs,
    get_ocr_failure_summary,
    delete_stale_tesseract_ocr_jobs,
)

from app.services.ocr_test_service import (
    list_ocr_test_files,
    save_ocr_test_uploads,
    run_ocr_test_file,
)

from app.services.ocr_exporter import create_ocr_data_export_zip

router = APIRouter()

LATEST_AI_EXPORT_DIR = Path(__file__).resolve().parents[2] / "data" / "ocr_exports"
LATEST_AI_EXPORT_JSONL_PATH = LATEST_AI_EXPORT_DIR / "export.jsonl"
LATEST_AI_EXPORT_SUMMARY_PATH = LATEST_AI_EXPORT_DIR / "summary.csv"
LATEST_AI_EXPORT_TEXT_PATH = LATEST_AI_EXPORT_DIR / "combined_ocr_text.md"
LATEST_AI_EXPORT_META_PATH = LATEST_AI_EXPORT_DIR / "export_meta.json"


def save_latest_ai_rule_export_from_zip(zip_path: Path) -> dict:
    """
    OCR 데이터 ZIP 안의 export.jsonl / summary.csv / combined_ocr_text.md를
    AI 규칙 리뷰용 최신 파일 위치에 저장한다.
    """
    zip_path = Path(zip_path)

    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP 파일을 찾을 수 없습니다: {zip_path}")

    LATEST_AI_EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    saved_files = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())

        if "export.jsonl" not in names:
            raise FileNotFoundError("ZIP 내부에서 export.jsonl을 찾지 못했습니다.")

        with zf.open("export.jsonl") as src, LATEST_AI_EXPORT_JSONL_PATH.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        saved_files.append(str(LATEST_AI_EXPORT_JSONL_PATH))

        if "summary.csv" in names:
            with zf.open("summary.csv") as src, LATEST_AI_EXPORT_SUMMARY_PATH.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            saved_files.append(str(LATEST_AI_EXPORT_SUMMARY_PATH))

        if "combined_ocr_text.md" in names:
            with zf.open("combined_ocr_text.md") as src, LATEST_AI_EXPORT_TEXT_PATH.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            saved_files.append(str(LATEST_AI_EXPORT_TEXT_PATH))

    meta = {
        "ok": True,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "source_zip": str(zip_path),
        "latest_export_jsonl_path": str(LATEST_AI_EXPORT_JSONL_PATH),
        "latest_summary_path": str(LATEST_AI_EXPORT_SUMMARY_PATH),
        "latest_text_path": str(LATEST_AI_EXPORT_TEXT_PATH),
        "saved_files": saved_files,
    }

    LATEST_AI_EXPORT_META_PATH.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return meta


def resolve_ocr_export_result(result) -> tuple[Path, int, str]:
    """
    create_ocr_data_export_zip() 반환값이 dict/object 중 무엇이든
    zip_path / record_count / export_version을 안정적으로 꺼낸다.
    """
    if isinstance(result, dict):
        zip_value = (
            result.get("zip_path")
            or result.get("path")
            or result.get("file_path")
            or result.get("output_path")
        )
        record_count = (
            result.get("record_count")
            or result.get("recordCount")
            or result.get("count")
            or 0
        )
        export_version = result.get("export_version") or "ocr_rule_review_v1"
    else:
        zip_value = getattr(result, "zip_path", None) or getattr(result, "path", None)
        record_count = getattr(result, "record_count", 0)
        export_version = getattr(result, "export_version", "ocr_rule_review_v1")

    if not zip_value:
        raise RuntimeError(
            "create_ocr_data_export_zip() 반환값에서 zip_path/path/file_path를 찾지 못했습니다."
        )

    return Path(zip_value), int(record_count or 0), str(export_version or "ocr_rule_review_v1")

class OcrJobCreateRequest(BaseModel):
    source_path: str
    ocr_scanned_pages: bool = True
    lang: str = "eng"

class OcrTestRunRequest(BaseModel):
    ocr_scanned_pages: bool = True
    lang: str = "eng"
    skip_done: bool = True

class OcrJobDeleteRequest(BaseModel):
    job_ids: list[int]

@router.get("/data-export")
def download_ocr_data_export(
    limit: int = Query(10000, ge=1, le=50000),
    include_ocr_jobs: bool = True,
    include_ocr_tests: bool = True,
    save_latest_for_ai: bool = False,
):
    """
    관리 > 데이터 추출 > OCR 데이터 추출.
    OCR 작업이력과 OCR 테스트 결과를 export.jsonl / summary.csv / combined_ocr_text.md로 묶어 ZIP 생성.
    save_latest_for_ai=True이면 backend/data/ocr_exports/export.jsonl에도 최신본을 저장한다.
    """
    result = create_ocr_data_export_zip(
        limit=limit,
        include_ocr_jobs=include_ocr_jobs,
        include_ocr_tests=include_ocr_tests,
    )

    zip_path, record_count, export_version = resolve_ocr_export_result(result)

    if not zip_path.exists():
        raise FileNotFoundError(f"생성된 OCR export ZIP 파일을 찾지 못했습니다: {zip_path}")

    latest_ai_export_meta = None

    if save_latest_for_ai:
        latest_ai_export_meta = save_latest_ai_rule_export_from_zip(zip_path)

    headers = {
        "X-Export-Version": export_version,
        "X-Export-Record-Count": str(record_count),
        "X-Saved-Latest-For-AI": "true" if save_latest_for_ai else "false",
    }

    if latest_ai_export_meta:
        headers["X-Latest-Export-Path"] = latest_ai_export_meta.get(
            "latest_export_jsonl_path",
            "",
        )

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=zip_path.name,
        headers=headers,
    )

@router.get("/files")
def ocr_files(limit: int = Query(300, ge=1, le=1000)):
    """
    수신메일 첨부 다운로드 폴더에서 인증서 후보 파일 목록 조회.
    """
    return list_certificate_files(limit=limit)


@router.post("/jobs")
def create_job(payload: OcrJobCreateRequest):
    """
    인증서 파일 OCR 작업 실행.
    현재는 동기 처리 방식.
    """
    return create_ocr_job(
        source_path=payload.source_path,
        ocr_scanned_pages=payload.ocr_scanned_pages,
        lang=payload.lang,
    )


@router.get("/jobs")
def ocr_jobs(
    limit: int = Query(100, ge=1, le=500),
    status: str = "",
    org: str = "",
    keyword: str = "",
    include_test: bool = False,
):
    """
    OCR 작업 이력 목록.
    기본값은 OCR 테스트 파일 제외.
    """
    return list_ocr_jobs(
        limit=limit,
        status=status,
        org=org,
        keyword=keyword,
        include_test=include_test,
    )

@router.delete("/jobs")
def delete_jobs(payload: OcrJobDeleteRequest):
    """
    OCR 작업 이력 선택 삭제.
    파일 원본은 삭제하지 않고 OCR job DB 이력만 삭제한다.
    """
    return delete_ocr_jobs(payload.job_ids)

@router.get("/failure-summary")
def ocr_failure_summary(
    limit: int = Query(300, ge=1, le=1000),
    keyword: str = "",
    include_test: bool = True,
    hide_stale_tesseract: bool = True,
    latest_only: bool = False,
):
    """
    OCR 오류 모니터링.
    현재 오류와 과거 Tesseract 실패 이력을 분리해서 반환한다.
    """
    return get_ocr_failure_summary(
        limit=limit,
        keyword=keyword,
        include_test=include_test,
        hide_stale_tesseract=hide_stale_tesseract,
        latest_only=latest_only,
    )


@router.delete("/failure-summary/stale-tesseract")
def delete_stale_tesseract_history(
    include_test: bool = True,
):
    """
    같은 파일에 더 최신 정상 DONE job이 있는 과거 Tesseract 오류 이력만 삭제한다.
    """
    return delete_stale_tesseract_ocr_jobs(
        include_test=include_test,
    )

@router.get("/jobs/{job_id}")
def ocr_job_detail(job_id: int):
    """
    OCR 작업 상세.
    """
    return get_ocr_job(job_id)

@router.post("/manual-upload")
async def upload_ocr_manual_files(files: list[UploadFile] = File(...)):
    """
    인증서 판독 메뉴용 수동 파일 업로드.
    저장 위치: backend/data/ocr_manual_uploads/YYYYMMDD_HHMMSS/
    반환 saved_path는 /ocr/jobs source_path로 바로 사용한다.
    OCR 테스트 메뉴 이력에는 들어가지 않는다.
    """
    backend_dir = Path(__file__).resolve().parents[2]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_dir = backend_dir / "data" / "ocr_manual_uploads" / stamp
    target_dir.mkdir(parents=True, exist_ok=True)

    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
    rows = []

    for idx, file in enumerate(files, start=1):
        original = file.filename or f"manual_upload_{idx}"
        safe_name = re.sub(r'[\\/:*?"<>|]+', "_", original).strip() or f"manual_upload_{idx}"
        ext = Path(safe_name).suffix.lower()

        if ext not in allowed:
            rows.append({
                "ok": False,
                "original_filename": original,
                "message": f"지원하지 않는 확장자입니다: {ext}",
            })
            continue

        save_path = target_dir / safe_name

        with save_path.open("wb") as out:
            shutil.copyfileobj(file.file, out)

        rel_path = to_backend_storage_path(save_path)

        rows.append({
            "ok": True,
            "original_filename": original,
            "saved_filename": safe_name,
            "saved_path": rel_path,
            "size_bytes": save_path.stat().st_size,
        })

    return {
        "ok": True,
        "rows": rows,
        "count": len(rows),
    }

@router.post("/test-upload")
async def upload_ocr_test_files(files: list[UploadFile] = File(...)):
    """
    OCR 테스트 메뉴용 임시 업로드 + DB 저장.
    동일 파일 hash가 있으면 기존 결과를 재사용한다.
    """
    return save_ocr_test_uploads(files)

@router.get("/test-files")
def ocr_test_files(limit: int = Query(300, ge=1, le=500)):
    """
    OCR 테스트 파일 목록.
    메뉴를 이동해도 이 목록으로 복원한다.
    """
    return list_ocr_test_files(limit=limit)


@router.post("/test-files/{file_id}/run")
def run_one_ocr_test_file(file_id: int, payload: OcrTestRunRequest):
    """
    OCR 테스트 파일 1건 실행.
    hash 기준으로 이미 DONE인 파일은 skip_done=True일 때 재사용한다.
    """
    return run_ocr_test_file(
        file_id=file_id,
        ocr_scanned_pages=payload.ocr_scanned_pages,
        lang=payload.lang,
        skip_done=payload.skip_done,
    )
