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
    r"---\s*PAGE\s+(\d+)\s*\[[^\]]*\]\s*---",
    re.IGNORECASE,
)
DATE_NUMERIC_RE = re.compile(
    r"\b(20\d{2})[-./](\d{1,2})[-./](\d{1,2})\b"
)
DATE_DMY_RE = re.compile(
    r"\b(\d{1,2})[-./](\d{1,2})[-./](20\d{2})\b"
)
MONTH_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+"
    r"(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|"
    r"SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+(20\d{2})\b",
    re.IGNORECASE,
)
COMPANY_SUFFIX_RE = re.compile(
    r"\b(?:CO\.?|COMPANY|CORP\.?|CORPORATION|INC\.?|LTD\.?|LIMITED|"
    r"LLC|PTE\.?\s*LTD\.?|SDN\.?\s*BHD\.?|GMBH|B\.?V\.?|"
    r"S\.?A\.?|PLC|AG|INDUSTRIES?)\b",
    re.IGNORECASE,
)
CERT_LABEL_RE = re.compile(
    r"^\s*(?:CERTIFICATE|CERTIFICATION|REGISTRATION)?\s*"
    r"(?:NO\.?|NUMBER|ID|CERT\.?\s*NO\.?)\s*[:：#-]*\s*",
    re.IGNORECASE,
)
MANUFACTURER_LABEL_RE = re.compile(
    r"^\s*(?:COMPANY\s+NAME|NAME\s+OF\s+COMPANY|MANUFACTURER|"
    r"MANUFACTURED\s+BY|PRODUCED\s+BY|FACTORY\s+NAME|APPLICANT)"
    r"\s*[:：-]*\s*",
    re.IGNORECASE,
)
ARABIC_RE = re.compile(r"[\u0600-\u06FF].*$")
WHITESPACE_RE = re.compile(r"\s+")

FIELD_ORDER = (
    "cert_no",
    "manufacturer",
    "expiry_date",
    "manufacturing_country",
)


def _clean(value: Any) -> str:
    text = str(value or "").replace("\u00a0", " ").replace("\x00", " ")
    return WHITESPACE_RE.sub(" ", text).strip()


def _norm_key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9가-힣]+", "", _clean(value).upper())


def _split_pages_and_lines(text: str) -> list[dict[str, Any]]:
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
    global_index = 0

    for page, chunk in chunks:
        for line_no, line in enumerate(chunk.splitlines(), start=1):
            current = _clean(line)
            if not current:
                continue
            rows.append({
                "global_index": global_index,
                "page": page,
                "line_no": line_no,
                "line": current,
            })
            global_index += 1

    return rows


def _contains_date(line: str) -> bool:
    upper = line.upper()
    return bool(
        DATE_NUMERIC_RE.search(line)
        or DATE_DMY_RE.search(line)
        or MONTH_DATE_RE.search(upper)
    )


def _eligible(field: str, row: dict[str, Any]) -> bool:
    line = row["line"]
    upper = line.upper()
    page = int(row["page"])

    if len(line) < 2 or len(line) > 280:
        return False

    if field == "cert_no":
        return bool(
            page <= 3
            and (
                re.search(r"\d", line)
                or "CERT" in upper
                or "REGISTRATION" in upper
            )
        )

    if field == "expiry_date":
        return bool(
            page <= 4
            and (
                _contains_date(line)
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
        )

    if field == "manufacturer":
        return bool(
            page <= 4
            and re.search(r"[A-Za-z가-힣]", line)
            and len(_norm_key(line)) >= 3
        )

    if field == "manufacturing_country":
        return bool(
            page <= 4
            and re.search(r"[A-Za-z가-힣]", line)
            and len(_norm_key(line)) >= 3
        )

    return False


def _feature_text(
    field: str,
    institution: str,
    rows: list[dict[str, Any]],
    index: int,
) -> str:
    row = rows[index]
    current = row["line"]
    previous = rows[index - 1]["line"] if index > 0 else ""
    following = rows[index + 1]["line"] if index + 1 < len(rows) else ""
    upper = current.upper()

    page = int(row["page"])
    line_no = int(row["line_no"])
    position_bucket = min(9, line_no // 5)

    tokens = [
        f"__FIELD_{field.upper()}__",
        f"__ORG_{re.sub(r'[^A-Z0-9]+', '_', institution.upper()).strip('_')}__",
        f"__PAGE_{min(page, 9)}__",
        f"__POS_{position_bucket}__",
    ]

    if page == 1:
        tokens.append("__FIRST_PAGE__")
    if re.search(r"\d", current):
        tokens.append("__HAS_DIGIT__")
    if _contains_date(current):
        tokens.append("__HAS_DATE__")
    if COMPANY_SUFFIX_RE.search(current):
        tokens.append("__HAS_COMPANY_SUFFIX__")
    if any(token in upper for token in ("CERT", "REGISTRATION", "LICENSE")):
        tokens.append("__CERT_KEYWORD__")
    if any(token in upper for token in ("VALID", "EXPIR", "UNTIL")):
        tokens.append("__EXPIRY_KEYWORD__")
    if any(
        token in upper
        for token in (
            "MANUFACTURER",
            "MANUFACTURED BY",
            "COMPANY NAME",
            "FACTORY",
            "APPLICANT",
        )
    ):
        tokens.append("__MAKER_KEYWORD__")
    if any(token in upper for token in ("COUNTRY", "ADDRESS", "SITE", "PLANT")):
        tokens.append("__COUNTRY_CONTEXT__")

    return (
        " ".join(tokens)
        + "\nPREV: "
        + previous
        + "\nCUR: "
        + current
        + "\nNEXT: "
        + following
    )


def _candidate_rows(
    field: str,
    institution: str,
    combined_text: str,
) -> list[dict[str, Any]]:
    rows = _split_pages_and_lines(combined_text)
    candidates: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        if not _eligible(field, row):
            continue

        candidates.append({
            **row,
            "feature_text": _feature_text(
                field,
                institution,
                rows,
                index,
            ),
        })

    return candidates


def normalize_cert_no_for_match(value: Any) -> str:
    """
    저장값은 바꾸지 않고 비교할 때만 사용하는 정규화 함수입니다.
    LPPOM- 접두어와 BPJPH의 ID+숫자 접두어 차이를 비교용으로만 제거합니다.
    """
    text = _norm_key(value)

    if text.startswith("LPPOM"):
        text = text[5:]

    if re.fullmatch(r"ID\d{10,}", text):
        text = text[2:]

    return text


def cert_no_match_variants(value: Any) -> list[str]:
    raw = _norm_key(value)
    normalized = normalize_cert_no_for_match(value)
    return list(dict.fromkeys(item for item in (raw, normalized) if item))


def manufacturer_match_tokens(value: Any) -> list[str]:
    """
    ANHUI HUAHENG ... 과 HUAHENG ...처럼 앞 지역명 한 단어가 추가돼도
    핵심 회사명 토큰으로 비교할 수 있게 합니다. 원문 저장값은 유지합니다.
    """
    text = _clean(value).upper()
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
    left_tokens = manufacturer_match_tokens(left)
    right_tokens = manufacturer_match_tokens(right)

    if not left_tokens or not right_tokens:
        return 0.0

    left_set = set(left_tokens)
    right_set = set(right_tokens)
    intersection = len(left_set & right_set)

    containment = intersection / max(
        1,
        min(len(left_set), len(right_set)),
    )
    jaccard = intersection / max(
        1,
        len(left_set | right_set),
    )

    # 한쪽에 지역명 한 단어만 추가된 경우 containment가 1.0이 됩니다.
    return round(max(containment, jaccard), 4)


def _extract_cert_no(line: str) -> str:
    cleaned = CERT_LABEL_RE.sub("", _clean(line))
    tokens = re.findall(
        r"[A-Z0-9][A-Z0-9./_-]{4,}",
        cleaned.upper(),
    )
    tokens = [
        token.strip("._/-")
        for token in tokens
        if re.search(r"\d", token)
    ]

    if not tokens:
        return cleaned

    tokens.sort(
        key=lambda token: (
            sum(character.isdigit() for character in token),
            len(token),
        ),
        reverse=True,
    )
    return tokens[0]


def _extract_manufacturer(line: str) -> str:
    cleaned = MANUFACTURER_LABEL_RE.sub("", _clean(line))
    cleaned = ARABIC_RE.sub("", cleaned)
    return cleaned.strip(" .,:;-")


def _extract_expiry_date(line: str) -> str:
    match = DATE_NUMERIC_RE.search(line)
    if match:
        year, month, day = map(int, match.groups())
        try:
            return f"{year:04d}-{month:02d}-{day:02d}"
        except ValueError:
            pass

    match = DATE_DMY_RE.search(line)
    if match:
        day, month, year = map(int, match.groups())
        try:
            return f"{year:04d}-{month:02d}-{day:02d}"
        except ValueError:
            pass

    match = MONTH_DATE_RE.search(line.upper())
    if match:
        day = int(match.group(1))
        month_name = match.group(2).upper()
        year = int(match.group(3))
        month_map = {
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
        month = month_map[month_name]
        return f"{year:04d}-{month:02d}-{day:02d}"

    return ""


def _extract_country(
    line: str,
    known_countries: list[str],
) -> str:
    line_key = _norm_key(line)

    matches = [
        country
        for country in known_countries
        if _norm_key(country)
        and _norm_key(country) in line_key
    ]

    if not matches:
        return _clean(line)

    matches.sort(key=len, reverse=True)
    return matches[0]


def _extract_value(
    field: str,
    line: str,
    known_countries: list[str],
) -> str:
    if field == "cert_no":
        return _extract_cert_no(line)
    if field == "manufacturer":
        return _extract_manufacturer(line)
    if field == "expiry_date":
        return _extract_expiry_date(line)
    if field == "manufacturing_country":
        return _extract_country(line, known_countries)
    return _clean(line)


def _sigmoid_gap(gap: float) -> float:
    try:
        return round(1.0 / (1.0 + math.exp(-float(gap))), 6)
    except OverflowError:
        return 1.0 if gap > 0 else 0.0


def _default_runtime_root() -> Path:
    return Path(
        os.getenv(
            "HALAL_ML_RUNTIME_ROOT",
            r"D:\halal_web_runtime\certificate_classifier",
        )
    )


def _resolve_model_root(
    model_root: str | Path | None = None,
) -> Path:
    if model_root:
        root = Path(model_root)
    else:
        pointer = (
            _default_runtime_root()
            / "models"
            / "current_field_model.txt"
        )
        if not pointer.exists():
            raise FileNotFoundError(
                f"필드 모델 포인터가 없습니다: {pointer}"
            )
        root = Path(
            pointer.read_text(
                encoding="utf-8-sig",
            ).strip()
        )

    if not root.exists():
        raise FileNotFoundError(
            f"필드 모델 폴더가 없습니다: {root}"
        )

    return root


@lru_cache(maxsize=8)
def _load_field_model(
    model_root_text: str,
    field: str,
) -> dict[str, Any]:
    path = Path(model_root_text) / f"{field}_ranker.joblib"
    if not path.exists():
        raise FileNotFoundError(path)
    return joblib.load(path)


def predict_fields(
    combined_text: str,
    institution: str,
    *,
    fields: list[str] | tuple[str, ...] | None = None,
    top_k: int = 3,
    model_root: str | Path | None = None,
) -> dict[str, Any]:
    root = _resolve_model_root(model_root)
    selected_fields = tuple(fields or FIELD_ORDER)
    results: dict[str, Any] = {}

    for field in selected_fields:
        payload = _load_field_model(str(root), field)
        pipeline = payload["pipeline"]
        metadata = payload.get("metadata") or {}
        candidates = _candidate_rows(
            field,
            institution,
            combined_text,
        )

        if not candidates:
            results[field] = {
                "value": "",
                "selected_line": "",
                "candidates": [],
                "requires_review": True,
                "reason": "후보 줄을 생성하지 못했습니다.",
            }
            continue

        matrix = [
            candidate["feature_text"]
            for candidate in candidates
        ]
        scores = np.asarray(
            pipeline.decision_function(matrix),
            dtype=float,
        ).reshape(-1)

        order = np.argsort(scores)[::-1]
        top_indices = order[: max(1, int(top_k))]
        top_rows: list[dict[str, Any]] = []
        known_countries = list(
            metadata.get("known_countries") or []
        )

        for index in top_indices:
            candidate = candidates[int(index)]
            top_rows.append({
                "page": int(candidate["page"]),
                "line_no": int(candidate["line_no"]),
                "line": candidate["line"],
                "score": round(float(scores[int(index)]), 6),
                "value": _extract_value(
                    field,
                    candidate["line"],
                    known_countries,
                ),
            })

        top_score = float(top_rows[0]["score"])
        second_score = (
            float(top_rows[1]["score"])
            if len(top_rows) > 1
            else top_score
        )
        gap = top_score - second_score
        threshold = float(
            metadata.get(
                "recommended_review_gap_threshold",
                0.0,
            )
            or 0.0
        )

        experimental = bool(
            metadata.get("experimental", False)
        )
        requires_review = bool(
            experimental
            or gap < threshold
        )

        results[field] = {
            "value": top_rows[0]["value"],
            "selected_line": top_rows[0]["line"],
            "page": top_rows[0]["page"],
            "line_no": top_rows[0]["line_no"],
            "score": top_score,
            "score_gap": round(gap, 6),
            "relative_confidence": _sigmoid_gap(gap),
            "requires_review": requires_review,
            "experimental": experimental,
            "candidates": top_rows,
            "confidence_note": (
                "relative_confidence는 후보 간 SVM 점수 차이를 "
                "변환한 상대값이며 보정된 확률이 아닙니다."
            ),
        }

    return {
        "institution": institution,
        "model_root": str(root),
        "fields": results,
    }


def load_combined_text_by_sha(
    sha256: str,
    *,
    runtime_root: str | Path | None = None,
) -> str:
    root = (
        Path(runtime_root)
        if runtime_root
        else _default_runtime_root()
    )
    path = (
        root
        / "text_cache"
        / "combined"
        / f"{sha256}.json"
    )
    payload = json.loads(
        path.read_text(encoding="utf-8-sig")
    )
    return str(payload.get("combined_text") or "")