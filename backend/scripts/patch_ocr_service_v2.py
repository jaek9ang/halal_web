from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path


def patch_ocr_service(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"ocr_service.py를 찾지 못했습니다: {path}")

    text = path.read_text(encoding="utf-8-sig")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.bak_ocr_rule_v2_{timestamp}")
    shutil.copy2(path, backup)

    import_line = (
        "from app.services.ocr_context_service import "
        "parse_certificate_with_linked_context\n"
    )
    if import_line not in text:
        marker = "from app.services.certificate_rule_service import parse_certificate_rule\n"
        if marker not in text:
            raise RuntimeError("certificate_rule_service import 위치를 찾지 못했습니다.")
        text = text.replace(marker, marker + import_line, 1)

    start_marker = "def guess_certificate_fields(raw_text: str, filename: str = \"\") -> dict[str, Any]:\n"
    end_marker = "\ndef create_ocr_job(\n"
    start = text.find(start_marker)
    end = text.find(end_marker, start)
    if start < 0 or end < 0:
        raise RuntimeError("guess_certificate_fields 함수 구간을 찾지 못했습니다.")

    replacement = '''def guess_certificate_fields(
    raw_text: str,
    filename: str = "",
    source_path: str = "",
    ocr_job_id: int | None = None,
) -> dict[str, Any]:
    """
    OCR 기본 규칙을 실행한 뒤, 메일 관리번호와 PMF 연결이 확인되는 경우에만
    제품명·제조사 문맥으로 교차검증한다.
    """
    if source_path:
        parsed = parse_certificate_with_linked_context(
            raw_text=raw_text,
            filename=filename,
            source_path=source_path,
            ocr_job_id=ocr_job_id,
        )
    else:
        parsed = parse_certificate_rule(
            raw_text=raw_text,
            filename=filename,
        )

    org = parsed.get("cert_org")
    org_candidates = []

    if org and org != "UNKNOWN":
        org_candidates.append(org)

    return {
        "org_candidates": org_candidates,
        "has_text": bool((raw_text or "").strip()),
        "text_length": len(raw_text or ""),
        "certificate_rule": parsed,
    }
'''
    text = text[:start] + replacement + text[end:]

    old_call = "field_guess = guess_certificate_fields(raw_text, filename=path.name)"
    new_call = '''field_guess = guess_certificate_fields(
            raw_text,
            filename=path.name,
            source_path=str(path),
            ocr_job_id=job_id,
        )'''
    if old_call in text:
        text = text.replace(old_call, new_call, 1)
    elif "source_path=str(path)" not in text:
        raise RuntimeError("create_ocr_job의 guess_certificate_fields 호출부를 찾지 못했습니다.")

    path.write_text(text, encoding="utf-8")
    return backup


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        default=str(Path(__file__).resolve().parents[1] / "app" / "services" / "ocr_service.py"),
    )
    args = parser.parse_args()
    backup = patch_ocr_service(Path(args.path))
    print(f"ocr_service.py 패치 완료: {args.path}")
    print(f"백업: {backup}")


if __name__ == "__main__":
    main()
