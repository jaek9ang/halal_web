from app.services import (
    certificate_filing_workflow_service as workflow,
)


renewal = {
    "change_decision": {
        "decision_code": "SAME_AUTHORITY_RENEWAL",
        "requires_review": False,
        "blocked": False,
        "auto_action": "UPDATE_CURRENT",
        "review_options": [],
    }
}

authority_change = {
    "change_decision": {
        "decision_code": "AUTHORITY_CHANGE_REVIEW",
        "requires_review": True,
        "blocked": False,
        "auto_action": "REVIEW",
        "review_options": [
            "REPLACE_CURRENT",
            "ADD_SECONDARY",
            "HOLD",
            "REJECT",
        ],
    }
}


renewal_result = (
    workflow.validate_change_decision_for_confirm(
        renewal
    )
)

secondary_result = (
    workflow.validate_change_decision_for_confirm(
        authority_change,
        "ADD_SECONDARY",
    )
)

replace_result = (
    workflow.validate_change_decision_for_confirm(
        authority_change,
        "REPLACE_CURRENT",
    )
)

assert renewal_result["change_action"] == "UPDATE_CURRENT"
assert secondary_result["change_action"] == "ADD_SECONDARY"
assert replace_result["change_action"] == "REPLACE_CURRENT"

try:
    workflow.validate_change_decision_for_confirm(
        renewal,
        "ADD_SECONDARY",
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "Automatic decision override was allowed"
    )

try:
    workflow.validate_change_decision_for_confirm(
        authority_change,
        "HOLD",
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "HOLD was treated as confirmation"
    )

print("RENEWAL:", renewal_result)
print("SECONDARY:", secondary_result)
print("REPLACE:", replace_result)
print("CONFIRM_HISTORY_GATE_OK")
