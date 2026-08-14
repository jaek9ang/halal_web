from __future__ import annotations

import ast
import shutil
from datetime import datetime
from pathlib import Path


PMF_PATH = Path(
    "backend/app/services/pmf_service.py"
)

MAIL_PATH = Path(
    "backend/app/services/mail_request_item_service.py"
)

FILING_PATH = Path(
    "backend/app/services/"
    "certificate_filing_workflow_service.py"
)


def read_source(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)

    return path.read_text(
        encoding="utf-8-sig",
    )


def replace_once(
    text: str,
    old: str,
    new: str,
    label: str,
) -> str:
    count = text.count(old)

    if count != 1:
        raise RuntimeError(
            f"{label}: expected 1 match, found {count}"
        )

    return text.replace(
        old,
        new,
        1,
    )


def has_import_name(
    text: str,
    name: str,
) -> bool:
    tree = ast.parse(text)

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname == name:
                    return True

                if alias.name.split(".")[-1] == name:
                    return True

        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == name:
                    return True

                if alias.asname == name:
                    return True

    return False


def validate_python(
    path: Path,
    text: str,
) -> None:
    ast.parse(
        text,
        filename=str(path),
    )


def main() -> None:
    pmf_text = read_source(PMF_PATH)
    mail_text = read_source(MAIL_PATH)
    filing_text = read_source(FILING_PATH)

    # ---------------------------------------------------------
    # 1. Reuse the already opened ExcelFile inside one bundle.
    # ---------------------------------------------------------
    pmf_text = replace_once(
        pmf_text,
        '''    df_raw = pd.read_excel(
        PMF_ACTIVE_PATH,
        sheet_name=raw_sheet,
        header=None,
        engine="openpyxl",
    )
''',
        '''    df_raw = xls.parse(
        sheet_name=raw_sheet,
        header=None,
    )
''',
        "replace df_raw loader",
    )

    pmf_text = replace_once(
        pmf_text,
        '''    df_email = pd.read_excel(
        PMF_ACTIVE_PATH,
        sheet_name=email_sheet,
        header=None,
        engine="openpyxl",
    )
''',
        '''    df_email = xls.parse(
        sheet_name=email_sheet,
        header=None,
    )
''',
        "replace df_email loader",
    )

    pmf_text = replace_once(
        pmf_text,
        '''        df_mail_contents = pd.read_excel(
            PMF_ACTIVE_PATH,
            sheet_name=mail_contents_sheet,
            header=None,
            engine="openpyxl",
        )

    return {
''',
        '''        df_mail_contents = xls.parse(
            sheet_name=mail_contents_sheet,
            header=None,
        )

    xls.close()

    return {
''',
        "replace mail contents loader",
    )

    # ---------------------------------------------------------
    # 2. Allow callers to pass one PMF bundle.
    # ---------------------------------------------------------
    mail_text = replace_once(
        mail_text,
        '''def match_mail_item_to_pmf(
    mail_item: dict[str, Any],
    supplier: str = "",
    limit: int = 5,
) -> list[dict[str, Any]]:
    bundle = read_pmf_bundle()
''',
        '''def match_mail_item_to_pmf(
    mail_item: dict[str, Any],
    supplier: str = "",
    limit: int = 5,
    pmf_bundle: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    bundle = (
        pmf_bundle
        if pmf_bundle is not None
        else read_pmf_bundle()
    )
''',
        "update match_mail_item_to_pmf",
    )

    mail_text = replace_once(
        mail_text,
        '''def build_pmf_candidates_for_request_context(
    request_context: dict[str, Any],
    limit_per_item: int = 5,
) -> list[dict[str, Any]]:
    supplier = normalize_text((request_context.get("mail_log") or {}).get("supplier"))
    rows: list[dict[str, Any]] = []
''',
        '''def build_pmf_candidates_for_request_context(
    request_context: dict[str, Any],
    limit_per_item: int = 5,
    pmf_bundle: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    bundle = (
        pmf_bundle
        if pmf_bundle is not None
        else read_pmf_bundle()
    )
    supplier = normalize_text(
        (request_context.get("mail_log") or {}).get(
            "supplier"
        )
    )
    rows: list[dict[str, Any]] = []
''',
        "update build_pmf_candidates signature",
    )

    mail_text = replace_once(
        mail_text,
        '''        matches = match_mail_item_to_pmf(item, supplier=supplier, limit=limit_per_item)
''',
        '''        matches = match_mail_item_to_pmf(
            item,
            supplier=supplier,
            limit=limit_per_item,
            pmf_bundle=bundle,
        )
''',
        "pass bundle to PMF matcher",
    )

    # ---------------------------------------------------------
    # 3. Import read_pmf_bundle in the filing service.
    # ---------------------------------------------------------
    if not has_import_name(
        filing_text,
        "read_pmf_bundle",
    ):
        filing_text = replace_once(
            filing_text,
            '''from __future__ import annotations
''',
            '''from __future__ import annotations

from app.services.pmf_service import read_pmf_bundle
''',
            "add read_pmf_bundle import",
        )

    # ---------------------------------------------------------
    # 4. Load the PMF bundle only once per candidate request.
    # ---------------------------------------------------------
    filing_text = replace_once(
        filing_text,
        '''    rows: list[dict[str, Any]] = []

    for job in jobs.get("rows") or []:
''',
        '''    rows: list[dict[str, Any]] = []
    job_rows = jobs.get("rows") or []
    pmf_bundle: dict[str, Any] | None = None

    for job in job_rows:
''',
        "initialize request PMF bundle",
    )

    filing_text = replace_once(
        filing_text,
        '''        if history:
            continue

        cert_values = resolve_cert_values(job)
''',
        '''        if history:
            continue

        if pmf_bundle is None:
            pmf_bundle = read_pmf_bundle()

        cert_values = resolve_cert_values(job)
''',
        "lazy load PMF bundle",
    )

    # ---------------------------------------------------------
    # 5. Build groups once and reuse the selected item result.
    # ---------------------------------------------------------
    start_marker = '''        selected_matches = (
'''
    end_marker = '''        pmf_groups = build_pmf_candidates_for_request_context(request_context, limit_per_item=5)
'''

    start_index = filing_text.find(start_marker)
    end_index = filing_text.find(
        end_marker,
        start_index,
    )

    if start_index < 0 or end_index < 0:
        raise RuntimeError(
            "selected PMF matching block was not found"
        )

    end_index += len(end_marker)

    replacement = '''        pmf_groups = build_pmf_candidates_for_request_context(
            request_context,
            limit_per_item=5,
            pmf_bundle=pmf_bundle,
        )

        selected_matches: list[dict[str, Any]] = []

        if selected_mail_item:
            for group in pmf_groups:
                group_item = group.get("mail_item")

                if (
                    group_item is selected_mail_item
                    or group_item == selected_mail_item
                ):
                    selected_matches = list(
                        group.get("pmf_matches")
                        or []
                    )
                    break

            if not selected_matches:
                selected_matches = match_mail_item_to_pmf(
                    selected_mail_item,
                    supplier=supplier,
                    limit=5,
                    pmf_bundle=pmf_bundle,
                )

        top_match = (
            selected_matches[0]
            if selected_matches
            else None
        )
'''

    filing_text = (
        filing_text[:start_index]
        + replacement
        + filing_text[end_index:]
    )

    # Validate all modified source before writing.
    validate_python(PMF_PATH, pmf_text)
    validate_python(MAIL_PATH, mail_text)
    validate_python(FILING_PATH, filing_text)

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    modified = {
        PMF_PATH: pmf_text,
        MAIL_PATH: mail_text,
        FILING_PATH: filing_text,
    }

    for path, text in modified.items():
        backup_path = path.with_name(
            path.name
            + ".backup_"
            + stamp
        )

        shutil.copy2(
            path,
            backup_path,
        )

        path.write_text(
            text,
            encoding="utf-8",
        )

        print(
            "UPDATED:",
            path,
        )

        print(
            "BACKUP:",
            backup_path,
        )

    print(
        "FILING_PERFORMANCE_PATCH_OK"
    )


if __name__ == "__main__":
    main()
