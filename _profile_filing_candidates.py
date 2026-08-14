from __future__ import annotations

import cProfile
import inspect
import io
import pstats
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services import (
    certificate_filing_workflow_service as service,
)


LIMIT = 10
OUTPUT_DIR = Path("backend/data/ocr_exports")


def get_rows(result: Any) -> list[Any]:
    if not isinstance(result, dict):
        return []

    rows = result.get("rows")

    if isinstance(rows, list):
        return rows

    return []


def make_stats_text(
    profiler: cProfile.Profile,
    sort_key: str,
    limit: int = 80,
) -> str:
    stream = io.StringIO()

    stats = pstats.Stats(
        profiler,
        stream=stream,
    )

    stats.strip_dirs()
    stats.sort_stats(sort_key)
    stats.print_stats(limit)

    return stream.getvalue()


def main() -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    profile_path = OUTPUT_DIR / (
        f"filing_candidates_profile_{stamp}.prof"
    )

    report_path = OUTPUT_DIR / (
        f"filing_candidates_profile_{stamp}.txt"
    )

    profiler = cProfile.Profile()

    started = time.perf_counter()

    profiler.enable()

    try:
        result = service.list_filing_candidates(
            limit=LIMIT,
        )
    finally:
        profiler.disable()

    elapsed = time.perf_counter() - started
    rows = get_rows(result)

    profiler.dump_stats(
        str(profile_path)
    )

    cumulative_text = make_stats_text(
        profiler=profiler,
        sort_key="cumulative",
    )

    own_time_text = make_stats_text(
        profiler=profiler,
        sort_key="tottime",
    )

    try:
        function_source = inspect.getsource(
            service.list_filing_candidates
        )
    except (OSError, TypeError) as exc:
        function_source = (
            "SOURCE_READ_FAILED: "
            + str(exc)
        )

    report = "\n".join(
        [
            "=== SUMMARY ===",
            f"LIMIT: {LIMIT}",
            f"ELAPSED_SECONDS: {elapsed:.3f}",
            f"RESULT_COUNT: {len(rows)}",
            "",
            "=== LIST_FILING_CANDIDATES SOURCE ===",
            function_source,
            "",
            "=== TOP CUMULATIVE TIME ===",
            cumulative_text,
            "",
            "=== TOP OWN TIME ===",
            own_time_text,
        ]
    )

    report_path.write_text(
        report,
        encoding="utf-8",
    )

    print()
    print("LIMIT:", LIMIT)
    print(
        "ELAPSED_SECONDS:",
        round(elapsed, 3),
    )
    print("RESULT_COUNT:", len(rows))
    print()
    print("=== TOP CUMULATIVE TIME ===")
    print(cumulative_text)
    print("PROFILE_PATH:", profile_path)
    print("REPORT_PATH:", report_path)
    print("FILING_CANDIDATE_PROFILE_OK")


if __name__ == "__main__":
    main()
