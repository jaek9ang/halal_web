from __future__ import annotations

from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.mail_request_item_service import parse_mail_request_items
from app.services.certificate_filing_workflow_service import ensure_filing_tables
from app.services.filing_name_service import get_halal_raw_material_root
from app.services.pmf_filing_service import resolve_pmf_update_path


def main() -> None:
    sample_body = """
    <div><b>1. 글리신</b></div>
    <div>- 영문명: Glycine</div>
    <div>- 제조사: HEBEI HUAYANG BIOLOGICAL TECHNOLOGY CO.,LTD</div>
    <div>- 제조국: CHINA</div>
    <div>- 인증기관: BPJPH</div>
    <div>- 인증번호: ID00410011902561221</div>
    <div>- 현재 유효기간: 2026-02-17 / 유지 확인 시 적용 예정: 2027-02-17</div>
    """

    rows = parse_mail_request_items(
        sample_body,
        request_id="HALAL-REQ-TEST",
        supplier="테스트 공급사",
        mail_type="BPJPH 유지확인",
    )

    assert len(rows) == 1
    assert rows[0]["english_name"] == "Glycine"
    assert rows[0]["planned_expiry"] == "2027-02-17"

    ensure_filing_tables()

    print("mail parser: OK")
    print("filing table: OK")
    print("filing root:", get_halal_raw_material_root())
    print("pmf update path:", resolve_pmf_update_path())
    print("phase2 import verification passed")


if __name__ == "__main__":
    main()
