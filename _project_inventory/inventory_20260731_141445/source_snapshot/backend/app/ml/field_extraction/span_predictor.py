from __future__ import annotations

import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np


PAGE_MARKER_RE = re.compile(
    r"---\s*PAGE\s+(\d+)(?:\s*\[[^\]]*\])?\s*---",
    re.IGNORECASE,
)
WHITESPACE_RE = re.compile(r"\s+")
DATE_NUMERIC_RE = re.compile(
    r"\b(20\d{2})[-./](\d{1,2})[-./](\d{1,2})\b"
)
DATE_DMY_RE = re.compile(
    r"\b(\d{1,2})[-./](\d{1,2})[-./](20\d{2})\b"
)
DATE_MONTH_FIRST_RE = re.compile(
    r"\b("
    r"JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|"
    r"SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER"
    r")\s+(\d{1,2})(?:ST|ND|RD|TH)?[,.]?\s+(20\d{2})\b",
    re.IGNORECASE,
)
DATE_DAY_FIRST_RE = re.compile(
    r"\b(\d{1,2})(?:ST|ND|RD|TH)?\s+("
    r"JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|"
    r"SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER"
    r")[,.]?\s+(20\d{2})\b",
    re.IGNORECASE,
)
COMPANY_SUFFIX_RE = re.compile(
    r"\b(?:CO\.?|COMPANY|CORP\.?|CORPORATION|INC\.?|LTD\.?|LIMITED|"
    r"LLC|PTE\.?\s*LTD\.?|SDN\.?\s*BHD\.?|GMBH|B\.?V\.?|"
    r"S\.?A\.?|PLC|AG|INDUSTRIES?|PRIVATE\s+LIMITED)\b",
    re.IGNORECASE,
)
GENERIC_LINE_RE = re.compile(
    r"^\s*(?:COMPANY|COMPANY\s+NAME|NAME\s+OF\s+COMPANY|"
    r"MANUFACTURER|MANUFACTURED\s+BY|FACTORY|FACILITY\s+NAME|"
    r"PLANT\s+NAME(?:\s*&\s*ADDRESS)?|CERTIFICATE\s+(?:NO|NUMBER)|"
    r"VALID\s+UNTIL|EXPIRY\s+DATE|EXPIRATION\s+DATE|"
    r"CO\.?\s*,?\s*LTD\.?|LTD\.?|PRIVATE\s+LIMITED)\s*[:：-]*\s*$",
    re.IGNORECASE,
)

MONTHS = {
    "JANUARY": 1,
    "FEBRUARY": 2,
    "MARCH": 3,
    "APRIL": 4,
    "MAY": 5,
    "JUNE": 6,
    "JULY": 7,
    "AUGUST": 8,
    "SEPTEMBER": 9,
    "OCTOBER": 10,
    "NOVEMBER": 11,
    "DECEMBER": 12,
}
FIELDS = ("cert_no", "manufacturer", "expiry_date")


def clean(value: Any) -> str:
    text = str(value or "").replace("\u00a0", " ").replace("\x00", " ")
    return WHITESPACE_RE.sub(" ", text).strip()


def norm_key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9가-힣]+", "", clean(value).upper())


def split_pages(text: str) -> list[dict[str, Any]]:
    raw = str(text or "")
    matches = list(PAGE_MARKER_RE.finditer(raw))
    chunks: list[tuple[int, str]] = []

    if matches:
        for index, match in enumerate(matches):
            page = int(match.group(1))
            start = match.end()
            end = (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(raw)
            )
            chunks.append((page, raw[start:end]))
    else:
        chunks.append((1, raw))

    rows: list[dict[str, Any]] = []
    for page, chunk in chunks:
        page_lines = [
            clean(line)
            for line in chunk.splitlines()
            if clean(line)
            and not PAGE_MARKER_RE.fullmatch(clean(line))
        ]
        for line_no, line in enumerate(page_lines, start=1):
            rows.append({
                "page": page,
                "line_no": line_no,
                "line": line,
            })

    return rows


def extract_dates(text: str) -> list[str]:
    results: list[str] = []

    for match in DATE_NUMERIC_RE.finditer(text):
        year, month, day = map(int, match.groups())
        if 1 <= month <= 12 and 1 <= day <= 31:
            results.append(f"{year:04d}-{month:02d}-{day:02d}")

    for match in DATE_DMY_RE.finditer(text):
        day, month, year = map(int, match.groups())
        if 1 <= month <= 12 and 1 <= day <= 31:
            results.append(f"{year:04d}-{month:02d}-{day:02d}")

    for match in DATE_MONTH_FIRST_RE.finditer(text.upper()):
        month_name, day, year = match.groups()
        results.append(
            f"{int(year):04d}-{MONTHS[month_name]:02d}-{int(day):02d}"
        )

    for match in DATE_DAY_FIRST_RE.finditer(text.upper()):
        day, month_name, year = match.groups()
        results.append(
            f"{int(year):04d}-{MONTHS[month_name]:02d}-{int(day):02d}"
        )

    return list(dict.fromkeys(results))


def normalize_cert_for_match(value: Any) -> str:
    text = norm_key(value)
    if text.startswith("LPPOM"):
        text = text[5:]
    if re.fullmatch(r"ID\d{10,}", text):
        text = text[2:]
    return text


def manufacturer_tokens(value: Any) -> list[str]:
    text = clean(value).upper()
    text = COMPANY_SUFFIX_RE.sub(" ", text)
    text = re.sub(r"[^A-Z0-9가-힣]+", " ", text)
    stop_words = {
        "THE",
        "OF",
        "AND",
        "GROUP",
        "HOLDING",
        "HOLDINGS",
    }
    return [
        token
        for token in text.split()
        if token and token not in stop_words
    ]


def manufacturer_match_score(left: Any, right: Any) -> float:
    left_set = set(manufacturer_tokens(left))
    right_set = set(manufacturer_tokens(right))
    if not left_set or not right_set:
        return 0.0
    intersection = len(left_set & right_set)
    containment = intersection / max(1, min(len(left_set), len(right_set)))
    jaccard = intersection / max(1, len(left_set | right_set))
    return round(max(containment, jaccard), 4)


def candidate_spans(
    field: str,
    institution: str,
    combined_text: str,
) -> list[dict[str, Any]]:
    rows = split_pages(combined_text)
    spans: list[dict[str, Any]] = []

    for start in range(len(rows)):
        if rows[start]["page"] > 4:
            continue

        for length in (1, 2, 3):
            end = start + length
            if end > len(rows):
                break

            selected = rows[start:end]
            if len({row["page"] for row in selected}) != 1:
                break

            span_text = " | ".join(row["line"] for row in selected)
            upper = span_text.upper()

            if len(span_text) > 500:
                continue

            if field == "cert_no":
                eligible = bool(
                    re.search(r"\d", span_text)
                    and (
                        length > 1
                        or "CERT" in upper
                        or "REGISTRATION" in upper
                        or len(norm_key(span_text)) >= 5
                    )
                )
            elif field == "manufacturer":
                eligible = bool(
                    re.search(r"[A-Za-z가-힣]", span_text)
                    and len(norm_key(span_text)) >= 4
                )
            elif field == "expiry_date":
                eligible = bool(
                    extract_dates(span_text)
                    or any(
                        token in upper
                        for token in (
                            "VALID",
                            "EXPIR",
                            "UNTIL",
                            "PERIOD",
                            "DATE",
                        )
                    )
                )
            else:
                eligible = False

            if not eligible:
                continue

            previous = rows[start - 1]["line"] if start > 0 else ""
            following = rows[end]["line"] if end < len(rows) else ""
            page = int(selected[0]["page"])
            position_bucket = min(9, int(selected[0]["line_no"]) // 5)
            org_token = re.sub(
                r"[^A-Z0-9]+",
                "_",
                institution.upper(),
            ).strip("_")

            tokens = [
                f"__FIELD_{field.upper()}__",
                f"__ORG_{org_token}__",
                f"__PAGE_{page}__",
                f"__POS_{position_bucket}__",
                f"__SPAN_{length}__",
            ]

            if page == 1:
                tokens.append("__FIRST_PAGE__")
            if extract_dates(span_text):
                tokens.append("__HAS_DATE__")
            if COMPANY_SUFFIX_RE.search(span_text):
                tokens.append("__HAS_COMPANY_SUFFIX__")
            if GENERIC_LINE_RE.fullmatch(clean(selected[0]["line"])):
                tokens.append("__STARTS_WITH_LABEL_ONLY__")
            if any(token in upper for token in ("CERT", "REGISTRATION", "LICENSE")):
                tokens.append("__CERT_CONTEXT__")
            if any(token in upper for token in ("VALID", "EXPIR", "UNTIL")):
                tokens.append("__EXPIRY_CONTEXT__")
            if any(
                token in upper
                for token in (
                    "MANUFACTURER",
                    "MANUFACTURED BY",
                    "COMPANY NAME",
                    "NAME OF COMPANY",
                    "FACTORY",
                    "FACILITY",
                    "APPLICANT",
                )
            ):
                tokens.append("__MAKER_CONTEXT__")

            feature_text = (
                " ".join(tokens)
                + "\nPREV: "
                + previous
                + "\nSPAN: "
                + span_text
                + "\nNEXT: "
                + following
            )

            spans.append({
                "page": page,
                "start_line_no": int(selected[0]["line_no"]),
                "end_line_no": int(selected[-1]["line_no"]),
                "span_length": length,
                "span_text": span_text,
                "feature_text": feature_text,
            })

    return spans


def extract_cert_no(span_text: str) -> str:
    candidates = re.findall(
        r"[A-Z0-9][A-Z0-9./_-]{4,}",
        span_text.upper(),
    )
    candidates = [
        value.strip("._/-")
        for value in candidates
        if re.search(r"\d", value)
        and value not in {"CERTIFICATE", "REGISTRATION"}
    ]
    if not candidates:
        return clean(span_text)

    candidates.sort(
        key=lambda value: (
            sum(character.isdigit() for character in value),
            len(value),
        ),
        reverse=True,
    )
    return candidates[0]


def extract_manufacturer(span_text: str) -> str:
    parts = [
        clean(part)
        for part in span_text.split("|")
        if clean(part)
        and not GENERIC_LINE_RE.fullmatch(clean(part))
    ]
    if not parts:
        return clean(span_text)

    return " ".join(parts).strip(" .,:;-")


def extract_value(field: str, span_text: str) -> str:
    if field == "cert_no":
        return extract_cert_no(span_text)
    if field == "manufacturer":
        return extract_manufacturer(span_text)
    if field == "expiry_date":
        dates = extract_dates(span_text)
        return dates[-1] if dates else ""
    return clean(span_text)


def default_runtime_root() -> Path:
    return Path(
        os.getenv(
            "HALAL_ML_RUNTIME_ROOT",
            r"D:\halal_web_runtime\certificate_classifier",
        )
    )


def resolve_model_root(model_root: str | Path | None = None) -> Path:
    if model_root:
        root = Path(model_root)
    else:
        pointer = (
            default_runtime_root()
            / "models"
            / "current_field_span_model.txt"
        )
        root = Path(pointer.read_text(encoding="utf-8-sig").strip())

    if not root.exists():
        raise FileNotFoundError(root)
    return root


@lru_cache(maxsize=8)
def load_model(model_root_text: str, field: str) -> dict[str, Any]:
    path = Path(model_root_text) / f"{field}_span_ranker.joblib"
    return joblib.load(path)


def sigmoid_gap(gap: float) -> float:
    try:
        return round(1.0 / (1.0 + math.exp(-float(gap))), 6)
    except OverflowError:
        return 1.0 if gap > 0 else 0.0


def predict_fields(
    combined_text: str,
    institution: str,
    *,
    fields: list[str] | tuple[str, ...] | None = None,
    top_k: int = 3,
    model_root: str | Path | None = None,
) -> dict[str, Any]:
    root = resolve_model_root(model_root)
    selected_fields = tuple(fields or FIELDS)
    output: dict[str, Any] = {}

    for field in selected_fields:
        payload = load_model(str(root), field)
        pipeline = payload["pipeline"]
        metadata = payload.get("metadata") or {}
        spans = candidate_spans(field, institution, combined_text)

        if not spans:
            output[field] = {
                "value": "",
                "requires_review": True,
                "reason": "후보 Span 없음",
                "candidates": [],
            }
            continue

        scores = np.asarray(
            pipeline.decision_function(
                [span["feature_text"] for span in spans]
            ),
            dtype=float,
        ).reshape(-1)

        order = np.argsort(scores)[::-1]
        candidates: list[dict[str, Any]] = []

        for index in order[: max(1, int(top_k))]:
            span = spans[int(index)]
            candidates.append({
                "value": extract_value(field, span["span_text"]),
                "page": span["page"],
                "start_line_no": span["start_line_no"],
                "end_line_no": span["end_line_no"],
                "span_text": span["span_text"],
                "score": round(float(scores[int(index)]), 6),
            })

        top_score = float(candidates[0]["score"])
        second_score = (
            float(candidates[1]["score"])
            if len(candidates) > 1
            else top_score
        )
        gap = top_score - second_score
        threshold = float(
            metadata.get("recommended_review_gap_threshold", 0.0) or 0.0
        )

        output[field] = {
            **candidates[0],
            "score_gap": round(gap, 6),
            "relative_confidence": sigmoid_gap(gap),
            "requires_review": gap < threshold,
            "candidates": candidates,
            "confidence_note": (
                "relative_confidence는 후보 간 SVM 점수 차이를 변환한 "
                "상대값이며 보정된 확률이 아닙니다."
            ),
        }

    return {
        "institution": institution,
        "model_root": str(root),
        "fields": output,
    }


def load_combined_text_by_sha(
    sha256: str,
    *,
    runtime_root: str | Path | None = None,
) -> str:
    root = Path(runtime_root) if runtime_root else default_runtime_root()
    path = root / "text_cache" / "combined" / f"{sha256}.json"
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return str(payload.get("combined_text") or "")