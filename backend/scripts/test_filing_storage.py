from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.certificate_filing_service import (
    copy_certificate_atomically,
    preview_certificate_filing,
)
from app.services.filing_name_service import FilingNameInput
from app.services.storage_path_service import get_storage_root_status


def make_test_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"%PDF-1.4\n"
        b"% filing storage test\n"
        b"1 0 obj\n"
        b"<< /Type /Catalog >>\n"
        b"endobj\n"
        b"%%EOF\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--copy", action="store_true")
    parser.add_argument("--source")
    args = parser.parse_args()

    status = get_storage_root_status()
    source = (
        Path(args.source)
        if args.source
        else Path(r"D:\halal_web_runtime\test_input\filing_test.pdf")
    )

    if not source.exists():
        make_test_pdf(source)

    naming = FilingNameInput(
        material_no="81",
        material_name_en="Onion flavor oil",
        manufacturer="SHIN YANG Poseung branch Co.,Ltd.",
        supplier="신양포스팅점",
        cert_org="MUI",
        expiry_date="2025-12-21",
        source_extension=source.suffix or ".pdf",
    )

    preview = preview_certificate_filing(source, naming)

    print("=== 파일자동분류 저장경로 테스트 ===")
    print(json.dumps(status.to_dict(), ensure_ascii=False, indent=2))
    print(json.dumps(preview.to_dict(), ensure_ascii=False, indent=2))

    if not args.copy:
        print("FILING_PREVIEW_OK")
        print("실제 복사 테스트: python .\\scripts\\test_filing_storage.py --copy")
        return

    first = copy_certificate_atomically(source, naming)
    second = copy_certificate_atomically(source, naming)

    print(json.dumps(first.to_dict(), ensure_ascii=False, indent=2))
    print(json.dumps(second.to_dict(), ensure_ascii=False, indent=2))

    if first.status not in {"COPIED", "DUPLICATE_SKIPPED"}:
        raise SystemExit(1)

    if second.status != "DUPLICATE_SKIPPED":
        raise SystemExit(1)

    print("FILING_STORAGE_TEST_OK")


if __name__ == "__main__":
    main()
