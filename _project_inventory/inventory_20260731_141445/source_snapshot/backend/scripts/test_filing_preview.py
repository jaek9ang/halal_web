from pathlib import Path
import sys

# backend 폴더를 Python 모듈 검색 경로에 추가
BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.certificate_filing_service import preview_certificate_filing
from app.services.filing_name_service import FilingNameInput


def main() -> None:
    mui = FilingNameInput("81", "Onion flavor oil", "SHIN YANG Poseung branch Co.,Ltd.", "신양포스팅점", "MUI", "2025-12-21", ".pdf")
    p1 = preview_certificate_filing(Path("sample.pdf"), mui, root=Path(r"C:\TEMP\halal_filing_test"))
    print("MUI folder:", p1.target_folder)
    print("MUI file  :", p1.target_filename)

    bpjph = FilingNameInput("82", "Glycine", "HEBEI HUAYANG BIOLOGICAL TECHNOLOGY CO.,LTD", "신양포스팅점", "BPJPH", "2027-02-17", ".pdf")
    p2 = preview_certificate_filing(Path("bpjph.pdf"), bpjph, root=Path(r"C:\TEMP\halal_filing_test"))
    print("BPJPH folder:", p2.target_folder)
    print("BPJPH file  :", p2.target_filename)

if __name__ == "__main__":
    main()
