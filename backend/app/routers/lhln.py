from fastapi import APIRouter, Query

from app.services.lhln_service import (
    get_lhln_status,
    sync_lhln_reference,
    get_lhln_records,
    create_lhln_guide_pdf,
)

router = APIRouter()


@router.get("/status")
def lhln_status():
    """
    LHLN DB 상태, 기관 수, PDF 생성 여부 확인.
    """
    return get_lhln_status()


@router.post("/sync")
def lhln_sync():
    """
    BPJPH LHLN 교차인정기관 DB 동기화.
    """
    return sync_lhln_reference()


@router.get("/records")
def lhln_records(
    country: str = Query(""),
    keyword: str = Query(""),
    limit: int = Query(300, ge=1, le=1000),
):
    """
    LHLN 기관 목록 조회.
    """
    return get_lhln_records(
        country=country,
        keyword=keyword,
        limit=limit,
    )


@router.post("/create-pdf")
def lhln_create_pdf():
    """
    BPJPH 교차인정기관 안내 PDF 생성.
    """
    return create_lhln_guide_pdf()