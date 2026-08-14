from __future__ import annotations

import ast
from pathlib import Path


TARGETS = {
    Path(
        "backend/app/services/pmf_service.py"
    ): {
        "get_excel_file",
        "read_pmf_bundle",
    },
    Path(
        "backend/app/services/"
        "mail_request_item_service.py"
    ): {
        "match_mail_item_to_pmf",
        "build_pmf_candidates_for_request_context",
    },
    Path(
        "backend/app/services/"
        "certificate_filing_workflow_service.py"
    ): {
        "list_filing_candidates",
    },
}


def extract_functions(
    path: Path,
    function_names: set[str],
) -> str:
    text = path.read_text(
        encoding="utf-8",
    )

    tree = ast.parse(
        text,
        filename=str(path),
    )

    lines = text.splitlines()

    output: list[str] = [
        "=" * 100,
        f"FILE: {path}",
        "=" * 100,
    ]

    found: set[str] = set()

    for node in tree.body:
        if not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ):
            continue

        if node.name not in function_names:
            continue

        found.add(node.name)

        start = node.lineno - 1
        end = node.end_lineno or node.lineno

        output.append("")
        output.append(
            f"--- FUNCTION: {node.name} "
            f"(lines {start + 1}-{end}) ---"
        )

        output.extend(lines[start:end])

    missing = function_names - found

    if missing:
        output.append("")
        output.append(
            "MISSING_FUNCTIONS: "
            + ", ".join(sorted(missing))
        )

    return "\n".join(output)


def main() -> None:
    reports: list[str] = []

    for path, function_names in TARGETS.items():
        if not path.exists():
            reports.append(
                "=" * 100
                + "\nFILE_NOT_FOUND: "
                + str(path)
            )
            continue

        reports.append(
            extract_functions(
                path,
                function_names,
            )
        )

    output = "\n\n".join(reports)

    output_path = Path(
        "filing_performance_functions.txt"
    )

    output_path.write_text(
        output,
        encoding="utf-8",
    )

    print(output)
    print()
    print(
        "RESULT_PATH:",
        output_path.resolve(),
    )
    print(
        "FILING_PERFORMANCE_SOURCE_EXTRACT_OK"
    )


if __name__ == "__main__":
    main()
