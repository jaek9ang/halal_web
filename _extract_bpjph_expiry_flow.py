from __future__ import annotations

from pathlib import Path


TARGET = Path(
    "backend/app/services/"
    "certificate_filing_workflow_service.py"
)

PATTERNS = (
    "pmf_expiry",
    "classify_certificate_change",
    "BPJPH_MAINTENANCE_ONLY",
    "change_decision",
    "preview_pmf_update",
    "pmf_update_preview",
)

CONTEXT_BEFORE = 18
CONTEXT_AFTER = 30


def main() -> None:
    text = TARGET.read_text(
        encoding="utf-8-sig",
    )

    lines = text.splitlines()
    matched_indexes: list[int] = []

    for index, line in enumerate(lines):
        if any(
            pattern in line
            for pattern in PATTERNS
        ):
            matched_indexes.append(index)

    ranges: list[tuple[int, int]] = []

    for index in matched_indexes:
        start = max(
            0,
            index - CONTEXT_BEFORE,
        )

        end = min(
            len(lines),
            index + CONTEXT_AFTER + 1,
        )

        if ranges and start <= ranges[-1][1]:
            previous_start, previous_end = ranges[-1]

            ranges[-1] = (
                previous_start,
                max(previous_end, end),
            )
        else:
            ranges.append((start, end))

    output: list[str] = [
        f"FILE: {TARGET}",
        "",
    ]

    for block_number, (start, end) in enumerate(
        ranges,
        start=1,
    ):
        output.append(
            "=" * 100
        )

        output.append(
            f"BLOCK {block_number}: "
            f"LINES {start + 1}-{end}"
        )

        output.append(
            "=" * 100
        )

        for line_index in range(start, end):
            output.append(
                f"{line_index + 1:5d}: "
                f"{lines[line_index]}"
            )

        output.append("")

    result = "\n".join(output)

    output_path = Path(
        "bpjph_expiry_flow.txt"
    )

    output_path.write_text(
        result,
        encoding="utf-8",
    )

    print(result)
    print()
    print(
        "RESULT_PATH:",
        output_path.resolve(),
    )
    print(
        "BPJPH_EXPIRY_FLOW_EXTRACT_OK"
    )


if __name__ == "__main__":
    main()
