from pathlib import Path
from types import SimpleNamespace
import tempfile

from app.services import (
    certificate_filing_workflow_service
    as workflow,
)


tmp = Path(
    tempfile.mkdtemp(
        prefix="rollback_flow_"
    )
)

source_file = tmp / "source.pdf"
target_file = tmp / "target.pdf"
backup_file = tmp / "backup.xlsm"
pmf_file = tmp / "pmf.xlsm"

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


preview = {
    "hard_blockers": [],
    "blockers": [],
    "warnings": [],
    "change_decision": {
        "decision_code": (
            "AUTHORITY_CHANGE_REVIEW"
        ),
        "requires_review": True,
        "blocked": False,
        "auto_action": "REVIEW",
        "review_options": [
            "REPLACE_CURRENT"
        ],
    },
    "pmf_material": {
        "material_no": "62",
        "english_name": (
            "NAT SHALLOT FLAVOR(962539)"
        ),
        "maker": (
            "Symrise Asia Pasific Pte Ltd"
        ),
        "supplier": "TEST SUPPLIER",
        "org": "MUIS",
        "cert_no": "PRN22020011873",
        "expiry_date": "2026-05-31",
    },
    "certificate": {
        "cert_org": "HCA",
        "cert_no": "HCA-ROLLBACK-2029",
        "expiry_date": "2029-12-31",
        "manufacturer": (
            "SYMRISE ASIA PACIFIC PTE LTD"
        ),
    },
    "request_context": {
        "request_id": "ROLLBACK-TEST",
        "matched_mail_item": {},
    },
}


state = {
    "insert_count": 0,
    "rollback_history": 0,
    "restore_pmf": 0,
    "error_history": 0,
}


workflow.preview_filing_workflow = (
    lambda **kwargs: preview
)

workflow.get_ocr_job = (
    lambda job_id: {
        "source_path": str(source_file),
        "file_ext": ".pdf",
    }
)

workflow.copy_certificate_atomically = (
    lambda **kwargs: copy_result
)

workflow.update_pmf_certificate_fields = (
    lambda **kwargs: pmf_result
)

workflow.get_active_material_certificates = (
    lambda **kwargs: []
)

workflow.insert_material_certificate_history = (
    lambda payload: 1
)

workflow.apply_material_certificate_history_action = (
    lambda payload, action: {
        "ok": True,
        "changed": True,
        "action": action,
        "inserted_id": 2,
        "previous_primary_id": 1,
        "previous_primary_status": "ACTIVE",
    }
)

workflow.get_halal_raw_material_root = (
    lambda: tmp
)


def fake_rollback_history(result):
    state["rollback_history"] += 1


def fake_restore_pmf(
    backup_path,
    target_path,
):
    state["restore_pmf"] += 1


def fake_insert_history(payload):
    state["insert_count"] += 1

    if state["insert_count"] == 1:
        raise RuntimeError(
            "FORCED_HISTORY_FAILURE"
        )

    assert payload["status"] == "ERROR"

    assert (
        "FORCED_HISTORY_FAILURE"
        in payload["error_message"]
    )

    state["error_history"] += 1
    return 999


workflow.rollback_material_certificate_history_action = (
    fake_rollback_history
)

workflow.restore_pmf_backup = (
    fake_restore_pmf
)

workflow._insert_history = (
    fake_insert_history
)


caught = ""

try:
    workflow.confirm_filing_workflow(
        ocr_job_id=521,
        pmf_row_pos=90,
        pmf_depth=0,
        overwrite=False,
        force=False,
        allow_date_regression=False,
        change_action="REPLACE_CURRENT",
    )

except RuntimeError as exc:
    caught = str(exc)


assert caught == "FORCED_HISTORY_FAILURE"

assert state["rollback_history"] == 1
assert state["restore_pmf"] == 1
assert state["error_history"] == 1

assert not target_file.exists()


print("CAUGHT:", caught)

print(
    "ROLLBACK_HISTORY_CALLS:",
    state["rollback_history"],
)

print(
    "RESTORE_PMF_CALLS:",
    state["restore_pmf"],
)

print(
    "ERROR_HISTORY_CALLS:",
    state["error_history"],
)

print(
    "TARGET_FILE_EXISTS:",
    target_file.exists(),
)

print("ROLLBACK_FLOW_TEST_OK")
