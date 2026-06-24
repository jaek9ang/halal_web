from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.ai_rule_review_service import analyze_export_with_ai, extract_problem_cases, get_ai_rule_review_status
from app.services.rule_apply_service import apply_rule_candidate, reject_rule_candidate
from app.services.rule_candidate_service import get_rule_candidate, get_rule_overrides, list_approved_rule_history, list_rule_candidates
from app.services.rule_validation_service import get_validation_report, list_validation_reports, validate_rule_candidate

router = APIRouter()


class AnalyzeExportRequest(BaseModel):
    export_path: Optional[str] = None
    limit: int = 10000
    max_cases: int = 20
    model: Optional[str] = None
    save_candidates: bool = True


class ValidateCandidateRequest(BaseModel):
    export_path: Optional[str] = None
    limit: int = 10000


class ApplyCandidateRequest(BaseModel):
    validation_report_id: Optional[str] = ""
    actor: str = "user"


class RejectCandidateRequest(BaseModel):
    reason: str = ""
    actor: str = "user"


@router.get("/status")
def ai_rule_review_status():
    return get_ai_rule_review_status()


@router.post("/analyze-export")
def analyze_export(payload: AnalyzeExportRequest):
    try:
        return analyze_export_with_ai(
            export_path=payload.export_path,
            limit=payload.limit,
            max_cases=payload.max_cases,
            model=payload.model,
            save_candidates=payload.save_candidates,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/problem-cases")
def problem_cases(
    export_path: str = "",
    limit: int = Query(10000, ge=1, le=100000),
    max_cases: int = Query(20, ge=1, le=100),
):
    try:
        rows = extract_problem_cases(export_path=export_path or None, limit=limit, max_cases=max_cases)
        return {"ok": True, "rows": rows, "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/candidates")
def candidates(
    limit: int = Query(100, ge=1, le=500),
    apply_status: str = "",
    target_org: str = "",
    target_field: str = "",
):
    return list_rule_candidates(limit=limit, apply_status=apply_status, target_org=target_org, target_field=target_field)


@router.get("/candidates/{rule_candidate_id}")
def candidate_detail(rule_candidate_id: str):
    candidate = get_rule_candidate(rule_candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="rule_candidate_id를 찾을 수 없습니다.")
    return {"ok": True, "candidate": candidate}


@router.post("/candidates/{rule_candidate_id}/validate")
def validate_candidate(rule_candidate_id: str, payload: ValidateCandidateRequest):
    try:
        return validate_rule_candidate(rule_candidate_id=rule_candidate_id, export_path=payload.export_path, limit=payload.limit, save_report=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/candidates/{rule_candidate_id}/apply")
def apply_candidate(rule_candidate_id: str, payload: ApplyCandidateRequest):
    try:
        return apply_rule_candidate(rule_candidate_id=rule_candidate_id, validation_report_id=payload.validation_report_id or "", actor=payload.actor or "user")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/candidates/{rule_candidate_id}/reject")
def reject_candidate(rule_candidate_id: str, payload: RejectCandidateRequest):
    try:
        return reject_rule_candidate(rule_candidate_id=rule_candidate_id, reason=payload.reason, actor=payload.actor or "user")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/reports")
def validation_reports(limit: int = Query(100, ge=1, le=500)):
    return list_validation_reports(limit=limit)


@router.get("/reports/{validation_report_id}")
def validation_report_detail(validation_report_id: str):
    try:
        return get_validation_report(validation_report_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/history")
def approved_history(limit: int = Query(200, ge=1, le=1000)):
    return list_approved_rule_history(limit=limit)


@router.get("/overrides")
def rule_overrides():
    return {"ok": True, "overrides": get_rule_overrides()}
