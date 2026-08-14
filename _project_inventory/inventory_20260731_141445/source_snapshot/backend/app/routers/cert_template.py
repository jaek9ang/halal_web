# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.cert_template_service import (
    classify_file_path,
    classify_folder,
    classify_paths,
    get_candidates,
    get_preview_image_path,
    get_review_items,
    get_template_status,
    get_org_decisions,
    clear_org_decision,
    clear_org_decisions_bulk,
    import_template_folder,
    init_cert_template_db,
    save_org_decision,
    save_org_decisions_bulk,
)

router = APIRouter(prefix="/cert-template", tags=["cert-template"])

class TemplateImportRequest(BaseModel):
    root_dir: str = Field(..., description="기관별 인증서 샘플 폴더들이 들어있는 루트 경로")
    rebuild: bool = False
    max_pages: int = Field(1, ge=1, le=3)

class TemplateTestFolderRequest(BaseModel):
    folder_path: str
    enhanced_retry: bool = True

class TemplateClassifyPathRequest(BaseModel):
    file_path: str
    enhanced_retry: bool = True
    max_pages: int = Field(1, ge=1, le=3)

class TemplateClassifyPathsRequest(BaseModel):
    file_paths: List[str]
    enhanced_retry: bool = True

class TemplateDecisionRequest(BaseModel):
    file_hash: str
    final_org: str = ""
    predicted_org: str = ""
    decision_type: str = "MANUAL_CONFIRMED"
    decision_score: float = 1.0
    image_score: float = 0.0
    margin: float = 0.0
    original_decision: str = ""
    original_filename: str = ""
    file_path: str = ""
    memo: str = ""
    decision_reason: str = ""
    confirmed_by: str = "admin"

class TemplateDecisionBulkRequest(BaseModel):
    items: List[TemplateDecisionRequest]
    confirmed_by: str = "admin"

class TemplateDecisionClearRequest(BaseModel):
    file_hash: str
    confirmed_by: str = "admin"

class TemplateDecisionClearBulkRequest(BaseModel):
    file_hashes: List[str]
    confirmed_by: str = "admin"

@router.on_event("startup")
def startup_init_template_db():
    init_cert_template_db()

@router.get("/status")
def status():
    return get_template_status()

@router.post("/import")
def import_templates(payload: TemplateImportRequest):
    try:
        return import_template_folder(payload.root_dir, rebuild=payload.rebuild, max_pages=payload.max_pages)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/test-folder")
def test_folder(payload: TemplateTestFolderRequest):
    try:
        return classify_folder(payload.folder_path, enhanced_retry=payload.enhanced_retry)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/classify-path")
def classify_path(payload: TemplateClassifyPathRequest):
    try:
        return classify_file_path(payload.file_path, enhanced_retry=payload.enhanced_retry, max_pages=payload.max_pages)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/classify-paths")
def classify_many_paths(payload: TemplateClassifyPathsRequest):
    try:
        return {"ok": True, "rows": classify_paths(payload.file_paths, enhanced_retry=payload.enhanced_retry)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/review")
def review(limit: int = Query(100, ge=1, le=500)):
    return get_review_items(limit=limit)

@router.get("/candidates/{file_hash}")
def candidates(file_hash: str):
    return get_candidates(file_hash)

@router.get("/decisions")
def decisions(include_excluded: bool = Query(True), limit: int = Query(500, ge=1, le=5000)):
    return get_org_decisions(include_excluded=include_excluded, limit=limit)

@router.post("/decision")
def decision(payload: TemplateDecisionRequest):
    try:
        return save_org_decision(
            file_hash=payload.file_hash,
            predicted_org=payload.predicted_org,
            final_org=payload.final_org or payload.predicted_org,
            decision_type=payload.decision_type,
            decision_score=payload.decision_score,
            decision_reason=payload.decision_reason,
            confirmed_by=payload.confirmed_by,
            original_decision=payload.original_decision,
            original_filename=payload.original_filename,
            file_path=payload.file_path,
            image_score=payload.image_score,
            margin=payload.margin,
            memo=payload.memo,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/decisions/bulk")
def decisions_bulk(payload: TemplateDecisionBulkRequest):
    try:
        return save_org_decisions_bulk(
            [item.model_dump() for item in payload.items],
            confirmed_by=payload.confirmed_by,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/decision/clear")
def decision_clear(payload: TemplateDecisionClearRequest):
    try:
        return clear_org_decision(
            file_hash=payload.file_hash,
            confirmed_by=payload.confirmed_by,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/decisions/clear")
def decisions_clear(payload: TemplateDecisionClearBulkRequest):
    try:
        return clear_org_decisions_bulk(
            file_hashes=payload.file_hashes,
            confirmed_by=payload.confirmed_by,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/preview/{file_hash}")
def preview(file_hash: str):
    path = get_preview_image_path(file_hash)
    if not path:
        raise HTTPException(status_code=404, detail="미리보기 이미지가 없습니다.")
    return FileResponse(path=str(path), media_type="image/jpeg", filename=path.name)
