"""확정 실행. 파일 복사 → PMF 갱신 → 이력 기록을 한 흐름으로 묶고,
중간에 실패하면 앞 단계를 되돌린다."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import copy

from app.services.certificate_filing_service import copy_certificate_atomically
from app.services.filing_name_service import FilingNameInput, get_halal_raw_material_root
from app.services.ocr_service import get_ocr_job
from app.services.pmf_filing_service import restore_pmf_backup, update_pmf_certificate_fields

from app.services.filing.helpers import (
    _clean,
    resolve_filing_status,
)
from app.services.filing.history import (
    _insert_history,
    apply_material_certificate_history_action,
    get_active_material_certificates,
    insert_material_certificate_history,
    rollback_material_certificate_history_action,
)
from app.services.filing.gate import (
    validate_change_decision_for_confirm,
)
from app.services.filing.preview import (
    preview_filing_workflow,
)


def confirm_filing_workflow(
    ocr_job_id: int,
    pmf_row_pos: int,
    pmf_depth: int = 0,
    overwrite: bool = False,
    force: bool = False,
    allow_date_regression: bool = False,
    change_action: str = "",
) -> dict[str, Any]:
    preview = preview_filing_workflow(
        ocr_job_id=ocr_job_id,
        pmf_row_pos=pmf_row_pos,
        pmf_depth=pmf_depth,
    )

    if preview.get("hard_blockers"):
        raise ValueError(
            " / ".join(
                preview["hard_blockers"]
            )
        )

    change_gate = (
        validate_change_decision_for_confirm(
            preview=preview,
            change_action=change_action,
        )
    )

    if (
        preview.get("blockers")
        and not force
    ):
        raise ValueError(
            " / ".join(
                preview["blockers"]
            )
        )

    job = get_ocr_job(
        int(ocr_job_id)
    )

    material = preview[
        "pmf_material"
    ]

    certificate = preview[
        "certificate"
    ]

    request_context = (
        preview.get("request_context")
        or {}
    )

    mail_item = (
        request_context.get(
            "matched_mail_item"
        )
        or {}
    )

    request_id = request_context.get(
        "request_id",
        "",
    )

    pmf_expiry = certificate.get(
        "expiry_date",
        "",
    )

    if (
        certificate.get("cert_org")
        == "BPJPH"
    ):
        pmf_expiry = _clean(
            mail_item.get(
                "planned_expiry"
            )
        )

    source_path = Path(
        str(
            job.get("source_path")
            or ""
        )
    )

    naming_input = FilingNameInput(
        material_no=material[
            "material_no"
        ],
        material_name_en=material[
            "english_name"
        ],
        manufacturer=material[
            "maker"
        ],
        supplier=material[
            "supplier"
        ],
        cert_org=certificate.get(
            "cert_org",
            "",
        ),
        expiry_date=certificate.get(
            "expiry_date",
            "",
        ),
        source_extension=(
            source_path.suffix
            or job.get("file_ext")
            or ".pdf"
        ),
    )

    copy_result = None
    pmf_result = None
    material_history_result = None
    legacy_primary_history_id = None

    try:
        copy_result = (
            copy_certificate_atomically(
                source_path=source_path,
                naming_input=naming_input,
                root=(
                    get_halal_raw_material_root()
                ),
                overwrite=overwrite,
            )
        )

        resolved_action = change_gate[
            "change_action"
        ]

        if (
            resolved_action
            != "ADD_SECONDARY"
        ):
            pmf_result = (
                update_pmf_certificate_fields(
                    row_pos=pmf_row_pos,
                    depth=pmf_depth,
                    cert_org=certificate.get(
                        "cert_org",
                        "",
                    ),
                    cert_no=certificate.get(
                        "cert_no",
                        "",
                    ),
                    expiry_date=pmf_expiry,
                    allow_date_regression=(
                        allow_date_regression
                    ),
                )
            )

        active_certificates = (
            get_active_material_certificates(
                pmf_row_pos=pmf_row_pos,
                pmf_depth=pmf_depth,
            )
        )

        has_active_primary = any(
            int(
                item.get(
                    "is_primary"
                )
                or 0
            )
            == 1
            for item in active_certificates
        )

        current_org = _clean(
            material.get("org")
        ).upper()

        current_cert_no = _clean(
            material.get("cert_no")
        )

        current_expiry = _clean(
            material.get(
                "expiry_date"
            )
        )

        if (
            not has_active_primary
            and (
                current_org
                or current_cert_no
                or current_expiry
            )
        ):
            legacy_primary_history_id = (
                insert_material_certificate_history(
                    {
                        "ocr_job_id": None,
                        "request_id": (
                            request_id
                        ),
                        "pmf_row_pos": (
                            pmf_row_pos
                        ),
                        "pmf_depth": (
                            pmf_depth
                        ),
                        "cert_org": (
                            current_org
                        ),
                        "cert_no": (
                            current_cert_no
                        ),
                        "expiry_date": (
                            current_expiry
                        ),
                        "manufacturer": (
                            material.get(
                                "maker",
                                "",
                            )
                        ),
                        "source_path": "",
                        "target_path": "",
                        "certificate_role": (
                            "PRIMARY"
                        ),
                        "status": "ACTIVE",
                        "change_action": (
                            "LEGACY_IMPORT"
                        ),
                        "is_primary": True,
                    }
                )
            )

        material_history_result = (
            apply_material_certificate_history_action(
                {
                    "ocr_job_id": (
                        ocr_job_id
                    ),
                    "request_id": (
                        request_id
                    ),
                    "pmf_row_pos": (
                        pmf_row_pos
                    ),
                    "pmf_depth": (
                        pmf_depth
                    ),
                    "cert_org": (
                        certificate.get(
                            "cert_org",
                            "",
                        )
                    ),
                    "cert_no": (
                        certificate.get(
                            "cert_no",
                            "",
                        )
                    ),
                    "expiry_date": (
                        pmf_expiry
                    ),
                    "manufacturer": (
                        certificate.get(
                            "manufacturer"
                        )
                        or material.get(
                            "maker",
                            "",
                        )
                    ),
                    "source_path": (
                        str(source_path)
                    ),
                    "target_path": (
                        copy_result.target_path
                    ),
                },
                resolved_action,
            )
        )

        status = resolve_filing_status(
            copy_status=copy_result.status,
            change_action=resolved_action,
        )

        pmf_update_payload = (
            pmf_result.to_dict()
            if pmf_result
            else {
                "skipped": True,
                "reason": (
                    "ADD_SECONDARY"
                ),
            }
        )

        history_id = _insert_history(
            {
                "ocr_job_id": (
                    ocr_job_id
                ),
                "request_id": (
                    request_id
                ),
                "pmf_row_pos": (
                    pmf_row_pos
                ),
                "pmf_depth": (
                    pmf_depth
                ),
                "source_path": (
                    str(source_path)
                ),
                "target_path": (
                    copy_result.target_path
                ),
                "cert_org": (
                    certificate.get(
                        "cert_org",
                        "",
                    )
                ),
                "cert_no": (
                    certificate.get(
                        "cert_no",
                        "",
                    )
                ),
                "expiry_date": (
                    pmf_expiry
                ),
                "status": status,
                "copy_status": (
                    copy_result.status
                ),
                "pmf_update": (
                    pmf_update_payload
                ),
                "warnings": (
                    preview.get(
                        "warnings"
                    )
                    or []
                ),
            }
        )

        return {
            "ok": True,
            "history_id": history_id,
            "status": status,
            "change_gate": (
                change_gate
            ),
            "copy": (
                copy_result.to_dict()
            ),
            "pmf_update": (
                pmf_update_payload
            ),
            "material_certificate_history": (
                material_history_result
            ),
            "legacy_primary_history_id": (
                legacy_primary_history_id
            ),
            "preview": preview,
        }

    except Exception as exc:
        if material_history_result:
            try:
                rollback_material_certificate_history_action(
                    material_history_result
                )
            except Exception:
                pass

        if pmf_result:
            try:
                restore_pmf_backup(
                    pmf_result.backup_path,
                    pmf_result.pmf_path,
                )
            except Exception:
                pass

        if (
            copy_result
            and (
                copy_result.status
                == "COPIED"
            )
        ):
            Path(
                copy_result.target_path
            ).unlink(
                missing_ok=True
            )

        _insert_history(
            {
                "ocr_job_id": (
                    ocr_job_id
                ),
                "request_id": (
                    request_id
                ),
                "pmf_row_pos": (
                    pmf_row_pos
                ),
                "pmf_depth": (
                    pmf_depth
                ),
                "source_path": (
                    str(source_path)
                ),
                "target_path": (
                    copy_result.target_path
                    if copy_result
                    else ""
                ),
                "cert_org": (
                    certificate.get(
                        "cert_org",
                        "",
                    )
                ),
                "cert_no": (
                    certificate.get(
                        "cert_no",
                        "",
                    )
                ),
                "expiry_date": (
                    pmf_expiry
                ),
                "status": "ERROR",
                "copy_status": (
                    copy_result.status
                    if copy_result
                    else ""
                ),
                "pmf_update": (
                    pmf_result.to_dict()
                    if pmf_result
                    else {}
                ),
                "warnings": (
                    preview.get(
                        "warnings"
                    )
                    or []
                ),
                "error_message": (
                    str(exc)
                ),
            }
        )

        raise
