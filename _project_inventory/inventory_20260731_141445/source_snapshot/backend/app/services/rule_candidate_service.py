from __future__ import annotations

import json
import re
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
RULES_DATA_DIR = BACKEND_ROOT / "data" / "rules"

RULE_OVERRIDES_PATH = RULES_DATA_DIR / "certificate_rule_overrides.json"
RULE_CANDIDATES_PATH = RULES_DATA_DIR / "rule_candidates.jsonl"
APPROVED_RULE_HISTORY_PATH = RULES_DATA_DIR / "approved_rule_history.jsonl"
RULE_VALIDATION_REPORT_DIR = RULES_DATA_DIR / "rule_validation_reports"

RULE_CANDIDATE_SCHEMA_VERSION = "ai_rule_candidate_v1"
ALLOWED_CANDIDATE_STATUSES = {"PENDING", "VALIDATED", "APPLIED", "REJECTED", "ERROR"}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_rule_storage() -> None:
    RULES_DATA_DIR.mkdir(parents=True, exist_ok=True)
    RULE_VALIDATION_REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if not RULE_OVERRIDES_PATH.exists():
        write_json_file(RULE_OVERRIDES_PATH, {
            "schema_version": "certificate_rule_overrides_v1",
            "updated_at": now_iso(),
            "rules": [],
        })

    if not RULE_CANDIDATES_PATH.exists():
        RULE_CANDIDATES_PATH.write_text("", encoding="utf-8")

    if not APPROVED_RULE_HISTORY_PATH.exists():
        APPROVED_RULE_HISTORY_PATH.write_text("", encoding="utf-8")


def read_json_file(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return deepcopy(default)

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return deepcopy(default)


def write_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except Exception:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp_path.replace(path)


def normalize_key(value: str) -> str:
    key = re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "").upper()).strip("_")
    return re.sub(r"_+", "_", key) or "RULE"


def generate_rule_candidate_id(target_org: str = "", target_field: str = "", rule_kind: str = "") -> str:
    prefix = "_".join([
        normalize_key(target_org or "ORG"),
        normalize_key(target_field or "FIELD"),
        normalize_key(rule_kind or "RULE"),
    ])
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8].upper()}"


def normalize_rule_candidate(candidate: dict[str, Any], source: str = "AI") -> dict[str, Any]:
    ensure_rule_storage()
    data = deepcopy(candidate or {})

    target_org = str(data.get("target_org") or "").upper().strip()
    target_field = str(data.get("target_field") or "").strip()
    rule_kind = str(data.get("rule_kind") or "").strip()

    rule_candidate_id = str(data.get("rule_candidate_id") or "").strip()
    if not rule_candidate_id:
        rule_candidate_id = generate_rule_candidate_id(target_org, target_field, rule_kind)

    status = str(data.get("apply_status") or data.get("status") or "PENDING").upper()
    if status not in ALLOWED_CANDIDATE_STATUSES:
        status = "PENDING"

    risk_level = str(data.get("risk_level") or "MEDIUM").upper()
    if risk_level not in {"LOW", "MEDIUM", "HIGH"}:
        risk_level = "MEDIUM"

    normalized = {
        "schema_version": RULE_CANDIDATE_SCHEMA_VERSION,
        "rule_candidate_id": rule_candidate_id,
        "review_version": str(data.get("review_version") or "ai_rule_review_v1"),
        "source": source,
        "target_org": target_org,
        "target_field": target_field,
        "rule_kind": rule_kind,
        "problem_summary": str(data.get("problem_summary") or data.get("problem") or ""),
        "proposed_rule": data.get("proposed_rule") or {},
        "expected_cases": data.get("expected_cases") or [],
        "risk_level": risk_level,
        "safe_to_auto_apply": bool(data.get("safe_to_auto_apply", False)),
        "reason": str(data.get("reason") or ""),
        "apply_status": status,
        "validation_report_id": data.get("validation_report_id") or "",
        "validation_summary": data.get("validation_summary") or {},
        "created_at": data.get("created_at") or now_iso(),
        "updated_at": now_iso(),
    }
    return normalized


def create_rule_candidate(candidate: dict[str, Any], source: str = "AI") -> dict[str, Any]:
    row = normalize_rule_candidate(candidate, source=source)
    append_jsonl(RULE_CANDIDATES_PATH, row)
    return row


def create_rule_candidates(candidates: list[dict[str, Any]], source: str = "AI") -> list[dict[str, Any]]:
    created = []
    for candidate in candidates or []:
        if isinstance(candidate, dict):
            created.append(create_rule_candidate(candidate, source=source))
    return created


def list_rule_candidates(limit: int = 100, apply_status: str = "", target_org: str = "", target_field: str = "") -> dict[str, Any]:
    ensure_rule_storage()
    limit = max(1, min(int(limit), 500))
    apply_status = str(apply_status or "").upper().strip()
    target_org = str(target_org or "").upper().strip()
    target_field = str(target_field or "").strip()

    rows = list(reversed(read_jsonl(RULE_CANDIDATES_PATH)))
    filtered = []
    for row in rows:
        if apply_status and row.get("apply_status") != apply_status:
            continue
        if target_org and row.get("target_org") != target_org:
            continue
        if target_field and row.get("target_field") != target_field:
            continue
        filtered.append(row)
        if len(filtered) >= limit:
            break

    return {"ok": True, "limit": limit, "total": len(rows), "rows": filtered}


def get_rule_candidate(rule_candidate_id: str) -> dict[str, Any] | None:
    ensure_rule_storage()
    rule_candidate_id = str(rule_candidate_id or "").strip()
    for row in reversed(read_jsonl(RULE_CANDIDATES_PATH)):
        if row.get("rule_candidate_id") == rule_candidate_id:
            return row
    return None


def update_rule_candidate(rule_candidate_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    ensure_rule_storage()
    rows = read_jsonl(RULE_CANDIDATES_PATH)
    updated_row = None
    for row in rows:
        if row.get("rule_candidate_id") == rule_candidate_id:
            row.update(updates or {})
            row["updated_at"] = now_iso()
            updated_row = row
    if updated_row is None:
        raise ValueError(f"rule_candidate_id를 찾을 수 없습니다: {rule_candidate_id}")
    write_jsonl(RULE_CANDIDATES_PATH, rows)
    return updated_row


def update_rule_candidate_status(rule_candidate_id: str, apply_status: str, message: str = "", validation_report_id: str = "", validation_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    status = str(apply_status or "").upper()
    if status not in ALLOWED_CANDIDATE_STATUSES:
        raise ValueError(f"허용되지 않는 apply_status입니다: {apply_status}")
    updates: dict[str, Any] = {"apply_status": status}
    if message:
        updates["message"] = message
    if validation_report_id:
        updates["validation_report_id"] = validation_report_id
    if validation_summary is not None:
        updates["validation_summary"] = validation_summary
    return update_rule_candidate(rule_candidate_id, updates)


def get_rule_overrides() -> dict[str, Any]:
    ensure_rule_storage()
    data = read_json_file(RULE_OVERRIDES_PATH, default={
        "schema_version": "certificate_rule_overrides_v1",
        "updated_at": now_iso(),
        "rules": [],
    })
    if not isinstance(data, dict):
        data = {"schema_version": "certificate_rule_overrides_v1", "updated_at": now_iso(), "rules": []}
    if not isinstance(data.get("rules"), list):
        data["rules"] = []
    return data


def save_rule_overrides(data: dict[str, Any]) -> dict[str, Any]:
    data = deepcopy(data or {})
    data["schema_version"] = data.get("schema_version") or "certificate_rule_overrides_v1"
    data["updated_at"] = now_iso()
    data.setdefault("rules", [])
    write_json_file(RULE_OVERRIDES_PATH, data)
    return data


def append_approved_rule_history(row: dict[str, Any]) -> None:
    ensure_rule_storage()
    data = deepcopy(row or {})
    data.setdefault("created_at", now_iso())
    append_jsonl(APPROVED_RULE_HISTORY_PATH, data)


def list_approved_rule_history(limit: int = 200) -> dict[str, Any]:
    ensure_rule_storage()
    limit = max(1, min(int(limit), 1000))
    rows = list(reversed(read_jsonl(APPROVED_RULE_HISTORY_PATH)))
    return {"ok": True, "limit": limit, "rows": rows[:limit], "total": len(rows)}


def get_rule_storage_status() -> dict[str, Any]:
    ensure_rule_storage()
    return {
        "ok": True,
        "rules_data_dir": str(RULES_DATA_DIR),
        "rule_overrides_path": str(RULE_OVERRIDES_PATH),
        "rule_candidates_path": str(RULE_CANDIDATES_PATH),
        "rule_validation_report_dir": str(RULE_VALIDATION_REPORT_DIR),
        "approved_rule_history_path": str(APPROVED_RULE_HISTORY_PATH),
        "candidate_count": len(read_jsonl(RULE_CANDIDATES_PATH)),
        "approved_history_count": len(read_jsonl(APPROVED_RULE_HISTORY_PATH)),
        "override_rule_count": len(get_rule_overrides().get("rules") or []),
    }
