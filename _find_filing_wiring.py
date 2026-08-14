from __future__ import annotations

from pathlib import Path


ROOTS = [
    Path("frontend"),
    Path("backend/app"),
]

EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".html",
}

PATTERNS = [
    "/certificate-filing/preview",
    "/certificate-filing/confirm",
    "certificate-filing",
    "preview_filing_workflow",
    "confirm_filing_workflow",
    "list_filing_candidates",
    "change_action",
    "AUTHORITY_CHANGE_REVIEW",
    "SAME_AUTHORITY_RENEWAL",
    "REPLACE_CURRENT",
    "ADD_SECONDARY",
]

CONTEXT_BEFORE = 4
CONTEXT_AFTER = 10


def find_source_files() -> list[Path]:
    files: list[Path] = []

    for root in ROOTS:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower() in EXTENSIONS
                and ".venv" not in path.parts
                and "node_modules" not in path.parts
                and "__pycache__" not in path.parts
            ):
                files.append(path)

    return sorted(files)


def main() -> None:
    source_files = find_source_files()
    findings: list[str] = []

    for path in source_files:
        try:
            text = path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            continue

        lines = text.splitlines()

        matched_indexes: set[int] = set()

        for index, line in enumerate(lines):
            if any(
                pattern.lower() in line.lower()
                for pattern in PATTERNS
            ):
                matched_indexes.add(index)

        if not matched_indexes:
            continue

        findings.append("")
        findings.append("=" * 100)
        findings.append(f"FILE: {path}")
        findings.append("=" * 100)

        printed_ranges: list[tuple[int, int]] = []

        for index in sorted(matched_indexes):
            start = max(
                0,
                index - CONTEXT_BEFORE,
            )
            end = min(
                len(lines),
                index + CONTEXT_AFTER + 1,
            )

            if any(
                start >= old_start
                and end <= old_end
                for old_start, old_end
                in printed_ranges
            ):
                continue

            printed_ranges.append((start, end))

            findings.append(
                f"\n--- MATCH AROUND LINE {index + 1} ---"
            )

            for line_index in range(start, end):
                marker = (
                    ">>"
                    if line_index == index
                    else "  "
                )

                findings.append(
                    f"{marker} "
                    f"{line_index + 1:5d}: "
                    f"{lines[line_index]}"
                )

    output_path = Path(
        "filing_wiring_locations.txt"
    )

    if findings:
        output = "\n".join(findings)
    else:
        output = (
            "관련 API 또는 함수 호출 위치를 "
            "찾지 못했습니다."
        )

    output_path.write_text(
        output,
        encoding="utf-8",
    )

    print(output)
    print()
    print("RESULT_PATH:", output_path.resolve())
    print("FILING_WIRING_SEARCH_OK")


if __name__ == "__main__":
    main()
