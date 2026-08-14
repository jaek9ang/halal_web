from app.services.certificate_change_service import (
    classify_certificate_change,
)


CURRENT = {
    "cert_org": "HQC",
    "cert_no": "2021-08077",
    "expiry_date": "2025-06-30",
    "manufacturer": "Novozymes AS",
}


CASES = [
    {
        "name": "same authority renewal",
        "incoming": {
            "cert_org": "HQC",
            "cert_no": "2021-08077",
            "expiry_date": "2028-07-01",
            "manufacturer": "Novozymes AS",
        },
        "product_match": True,
        "manufacturer_match": True,
        "expected": "SAME_AUTHORITY_RENEWAL",
    },
    {
        "name": "authority changed",
        "incoming": {
            "cert_org": "HCA",
            "cert_no": "HCA-2026-001",
            "expiry_date": "2028-07-01",
            "manufacturer": "Novozymes AS",
        },
        "product_match": True,
        "manufacturer_match": True,
        "expected": "AUTHORITY_CHANGE_REVIEW",
    },
    {
        "name": "certificate number changed",
        "incoming": {
            "cert_org": "HQC",
            "cert_no": "2026-12345",
            "expiry_date": "2028-07-01",
            "manufacturer": "Novozymes AS",
        },
        "product_match": True,
        "manufacturer_match": True,
        "expected": "CERTIFICATE_NUMBER_CHANGED",
    },
    {
        "name": "duplicate",
        "incoming": dict(CURRENT),
        "product_match": True,
        "manufacturer_match": True,
        "expected": "DUPLICATE",
    },
    {
        "name": "older certificate",
        "incoming": {
            "cert_org": "HQC",
            "cert_no": "2021-08077",
            "expiry_date": "2024-06-30",
            "manufacturer": "Novozymes AS",
        },
        "product_match": True,
        "manufacturer_match": True,
        "expected": "OLDER_CERTIFICATE",
    },
    {
        "name": "manufacturer changed",
        "incoming": {
            "cert_org": "HQC",
            "cert_no": "2021-08077",
            "expiry_date": "2028-07-01",
            "manufacturer": "Another Company",
        },
        "product_match": True,
        "manufacturer_match": False,
        "expected": "MANUFACTURER_CHANGED",
    },
    {
        "name": "wrong product",
        "incoming": {
            "cert_org": "HQC",
            "cert_no": "2021-08077",
            "expiry_date": "2028-07-01",
            "manufacturer": "Novozymes AS",
        },
        "product_match": False,
        "manufacturer_match": True,
        "expected": "WRONG_CERTIFICATE",
    },
    {
        "name": "unknown authority",
        "incoming": {
            "cert_org": "UNKNOWN",
            "cert_no": "",
            "expiry_date": "",
            "manufacturer": "",
        },
        "product_match": True,
        "manufacturer_match": None,
        "expected": "OCR_REVIEW_REQUIRED",
    },
]


for case in CASES:
    result = classify_certificate_change(
        CURRENT,
        case["incoming"],
        product_match=case["product_match"],
        manufacturer_match=case["manufacturer_match"],
    )

    actual = result["decision_code"]

    print(
        f"{case['name']}: "
        f"{actual}"
    )

    assert actual == case["expected"], (
        f"{case['name']} failed: "
        f"expected={case['expected']}, actual={actual}"
    )


print("CERTIFICATE_CHANGE_RULES_OK")
