from __future__ import annotations

import ast
import shutil
from datetime import datetime
from pathlib import Path


TARGET = Path(
    "backend/app/services/"
    "certificate_change_service.py"
)


HELPER_CODE = '''
_MANUFACTURER_LEGAL_SUFFIXES = tuple(
    sorted(
        {
            "PRIVATELIMITED",
            "PRIVATELTD",
            "PVTLIMITED",
            "PVTLTD",
            "COMPANYLIMITED",
            "COLIMITED",
            "COLTD",
            "PTELIMITED",
            "PTELTD",
            "INCORPORATED",
            "CORPORATION",
            "LIMITED",
            "SDNBHD",
            "GMBH",
            "CORP",
            "LTD",
            "LLC",
            "INC",
            "BHD",
            "PLC",
            "PTE",
            "BV",
            "NV",
            "AG",
            "SA",
        },
        key=len,
        reverse=True,
    )
)


def _manufacturer_core(
    value: Any,
) -> str:
    """
    제조사 비교용 핵심 명칭을 반환한다.

    법인격 표기만 문자열 끝에서 제거하며,
    제조사 본체 명칭은 유지한다.
    """
    normalized = _normal(value)

    if not normalized:
        return ""

    changed = True

    while changed:
        changed = False

        for suffix in (
            _MANUFACTURER_LEGAL_SUFFIXES
        ):
            if (
                normalized.endswith(suffix)
                and len(normalized) > len(suffix)
            ):
                normalized = normalized[
                    :-len(suffix)
                ]
                changed = True
                break

    return normalized


'''


OLD_BLOCK = '''    if manufacturer_match is None:
        if current_manufacturer and incoming_manufacturer:
            current_normal = _normal(current_manufacturer)
            incoming_normal = _normal(incoming_manufacturer)

            manufacturer_similarity = SequenceMatcher(
                None,
                current_normal,
                incoming_normal,
            ).ratio()

            manufacturer_match = (
                current_normal == incoming_normal
                or manufacturer_similarity >= 0.92
            )
'''


NEW_BLOCK = '''    if manufacturer_match is None:
        if current_manufacturer and incoming_manufacturer:
            current_normal = _normal(
                current_manufacturer
            )
            incoming_normal = _normal(
                incoming_manufacturer
            )

            manufacturer_similarity = (
                SequenceMatcher(
                    None,
                    current_normal,
                    incoming_normal,
                ).ratio()
            )

            current_core = _manufacturer_core(
                current_manufacturer
            )
            incoming_core = _manufacturer_core(
                incoming_manufacturer
            )

            core_similarity = (
                SequenceMatcher(
                    None,
                    current_core,
                    incoming_core,
                ).ratio()
                if current_core and incoming_core
                else 0.0
            )

            core_fuzzy_match = (
                min(
                    len(current_core),
                    len(incoming_core),
                ) >= 8
                and core_similarity >= 0.92
            )

            manufacturer_match = (
                current_normal == incoming_normal
                or manufacturer_similarity >= 0.92
                or (
                    current_core
                    and current_core
                    == incoming_core
                )
                or core_fuzzy_match
            )
'''


def main() -> None:
    if not TARGET.exists():
        raise FileNotFoundError(TARGET)

    source = TARGET.read_text(
        encoding="utf-8-sig",
    )

    if "_manufacturer_core(" not in source:
        marker = (
            "def classify_certificate_change("
        )

        marker_index = source.find(marker)

        if marker_index < 0:
            raise RuntimeError(
                "classify_certificate_change "
                "함수를 찾지 못했습니다."
            )

        source = (
            source[:marker_index]
            + HELPER_CODE
            + source[marker_index:]
        )

    old_count = source.count(OLD_BLOCK)

    if old_count != 1:
        raise RuntimeError(
            "제조사 비교 블록 검색 실패: "
            f"{old_count}개 발견"
        )

    source = source.replace(
        OLD_BLOCK,
        NEW_BLOCK,
        1,
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
    print(
        "MANUFACTURER_MATCH_PATCH_OK"
    )


if __name__ == "__main__":
    main()
