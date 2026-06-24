from __future__ import annotations

import importlib
import sys
from pathlib import Path


REQUIRED_MODULES = [
    'fastapi',
    'uvicorn',
    'pydantic',
    'pandas',
    'openpyxl',
    'requests',
    'fitz',
    'PIL',
    'pytesseract',
    'numpy',
    'cv2',
    'openai',
]


def main() -> None:
    print('python_executable =', sys.executable)
    print('python_version    =', sys.version.replace('\n', ' '))

    failed: list[str] = []
    for module_name in REQUIRED_MODULES:
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, '__version__', '')
            print(f'[OK] {module_name} {version}')
        except Exception as exc:
            failed.append(module_name)
            print(f'[FAIL] {module_name}: {exc}')

    try:
        from app.services.ocr_service import get_tesseract_runtime_info
        print('tesseract =', get_tesseract_runtime_info())
    except Exception as exc:
        failed.append('app.services.ocr_service')
        print('[FAIL] app.services.ocr_service:', exc)

    try:
        from app.services.filing_name_service import FilingNameInput, build_filing_names
        sample = build_filing_names(
            FilingNameInput(
                material_no='81',
                material_name_en='Onion flavor oil',
                manufacturer='SHIN YANG Poseung branch Co.,Ltd.',
                supplier='신양포스팅점',
                cert_org='MUI',
                expiry_date='2025-12-21',
                source_extension='.pdf',
            )
        )
        print('filing_sample =', sample.filename)
    except Exception as exc:
        failed.append('filing_name_service')
        print('[FAIL] filing_name_service:', exc)

    if failed:
        raise SystemExit(f'검증 실패: {failed}')

    print('runtime verification passed')


if __name__ == '__main__':
    main()
