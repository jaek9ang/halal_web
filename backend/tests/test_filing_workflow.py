"""인증서 자동분류 확정 흐름 테스트.

원본은 `tests/legacy/`의 print 기반 스크립트였다. 단언은 그대로 옮기고
전역 monkeypatch를 pytest 픽스처로 바꿔 테스트 간 오염을 막았다.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import certificate_filing_workflow_service as workflow


# --------------------------------------------------------------------------
# 변경 판정 게이트 — 외부 의존 없는 순수 로직
# --------------------------------------------------------------------------

RENEWAL_PREVIEW = {
    "change_decision": {
        "decision_code": "SAME_AUTHORITY_RENEWAL",
        "requires_review": False,
        "blocked": False,
        "auto_action": "UPDATE_CURRENT",
        "review_options": [],
    }
}

AUTHORITY_CHANGE_PREVIEW = {
    "change_decision": {
        "decision_code": "AUTHORITY_CHANGE_REVIEW",
        "requires_review": True,
        "blocked": False,
        "auto_action": "REVIEW",
        "review_options": [
            "REPLACE_CURRENT",
            "ADD_SECONDARY",
            "HOLD",
            "REJECT",
        ],
    }
}


def test_same_authority_renewal_resolves_to_update_current():
    result = workflow.validate_change_decision_for_confirm(RENEWAL_PREVIEW)

    assert result["change_action"] == "UPDATE_CURRENT"


@pytest.mark.parametrize("action", ["ADD_SECONDARY", "REPLACE_CURRENT"])
def test_authority_change_accepts_reviewed_action(action: str):
    result = workflow.validate_change_decision_for_confirm(
        AUTHORITY_CHANGE_PREVIEW,
        action,
    )

    assert result["change_action"] == action


def test_automatic_decision_cannot_be_overridden():
    """사람이 자동 판정을 임의로 뒤집지 못하게 막는다."""
    with pytest.raises(ValueError):
        workflow.validate_change_decision_for_confirm(
            RENEWAL_PREVIEW,
            "ADD_SECONDARY",
        )


def test_hold_is_not_a_confirmation():
    with pytest.raises(ValueError):
        workflow.validate_change_decision_for_confirm(
            AUTHORITY_CHANGE_PREVIEW,
            "HOLD",
        )


# --------------------------------------------------------------------------
# 확정 실패 시 롤백
# --------------------------------------------------------------------------

ROLLBACK_PREVIEW = {
    "hard_blockers": [],
    "blockers": [],
    "warnings": [],
    "change_decision": {
        "decision_code": "AUTHORITY_CHANGE_REVIEW",
        "requires_review": True,
        "blocked": False,
        "auto_action": "REVIEW",
        "review_options": ["REPLACE_CURRENT"],
    },
    "pmf_material": {
        "material_no": "62",
        "english_name": "NAT SHALLOT FLAVOR(962539)",
        "maker": "Symrise Asia Pasific Pte Ltd",
        "supplier": "TEST SUPPLIER",
        "org": "MUIS",
        "cert_no": "PRN22020011873",
        "expiry_date": "2026-05-31",
    },
    "certificate": {
        "cert_org": "HCA",
        "cert_no": "HCA-ROLLBACK-2029",
        "expiry_date": "2029-12-31",
        "manufacturer": "SYMRISE ASIA PACIFIC PTE LTD",
    },
    "request_context": {
        "request_id": "ROLLBACK-TEST",
        "matched_mail_item": {},
    },
}


@pytest.fixture
def rollback_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """이력 기록이 실패하도록 배선한 확정 흐름.

    복사된 인증서 파일과 PMF 백업이 되돌려지는지 보는 것이 목적이다.
    """
    source_file = tmp_path / "source.pdf"
    target_file = tmp_path / "target.pdf"
    backup_file = tmp_path / "backup.xlsm"
    pmf_file = tmp_path / "pmf.xlsm"

    for path, data in (
        (source_file, b"source"),
        (target_file, b"copied"),
        (backup_file, b"backup"),
        (pmf_file, b"updated"),
    ):
        path.write_bytes(data)

    copy_result = SimpleNamespace(
        status="COPIED",
        target_path=str(target_file),
        to_dict=lambda: {
            "status": "COPIED",
            "target_path": str(target_file),
        },
    )

    pmf_result = SimpleNamespace(
        backup_path=str(backup_file),
        pmf_path=str(pmf_file),
        to_dict=lambda: {
            "backup_path": str(backup_file),
            "pmf_path": str(pmf_file),
        },
    )

    calls = {
        "insert": 0,
        "rollback_history": 0,
        "restore_pmf": 0,
        "error_history": 0,
    }

    monkeypatch.setattr(workflow, "preview_filing_workflow", lambda **kw: ROLLBACK_PREVIEW)
    monkeypatch.setattr(
        workflow,
        "get_ocr_job",
        lambda job_id: {"source_path": str(source_file), "file_ext": ".pdf"},
    )
    monkeypatch.setattr(workflow, "copy_certificate_atomically", lambda **kw: copy_result)
    monkeypatch.setattr(workflow, "update_pmf_certificate_fields", lambda **kw: pmf_result)
    monkeypatch.setattr(workflow, "get_active_material_certificates", lambda **kw: [])
    monkeypatch.setattr(workflow, "insert_material_certificate_history", lambda payload: 1)
    monkeypatch.setattr(workflow, "get_halal_raw_material_root", lambda: tmp_path)
    monkeypatch.setattr(
        workflow,
        "apply_material_certificate_history_action",
        lambda payload, action: {
            "ok": True,
            "changed": True,
            "action": action,
            "inserted_id": 2,
            "previous_primary_id": 1,
            "previous_primary_status": "ACTIVE",
        },
    )

    def fake_rollback_history(result):
        calls["rollback_history"] += 1

    def fake_restore_pmf(backup_path, target_path):
        calls["restore_pmf"] += 1

    def fake_insert_history(payload):
        calls["insert"] += 1

        if calls["insert"] == 1:
            raise RuntimeError("FORCED_HISTORY_FAILURE")

        assert payload["status"] == "ERROR"
        assert "FORCED_HISTORY_FAILURE" in payload["error_message"]

        calls["error_history"] += 1
        return 999

    monkeypatch.setattr(
        workflow,
        "rollback_material_certificate_history_action",
        fake_rollback_history,
    )
    monkeypatch.setattr(workflow, "restore_pmf_backup", fake_restore_pmf)
    monkeypatch.setattr(workflow, "_insert_history", fake_insert_history)

    return SimpleNamespace(calls=calls, target_file=target_file)


def test_history_failure_rolls_everything_back(rollback_env):
    with pytest.raises(RuntimeError, match="FORCED_HISTORY_FAILURE"):
        workflow.confirm_filing_workflow(
            ocr_job_id=521,
            pmf_row_pos=90,
            pmf_depth=0,
            overwrite=False,
            force=False,
            allow_date_regression=False,
            change_action="REPLACE_CURRENT",
        )

    calls = rollback_env.calls

    assert calls["rollback_history"] == 1, "이력 액션이 되돌려지지 않았다"
    assert calls["restore_pmf"] == 1, "PMF 백업이 복원되지 않았다"
    assert calls["error_history"] == 1, "ERROR 이력이 남지 않았다"
    assert not rollback_env.target_file.exists(), "복사된 인증서 파일이 남아 있다"
