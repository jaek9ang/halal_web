from __future__ import annotations

import ast
import shutil
from datetime import datetime
from pathlib import Path


WORKFLOW_PATH = Path(
    "backend/app/services/"
    "certificate_filing_workflow_service.py"
)

CHANGE_PATH = Path(
    "backend/app/services/"
    "certificate_change_service.py"
)


BROKEN_BLOCKED = '''        message = (
            "???? ?? ??? ?? ?? ??? "
            f"???????: {decision_code}"
        )
'''

FIXED_BLOCKED = '''        message = (
            "인증서 변경 판정으로 확정 처리가 차단되었습니다: "
            f"{decision_code}"
        )
'''


BROKEN_REVIEW = '''        message = (
            "???? ?? ??? ?????: "
            f"{decision_code}"
        )
'''

FIXED_REVIEW = '''        message = (
            "인증서 변경 판정에 수동 검토가 필요합니다: "
            f"{decision_code}"
        )
'''


BROKEN_REASON = '''        message = f"?? ??: {reason}"
'''

FIXED_REASON = '''        message = f"판정 사유: {reason}"
'''


MANUFACTURER_FALSE_MARKER = '''    if manufacturer_match is False:
'''

MANUFACTURER_EQUIVALENT_BLOCK = '''    if manufacturer_match is True:
        manufacturer_change = (
            changes.get("manufacturer")
            or {}
        )

        if manufacturer_change.get("changed"):
            manufacturer_change[
                "text_changed"
            ] = True
            manufacturer_change[
                "equivalent"
            ] = True
            manufacturer_change[
                "changed"
            ] = False

    if manufacturer_match is False:
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


def backup_file(path: Path) -> Path:
    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup = path.with_name(
        path.name + ".backup_" + stamp
    )

    shutil.copy2(
        path,
        backup,
    )

    return backup


def patch_workflow() -> None:
    source = WORKFLOW_PATH.read_text(
        encoding="utf-8-sig",
    )

    source = replace_once(
        source,
        BROKEN_BLOCKED,
        FIXED_BLOCKED,
        "blocked message",
    )

    source = replace_once(
        source,
        BROKEN_REVIEW,
        FIXED_REVIEW,
        "review message",
    )

    source = replace_once(
        source,
        BROKEN_REASON,
        FIXED_REASON,
        "reason message",
    )

    ast.parse(
        source,
        filename=str(WORKFLOW_PATH),
    )

    backup = backup_file(
        WORKFLOW_PATH
    )

    WORKFLOW_PATH.write_text(
        source,
        encoding="utf-8",
    )

    print(
        "WORKFLOW_UPDATED:",
        WORKFLOW_PATH,
    )
    print(
        "WORKFLOW_BACKUP :",
        backup,
    )


def patch_change_service() -> None:
    source = CHANGE_PATH.read_text(
        encoding="utf-8-sig",
    )

    if '"text_changed"' in source:
        print(
            "MANUFACTURER_EQUIVALENT_BLOCK_ALREADY_EXISTS"
        )
        return

    source = replace_once(
        source,
        MANUFACTURER_FALSE_MARKER,
        MANUFACTURER_EQUIVALENT_BLOCK,
        "manufacturer equivalent block",
    )

    ast.parse(
        source,
        filename=str(CHANGE_PATH),
    )

    backup = backup_file(
        CHANGE_PATH
    )

    CHANGE_PATH.write_text(
        source,
        encoding="utf-8",
    )

    print(
        "CHANGE_SERVICE_UPDATED:",
        CHANGE_PATH,
    )
    print(
        "CHANGE_SERVICE_BACKUP :",
        backup,
    )


def main() -> None:
    if not WORKFLOW_PATH.exists():
        raise FileNotFoundError(
            WORKFLOW_PATH
        )

    if not CHANGE_PATH.exists():
        raise FileNotFoundError(
            CHANGE_PATH
        )

    patch_workflow()
    patch_change_service()

    print(
        "CHANGE_DISPLAY_CLEANUP_PATCH_OK"
    )


if __name__ == "__main__":
    main()
