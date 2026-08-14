from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import shutil
import sqlite3
import sys


OCR_JOB_ID = 521
PMF_ROW_POS = 90
PMF_DEPTH = 0

PROJECT_ROOT = Path.cwd()
BACKEND_ROOT = PROJECT_ROOT / "backend"

SOURCE_PMF = Path(
    "D:/halal_web_runtime/pmf_test/active_pmf_test.xlsm"
)

TEST_ROOT = (
    PROJECT_ROOT
    / ".tmp_confirm_integration_test"
)

TEST_PMF = (
    TEST_ROOT
    / "active_pmf_test_copy.xlsm"
)

TEST_FILING_ROOT = (
    TEST_ROOT
    / "raw_material"
)

TEST_DB = (
    TEST_ROOT
    / "pmf_app_test.db"
)


if not BACKEND_ROOT.exists():
    raise FileNotFoundError(
        f"Backend directory not found: {BACKEND_ROOT}"
    )

if not SOURCE_PMF.exists():
    raise FileNotFoundError(
        f"Source PMF not found: {SOURCE_PMF}"
    )


if TEST_ROOT.exists():
    shutil.rmtree(TEST_ROOT)

TEST_FILING_ROOT.mkdir(
    parents=True,
    exist_ok=True,
)

shutil.copy2(
    SOURCE_PMF,
    TEST_PMF,
)

sys.path.insert(
    0,
    str(BACKEND_ROOT.resolve()),
)


from app.services import certificate_filing_service
from app.services import certificate_filing_workflow_service as workflow
from app.services import filing_name_service
from app.services import pmf_filing_service


def test_get_conn():
    conn = sqlite3.connect(
        TEST_DB
    )
    conn.row_factory = sqlite3.Row
    return conn


def test_root():
    return TEST_FILING_ROOT


def test_pmf_path():
    return TEST_PMF


workflow.get_conn = test_get_conn
workflow.get_halal_raw_material_root = test_root

if hasattr(
    certificate_filing_service,
    "get_halal_raw_material_root",
):
    certificate_filing_service.get_halal_raw_material_root = (
        test_root
    )

if hasattr(
    filing_name_service,
    "get_halal_raw_material_root",
):
    filing_name_service.get_halal_raw_material_root = (
        test_root
    )

for module in (
    workflow,
    pmf_filing_service,
):
    if hasattr(
        module,
        "resolve_pmf_update_path",
    ):
        module.resolve_pmf_update_path = test_pmf_path


original_preview = (
    workflow.preview_filing_workflow
)


def standalone_preview(
    ocr_job_id: int,
    pmf_row_pos: int,
    pmf_depth: int = 0,
):
    result = original_preview(
        ocr_job_id=ocr_job_id,
        pmf_row_pos=pmf_row_pos,
        pmf_depth=pmf_depth,
    )

    result = deepcopy(result)

    decision = (
        result.get("change_decision")
        or {}
    )

    if (
        decision.get("decision_code")
        != "SAME_AUTHORITY_RENEWAL"
    ):
        raise AssertionError(
            "Unexpected change decision: "
            + json.dumps(
                decision,
                ensure_ascii=False,
                default=str,
            )
        )

    request_context = (
        result.get("request_context")
        or {}
    )

    if request_context.get("request_id"):
        raise AssertionError(
            "This test is intended for a standalone OCR job."
        )

    # Job 521 has no mail/request link. Only that standalone
    # linkage gate is bypassed here. Other blockers remain and
    # are handled by force=True.
    result["hard_blockers"] = []

    return result


workflow.preview_filing_workflow = (
    standalone_preview
)


result = workflow.confirm_filing_workflow(
    ocr_job_id=OCR_JOB_ID,
    pmf_row_pos=PMF_ROW_POS,
    pmf_depth=PMF_DEPTH,
    overwrite=False,
    force=True,
    allow_date_regression=False,
    change_action="",
)


assert result.get("ok") is True
assert (
    result.get("change_gate", {})
    .get("change_action")
    == "UPDATE_CURRENT"
)

copy_result = (
    result.get("copy")
    or {}
)

target_path = Path(
    copy_result.get("target_path")
    or ""
)

assert target_path.exists()
assert (
    copy_result.get("status")
    == "COPIED"
)


snapshot = (
    workflow.get_pmf_material_snapshot(
        PMF_ROW_POS,
        PMF_DEPTH,
    )
)

material = snapshot.to_dict()

assert (
    material.get("org")
    == "MUIS"
)

assert (
    material.get("cert_no")
    == "PRN22020011873"
)

assert (
    material.get("expiry_date")
    == "2028-05-31"
)


certificate_rows = (
    workflow.list_material_certificate_history(
        pmf_row_pos=PMF_ROW_POS,
        pmf_depth=PMF_DEPTH,
        limit=20,
    )
)

rows = certificate_rows["rows"]

active_primary = [
    row
    for row in rows
    if (
        row.get("status") == "ACTIVE"
        and int(
            row.get("is_primary")
            or 0
        ) == 1
    )
]

superseded_primary = [
    row
    for row in rows
    if (
        row.get("status")
        == "SUPERSEDED"
        and int(
            row.get("is_primary")
            or 0
        ) == 1
    )
]

assert len(active_primary) == 1
assert (
    active_primary[0]["expiry_date"]
    == "2028-05-31"
)

assert len(superseded_primary) == 1
assert (
    superseded_primary[0]["expiry_date"]
    == "2026-05-31"
)


filing_history = (
    workflow.list_filing_history(
        limit=20
    )
)

confirmed_rows = [
    row
    for row in filing_history["rows"]
    if row.get("ocr_job_id") == OCR_JOB_ID
]

assert len(confirmed_rows) == 1
assert (
    confirmed_rows[0]["status"]
    == "CONFIRMED"
)


print("=== CONFIRM RESULT ===")
print(
    json.dumps(
        {
            "status": result.get("status"),
            "change_gate": result.get(
                "change_gate"
            ),
            "copy": result.get("copy"),
            "pmf_update": result.get(
                "pmf_update"
            ),
            "material_certificate_history": (
                result.get(
                    "material_certificate_history"
                )
            ),
            "legacy_primary_history_id": (
                result.get(
                    "legacy_primary_history_id"
                )
            ),
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )
)

print()
print("=== UPDATED PMF ===")
print(
    json.dumps(
        {
            "org": material.get("org"),
            "cert_no": material.get(
                "cert_no"
            ),
            "expiry_date": material.get(
                "expiry_date"
            ),
        },
        ensure_ascii=False,
        indent=2,
    )
)

print()
print("=== CERTIFICATE HISTORY ===")
print(
    json.dumps(
        rows,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
)

print()
print("TEST_ROOT:", TEST_ROOT)
print("TEST_PMF:", TEST_PMF)
print("TEST_DB:", TEST_DB)
print("TARGET_PATH:", target_path)
print("CONFIRM_INTEGRATION_TEST_OK")
