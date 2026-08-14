"""원료별 인증서 이력. 주/부 인증서 승격·강등과 롤백이 여기 있다.

할랄 심사 근거자료로 재사용되는 로그이므로 이력은 지우지 않고 상태로만 관리한다."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import json

from app.services.filing.store import (
    ensure_filing_tables,
    get_conn,
)
from app.services.filing.helpers import (
    _clean,
)


def _insert_history(payload: dict[str, Any]) -> int:
    ensure_filing_tables()
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO certificate_filing_history (
                ocr_job_id,
                request_id,
                pmf_row_pos,
                pmf_depth,
                source_path,
                target_path,
                cert_org,
                cert_no,
                expiry_date,
                status,
                copy_status,
                pmf_update_json,
                warning_json,
                error_message,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("ocr_job_id"),
                payload.get("request_id", ""),
                payload.get("pmf_row_pos"),
                payload.get("pmf_depth"),
                payload.get("source_path", ""),
                payload.get("target_path", ""),
                payload.get("cert_org", ""),
                payload.get("cert_no", ""),
                payload.get("expiry_date", ""),
                payload.get("status", ""),
                payload.get("copy_status", ""),
                json.dumps(payload.get("pmf_update") or {}, ensure_ascii=False),
                json.dumps(payload.get("warnings") or [], ensure_ascii=False),
                payload.get("error_message", ""),
                now,
                now,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def insert_material_certificate_history(
    payload: dict[str, Any],
) -> int:
    ensure_filing_tables()

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    is_primary = (
        1
        if payload.get("is_primary")
        else 0
    )

    certificate_role = _clean(
        payload.get("certificate_role")
    ).upper()

    if not certificate_role:
        certificate_role = (
            "PRIMARY"
            if is_primary
            else "SECONDARY"
        )

    status = (
        _clean(payload.get("status")).upper()
        or "ACTIVE"
    )

    conn = get_conn()

    try:
        cur = conn.execute(
            """
            INSERT INTO material_certificate_history (
                ocr_job_id,
                request_id,
                pmf_row_pos,
                pmf_depth,
                cert_org,
                cert_no,
                expiry_date,
                manufacturer,
                source_path,
                target_path,
                certificate_role,
                status,
                change_action,
                is_primary,
                supersedes_id,
                created_at,
                updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                payload.get("ocr_job_id"),
                payload.get("request_id", ""),
                int(payload.get("pmf_row_pos")),
                int(payload.get("pmf_depth") or 0),
                _clean(payload.get("cert_org")).upper(),
                _clean(payload.get("cert_no")),
                _clean(payload.get("expiry_date")),
                _clean(payload.get("manufacturer")),
                _clean(payload.get("source_path")),
                _clean(payload.get("target_path")),
                certificate_role,
                status,
                _clean(
                    payload.get("change_action")
                ).upper(),
                is_primary,
                payload.get("supersedes_id"),
                now,
                now,
            ),
        )

        conn.commit()
        return int(cur.lastrowid)

    finally:
        conn.close()


def list_material_certificate_history(
    pmf_row_pos: int | None = None,
    pmf_depth: int | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    ensure_filing_tables()

    limit = max(
        1,
        min(int(limit), 500),
    )

    where_parts: list[str] = []
    params: list[Any] = []

    if pmf_row_pos is not None:
        where_parts.append(
            "pmf_row_pos = ?"
        )
        params.append(
            int(pmf_row_pos)
        )

    if pmf_depth is not None:
        where_parts.append(
            "pmf_depth = ?"
        )
        params.append(
            int(pmf_depth)
        )

    where_sql = ""

    if where_parts:
        where_sql = (
            " WHERE "
            + " AND ".join(where_parts)
        )

    query = (
        "SELECT * "
        "FROM material_certificate_history"
        + where_sql
        + " ORDER BY id DESC LIMIT ?"
    )

    params.append(limit)

    conn = get_conn()

    try:
        rows = conn.execute(
            query,
            tuple(params),
        ).fetchall()

    finally:
        conn.close()

    result_rows = [
        dict(row)
        for row in rows
    ]

    return {
        "ok": True,
        "count": len(result_rows),
        "rows": result_rows,
    }


def get_active_material_certificates(
    pmf_row_pos: int,
    pmf_depth: int = 0,
) -> list[dict[str, Any]]:
    ensure_filing_tables()

    conn = get_conn()

    try:
        rows = conn.execute(
            """
            SELECT *
            FROM material_certificate_history
            WHERE pmf_row_pos = ?
              AND pmf_depth = ?
              AND status = 'ACTIVE'
            ORDER BY
                is_primary DESC,
                expiry_date DESC,
                id DESC
            """,
            (
                int(pmf_row_pos),
                int(pmf_depth),
            ),
        ).fetchall()

    finally:
        conn.close()

    return [
        dict(row)
        for row in rows
    ]


def apply_material_certificate_history_action(
    payload: dict[str, Any],
    change_action: str,
) -> dict[str, Any]:
    ensure_filing_tables()

    action = _clean(change_action).upper()

    action_aliases = {
        "APPROVE_RENEWAL": "UPDATE_CURRENT",
        "REGISTER_AS_PRIMARY": "UPDATE_CURRENT",
    }

    action = action_aliases.get(
        action,
        action,
    )

    allowed_actions = {
        "UPDATE_CURRENT",
        "REPLACE_CURRENT",
        "ADD_SECONDARY",
    }

    if action not in allowed_actions:
        raise ValueError(
            "Unsupported material certificate action: "
            + action
        )

    if payload.get("pmf_row_pos") is None:
        raise ValueError(
            "pmf_row_pos is required"
        )

    pmf_row_pos = int(
        payload["pmf_row_pos"]
    )

    pmf_depth = int(
        payload.get("pmf_depth")
        or 0
    )

    cert_org = _clean(
        payload.get("cert_org")
    ).upper()

    cert_no = _clean(
        payload.get("cert_no")
    )

    expiry_date = _clean(
        payload.get("expiry_date")
    )

    manufacturer = _clean(
        payload.get("manufacturer")
    )

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    if not cert_org:
        raise ValueError(
            "cert_org is required"
        )

    previous_primary: (
        dict[str, Any] | None
    ) = None

    conn = get_conn()

    try:
        conn.execute(
            "BEGIN IMMEDIATE"
        )

        if action in {
            "UPDATE_CURRENT",
            "REPLACE_CURRENT",
        }:
            row = conn.execute(
                """
                SELECT *
                FROM material_certificate_history
                WHERE pmf_row_pos = ?
                  AND pmf_depth = ?
                  AND status = 'ACTIVE'
                  AND is_primary = 1
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    pmf_row_pos,
                    pmf_depth,
                ),
            ).fetchone()

            if row:
                previous_primary = dict(
                    row
                )

                conn.execute(
                    """
                    UPDATE material_certificate_history
                    SET status = 'SUPERSEDED',
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        now,
                        int(
                            previous_primary["id"]
                        ),
                    ),
                )

            certificate_role = "PRIMARY"
            is_primary = 1

            supersedes_id = (
                int(previous_primary["id"])
                if previous_primary
                else None
            )

        else:
            duplicate = conn.execute(
                """
                SELECT *
                FROM material_certificate_history
                WHERE pmf_row_pos = ?
                  AND pmf_depth = ?
                  AND status = 'ACTIVE'
                  AND is_primary = 0
                  AND cert_org = ?
                  AND cert_no = ?
                  AND expiry_date = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    pmf_row_pos,
                    pmf_depth,
                    cert_org,
                    cert_no,
                    expiry_date,
                ),
            ).fetchone()

            if duplicate:
                conn.commit()

                return {
                    "ok": True,
                    "changed": False,
                    "action": action,
                    "status": (
                        "DUPLICATE_ACTIVE"
                    ),
                    "inserted_id": int(
                        duplicate["id"]
                    ),
                    "previous_primary_id": None,
                    "previous_primary_status": "",
                }

            certificate_role = "SECONDARY"
            is_primary = 0
            supersedes_id = None

        cur = conn.execute(
            """
            INSERT INTO material_certificate_history (
                ocr_job_id,
                request_id,
                pmf_row_pos,
                pmf_depth,
                cert_org,
                cert_no,
                expiry_date,
                manufacturer,
                source_path,
                target_path,
                certificate_role,
                status,
                change_action,
                is_primary,
                supersedes_id,
                created_at,
                updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                payload.get("ocr_job_id"),
                _clean(
                    payload.get("request_id")
                ),
                pmf_row_pos,
                pmf_depth,
                cert_org,
                cert_no,
                expiry_date,
                manufacturer,
                _clean(
                    payload.get("source_path")
                ),
                _clean(
                    payload.get("target_path")
                ),
                certificate_role,
                "ACTIVE",
                action,
                is_primary,
                supersedes_id,
                now,
                now,
            ),
        )

        inserted_id = int(
            cur.lastrowid
        )

        conn.commit()

        return {
            "ok": True,
            "changed": True,
            "action": action,
            "status": "INSERTED",
            "inserted_id": inserted_id,
            "previous_primary_id": (
                int(previous_primary["id"])
                if previous_primary
                else None
            ),
            "previous_primary_status": (
                _clean(
                    previous_primary.get(
                        "status"
                    )
                )
                if previous_primary
                else ""
            ),
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def rollback_material_certificate_history_action(
    result: dict[str, Any] | None,
) -> None:
    if not result:
        return

    if not result.get("changed"):
        return

    inserted_id = result.get(
        "inserted_id"
    )

    previous_primary_id = result.get(
        "previous_primary_id"
    )

    previous_primary_status = (
        _clean(
            result.get(
                "previous_primary_status"
            )
        )
        or "ACTIVE"
    )

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    conn = get_conn()

    try:
        conn.execute(
            "BEGIN IMMEDIATE"
        )

        if inserted_id is not None:
            conn.execute(
                """
                DELETE FROM material_certificate_history
                WHERE id = ?
                """,
                (
                    int(inserted_id),
                ),
            )

        if previous_primary_id is not None:
            conn.execute(
                """
                UPDATE material_certificate_history
                SET status = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    previous_primary_status,
                    now,
                    int(
                        previous_primary_id
                    ),
                ),
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def get_confirmed_history_for_job(
    ocr_job_id: int,
) -> dict[str, Any] | None:
    ensure_filing_tables()

    conn = get_conn()

    try:
        row = conn.execute(
            '''
            SELECT *
            FROM certificate_filing_history
            WHERE ocr_job_id = ?
              AND status IN (
                  'CONFIRMED',
                  'REPLACED',
                  'SECONDARY_ADDED',
                  'DUPLICATE_SKIPPED'
              )
            ORDER BY id DESC
            LIMIT 1
            ''',
            (
                int(ocr_job_id),
            ),
        ).fetchone()

        return (
            dict(row)
            if row
            else None
        )

    finally:
        conn.close()


def list_filing_history(limit: int = 100) -> dict[str, Any]:
    ensure_filing_tables()
    limit = max(1, min(int(limit), 500))
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM certificate_filing_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    result_rows: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        for key in ("pmf_update_json", "warning_json"):
            default_value = {} if key == "pmf_update_json" else []
            raw_value = data.get(key)
            try:
                parsed_value = json.loads(raw_value) if raw_value else default_value
            except Exception:
                parsed_value = default_value
            data[key.removesuffix("_json")] = parsed_value
            data.pop(key, None)
        result_rows.append(data)

    return {"ok": True, "count": len(result_rows), "rows": result_rows}
