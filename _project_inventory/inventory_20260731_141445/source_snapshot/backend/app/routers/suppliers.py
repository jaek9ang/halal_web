from pydantic import BaseModel
from fastapi import APIRouter

from app.services.supplier_service import (
    get_supplier_email_review,
    load_supplier_email_overrides,
    upsert_supplier_email_override,
)

router = APIRouter()


class SupplierEmailOverrideIn(BaseModel):
    supplier_name: str
    supplier_key: str = ""
    final_to: str
    final_cc: str = ""
    memo: str = ""


@router.get("/email-review")
def supplier_email_review():
    """
    Raw PMF + E-mail 시트 + 수동확정 DB를 합친 메일주소 정리 데이터.
    """
    return get_supplier_email_review()


@router.get("/email-overrides")
def supplier_email_overrides():
    """
    사용자가 확정 저장한 업체별 최종 TO/CC 목록.
    """
    return {
        "rows": list(load_supplier_email_overrides().values())
    }


@router.post("/email-overrides")
def save_supplier_email_override(payload: SupplierEmailOverrideIn):
    """
    업체별 최종 TO/CC 수동 확정 저장.
    """
    return upsert_supplier_email_override(
        supplier_name=payload.supplier_name,
        supplier_key=payload.supplier_key,
        final_to=payload.final_to,
        final_cc=payload.final_cc,
        memo=payload.memo,
    )