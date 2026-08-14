from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
import importlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile


OCR_JOB_ID = 521
PMF_ROW_POS = 90
PMF_DEPTH = 0

PROJECT_ROOT = Path.cwd()
BACKEND_ROOT = PROJECT_ROOT / "backend"

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
        prefix="job521_",
        dir=str(TEST_BASE),
    )
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


def normalize_date(value) -> str:
    if value is None:
        return ""

    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")

    text = str(value).strip()

    if not text:
        return ""

    text = text.replace(".", "-").replace("/", "-")

    if "T" in text:
        text = text.split("T", 1)[0]

    if " " in text:
        first = text.split(" ", 1)[0]
        if len(first) >= 10:
            text = first

    return text[:10]


def patch_resolver_owner(
    function,
    resolver_name: str,
    resolver,
) -> None:
    module = importlib.import_module(
        function.__module__
    )

    if hasattr(module, resolver_name):
        setattr(
            module,
            resolver_name,
            resolver,
        )


if not BACKEND_ROOT.exists():
    raise FileNotFoundError(
        f"Backend directory not found: {BACKEND_ROOT}"
    )

if not SOURCE_PMF.exists():
    raise FileNotFoundError(
        f"Source PMF not found: {SOURCE_PMF}"
    )


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


patch_resolver_owner(
    workflow.get_pmf_material_snapshot,
    "resolve_pmf_update_path",
    test_pmf_path,
)

patch_resolver_owner(
    workflow.update_pmf_certificate_fields,
    "resolve_pmf_update_path",
    test_pmf_path,
)


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


child_code = r'''
from pathlib import Path
import importlib
import json
import sys

backend_root = Path(sys.argv[1])
pmf_path = Path(sys.argv[2])
row_pos = int(sys.argv[3])
depth = int(sys.argv[4])

sys.path.insert(
    0,
    str(backend_root.resolve()),
)

from app.services import certificate_filing_workflow_service as workflow
from app.services import pmf_filing_service


def resolve_test_pmf():
    return pmf_path


for module in (
    workflow,
    pmf_filing_service,
):
    if hasattr(
        module,
        "resolve_pmf_update_path",
    ):
        module.resolve_pmf_update_path = resolve_test_pmf


owner = importlib.import_module(
    workflow.get_pmf_material_snapshot.__module__
)

if hasattr(
    owner,
    "resolve_pmf_update_path",
):
    owner.resolve_pmf_update_path = resolve_test_pmf


snapshot = workflow.get_pmf_material_snapshot(
    row_pos,
    depth,
)

print(
    json.dumps(
        snapshot.to_dict(),
        ensure_ascii=False,
        default=str,
    )
)
'''


child = subprocess.run(
    [
        sys.executable,
        "-c",
        child_code,
        str(BACKEND_ROOT),
        str(TEST_PMF),
        str(PMF_ROW_POS),
        str(PMF_DEPTH),
    ],
    check=True,
    capture_output=True,
    text=True,
    encoding="utf-8",
)

child_lines = [
    line.strip()
    for line in child.stdout.splitlines()
    if line.strip()
]

if not child_lines:
    raise RuntimeError(
        "Fresh PMF reader returned no output."
    )

material = json.loads(
    child_lines[-1]
)

actual_expiry = normalize_date(
    material.get("expiry_date")
)


print("=== RAW PMF SNAPSHOT ===")
print(
    json.dumps(
        material,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
)

print()
print("NORMALIZED_EXPIRY:", actual_expiry)
print(
    "PMF_UPDATE_RESULT:",
    json.dumps(
        result.get("pmf_update") or {},
        ensure_ascii=False,
        indent=2,
        default=str,
    ),
)


assert (
    str(material.get("org") or "").strip().upper()
    == "MUIS"
)

assert (
    str(material.get("cert_no") or "").strip()
    == "PRN22020011873"
)

if actual_expiry != "2028-05-31":
    raise AssertionError(
        "Updated PMF expiry mismatch. "
        f"Expected 2028-05-31, got {material.get('expiry_date')!r}. "
        f"Test PMF: {TEST_PMF}"
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
    normalize_date(
        active_primary[0].get(
            "expiry_date"
        )
    )
    == "2028-05-31"
)

assert len(superseded_primary) == 1

assert (
    normalize_date(
        superseded_primary[0].get(
            "expiry_date"
        )
    )
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


print()
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
print("CONFIRM_INTEGRATION_TEST_V2_OK")
