"""메일 라우터의 요청 모델 검증.

패치 스크립트가 같은 클래스를 여러 번 붙여넣어, 나중 정의(필드가 더 적은 쪽)가
앞의 정의를 덮어쓰는 일이 있었다. 핸들러는 앞 정의의 필드를 참조하고 있어서
해당 엔드포인트가 호출되는 순간 AttributeError로 죽었다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.mail import SaveOcrCandidateRequest


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_save_ocr_candidate_model_has_every_field_the_handler_reads():
    """핸들러가 읽는 필드가 모델에 전부 있어야 한다."""
    required = {
        "attachment_id",
        "ocr_job_id",
        "status",
        "filename",
        "best_expiry",
        "expiry_candidates",
        "filename_candidates",
        "mail_candidates",
        "ocr_candidates",
        "message",
    }

    missing = required - set(SaveOcrCandidateRequest.model_fields)

    assert not missing, f"모델에 없는 필드를 핸들러가 읽는다: {sorted(missing)}"


def test_save_ocr_candidate_endpoint_does_not_crash_on_missing_attribute(
    client: TestClient,
):
    """존재하지 않는 첨부 ID라도 AttributeError로 죽지는 않아야 한다."""
    response = client.post(
        "/mail/inbox/ocr-results/save-candidate",
        json={
            "attachment_id": -1,
            "status": "DONE",
            "filename": "sample.pdf",
            "best_expiry": "2027-01-01",
            "expiry_candidates": [],
            "filename_candidates": [],
            "mail_candidates": [],
            "ocr_candidates": [],
            "message": "",
        },
    )

    assert response.status_code < 500, response.text
