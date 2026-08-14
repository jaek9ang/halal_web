from __future__ import annotations

import ast
import shutil
from datetime import datetime
from pathlib import Path


TARGET = Path(
    "backend/app/services/"
    "certificate_filing_workflow_service.py"
)


OLD_INCOMING_BLOCK = '''    incoming_certificate = {
        "cert_org": cert_values.get("cert_org", ""),
        "cert_no": cert_values.get("cert_no", ""),
        "expiry_date": cert_values.get("expiry_date", ""),
        "manufacturer": incoming_manufacturer,
    }
'''


NEW_INCOMING_BLOCK = '''    pmf_expiry = cert_values.get(
        "expiry_date",
        "",
    )

    if cert_values.get("cert_org") == "BPJPH":
        pmf_expiry = _clean(
            (mail_item or {}).get(
                "planned_expiry"
            )
        )

    incoming_certificate = {
        "cert_org": cert_values.get(
            "cert_org",
            "",
        ),
        "cert_no": cert_values.get(
            "cert_no",
            "",
        ),
        "expiry_date": pmf_expiry,
        "manufacturer": incoming_manufacturer,
    }
'''


OLD_LATE_EXPIRY_BLOCK = '''    pmf_expiry = cert_values.get("expiry_date", "")
    if cert_values.get("cert_org") == "BPJPH":
        pmf_expiry = _clean((mail_item or {}).get("planned_expiry"))

'''


OLD_RETURN_BLOCK = '''        "certificate": cert_values,
        "request_context": {
'''


NEW_RETURN_BLOCK = '''        "certificate": cert_values,
        "effective_certificate": incoming_certificate,
        "request_context": {
'''


def replace_once(
    source: str,
    old: str,
    new: str,
    label: str,
) -> str:
    count = source.count(old)

    if count != 1:
        raise RuntimeError(
            f"{label}: expected 1 match, "
            f"found {count}"
        )

    return source.replace(
        old,
        new,
        1,
    )


def main() -> None:
    if not TARGET.exists():
        raise FileNotFoundError(TARGET)

    source = TARGET.read_text(
        encoding="utf-8-sig",
    )

    source = replace_once(
        source,
        OLD_INCOMING_BLOCK,
        NEW_INCOMING_BLOCK,
        "incoming certificate block",
    )

    source = replace_once(
        source,
        OLD_LATE_EXPIRY_BLOCK,
        "",
        "late BPJPH expiry block",
    )

    source = replace_once(
        source,
        OLD_RETURN_BLOCK,
        NEW_RETURN_BLOCK,
        "preview return block",
    )

    ast.parse(
        source,
        filename=str(TARGET),
    )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup = TARGET.with_name(
        TARGET.name
        + ".backup_"
        + stamp
    )

    shutil.copy2(
        TARGET,
        backup,
    )

    TARGET.write_text(
        source,
        encoding="utf-8",
    )

    print("UPDATED:", TARGET)
    print("BACKUP :", backup)
    print("BPJPH_EFFECTIVE_EXPIRY_PATCH_OK")


if __name__ == "__main__":
    main()
