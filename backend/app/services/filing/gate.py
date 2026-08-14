"""확정 게이트.

자동 판정을 사람이 임의로 뒤집지 못하게 막고, 검토가 필요한 건은
선택된 조치(REPLACE_CURRENT / ADD_SECONDARY)가 허용 목록에 있는지 확인한다."""

from __future__ import annotations

from typing import Any

from app.services.filing.helpers import (
    _clean,
)


def validate_change_decision_for_confirm(
    preview: dict[str, Any],
    change_action: str = "",
) -> dict[str, str]:
    decision = preview.get("change_decision") or {}
    decision_code = _clean(
        decision.get("decision_code")
    ).upper()

    requested_action = _clean(
        change_action
    ).upper()

    aliases = {
        "APPROVE_RENEWAL": "UPDATE_CURRENT",
        "REGISTER_AS_PRIMARY": "UPDATE_CURRENT",
    }

    requested_action = aliases.get(
        requested_action,
        requested_action,
    )

    if decision.get("blocked"):
        raise ValueError(
            "Change decision blocks confirmation: "
            + decision_code
        )

    if decision.get("requires_review"):
        review_options = {
            aliases.get(value, value)
            for value in (
                _clean(item).upper()
                for item in (
                    decision.get("review_options")
                    or []
                )
                if _clean(item)
            )
        }

        if not requested_action:
            raise ValueError(
                "change_action is required for review decision: "
                + decision_code
            )

        if (
            review_options
            and requested_action not in review_options
        ):
            raise ValueError(
                "Invalid change_action for "
                + decision_code
                + ": "
                + requested_action
            )

        resolved_action = requested_action

    else:
        automatic_action = _clean(
            decision.get("auto_action")
        ).upper()

        automatic_action = aliases.get(
            automatic_action,
            automatic_action,
        )

        if (
            requested_action
            and requested_action != automatic_action
        ):
            raise ValueError(
                "change_action cannot override automatic decision: "
                + decision_code
            )

        resolved_action = automatic_action

    allowed_actions = {
        "UPDATE_CURRENT",
        "REPLACE_CURRENT",
        "ADD_SECONDARY",
    }

    if resolved_action not in allowed_actions:
        raise ValueError(
            "The selected action does not confirm the certificate: "
            + (
                resolved_action
                or decision_code
            )
        )

    return {
        "decision_code": decision_code,
        "change_action": resolved_action,
    }
