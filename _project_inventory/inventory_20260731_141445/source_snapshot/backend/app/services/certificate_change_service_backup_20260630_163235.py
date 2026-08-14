from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any, Mapping


UNKNOWN_ORGS = {
    "",
    "UNKNOWN",
    "UNDETECTED",
    "NO_TEXT",
}

EXPIRY_OPTIONAL_ORGS = {
    "BPJPH",
}


def _clean(value: Any) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip()


def _normal(value: Any) -> str:
    return re.sub(
        r"[^A-Z0-9]+",
        "",
        _clean(value).upper(),
    )


def _value(
    data: Mapping[str, Any] | None,
    *keys: str,
) -> str:
    if not data:
        return ""

    for key in keys:
        if key in data and data[key] is not None:
            return _clean(data[key])

    return ""


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = _clean(value)

    if not text:
        return None

    text = text[:10].replace(".", "-").replace("/", "-")

    try:
        return datetime.strptime(
            text,
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return None


def _field_change(
    before: str,
    after: str,
) -> dict[str, Any]:
    return {
        "before": before,
        "after": after,
        "changed": _normal(before) != _normal(after),
    }


def _make_result(
    *,
    decision_code: str,
    requires_review: bool,
    blocked: bool,
    auto_action: str,
    can_update_pmf: bool,
    reasons: list[str],
    changes: dict[str, Any],
    missing_fields: list[str],
    review_options: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "decision_code": decision_code,
        "requires_review": requires_review,
        "blocked": blocked,
        "auto_action": auto_action,
        "can_update_pmf": can_update_pmf,
        "review_options": review_options or [],
        "reasons": reasons,
        "missing_fields": missing_fields,
        "changes": changes,
    }


def classify_certificate_change(
    current: Mapping[str, Any] | None,
    incoming: Mapping[str, Any],
    *,
    product_match: bool,
    manufacturer_match: bool | None = None,
    current_active: bool = True,
) -> dict[str, Any]:
    current_org = _value(
        current,
        "cert_org",
        "org",
    )
    current_no = _value(
        current,
        "cert_no",
        "certificate_no",
    )
    current_expiry = _value(
        current,
        "expiry_date",
        "valid_end",
    )
    current_manufacturer = _value(
        current,
        "manufacturer",
        "maker",
    )

    incoming_org = _value(
        incoming,
        "cert_org",
        "org",
    )
    incoming_no = _value(
        incoming,
        "cert_no",
        "certificate_no",
    )
    incoming_expiry = _value(
        incoming,
        "expiry_date",
        "valid_end",
    )
    incoming_manufacturer = _value(
        incoming,
        "manufacturer",
        "maker",
    )

    changes = {
        "cert_org": _field_change(
            current_org,
            incoming_org,
        ),
        "cert_no": _field_change(
            current_no,
            incoming_no,
        ),
        "expiry_date": _field_change(
            current_expiry,
            incoming_expiry,
        ),
        "manufacturer": _field_change(
            current_manufacturer,
            incoming_manufacturer,
        ),
    }

    missing_fields: list[str] = []

    if not incoming_no:
        missing_fields.append("cert_no")

    if (
        not incoming_expiry
        and incoming_org.upper() not in EXPIRY_OPTIONAL_ORGS
    ):
        missing_fields.append("expiry_date")

    if not incoming_manufacturer:
        missing_fields.append("manufacturer")

    if not product_match:
        return _make_result(
            decision_code="WRONG_CERTIFICATE",
            requires_review=True,
            blocked=True,
            auto_action="BLOCK",
            can_update_pmf=False,
            reasons=[
                "The certificate product does not match the requested material.",
            ],
            changes=changes,
            missing_fields=missing_fields,
            review_options=[
                "REJECT",
                "MANUAL_REASSIGN",
            ],
        )

    if manufacturer_match is None:
        if current_manufacturer and incoming_manufacturer:
            manufacturer_match = (
                _normal(current_manufacturer)
                == _normal(incoming_manufacturer)
            )

    if manufacturer_match is False:
        return _make_result(
            decision_code="MANUFACTURER_CHANGED",
            requires_review=True,
            blocked=True,
            auto_action="BLOCK",
            can_update_pmf=False,
            reasons=[
                "The manufacturer differs from the current PMF manufacturer.",
            ],
            changes=changes,
            missing_fields=missing_fields,
            review_options=[
                "APPROVE_MANUFACTURER_CHANGE",
                "REJECT",
            ],
        )

    if incoming_org.upper() in UNKNOWN_ORGS:
        return _make_result(
            decision_code="OCR_REVIEW_REQUIRED",
            requires_review=True,
            blocked=True,
            auto_action="REVIEW",
            can_update_pmf=False,
            reasons=[
                "The certification authority could not be determined.",
            ],
            changes=changes,
            missing_fields=missing_fields,
            review_options=[
                "MANUAL_CORRECTION",
                "REJECT",
            ],
        )

    current_exists = any(
        (
            current_org,
            current_no,
            current_expiry,
            current_manufacturer,
        )
    )

    if not current_exists:
        return _make_result(
            decision_code="NEW_CERTIFICATE",
            requires_review=True,
            blocked=False,
            auto_action="REVIEW",
            can_update_pmf=False,
            reasons=[
                "No existing certificate information was found.",
            ],
            changes=changes,
            missing_fields=missing_fields,
            review_options=[
                "REGISTER_AS_PRIMARY",
                "REJECT",
            ],
        )

    if _normal(current_org) != _normal(incoming_org):
        return _make_result(
            decision_code="AUTHORITY_CHANGE_REVIEW",
            requires_review=True,
            blocked=False,
            auto_action="REVIEW",
            can_update_pmf=False,
            reasons=[
                f"Certification authority changed: "
                f"{current_org} -> {incoming_org}",
            ],
            changes=changes,
            missing_fields=missing_fields,
            review_options=[
                "REPLACE_CURRENT",
                "ADD_SECONDARY",
                "HOLD",
                "REJECT",
            ],
        )

    if missing_fields:
        return _make_result(
            decision_code="INCOMPLETE_CERTIFICATE_REVIEW",
            requires_review=True,
            blocked=False,
            auto_action="REVIEW",
            can_update_pmf=False,
            reasons=[
                "Required certificate fields are missing.",
            ],
            changes=changes,
            missing_fields=missing_fields,
            review_options=[
                "MANUAL_CORRECTION",
                "KEEP_EXISTING_VALUE",
                "REJECT",
            ],
        )

    same_cert_no = (
        _normal(current_no)
        == _normal(incoming_no)
    )

    current_date = _parse_date(current_expiry)
    incoming_date = _parse_date(incoming_expiry)

    if same_cert_no:
        if current_expiry == incoming_expiry:
            return _make_result(
                decision_code="DUPLICATE",
                requires_review=False,
                blocked=False,
                auto_action="SKIP",
                can_update_pmf=False,
                reasons=[
                    "Authority, certificate number and expiry date are unchanged.",
                ],
                changes=changes,
                missing_fields=missing_fields,
            )

        if current_date and incoming_date:
            if incoming_date > current_date:
                return _make_result(
                    decision_code="SAME_AUTHORITY_RENEWAL",
                    requires_review=False,
                    blocked=False,
                    auto_action="UPDATE_CURRENT",
                    can_update_pmf=True,
                    reasons=[
                        "The same certificate was renewed with a later expiry date.",
                    ],
                    changes=changes,
                    missing_fields=missing_fields,
                )

            if incoming_date < current_date:
                return _make_result(
                    decision_code="OLDER_CERTIFICATE",
                    requires_review=True,
                    blocked=False,
                    auto_action="REVIEW",
                    can_update_pmf=False,
                    reasons=[
                        "The incoming certificate expires earlier than the current certificate.",
                    ],
                    changes=changes,
                    missing_fields=missing_fields,
                    review_options=[
                        "KEEP_CURRENT",
                        "REGISTER_AS_HISTORY",
                        "REJECT",
                    ],
                )

        return _make_result(
            decision_code="SAME_AUTHORITY_UPDATE_REVIEW",
            requires_review=True,
            blocked=False,
            auto_action="REVIEW",
            can_update_pmf=False,
            reasons=[
                "The authority and certificate number match, but the expiry change requires review.",
            ],
            changes=changes,
            missing_fields=missing_fields,
            review_options=[
                "UPDATE_CURRENT",
                "KEEP_CURRENT",
                "REJECT",
            ],
        )

    return _make_result(
        decision_code="CERTIFICATE_NUMBER_CHANGED",
        requires_review=True,
        blocked=False,
        auto_action="REVIEW",
        can_update_pmf=False,
        reasons=[
            f"Certificate number changed: "
            f"{current_no} -> {incoming_no}",
        ],
        changes=changes,
        missing_fields=missing_fields,
        review_options=[
            "APPROVE_RENEWAL",
            "ADD_SECONDARY",
            "KEEP_CURRENT",
            "REJECT",
        ],
    )
