from __future__ import annotations

from app.services.mail_request_item_service import select_mail_item_for_ocr_job


def run_case(name, filename, cert_org, items, expected_index, expected_auto):
    job = {"filename": filename, "source_path": filename}
    context = {"attachment": {}, "mail_items": items, "mail_log": {}}
    cert = {"cert_org": cert_org, "cert_no": ""}
    result = select_mail_item_for_ocr_job(context, job, cert)
    selected = result.get("selected_mail_item") or {}
    actual_index = selected.get("item_index")
    print(name, actual_index, result.get("auto_selectable"), result.get("hard_blockers"))
    assert actual_index == expected_index, (name, actual_index, expected_index)
    assert bool(result.get("auto_selectable")) is expected_auto, (name, result)


def main():
    items = [
        {"item_index": 1, "material_name": "L-글루타민산", "english_name": "L-Glutamic Acid", "org": "MUI", "cert_no": "OLD1"},
        {"item_index": 2, "material_name": "정백당", "english_name": "Refined White Sugar", "org": "KMF", "cert_no": "OLD2"},
        {"item_index": 3, "material_name": "NU55-50", "english_name": "NU55-50", "org": "LLS-ISA", "cert_no": "OLD3"},
    ]

    run_case(
        "attachment 002 -> item 2",
        "HALAL-REQ-X__002__HALAL Certificate.pdf",
        "KMF",
        items,
        2,
        True,
    )
    run_case(
        "attachment 003 -> item 3 with ISA alias",
        "HALAL-REQ-X__003__NU55_할랄서류.pdf",
        "ISA",
        items,
        3,
        True,
    )
    run_case(
        "org mismatch blocks",
        "HALAL-REQ-X__001__L-글루탐산.pdf",
        "ARA",
        items,
        1,
        False,
    )
    print("phase2.1 matching tests passed")


if __name__ == "__main__":
    main()
