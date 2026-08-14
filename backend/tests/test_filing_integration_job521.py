"""OCR job 521 / PMF row 90 기준 확정 흐름 통합 테스트.

실제 PMF 워크북과 `pmf_app.db`(job 521, row 90 데이터)가 있어야 돌아간다.
없으면 모듈 전체를 skip한다 — 이 테스트들의 목적은 운영 환경에서 확정·이력·PMF
반영이 실제로 맞물려 도는지 확인하는 것이라 대체 픽스처로 흉내내면 의미가 없다.

돌리려면:
    HALAL_TEST_PMF=<PMF .xlsm 경로> HALAL_TEST_DB=<pmf_app.db 경로> pytest

원본은 `tests/legacy/`의 세 스크립트(v1/v2/v3 + add_secondary + replace_current)였다.
v1/v2는 v3에 흡수됐고, 세 시나리오가 공유하던 셋업을 픽스처로 합쳤다.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from app.services import certificate_filing_service
from app.services import certificate_filing_workflow_service as workflow
from app.services import filing_name_service
from app.services import pmf_filing_service

OCR_JOB_ID = 521
PMF_ROW_POS = 90
PMF_DEPTH = 0

# 대상 원료의 확정 전 상태 (PMF row 90)
BASE_ORG = "MUIS"
BASE_CERT_NO = "PRN22020011873"
BASE_EXPIRY = "2026-05-31"


def _env_path(name: str) -> Path | None:
    value = os.getenv(name, "").strip()
    return Path(value) if value else None


SOURCE_PMF = _env_path("HALAL_TEST_PMF")
SOURCE_DB = _env_path("HALAL_TEST_DB")

pytestmark = pytest.mark.skipif(
    not (SOURCE_PMF and SOURCE_PMF.exists() and SOURCE_DB and SOURCE_DB.exists()),
    reason="HALAL_TEST_PMF / HALAL_TEST_DB 환경변수로 실제 PMF와 pmf_app.db를 지정해야 실행된다",
)


def normalize_date(value: Any) -> str:
    """엑셀·SQLite가 돌려주는 날짜 표현을 YYYY-MM-DD로 맞춘다."""
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


@pytest.fixture
def filing_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """PMF와 DB를 tmp로 복사해 원본을 건드리지 않고 확정 흐름을 돌린다."""
    test_pmf = tmp_path / "active_pmf_test_copy.xlsm"
    test_db = tmp_path / "pmf_app_test.db"
    filing_root = tmp_path / "raw_material"

    shutil.copy2(SOURCE_PMF, test_pmf)
    shutil.copy2(SOURCE_DB, test_db)
    filing_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("PMF_UPDATE_PATH", str(test_pmf))

    def test_conn():
        conn = sqlite3.connect(test_db)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(workflow, "get_conn", test_conn)
    monkeypatch.setattr(workflow, "get_halal_raw_material_root", lambda: filing_root)

    for module in (certificate_filing_service, filing_name_service):
        if hasattr(module, "get_halal_raw_material_root"):
            monkeypatch.setattr(module, "get_halal_raw_material_root", lambda: filing_root)

    for module in (workflow, pmf_filing_service):
        if hasattr(module, "resolve_pmf_update_path"):
            monkeypatch.setattr(module, "resolve_pmf_update_path", lambda: test_pmf)

    return {"pmf": test_pmf, "db": test_db, "root": filing_root}


def _override_preview(
    monkeypatch: pytest.MonkeyPatch,
    certificate: dict[str, Any] | None,
    decision: dict[str, Any] | None,
):
    """실제 preview 결과에 시나리오별 인증서·판정을 덮어씌운다."""
    original = workflow.preview_filing_workflow

    def patched(ocr_job_id: int, pmf_row_pos: int, pmf_depth: int = 0):
        result = deepcopy(
            original(
                ocr_job_id=ocr_job_id,
                pmf_row_pos=pmf_row_pos,
                pmf_depth=pmf_depth,
            )
        )

        if certificate is not None:
            result["certificate"] = {**(result.get("certificate") or {}), **certificate}

        if decision is not None:
            result["change_decision"] = decision

        result["blockers"] = []
        result["hard_blockers"] = []

        return result

    monkeypatch.setattr(workflow, "preview_filing_workflow", patched)


AUTHORITY_CHANGE_DECISION = {
    "decision_code": "AUTHORITY_CHANGE_REVIEW",
    "requires_review": True,
    "blocked": False,
    "auto_action": "REVIEW",
    "can_update_pmf": False,
    "review_options": ["REPLACE_CURRENT", "ADD_SECONDARY", "HOLD", "REJECT"],
    "reasons": ["Certificate authority changed."],
    "missing_fields": [],
    "changes": {},
}


def _history_rows() -> list[dict[str, Any]]:
    return workflow.list_material_certificate_history(
        pmf_row_pos=PMF_ROW_POS,
        pmf_depth=PMF_DEPTH,
        limit=20,
    )["rows"]


def _split_rows(rows: list[dict[str, Any]]):
    active_primary = [
        r for r in rows if r["status"] == "ACTIVE" and int(r["is_primary"] or 0) == 1
    ]
    active_secondary = [
        r for r in rows if r["status"] == "ACTIVE" and int(r["is_primary"] or 0) == 0
    ]
    superseded_primary = [
        r for r in rows if r["status"] == "SUPERSEDED" and int(r["is_primary"] or 0) == 1
    ]

    return active_primary, active_secondary, superseded_primary


def test_same_authority_renewal_updates_pmf_and_supersedes_previous(
    filing_env, monkeypatch: pytest.MonkeyPatch
):
    """같은 기관 갱신: PMF 유효기간이 갱신되고 이전 인증서는 SUPERSEDED가 된다."""
    _override_preview(monkeypatch, certificate=None, decision=None)

    original_preview = workflow.preview_filing_workflow

    def guarded(**kwargs):
        result = original_preview(**kwargs)
        decision = result.get("change_decision") or {}

        assert decision.get("decision_code") == "SAME_AUTHORITY_RENEWAL", (
            f"예상과 다른 변경 판정: {decision}"
        )
        assert not (result.get("request_context") or {}).get("request_id"), (
            "이 테스트는 메일과 연결되지 않은 단독 OCR job을 전제로 한다"
        )

        return result

    monkeypatch.setattr(workflow, "preview_filing_workflow", guarded)

    result = workflow.confirm_filing_workflow(
        ocr_job_id=OCR_JOB_ID,
        pmf_row_pos=PMF_ROW_POS,
        pmf_depth=PMF_DEPTH,
        overwrite=False,
        force=True,
        allow_date_regression=False,
        change_action="",
    )

    assert result["ok"] is True
    assert result["change_gate"]["change_action"] == "UPDATE_CURRENT"
    assert result["copy"]["status"] == "COPIED"
    assert Path(result["copy"]["target_path"]).exists()

    material = workflow.get_pmf_material_snapshot(PMF_ROW_POS, PMF_DEPTH).to_dict()

    assert str(material["org"]).strip().upper() == BASE_ORG
    assert str(material["cert_no"]).strip() == BASE_CERT_NO
    assert normalize_date(material["expiry_date"]) == "2028-05-31"

    active_primary, _, superseded_primary = _split_rows(_history_rows())

    assert len(active_primary) == 1
    assert normalize_date(active_primary[0]["expiry_date"]) == "2028-05-31"

    assert len(superseded_primary) == 1
    assert normalize_date(superseded_primary[0]["expiry_date"]) == BASE_EXPIRY

    confirmed = [
        row
        for row in workflow.list_filing_history(limit=20)["rows"]
        if row.get("ocr_job_id") == OCR_JOB_ID
    ]

    assert len(confirmed) == 1
    assert confirmed[0]["status"] == "CONFIRMED"


def test_add_secondary_keeps_primary_and_leaves_pmf_untouched(
    filing_env, monkeypatch: pytest.MonkeyPatch
):
    """기관 변경 + ADD_SECONDARY: 기존 인증서가 주(primary)로 남고 PMF는 건드리지 않는다."""
    _override_preview(
        monkeypatch,
        certificate={
            "cert_org": "HCA",
            "cert_no": "HCA-SECONDARY-2029",
            "expiry_date": "2029-12-31",
            "manufacturer": "SYMRISE ASIA PACIFIC PTE LTD",
        },
        decision=AUTHORITY_CHANGE_DECISION,
    )

    result = workflow.confirm_filing_workflow(
        ocr_job_id=OCR_JOB_ID,
        pmf_row_pos=PMF_ROW_POS,
        pmf_depth=PMF_DEPTH,
        overwrite=False,
        force=False,
        allow_date_regression=False,
        change_action="ADD_SECONDARY",
    )

    assert result["ok"] is True
    assert result["change_gate"]["change_action"] == "ADD_SECONDARY"
    assert result["pmf_update"]["skipped"] is True
    assert result["copy"]["status"] == "COPIED"
    assert Path(result["copy"]["target_path"]).exists()

    material = workflow.get_pmf_material_snapshot(PMF_ROW_POS, PMF_DEPTH).to_dict()

    assert str(material["org"]).strip().upper() == BASE_ORG
    assert str(material["cert_no"]).strip() == BASE_CERT_NO
    assert normalize_date(material["expiry_date"]) == BASE_EXPIRY

    active_primary, active_secondary, superseded_primary = _split_rows(_history_rows())

    assert len(active_primary) == 1
    assert active_primary[0]["cert_org"] == BASE_ORG
    assert normalize_date(active_primary[0]["expiry_date"]) == BASE_EXPIRY

    assert len(active_secondary) == 1
    assert active_secondary[0]["cert_org"] == "HCA"
    assert active_secondary[0]["cert_no"] == "HCA-SECONDARY-2029"
    assert normalize_date(active_secondary[0]["expiry_date"]) == "2029-12-31"

    assert len(superseded_primary) == 0


def test_replace_current_promotes_new_certificate(
    filing_env, monkeypatch: pytest.MonkeyPatch
):
    """기관 변경 + REPLACE_CURRENT: 새 인증서가 주가 되고 기존 것은 SUPERSEDED."""
    _override_preview(
        monkeypatch,
        certificate={
            "cert_org": "HCA",
            "cert_no": "HCA-PRIMARY-2029",
            "expiry_date": "2029-12-31",
            "manufacturer": "SYMRISE ASIA PACIFIC PTE LTD",
        },
        decision=AUTHORITY_CHANGE_DECISION,
    )

    result = workflow.confirm_filing_workflow(
        ocr_job_id=OCR_JOB_ID,
        pmf_row_pos=PMF_ROW_POS,
        pmf_depth=PMF_DEPTH,
        overwrite=False,
        force=False,
        allow_date_regression=False,
        change_action="REPLACE_CURRENT",
    )

    assert result["ok"] is True
    assert result["status"] == "REPLACED"
    assert result["change_gate"]["change_action"] == "REPLACE_CURRENT"
    assert result["material_certificate_history"]["action"] == "REPLACE_CURRENT"
    assert result["copy"]["status"] == "COPIED"
    assert Path(result["copy"]["target_path"]).exists()

    material = workflow.get_pmf_material_snapshot(PMF_ROW_POS, PMF_DEPTH).to_dict()

    assert str(material["org"]).strip().upper() == "HCA"
    assert str(material["cert_no"]).strip() == "HCA-PRIMARY-2029"
    assert normalize_date(material["expiry_date"]) == "2029-12-31"

    active_primary, active_secondary, superseded_primary = _split_rows(_history_rows())

    assert len(active_primary) == 1
    assert active_primary[0]["cert_org"] == "HCA"
    assert active_primary[0]["cert_no"] == "HCA-PRIMARY-2029"
    assert normalize_date(active_primary[0]["expiry_date"]) == "2029-12-31"

    assert len(active_secondary) == 0

    assert len(superseded_primary) == 1
    assert superseded_primary[0]["cert_org"] == BASE_ORG
    assert superseded_primary[0]["cert_no"] == BASE_CERT_NO
    assert normalize_date(superseded_primary[0]["expiry_date"]) == BASE_EXPIRY

    confirmed = workflow.get_confirmed_history_for_job(OCR_JOB_ID)

    assert confirmed is not None
    assert confirmed["status"] == "REPLACED"
