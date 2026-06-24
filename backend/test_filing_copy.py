from __future__ import annotations

from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.certificate_filing_service import copy_certificate_atomically
from app.services.filing_name_service import FilingNameInput


def main() -> None:
    test_root = Path(r"C:\TEMP\halal_filing_test")
    test_root.mkdir(parents=True, exist_ok=True)

    source_file = test_root / "source_test.pdf"
    source_file.write_bytes(
        b"%PDF-1.4\n"
        b"% HALAL FILING TEST\n"
        b"1 0 obj\n"
        b"<< /Type /Catalog >>\n"
        b"endobj\n"
        b"%%EOF\n"
    )

    naming_input = FilingNameInput(
        material_no="81",
        material_name_en="Onion flavor oil",
        manufacturer="SHIN YANG Poseung branch Co.,Ltd.",
        supplier="신양포스팅점",
        cert_org="MUI",
        expiry_date="2025-12-21",
        source_extension=".pdf",
    )

    print("=== 첫 번째 복사 ===")
    first_result = copy_certificate_atomically(
        source_path=source_file,
        naming_input=naming_input,
        root=test_root,
        overwrite=False,
    )
    print(first_result.to_dict())

    print()
    print("=== 동일 파일 재실행 ===")
    second_result = copy_certificate_atomically(
        source_path=source_file,
        naming_input=naming_input,
        root=test_root,
        overwrite=False,
    )
    print(second_result.to_dict())

    print()
    print("=== 생성 파일 확인 ===")
    for path in sorted(test_root.rglob("*")):
        print(path)


if __name__ == "__main__":
    main()
