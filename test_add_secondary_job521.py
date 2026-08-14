from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import os
import shutil
import sqlite3
import sys
import tempfile


JOB_ID = 521
ROW_POS = 90
DEPTH = 0

ROOT = Path.cwd()
BACKEND = ROOT / "backend"

SOURCE_PMF = Path(
    "D:/halal_web_runtime/pmf_test/active_pmf_test.xlsm"
)

TEST_BASE = Path(
    "D:/halal_web_runtime/integration_tests"
)

TEST_BASE.mkdir(
    parents=True,
    exist_ok=True,
)

TEST_ROOT = Path(
    tempfile.mkdtemp(
        prefix="job521_secondary_",
        dir=str(TEST_BASE),
    )
)

TEST_PMF = (
    TEST_ROOT
    / "active_pmf_test_copy.xlsm"
)

TEST_FILES = (
    TEST_ROOT
    / "raw_material"
)

TEST_DB = (
    TEST_ROOT
    / "pmf_app_test.db"
)


if not BACKEND.exists():
    raise FileNotFoundError(
        f"Backend not found: {BACKEND}"
    )

if not SOURCE_PMF.exists():
    raise FileNotFoundError(
        f"PMF not found: {SOURCE_PMF}"
    )


TEST_FILES.mkdir(
    parents=True,
    exist_ok=True,
)

shutil.copy2(
    SOURCE_PMF,
    TEST_PMF,
)

os.environ["PMF_UPDATE_PATH"] = str(
    TEST_PMF
)

sys.path.insert(
    0,
    str(BACKEND.resolve()),
)


from app.services import (
    certificate_filing_workflow_service
    as workflow,
)


def test_get_conn():
    conn = sqlite3.connect(
        TEST_DB
    )

    conn.row_factory = sqlite3.Row
    return conn


workflow.get_conn = test_get_conn

workflow.get_halal_raw_material_root = (
    lambda: TEST_FILES
)


original_preview = (
    workflow.preview_filing_workflow
)


def test_preview(
    ocr_job_id: int,
    pmf_row_pos: int,
    pmf_depth: int = 0,
):
    result = deepcopy(
        original_preview(
            ocr_job_id=ocr_job_id,
            pmf_row_pos=pmf_row_pos,
            pmf_depth=pmf_depth,
        )
    )

    result["certificate"] = {
        **(
            result.get("certificate")
            or {}
        ),
        "cert_org": "HCA",
        "cert_no": "HCA-SECONDARY-2029",
        "expiry_date": "2029-12-31",
        "manufacturer": (
            "SYMRISE ASIA PACIFIC PTE LTD"
        ),
    }

    result["change_decision"] = {
        "decision_code": (
            "AUTHORITY_CHANGE_REVIEW"
        ),
        "requires_review": True,
        "blocked": False,
        "auto_action": "REVIEW",
        "can_update_pmf": False,
        "review_options": [
            "REPLACE_CURRENT",
            "ADD_SECONDARY",
            "HOLD",
            "REJECT",
        ],
        "reasons": [
            "Certificate authority changed."
        ],
        "missing_fields": [],
        "changes": {},
    }

    result["blockers"] = []
    result["hard_blockers"] = []

    return result


workflow.preview_filing_workflow = (
    test_preview
)


result = workflow.confirm_filing_workflow(
    ocr_job_id=JOB_ID,
    pmf_row_pos=ROW_POS,
    pmf_depth=DEPTH,
    overwrite=False,
    force=False,
    allow_date_regression=False,
    change_action="ADD_SECONDARY",
)


assert result["ok"] is True

assert (
    result["change_gate"]["change_action"]
    == "ADD_SECONDARY"
)

assert (
    result["pmf_update"]["skipped"]
    is True
)


target_path = Path(
    result["copy"]["target_path"]
)

assert target_path.exists()

assert (
    result["copy"]["status"]
    == "COPIED"
)


material = (
    workflow.get_pmf_material_snapshot(
        ROW_POS,
        DEPTH,
    ).to_dict()
)


assert (
    str(material["org"])
    .strip()
    .upper()
    == "MUIS"
)

assert (
    str(material["cert_no"])
    .strip()
    == "PRN22020011873"
)

assert (
    str(material["expiry_date"])
    .strip()
    == "2026-05-31"
)


rows = (
    workflow
    .list_material_certificate_history(
        pmf_row_pos=ROW_POS,
        pmf_depth=DEPTH,
        limit=20,
    )["rows"]
)


active_primary = [
    row
    for row in rows
    if (
        row["status"] == "ACTIVE"
        and int(
            row["is_primary"]
            or 0
        ) == 1
    )
]

active_secondary = [
    row
    for row in rows
    if (
        row["status"] == "ACTIVE"
        and int(
            row["is_primary"]
            or 0
        ) == 0
    )
]

superseded = [
    row
    for row in rows
    if (
        row["status"]
        == "SUPERSEDED"
    )
]


assert len(active_primary) == 1

assert (
    active_primary[0]["cert_org"]
    == "MUIS"
)

assert (
    active_primary[0]["expiry_date"]
    == "2026-05-31"
)


assert len(active_secondary) == 1

assert (
    active_secondary[0]["cert_org"]
    == "HCA"
)

assert (
    active_secondary[0]["cert_no"]
    == "HCA-SECONDARY-2029"
)

assert (
    active_secondary[0]["expiry_date"]
    == "2029-12-31"
)


assert len(superseded) == 0


print("=== ADD SECONDARY RESULT ===")

print(
    json.dumps(
        {
            "status": result["status"],
            "change_gate": (
                result["change_gate"]
            ),
            "copy": result["copy"],
            "pmf_update": (
                result["pmf_update"]
            ),
            "material_certificate_history": (
                result[
                    "material_certificate_history"
                ]
            ),
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )
)


print()
print("=== PMF PRIMARY REMAINS ===")

print(
    json.dumps(
        {
            "org": material["org"],
            "cert_no": (
                material["cert_no"]
            ),
            "expiry_date": (
                material["expiry_date"]
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
print("TARGET_PATH:", target_path)
print("ADD_SECONDARY_INTEGRATION_TEST_OK")
