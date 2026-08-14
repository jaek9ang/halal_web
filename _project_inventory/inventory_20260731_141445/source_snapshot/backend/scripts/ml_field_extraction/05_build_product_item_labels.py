from __future__ import annotations

import argparse
import html
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd


SCHEMA_VERSION = "product_item_label_candidates_v1"
ORG_ALIASES = {
    "LLS-ISA": "ISA",
    "LLS ISA": "ISA",
    "HALALCONTROL": "HALAL CONTROL",
}
EMPTY_WORDS = {"", "-", "NONE", "NULL", "NAN", "NAT", "UNKNOWN"}

PAGE_MARKER_RE = re.compile(
    r"---\s*PAGE\s+(\d+)(?:\s*\[[^\]]*\])?\s*---",
    re.IGNORECASE,
)
WHITESPACE_RE = re.compile(r"\s+")

PRODUCT_HEADER_RE = re.compile(
    r"\b("
    r"PRODUCT(?:S)?(?:\s+NAME|\s+LIST|\s+DESCRIPTION|\s+TYPE)?|"
    r"ITEM(?:S)?(?:\s+NAME|\s+DESCRIPTION)?|"
    r"NAMA\s+PRODUK|JENIS\s+PRODUK|PRODUCTTYPE|"
    r"NAME\s+OF\s+PRODUCT"
    r")\b",
    re.IGNORECASE,
)
PRODUCT_CERT_HEADER_RE = re.compile(
    r"\b("
    r"PRODUCT\s+CERTIFICATE(?:\s*(?:NO|NUMBER|#))?|"
    r"CERTIFICATE\s*#|CERTIFICATE\s+NO|"
    r"HALAL\s+CERTIFICATE\s*(?:NO|NUMBER|#)"
    r")\b",
    re.IGNORECASE,
)
HALAL_ID_HEADER_RE = re.compile(
    r"\b(HALAL[-\s]?ID|HALAL\s+ID|REGISTRATION\s+(?:NO|NUMBER))\b",
    re.IGNORECASE,
)
PRODUCT_CODE_HEADER_RE = re.compile(
    r"\b(PRODUCT\s+CODE|ITEM\s+CODE|CODE|KODE\s+PRODUK)\b",
    re.IGNORECASE,
)
DOCUMENT_NO_HEADER_RE = re.compile(
    r"\b(DOCUMENT\s*(?:NO|NUMBER|#)|DOC\.?\s*(?:NO|NUMBER|#))\b",
    re.IGNORECASE,
)
DOCUMENT_CERT_HEADER_RE = re.compile(
    r"\b("
    r"CERTIFICATE\s*(?:NO|NUMBER|#)|"
    r"NOMOR\s+SERTIFIKAT|CERTIFICATION\s+NO"
    r")\b",
    re.IGNORECASE,
)

DATE_RE = re.compile(
    r"\b(?:19|20)\d{2}[-./]\d{1,2}[-./]\d{1,2}\b|"
    r"\b\d{1,2}[-./]\d{1,2}[-./](?:19|20)\d{2}\b|"
    r"\b(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|"
    r"SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+\d{1,2}(?:ST|ND|RD|TH)?"
    r"[,.]?\s+(?:19|20)\d{2}\b|"
    r"\b\d{1,2}(?:ST|ND|RD|TH)?\s+(?:JANUARY|FEBRUARY|MARCH|APRIL|"
    r"MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)"
    r"[,.]?\s+(?:19|20)\d{2}\b",
    re.IGNORECASE,
)

COMPANY_SUFFIX_RE = re.compile(
    r"\b(?:CO\.?|COMPANY|CORP\.?|CORPORATION|INC\.?|LTD\.?|LIMITED|"
    r"LLC|PTE\.?\s*LTD\.?|SDN\.?\s*BHD\.?|GMBH|B\.?V\.?|"
    r"S\.?A\.?|PLC|AG|INDUSTRIES?|PRIVATE\s+LIMITED)\b",
    re.IGNORECASE,
)

GENERIC_LINE_RE = re.compile(
    r"^\s*(?:"
    r"PRODUCT(?:S)?|PRODUCT\s+NAME|PRODUCT\s+CODE|"
    r"PRODUCT\s+CERTIFICATE(?:\s*(?:NO|NUMBER|#))?|"
    r"HALAL[-\s]?ID|REGISTRATION\s+(?:NO|NUMBER)|"
    r"CERTIFICATE\s*(?:NO|NUMBER|#)|DOCUMENT\s*(?:NO|NUMBER|#)|"
    r"NO\.?|NUMBER|CODE|ITEM|DESCRIPTION|NAME|TYPE|"
    r"DATE|VALID\s+UNTIL|EXPIRY\s+DATE|"
    r"COMPANY\s+NAME|MANUFACTURER|FACTORY|ADDRESS|"
    r"PAGE\s+\d+(?:\s+OF\s+\d+)?"
    r")\s*[:：#-]*\s*$",
    re.IGNORECASE,
)

SIGNATURE_OR_FOOTER_RE = re.compile(
    r"\b("
    r"CHAIRMAN|PRESIDENT|DIRECTOR|SECRETARY|AUDITOR|MUFTI|"
    r"SIGNATURE|AUTHORIZED|THIS\s+CERTIFICATE|SUBJECT\s+TO\s+RENEWAL|"
    r"PAGE\s+\d+\s+OF\s+\d+|WEBSITE|TEL(?:EPHONE)?|FAX"
    r")\b",
    re.IGNORECASE,
)

# 너무 좁은 기관 전용 정규식이 아니라, 인증번호 후보를 찾는 일반 패턴입니다.
PRODUCT_CERT_NO_RE = re.compile(
    r"\b("
    r"HC[-\s][A-Z0-9][A-Z0-9./_-]{4,}|"
    r"HCA\s*[A-Z0-9][A-Z0-9./_-]{3,}|"
    r"HFQ[-\s][A-Z0-9][A-Z0-9./_-]{3,}|"
    r"PRN\d{8,}|"
    r"[A-Z]{1,6}[-/]\d{2,}[A-Z0-9./_-]{2,}"
    r")\b",
    re.IGNORECASE,
)

HALAL_ID_RE = re.compile(
    r"(?<![A-Z0-9])([A-Z]\d{4,7})(?![A-Z0-9])",
    re.IGNORECASE,
)
PRODUCT_CODE_RE = re.compile(
    r"(?<![A-Z0-9])("
    r"[A-Z0-9]{2,8}(?:[-_/][A-Z0-9]{2,8}){1,3}|"
    r"\d{5,12}"
    r")(?![A-Z0-9])",
    re.IGNORECASE,
)

CERT_STOP_TOKENS = {
    "CERTIFICATE",
    "REGISTRATION",
    "DOCUMENT",
    "PRODUCT",
    "NUMBER",
    "HALAL",
    "VALID",
    "DATE",
}


def clean(value: Any) -> str:
    text = str(value or "").replace("\u00a0", " ").replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    if text.upper() in EMPTY_WORDS:
        return ""

    return text


def normalize_org(value: Any) -> str:
    text = clean(value).upper().replace("_", " ")
    text = WHITESPACE_RE.sub(" ", text).strip()
    return ORG_ALIASES.get(text, text)


def norm_key(value: Any) -> str:
    return re.sub(
        r"[^A-Z0-9가-힣]+",
        "",
        clean(value).upper(),
    )


def norm_words(value: Any) -> str:
    return WHITESPACE_RE.sub(
        " ",
        re.sub(
            r"[^A-Z0-9가-힣]+",
            " ",
            clean(value).upper(),
        ),
    ).strip()


def text_similarity(left: Any, right: Any) -> float:
    left_key = norm_words(left)
    right_key = norm_words(right)

    if not left_key or not right_key:
        return 0.0

    if left_key == right_key:
        return 1.0

    if left_key in right_key or right_key in left_key:
        length_ratio = min(len(left_key), len(right_key)) / max(
            len(left_key),
            len(right_key),
        )
        return 0.86 + (0.14 * length_ratio)

    left_tokens = set(left_key.split())
    right_tokens = set(right_key.split())
    intersection = len(left_tokens & right_tokens)
    containment = intersection / max(
        1,
        min(len(left_tokens), len(right_tokens)),
    )
    jaccard = intersection / max(
        1,
        len(left_tokens | right_tokens),
    )
    sequence = SequenceMatcher(None, left_key, right_key).ratio()

    return max(sequence, containment, jaccard)


def normalize_cert_no(value: Any) -> str:
    text = norm_key(value)

    if text.startswith("LPPOM"):
        text = text[5:]

    if re.fullmatch(r"ID\d{10,}", text):
        text = text[2:]

    return text


def split_pages_and_lines(text: str) -> list[dict[str, Any]]:
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
        for original_line_no, line in enumerate(
            chunk.splitlines(),
            start=1,
        ):
            current = clean(line)

            if not current:
                continue

            if PAGE_MARKER_RE.fullmatch(current):
                continue

            rows.append({
                "global_index": global_index,
                "page": page,
                "line_no": original_line_no,
                "line": current,
            })
            global_index += 1

    return rows


def make_flat_text(lines: list[dict[str, Any]]) -> str:
    return clean(
        " ".join(row["line"] for row in lines)
    )


def find_product_headers(
    lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    headers: list[dict[str, Any]] = []

    for row in lines:
        line = row["line"]
        signals = {
            "product_header": bool(PRODUCT_HEADER_RE.search(line)),
            "product_cert_header": bool(
                PRODUCT_CERT_HEADER_RE.search(line)
            ),
            "halal_id_header": bool(HALAL_ID_HEADER_RE.search(line)),
            "product_code_header": bool(
                PRODUCT_CODE_HEADER_RE.search(line)
            ),
        }

        score = sum(signals.values())

        if score:
            headers.append({
                **row,
                "header_score": score,
                "signals": " | ".join(
                    key
                    for key, value in signals.items()
                    if value
                ),
            })

    return headers


def extract_product_cert_numbers(text: str) -> list[str]:
    values: list[str] = []

    for match in PRODUCT_CERT_NO_RE.finditer(text):
        value = clean(match.group(1)).strip(" .,:;|")
        key = normalize_cert_no(value)

        if len(key) < 5:
            continue

        if key in CERT_STOP_TOKENS:
            continue

        values.append(value)

    return list(dict.fromkeys(values))


def extract_halal_ids(text: str) -> list[str]:
    values: list[str] = []

    for match in HALAL_ID_RE.finditer(text):
        value = clean(match.group(1)).upper()

        if PRODUCT_CERT_NO_RE.fullmatch(value):
            continue

        values.append(value)

    return list(dict.fromkeys(values))


def extract_product_codes(text: str) -> list[str]:
    values: list[str] = []

    for match in PRODUCT_CODE_RE.finditer(text):
        value = clean(match.group(1)).upper()

        if PRODUCT_CERT_NO_RE.fullmatch(value):
            continue

        if DATE_RE.fullmatch(value):
            continue

        if value in {"PAGE", "PRODUCT", "CERTIFICATE"}:
            continue

        values.append(value)

    return list(dict.fromkeys(values))


def likely_product_name_line(line: str) -> bool:
    text = clean(line)

    if not text:
        return False

    if GENERIC_LINE_RE.fullmatch(text):
        return False

    if SIGNATURE_OR_FOOTER_RE.search(text):
        return False

    if DATE_RE.search(text):
        return False

    if DOCUMENT_NO_HEADER_RE.search(text):
        return False

    if PRODUCT_CERT_HEADER_RE.search(text):
        return False

    if len(norm_key(text)) < 3:
        return False

    alpha_count = sum(
        character.isalpha()
        for character in text
    )
    digit_count = sum(
        character.isdigit()
        for character in text
    )

    if alpha_count < 2:
        return False

    if digit_count > alpha_count * 2:
        return False

    return True


def choose_product_name(
    lines: list[dict[str, Any]],
    cert_index: int,
    span_start: int,
) -> tuple[str, int, int, list[str]]:
    candidates: list[tuple[float, int, str]] = []

    start = max(span_start, cert_index - 4)

    for index in range(start, cert_index + 1):
        line = lines[index]["line"]

        if not likely_product_name_line(line):
            continue

        upper = line.upper()
        score = 0.0

        if index < cert_index:
            score += 2.0

        distance = cert_index - index
        score += max(0.0, 2.5 - (distance * 0.55))

        if COMPANY_SUFFIX_RE.search(line):
            score -= 2.5

        if PRODUCT_HEADER_RE.search(line):
            score -= 3.0

        if len(line) <= 180:
            score += 0.5

        if re.match(r"^\s*\d+[.)]\s*", line):
            score += 0.4

        if PRODUCT_CERT_NO_RE.search(line):
            score -= 1.0

        candidates.append((score, index, line))

    if not candidates:
        return "", 0, 0, []

    candidates.sort(
        key=lambda item: (
            item[0],
            item[1],
        ),
        reverse=True,
    )
    _, selected_index, selected_line = candidates[0]

    block_start = selected_index
    block_end = selected_index
    block_lines = [selected_line]

    # 제품명이 두 줄로 분리됐을 때만 조건부로 병합합니다.
    if selected_index > start:
        previous = lines[selected_index - 1]["line"]

        if (
            likely_product_name_line(previous)
            and not PRODUCT_CERT_NO_RE.search(previous)
            and not PRODUCT_CODE_RE.fullmatch(norm_key(previous))
            and len(previous) <= 120
            and len(selected_line) <= 120
        ):
            previous_upper = previous.upper()
            selected_upper = selected_line.upper()

            join_signal = bool(
                selected_upper.startswith(
                    (
                        "CO.",
                        "CO,",
                        "LTD",
                        "LIMITED",
                        "INC",
                        "BV",
                        "B.V",
                        "PTE",
                        "SDN",
                    )
                )
                or previous.endswith(("-", "/", ","))
                or (
                    len(previous.split()) <= 8
                    and len(selected_line.split()) <= 8
                )
            )

            if join_signal:
                block_start = selected_index - 1
                block_lines.insert(0, previous)

    product_name = clean(
        " ".join(
            re.sub(
                r"^\s*\d+[.)]\s*",
                "",
                item,
            )
            for item in block_lines
        )
    )

    return (
        product_name,
        int(lines[block_start]["line_no"]),
        int(lines[block_end]["line_no"]),
        block_lines,
    )


def nearest_header_index(
    lines: list[dict[str, Any]],
    current_index: int,
) -> int:
    current_page = int(lines[current_index]["page"])

    for index in range(current_index, -1, -1):
        row = lines[index]

        if int(row["page"]) != current_page:
            break

        if (
            PRODUCT_HEADER_RE.search(row["line"])
            or PRODUCT_CERT_HEADER_RE.search(row["line"])
        ):
            return index

    return max(
        0,
        current_index - 8,
    )


def find_document_number_candidates(
    lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    for index, row in enumerate(lines):
        line = row["line"]
        upper = line.upper()

        if row["page"] > 3:
            continue

        label_type = ""

        if DOCUMENT_NO_HEADER_RE.search(line):
            label_type = "DOCUMENT_NO"
        elif DOCUMENT_CERT_HEADER_RE.search(line):
            label_type = "DOCUMENT_CERTIFICATE_NO"
        elif "CERTIFICATE" in upper and re.search(r"\d", line):
            label_type = "CERTIFICATE_CONTEXT"

        if not label_type:
            continue

        block = [line]

        if index + 1 < len(lines):
            following = lines[index + 1]

            if following["page"] == row["page"]:
                block.append(following["line"])

        block_text = clean(" | ".join(block))
        cert_numbers = extract_product_cert_numbers(block_text)

        # 일반 문서번호는 HC- 형식이 아닐 수 있어 추가 추출합니다.
        generic_numbers = re.findall(
            r"\b[A-Z0-9][A-Z0-9./_-]{5,}\b",
            block_text.upper(),
        )
        generic_numbers = [
            value
            for value in generic_numbers
            if re.search(r"\d", value)
            and value not in {
                "CERTIFICATE",
                "DOCUMENT",
                "REGISTRATION",
            }
        ]

        values = list(
            dict.fromkeys(
                cert_numbers + generic_numbers
            )
        )

        for value in values[:4]:
            candidates.append({
                "page": int(row["page"]),
                "line_no": int(row["line_no"]),
                "label_type": label_type,
                "value": value,
                "evidence": block_text[:500],
            })

    return candidates


def build_product_rows(
    lines: list[dict[str, Any]],
    institution: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    headers = find_product_headers(lines)
    rows: list[dict[str, Any]] = []

    seen: set[tuple[int, str, str]] = set()

    for index, row in enumerate(lines):
        line = row["line"]
        cert_numbers = extract_product_cert_numbers(line)

        if not cert_numbers:
            continue

        header_index = nearest_header_index(lines, index)
        header_line = lines[header_index]["line"]
        page = int(row["page"])

        for cert_no in cert_numbers:
            key = (
                page,
                normalize_cert_no(cert_no),
                norm_key(line),
            )

            if key in seen:
                continue

            seen.add(key)

            (
                product_name,
                product_start_line,
                product_end_line,
                product_name_lines,
            ) = choose_product_name(
                lines,
                index,
                header_index,
            )

            context_start = max(header_index, index - 4)
            context_end = min(len(lines), index + 3)
            context_rows = lines[context_start:context_end]
            block_text = clean(
                " | ".join(
                    item["line"]
                    for item in context_rows
                    if item["page"] == page
                )
            )

            halal_ids = [
                value
                for value in extract_halal_ids(block_text)
                if normalize_cert_no(value)
                != normalize_cert_no(cert_no)
            ]
            product_codes = [
                value
                for value in extract_product_codes(block_text)
                if normalize_cert_no(value)
                != normalize_cert_no(cert_no)
                and value not in halal_ids
            ]

            header_signals = {
                "product_header": bool(
                    PRODUCT_HEADER_RE.search(header_line)
                ),
                "product_cert_header": bool(
                    PRODUCT_CERT_HEADER_RE.search(header_line)
                ),
                "halal_id_header": bool(
                    HALAL_ID_HEADER_RE.search(header_line)
                ),
                "product_code_header": bool(
                    PRODUCT_CODE_HEADER_RE.search(header_line)
                ),
            }

            row_score = 0.0
            reasons: list[str] = []

            if product_name:
                row_score += 0.32
                reasons.append("product_name")

            if header_signals["product_header"]:
                row_score += 0.18
                reasons.append("product_header")

            if header_signals["product_cert_header"]:
                row_score += 0.22
                reasons.append("product_cert_header")

            if halal_ids:
                row_score += 0.08
                reasons.append("halal_id")

            if product_codes:
                row_score += 0.05
                reasons.append("product_code")

            if page > 1:
                row_score += 0.04
                reasons.append("appendix_page")

            same_page_cert_count = sum(
                1
                for candidate in lines
                if candidate["page"] == page
                and extract_product_cert_numbers(
                    candidate["line"]
                )
            )

            if same_page_cert_count >= 2:
                row_score += 0.16
                reasons.append("repeated_cert_rows")

            if (
                not product_name
                or GENERIC_LINE_RE.fullmatch(product_name)
            ):
                row_score -= 0.25
                reasons.append("weak_product_name")

            if COMPANY_SUFFIX_RE.search(product_name):
                row_score -= 0.12
                reasons.append("company_like_name")

            row_score = max(
                0.0,
                min(1.0, row_score),
            )

            status = (
                "AUTO_READY"
                if row_score >= 0.72
                else "REVIEW_REQUIRED"
                if row_score >= 0.48
                else "CANDIDATE_ONLY"
            )

            rows.append({
                "institution": institution,
                "page": page,
                "row_anchor_line_no": int(row["line_no"]),
                "product_start_line_no": product_start_line,
                "product_end_line_no": product_end_line,
                "product_name": product_name,
                "product_name_lines": json.dumps(
                    product_name_lines,
                    ensure_ascii=False,
                ),
                "product_code": (
                    product_codes[0]
                    if product_codes
                    else ""
                ),
                "halal_id": (
                    halal_ids[0]
                    if halal_ids
                    else ""
                ),
                "product_certificate_no": cert_no,
                "header_line": header_line,
                "block_text": block_text[:1000],
                "row_score": round(row_score, 4),
                "row_status": status,
                "row_reasons": " | ".join(reasons),
            })

    # 같은 페이지·인증번호가 중복 검출됐으면 높은 점수 한 건만 유지합니다.
    best_rows: dict[tuple[int, str], dict[str, Any]] = {}

    for item in rows:
        key = (
            int(item["page"]),
            normalize_cert_no(
                item["product_certificate_no"]
            ),
        )
        current = best_rows.get(key)

        if (
            current is None
            or float(item["row_score"])
            > float(current["row_score"])
        ):
            best_rows[key] = item

    return list(best_rows.values()), headers


def classify_structure(
    product_rows: list[dict[str, Any]],
    document_candidates: list[dict[str, Any]],
) -> tuple[str, float, str]:
    high_item_rows = [
        row
        for row in product_rows
        if row["row_status"] == "AUTO_READY"
    ]
    unique_item_numbers = {
        normalize_cert_no(
            row["product_certificate_no"]
        )
        for row in high_item_rows
        if normalize_cert_no(
            row["product_certificate_no"]
        )
    }
    unique_document_numbers = {
        normalize_cert_no(
            candidate["value"]
        )
        for candidate in document_candidates
        if normalize_cert_no(candidate["value"])
    }

    has_item_level = len(unique_item_numbers) >= 2
    has_document_level = bool(
        unique_document_numbers
        - unique_item_numbers
    )

    if has_item_level and has_document_level:
        return (
            "MIXED",
            0.92,
            "문서번호 후보와 서로 다른 품목별 인증번호가 함께 존재합니다.",
        )

    if has_item_level:
        return (
            "ITEM_LEVEL",
            0.88,
            "서로 다른 품목별 인증번호가 2개 이상 검출되었습니다.",
        )

    if has_document_level and len(unique_item_numbers) <= 1:
        return (
            "DOCUMENT_LEVEL",
            0.78,
            "문서번호 후보가 있고 반복 품목별 인증번호는 확인되지 않았습니다.",
        )

    if len(unique_item_numbers) == 1:
        return (
            "UNKNOWN",
            0.52,
            "인증번호 후보가 하나 있어 문서번호와 품목번호를 구분하기 어렵습니다.",
        )

    return (
        "UNKNOWN",
        0.25,
        "문서 구조를 판단할 근거가 부족합니다.",
    )


def load_cache(
    runtime_root: Path,
    sha256: str,
) -> dict[str, Any]:
    path = (
        runtime_root
        / "text_cache"
        / "combined"
        / f"{sha256}.json"
    )

    if not path.exists():
        raise FileNotFoundError(path)

    return json.loads(
        path.read_text(
            encoding="utf-8-sig",
        )
    )


def load_pmf_candidates(
    field_report_root: Path,
) -> pd.DataFrame:
    path = (
        field_report_root
        / "06_pmf_match_candidates.csv"
    )

    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(
        path,
        dtype=str,
        encoding="utf-8-sig",
    ).fillna("")


def bool_value(value: Any) -> bool:
    return clean(value).lower() in {
        "true",
        "1",
        "yes",
        "y",
    }


def build_pmf_links(
    sha256: str,
    product_rows: list[dict[str, Any]],
    pmf_frame: pd.DataFrame,
) -> list[dict[str, Any]]:
    if pmf_frame.empty:
        return []

    candidates = pmf_frame[
        pmf_frame["sha256"].astype(str)
        == sha256
    ].copy()

    if candidates.empty:
        return []

    links: list[dict[str, Any]] = []

    for _, pmf_row in candidates.iterrows():
        pmf_name = clean(
            pmf_row.get("english_name")
            or pmf_row.get("material_name")
        )
        material_name = clean(
            pmf_row.get("material_name")
        )
        english_name = clean(
            pmf_row.get("english_name")
        )

        row_scores: list[tuple[float, int]] = []

        for index, product_row in enumerate(product_rows):
            score = max(
                text_similarity(
                    pmf_name,
                    product_row.get("product_name"),
                ),
                text_similarity(
                    material_name,
                    product_row.get("product_name"),
                ),
                text_similarity(
                    english_name,
                    product_row.get("product_name"),
                ),
            )
            row_scores.append((score, index))

        row_scores.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        top_score = (
            row_scores[0][0]
            if row_scores
            else 0.0
        )
        second_score = (
            row_scores[1][0]
            if len(row_scores) > 1
            else 0.0
        )

        selected = (
            product_rows[row_scores[0][1]]
            if row_scores
            else {}
        )

        is_strong_doc_match = bool_value(
            pmf_row.get("is_strong")
        )
        link_status = "UNLINKED_SAMPLE"

        if top_score >= 0.88 and (
            top_score - second_score >= 0.08
            or top_score >= 0.96
        ):
            link_status = "PMF_LINKED"
        elif top_score >= 0.70:
            link_status = "PMF_MATCH_CANDIDATE"
        elif is_strong_doc_match:
            link_status = "PMF_DOCUMENT_ONLY"

        links.append({
            "sha256": sha256,
            "institution": clean(
                pmf_row.get("institution")
            ),
            "pmf_rank": clean(
                pmf_row.get("rank")
            ),
            "pmf_is_strong_document_match": (
                is_strong_doc_match
            ),
            "pmf_row_pos": clean(
                pmf_row.get("row_pos")
            ),
            "pmf_depth": clean(
                pmf_row.get("depth")
            ),
            "pmf_material_no": clean(
                pmf_row.get("material_no")
            ),
            "pmf_material_name": material_name,
            "pmf_english_name": english_name,
            "pmf_maker": clean(
                pmf_row.get("maker")
            ),
            "pmf_cert_no": clean(
                pmf_row.get("cert_no")
            ),
            "selected_product_name": clean(
                selected.get("product_name")
            ),
            "selected_product_certificate_no": clean(
                selected.get(
                    "product_certificate_no"
                )
            ),
            "selected_halal_id": clean(
                selected.get("halal_id")
            ),
            "product_name_similarity": round(
                top_score,
                4,
            ),
            "similarity_margin": round(
                top_score - second_score,
                4,
            ),
            "link_status": link_status,
        })

    return links


def write_jsonl(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    with path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )


def create_html_report(
    summary: dict[str, Any],
    structure_frame: pd.DataFrame,
    coverage_frame: pd.DataFrame,
    review_frame: pd.DataFrame,
    output_path: Path,
) -> None:
    structure_html = structure_frame.head(
        100
    ).to_html(
        index=False,
        escape=True,
    )
    coverage_html = coverage_frame.to_html(
        index=False,
        escape=True,
    )
    review_html = (
        review_frame.head(100).to_html(
            index=False,
            escape=True,
        )
        if not review_frame.empty
        else "<p>검토 대상 없음</p>"
    )

    cards = [
        ("문서", summary["total_documents"]),
        ("제품행 후보", summary["product_row_count"]),
        ("자동 학습 제품행", summary["auto_ready_product_row_count"]),
        ("PMF 연결", summary["pmf_linked_count"]),
        ("ITEM_LEVEL", summary["structure_counts"].get("ITEM_LEVEL", 0)),
        ("MIXED", summary["structure_counts"].get("MIXED", 0)),
    ]

    cards_html = "".join(
        "<div class='card'><div>"
        + html.escape(str(label))
        + "</div><div class='value'>"
        + html.escape(str(value))
        + "</div></div>"
        for label, value in cards
    )

    text = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>제품행·품목별 인증번호 라벨 후보</title>
<style>
body {{
    font-family: Arial, "Malgun Gothic", sans-serif;
    margin: 28px;
    color: #1f2937;
    background: #f8fafc;
}}
.grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 12px;
}}
.card, .section {{
    background: white;
    border: 1px solid #dbe3ec;
    border-radius: 10px;
    padding: 16px;
    margin: 14px 0;
}}
.value {{
    font-size: 24px;
    font-weight: 700;
    margin-top: 6px;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    font-size: 12px;
}}
th, td {{
    border-bottom: 1px solid #e5e7eb;
    padding: 7px;
    text-align: left;
    vertical-align: top;
}}
.note {{
    color: #64748b;
    font-size: 14px;
}}
</style>
</head>
<body>
<h1>제품행·품목별 인증번호 라벨 후보</h1>
<p class="note">
품목별 인증번호를 문서당 문자열 하나가 아니라
product_certificate_items 배열의 반복 항목으로 구성했습니다.
PMF는 제품행 추출 후 연결하며, PMF가 없는 샘플도 구조 학습에는 포함할 수 있습니다.
</p>
<div class="grid">{cards_html}</div>
<div class="section">
<h2>문서 구조 후보</h2>
{structure_html}
</div>
<div class="section">
<h2>기관별 커버리지</h2>
{coverage_html}
</div>
<div class="section">
<h2>검토 대상 제품행</h2>
{review_html}
</div>
</body>
</html>"""

    output_path.write_text(
        text,
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root",
        required=True,
    )
    parser.add_argument(
        "--runtime-root",
        required=True,
    )
    parser.add_argument(
        "--field-report-root",
        required=True,
    )
    args = parser.parse_args()

    project_root = Path(
        args.project_root
    ).resolve()
    runtime_root = Path(
        args.runtime_root
    ).resolve()
    field_report_root = Path(
        args.field_report_root
    ).resolve()

    document_path = (
        field_report_root
        / "01_document_candidates.csv"
    )
    group_path = (
        field_report_root
        / "07_group_assignments.csv"
    )

    if not document_path.exists():
        raise FileNotFoundError(document_path)

    documents = pd.read_csv(
        document_path,
        dtype=str,
        encoding="utf-8-sig",
    ).fillna("")

    groups = (
        pd.read_csv(
            group_path,
            dtype=str,
            encoding="utf-8-sig",
        ).fillna("")
        if group_path.exists()
        else pd.DataFrame()
    )

    group_map = {
        clean(row.get("sha256")): clean(
            row.get("validation_group")
        )
        for _, row in groups.iterrows()
        if clean(row.get("sha256"))
    }

    pmf_frame = load_pmf_candidates(
        field_report_root
    )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    report_root = (
        runtime_root
        / "reports"
        / f"product_item_labels_{stamp}"
    )
    report_root.mkdir(
        parents=True,
        exist_ok=False,
    )

    structure_rows: list[dict[str, Any]] = []
    product_rows_output: list[dict[str, Any]] = []
    header_rows_output: list[dict[str, Any]] = []
    document_number_rows: list[dict[str, Any]] = []
    pmf_links_output: list[dict[str, Any]] = []
    auto_ready_documents: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []

    for index, document in documents.iterrows():
        sha256 = clean(document.get("sha256"))
        institution = normalize_org(
            document.get("institution")
        )
        file_name = clean(
            document.get("file_name")
        )
        pdf_path = clean(
            document.get("pdf_path")
        )

        if not sha256:
            continue

        payload = load_cache(
            runtime_root,
            sha256,
        )
        combined_text = str(
            payload.get("combined_text")
            or ""
        )
        lines = split_pages_and_lines(
            combined_text
        )
        flat_text = make_flat_text(lines)

        product_rows, headers = build_product_rows(
            lines,
            institution,
        )
        document_numbers = (
            find_document_number_candidates(
                lines
            )
        )

        structure, structure_score, structure_reason = (
            classify_structure(
                product_rows,
                document_numbers,
            )
        )

        validation_group = group_map.get(
            sha256,
            f"{institution}::DOC::{sha256[:16]}",
        )

        pmf_links = build_pmf_links(
            sha256,
            product_rows,
            pmf_frame,
        )

        pmf_links_output.extend(pmf_links)

        linked_count = sum(
            link["link_status"] == "PMF_LINKED"
            for link in pmf_links
        )
        candidate_link_count = sum(
            link["link_status"]
            == "PMF_MATCH_CANDIDATE"
            for link in pmf_links
        )

        if not pmf_links:
            document_link_status = "UNLINKED_SAMPLE"
        elif linked_count:
            document_link_status = "PMF_LINKED"
        elif candidate_link_count:
            document_link_status = (
                "PMF_MATCH_CANDIDATE"
            )
        else:
            document_link_status = "PMF_DOCUMENT_ONLY"

        structure_rows.append({
            "sha256": sha256,
            "institution": institution,
            "file_name": file_name,
            "pdf_path": pdf_path,
            "validation_group": validation_group,
            "certificate_structure": structure,
            "structure_score": round(
                structure_score,
                4,
            ),
            "structure_reason": structure_reason,
            "product_header_count": len(headers),
            "product_row_count": len(product_rows),
            "auto_ready_product_row_count": sum(
                row["row_status"]
                == "AUTO_READY"
                for row in product_rows
            ),
            "document_number_candidate_count": len(
                document_numbers
            ),
            "document_link_status": (
                document_link_status
            ),
            "pmf_linked_row_count": linked_count,
            "flat_text_length": len(flat_text),
        })

        for header in headers:
            header_rows_output.append({
                "sha256": sha256,
                "institution": institution,
                "file_name": file_name,
                **header,
            })

        for candidate in document_numbers:
            document_number_rows.append({
                "sha256": sha256,
                "institution": institution,
                "file_name": file_name,
                **candidate,
            })

        document_item_payloads: list[dict[str, Any]] = []

        for row_index, row in enumerate(
            sorted(
                product_rows,
                key=lambda item: (
                    int(item["page"]),
                    int(item["row_anchor_line_no"]),
                ),
            ),
            start=1,
        ):
            row_payload = {
                "schema_version": SCHEMA_VERSION,
                "sha256": sha256,
                "institution": institution,
                "file_name": file_name,
                "pdf_path": pdf_path,
                "validation_group": validation_group,
                "certificate_structure": structure,
                "item_index": row_index,
                **row,
            }
            product_rows_output.append(row_payload)

            document_item_payloads.append({
                "item_index": row_index,
                "page": int(row["page"]),
                "product_name": clean(
                    row.get("product_name")
                ),
                "product_code": clean(
                    row.get("product_code")
                ),
                "halal_id": clean(
                    row.get("halal_id")
                ),
                "product_certificate_no": clean(
                    row.get(
                        "product_certificate_no"
                    )
                ),
                "evidence": clean(
                    row.get("block_text")
                ),
                "label_status": clean(
                    row.get("row_status")
                ),
                "label_score": float(
                    row.get("row_score")
                    or 0.0
                ),
            })

            if row["row_status"] != "AUTO_READY":
                review_rows.append(row_payload)

        auto_items = [
            item
            for item in document_item_payloads
            if item["label_status"] == "AUTO_READY"
        ]

        if auto_items:
            auto_ready_documents.append({
                "schema_version": SCHEMA_VERSION,
                "sha256": sha256,
                "institution": institution,
                "file_name": file_name,
                "validation_group": validation_group,
                "certificate_structure": structure,
                "document_link_status": document_link_status,
                "document_number_candidates": (
                    document_numbers
                ),
                "product_certificate_items": (
                    auto_items
                ),
            })

        if index % 25 == 0 or index + 1 == len(
            documents
        ):
            print(
                f"[{index + 1}/{len(documents)}] "
                "제품행 후보 생성 완료"
            )

    structure_frame = pd.DataFrame(
        structure_rows
    )
    product_frame = pd.DataFrame(
        product_rows_output
    )
    header_frame = pd.DataFrame(
        header_rows_output
    )
    document_number_frame = pd.DataFrame(
        document_number_rows
    )
    pmf_link_frame = pd.DataFrame(
        pmf_links_output
    )
    review_frame = pd.DataFrame(
        review_rows
    )

    if product_frame.empty:
        coverage_frame = pd.DataFrame(
            columns=[
                "institution",
                "documents",
                "product_rows",
                "auto_ready_rows",
                "review_rows",
                "auto_ready_rate",
            ]
        )
    else:
        coverage_rows: list[dict[str, Any]] = []

        for institution, group in product_frame.groupby(
            "institution"
        ):
            auto_count = int(
                (
                    group["row_status"]
                    == "AUTO_READY"
                ).sum()
            )
            review_count = int(
                (
                    group["row_status"]
                    != "AUTO_READY"
                ).sum()
            )

            coverage_rows.append({
                "institution": institution,
                "documents": int(
                    group["sha256"].nunique()
                ),
                "product_rows": int(
                    len(group)
                ),
                "auto_ready_rows": auto_count,
                "review_rows": review_count,
                "auto_ready_rate": round(
                    auto_count / len(group),
                    4,
                ),
            })

        coverage_frame = pd.DataFrame(
            coverage_rows
        ).sort_values(
            "institution"
        )

    structure_counts = Counter(
        structure_frame[
            "certificate_structure"
        ].astype(str)
    )

    link_counts = Counter(
        pmf_link_frame["link_status"].astype(str)
        if not pmf_link_frame.empty
        else []
    )

    row_status_counts = Counter(
        product_frame["row_status"].astype(str)
        if not product_frame.empty
        else []
    )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "run_id": stamp,
        "created_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "project_root": str(project_root),
        "runtime_root": str(runtime_root),
        "field_report_root": str(
            field_report_root
        ),
        "report_root": str(report_root),
        "total_documents": int(
            structure_frame["sha256"].nunique()
        ),
        "institution_count": int(
            structure_frame[
                "institution"
            ].nunique()
        ),
        "product_row_count": int(
            len(product_frame)
        ),
        "auto_ready_product_row_count": int(
            row_status_counts.get(
                "AUTO_READY",
                0,
            )
        ),
        "review_product_row_count": int(
            len(product_frame)
            - row_status_counts.get(
                "AUTO_READY",
                0,
            )
        ),
        "document_number_candidate_count": int(
            len(document_number_frame)
        ),
        "product_header_count": int(
            len(header_frame)
        ),
        "pmf_linked_count": int(
            link_counts.get(
                "PMF_LINKED",
                0,
            )
        ),
        "pmf_match_candidate_count": int(
            link_counts.get(
                "PMF_MATCH_CANDIDATE",
                0,
            )
        ),
        "structure_counts": dict(
            structure_counts
        ),
        "row_status_counts": dict(
            row_status_counts
        ),
        "pmf_link_status_counts": dict(
            link_counts
        ),
        "data_model": {
            "document_fields": [
                "document_no",
                "document_certificate_no",
                "certificate_holder",
                "manufacturing_site",
                "expiry_date",
            ],
            "repeated_field": "product_certificate_items",
            "item_fields": [
                "product_name",
                "product_code",
                "halal_id",
                "product_certificate_no",
            ],
            "certificate_structure_values": [
                "DOCUMENT_LEVEL",
                "ITEM_LEVEL",
                "MIXED",
                "UNKNOWN",
            ],
        },
        "text_policy": {
            "raw_text": (
                "줄바꿈과 페이지를 보존하여 표·제품행 근거로 사용"
            ),
            "block_text": (
                "같은 제품행 또는 라벨 주변의 인접 줄만 조건부 병합"
            ),
            "flat_text": (
                "전체 검색·분류 보조용이며 제품행 관계 추출에는 사용하지 않음"
            ),
        },
        "important_note": (
            "AUTO_READY 제품행은 약지도 학습 후보입니다. "
            "PMF_LINKED는 PMF 값으로 본문을 덮어쓴 것이 아니라 "
            "추출된 제품행과 PMF 원료를 후처리로 연결한 결과입니다."
        ),
        "next_step": (
            "02_product_item_candidates.csv와 08_review_required.csv를 검토한 뒤, "
            "validation_group 기준으로 제품 목록 페이지 분류 및 제품행 판별 "
            "머신러닝 모델을 학습합니다."
        ),
    }

    structure_frame.to_csv(
        report_root
        / "01_document_structure_candidates.csv",
        index=False,
        encoding="utf-8-sig",
    )
    product_frame.to_csv(
        report_root
        / "02_product_item_candidates.csv",
        index=False,
        encoding="utf-8-sig",
    )
    header_frame.to_csv(
        report_root
        / "03_product_header_candidates.csv",
        index=False,
        encoding="utf-8-sig",
    )
    document_number_frame.to_csv(
        report_root
        / "04_document_number_candidates.csv",
        index=False,
        encoding="utf-8-sig",
    )
    pmf_link_frame.to_csv(
        report_root
        / "05_pmf_product_item_links.csv",
        index=False,
        encoding="utf-8-sig",
    )
    coverage_frame.to_csv(
        report_root
        / "06_institution_product_coverage.csv",
        index=False,
        encoding="utf-8-sig",
    )
    write_jsonl(
        report_root
        / "07_auto_ready_product_items.jsonl",
        auto_ready_documents,
    )
    review_frame.to_csv(
        report_root
        / "08_review_required.csv",
        index=False,
        encoding="utf-8-sig",
    )
    (
        report_root
        / "09_summary.json"
    ).write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    review_template = review_frame.copy()

    if not review_template.empty:
        review_template[
            "review_decision"
        ] = ""
        review_template[
            "reviewed_product_name"
        ] = ""
        review_template[
            "reviewed_product_code"
        ] = ""
        review_template[
            "reviewed_halal_id"
        ] = ""
        review_template[
            "reviewed_product_certificate_no"
        ] = ""
        review_template[
            "review_note"
        ] = ""

    review_template.to_csv(
        report_root
        / "10_manual_review_template.csv",
        index=False,
        encoding="utf-8-sig",
    )

    create_html_report(
        summary,
        structure_frame,
        coverage_frame,
        review_frame,
        report_root / "11_annotation_report.html",
    )

    latest_pointer = (
        runtime_root
        / "reports"
        / "latest_product_item_labels.txt"
    )
    latest_pointer.write_text(
        str(report_root),
        encoding="utf-8",
    )

    print("")
    print("4C 제품행·품목별 인증번호 라벨 후보 생성 완료")
    print(f"문서               : {summary['total_documents']}")
    print(f"제품행 후보         : {summary['product_row_count']}")
    print(f"AUTO_READY 제품행   : {summary['auto_ready_product_row_count']}")
    print(f"PMF 연결            : {summary['pmf_linked_count']}")
    print(f"문서 구조           : {summary['structure_counts']}")
    print(f"보고서               : {report_root}")
    print("")
    print("다음 확인 파일")
    print(" - 09_summary.json")
    print(" - 01_document_structure_candidates.csv")
    print(" - 02_product_item_candidates.csv")
    print(" - 05_pmf_product_item_links.csv")
    print(" - 08_review_required.csv")
    print(" - 11_annotation_report.html")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())