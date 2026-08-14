"""날짜 인식. 인증서마다 표기가 제각각이라 규칙이 가장 많이 쌓이는 곳."""

from __future__ import annotations

from datetime import date
from datetime import datetime
from typing import Any
import re

from app.services.rules.text import (
    clean_ocr_text,
    lines_of,
    normalize_ocr_digits,
    upper_text,
)


MONTHS = {
    "JAN": 1, "JANUARY": 1,
    "FEB": 2, "FEBRUARY": 2,
    "MAR": 3, "MARCH": 3, "MAC": 3,
    "APR": 4, "APRIL": 4,
    "MAY": 5, "MEI": 5,
    "JUN": 6, "JUNE": 6,
    "JUL": 7, "JULY": 7,
    "AUG": 8, "AUGUST": 8, "OGOS": 8,
    "SEP": 9, "SEPT": 9, "SEPTEMBER": 9, "SEPTEMBET": 9,
    "OCT": 10, "OCTOBER": 10, "OKTOBER": 10,
    "NOV": 11, "NOVEMBER": 11,
    "DEC": 12, "DECEMBER": 12,
}


def two_digit_year(y: str) -> int:
    n = int(y)
    if n < 100:
        return 2000 + n if n <= 50 else 1900 + n
    return n


def iso_date(year: int, month: int, day: int) -> str | None:
    try:
        return datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
    except Exception:
        return None


def parse_date_text(raw: str) -> str | None:
    text = normalize_ocr_digits(str(raw or ""))
    text = re.sub(r"(?i)(st|nd|rd|th|rh)\b", "", text)
    text = re.sub(r"\s+", " ", text).strip(" :,-")

    # YYYY-MM-DD / YYYY.MM.DD / YYYY/MM/DD
    m = re.search(r"\b(20\d{2})[-./](\d{1,2})[-./](\d{1,2})\b", text)
    if m:
        return iso_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # DD/MM/YYYY or DD-MM-YYYY
    m = re.search(r"\b(\d{1,2})[-./](\d{1,2})[-./](20\d{2})\b", text)
    if m:
        return iso_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    # Month DD, YYYY
    m = re.search(r"\b([A-Za-z]+)\s+(\d{1,2})\s*,?\s*(20\d{2})\b", text, re.I)
    if m:
        mon = MONTHS.get(m.group(1).upper())
        if mon:
            return iso_date(int(m.group(3)), mon, int(m.group(2)))

    # DD Month YYYY
    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]+)\s*,?\s*(20\d{2})\b", text, re.I)
    if m:
        mon = MONTHS.get(m.group(2).upper())
        if mon:
            return iso_date(int(m.group(3)), mon, int(m.group(1)))

    # 26.12.17 / ~26.12.17
    m = re.search(r"\b(\d{2})[.](\d{1,2})[.](\d{1,2})\b", text)
    if m:
        return iso_date(two_digit_year(m.group(1)), int(m.group(2)), int(m.group(3)))

    return None


def is_ignored_date_context(full_text: str, start: int, end: int) -> bool:
    """
    날짜 후보 주변 문맥에서 유효기간이 아닌 양식 footer/revision/발급일 문구를 제외한다.
    특히 MUI attachment footer의 F.8.2-xx/B-0/06 Oktober 2023 방지.
    """
    around = upper_text(full_text[max(0, start - 80): min(len(full_text), end + 80)])

    ignored_markers = [
        "F.8.2",
        "/B-0/",
        "FORM REVISION",
        "REVISION DATE",
        "DATE OF GENERATE",
        "TARIKH JANAAN SIJIL",
        "GEDUNG MAJELIS ULAMA INDONESIA",
    ]

    return any(marker in around for marker in ignored_markers)


def normalize_date_ocr_text(value: str) -> str:
    """
    OCR 줄바꿈/첨자 때문에 끊긴 날짜를 parser가 읽을 수 있게 보정한다.
    예:
    DECEMBER 18 \\n TH, 2028 -> DECEMBER 18TH, 2028
    October 21°, 2026 -> October 21TH, 2026
    24th January 2027 -> 그대로 유지
    """
    s = str(value or "").replace("\r\n", "\n").replace("\r", "\n")

    months = (
        "JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|"
        "SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER|"
        "JAN|FEB|MAR|APR|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC|"
        "MAC|MEI|OKTOBER|DISEMBER"
    )

    # DECEMBER 18 \n TH, 2028
    s = re.sub(
        rf"\b({months})\s+(\d{{1,2}})\s*\n\s*(ST|ND|RD|TH|RH)\s*,?\s*(20\d{{2}})\b",
        r"\1 \2\3, \4",
        s,
        flags=re.I,
    )

    # MARCH 28 \n th, 2027
    s = re.sub(
        rf"\b({months})\s+(\d{{1,2}})\s*\n\s*(st|nd|rd|th|rh)\s*,?\s*(20\d{{2}})\b",
        r"\1 \2\3, \4",
        s,
        flags=re.I,
    )

    # October 21°, 2026 / October 21º, 2026
    s = re.sub(
        rf"\b({months})\s+(\d{{1,2}})[°º]\s*,?\s*(20\d{{2}})\b",
        r"\1 \2TH, \3",
        s,
        flags=re.I,
    )

    # 24th January 2027 형태 보존
    s = re.sub(
        rf"\b(\d{{1,2}})[°º]\s+({months})\s*,?\s*(20\d{{2}})\b",
        r"\1TH \2 \3",
        s,
        flags=re.I,
    )

    return s


def find_dates(text: str) -> list[dict[str, str]]:
    """
    문서에 나타난 순서대로 날짜 후보를 반환한다.

    기존 구현은 정규식 종류별로 후보를 append해서, 본문 앞의
    `15 Mei 2029`보다 뒤쪽의 `16/05/2024`가 먼저 반환될 수 있었다.
    모든 패턴의 위치를 함께 수집한 뒤 start 위치로 정렬한다.
    """
    t = normalize_ocr_digits(clean_ocr_text(normalize_date_ocr_text(text)))

    patterns = [
        r"\b20\d{2}[-./]\d{1,2}[-./]\d{1,2}\b",
        r"\b\d{1,2}[-./]\d{1,2}[-./]20\d{2}\b",
        r"\b[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th|rh)?\s*,?\s*20\d{2}\b",
        r"\b\d{1,2}(?:st|nd|rd|th|rh)?\s+[A-Za-z]+\s*,?\s*20\d{2}\b",
        r"\b\d{2}[.]\d{1,2}[.]\d{1,2}\b",
    ]

    positioned: list[dict[str, Any]] = []

    for pattern_rank, pattern in enumerate(patterns):
        for match in re.finditer(pattern, t, re.I):
            if is_ignored_date_context(t, match.start(), match.end()):
                continue

            raw = match.group(0)
            parsed = parse_date_text(raw)

            if not parsed:
                continue

            positioned.append({
                "date": parsed,
                "raw": raw,
                "start": match.start(),
                "end": match.end(),
                "pattern_rank": pattern_rank,
            })

    positioned.sort(key=lambda item: (
        int(item["start"]),
        int(item["end"]),
        int(item["pattern_rank"]),
    ))

    seen: set[tuple[str, int, int]] = set()
    output: list[dict[str, str]] = []

    for item in positioned:
        key = (str(item["date"]), int(item["start"]), int(item["end"]))
        if key in seen:
            continue
        seen.add(key)
        output.append({"date": str(item["date"]), "raw": str(item["raw"])})

    return output


def extract_date_after(text: str, anchors: list[str], window: int = 220) -> tuple[str | None, str]:
    upper = upper_text(text)
    src = clean_ocr_text(text)

    for anchor in anchors:
        anchor_u = anchor.upper()
        start = 0

        while True:
            idx = upper.find(anchor_u, start)

            if idx < 0:
                break

            chunk = src[idx: idx + window]

            # 발급일 또는 footer로 넘어가는 구간은 잘라낸다.
            chunk = re.split(
                r"\bISSUED\s+IN\s+JAKARTA\b|"
                r"\bDATE\s+OF\s+ISSUE\b|"
                r"\bISSUED\s+ON\b|"
                r"\bF\.8\.2\b|"
                r"\bGEDUNG\s+MAJELIS\b",
                chunk,
                maxsplit=1,
                flags=re.I,
            )[0]

            d = find_dates(chunk)

            if d:
                return d[0]["date"], d[0]["raw"]

            start = idx + len(anchor_u)

    return None, ""


def extract_latest_date_near_anchors(
    text: str,
    anchors: list[str],
    *,
    before: int = 80,
    after: int = 650,
) -> tuple[str | None, str]:
    """
    라벨 주변에 발급일과 만료일이 함께 있을 때 가장 늦은 날짜를 선택한다.

    ARA처럼 `Issue Date / Expired Date / Certificate No` 라벨을 먼저 배치하고
    실제 값은 아래에 순서대로 적는 표, MUIS처럼 날짜 뒤에 `(Date of Expiry)`가
    인쇄되는 양식에 사용한다. 전체 문서의 최종 날짜를 고르지 않고 라벨 인접
    구간만 사용하므로 footer/revision 날짜 오인을 줄인다.
    """
    src = clean_ocr_text(normalize_date_ocr_text(text))
    upper = upper_text(src)
    candidates: list[dict[str, str]] = []

    for anchor in anchors:
        anchor_u = str(anchor or "").upper().strip()
        if not anchor_u:
            continue

        start = 0
        while True:
            idx = upper.find(anchor_u, start)
            if idx < 0:
                break

            chunk_start = max(0, idx - max(0, int(before)))
            chunk_end = min(len(src), idx + len(anchor_u) + max(1, int(after)))
            chunk = src[chunk_start:chunk_end]
            candidates.extend(find_dates(chunk))
            start = idx + len(anchor_u)

    if not candidates:
        return None, ""

    # 같은 날짜가 여러 번 잡혀도 가장 늦은 달력 날짜만 사용한다.
    best = max(candidates, key=lambda item: item.get("date") or "")
    return best.get("date") or None, best.get("raw") or ""


def extract_muis_expiry_date(text: str, filename: str = "") -> tuple[str | None, str]:
    """
    MUIS의 만료일은 Expiry 라벨 인접 날짜와 파일명 날짜만 비교한다.

    일부 구형 스캔은 `Date of Expiry:` 값이 OCR에서 빠지고 직전의 발급일만
    남는다. 이 경우 파일명에 관리자가 기록한 만료일이 있으면 두 후보 중 더
    늦은 날짜를 택해 발급일 오인을 방지한다.
    """
    candidates: list[dict[str, str]] = []

    date, raw = extract_latest_date_near_anchors(
        text,
        ["DATE OF EXPIRY", "ATE OF EXPIRY", "EXPIRY DATE"],
        before=120,
        after=180,
    )
    if date:
        candidates.append({"date": date, "raw": raw, "source": "LABEL"})

    for item in find_dates(filename or ""):
        candidates.append({**item, "source": "FILENAME"})

    if not candidates:
        return None, ""

    best = max(candidates, key=lambda item: item.get("date") or "")
    return best.get("date") or None, best.get("raw") or ""


def extract_mui_valid_until_date(text: str) -> tuple[str | None, str]:
    """
    MUI는 Valid until만 신뢰한다.
    Issued in Jakarta on / footer F.8.2 날짜는 유효기간 후보에서 제외한다.
    """
    fixed_text = normalize_date_ocr_text(text)
    lines = lines_of(fixed_text)

    for i, line in enumerate(lines):
        if not re.search(r"\bVALID\s+UNTIL\b", upper_text(line)):
            continue

        chunk_lines = []

        for j in range(i, min(len(lines), i + 12)):
            u = upper_text(lines[j])

            if j > i and re.search(
                r"\bISSUED\s+IN\s+JAKARTA\b|"
                r"\bDATE\s+OF\s+ISSUE\b|"
                r"\bISSUED\s+ON\b",
                u,
            ):
                break

            if "F.8.2" in u or "/B-0/" in u or "GEDUNG MAJELIS" in u:
                continue

            chunk_lines.append(lines[j])

        chunk = "\n".join(chunk_lines)
        dates = find_dates(chunk)

        if dates:
            return dates[0]["date"], dates[0]["raw"]

    date, raw = extract_date_after(fixed_text, ["VALID UNTIL"], window=650)

    if date:
        return date, raw

    return None, ""


def extract_cicot_expiry_date(text: str, filename: str = "") -> tuple[str | None, str]:
    """
    CICOT는 Effective from / Issued on / Expired date가 한 문서에 섞인다.
    Issued on 날짜가 아니라 Expired date 또는 till 뒤 날짜를 우선한다.
    """
    fixed_text = normalize_date_ocr_text(text)
    lines = lines_of(fixed_text)

    # 1) 명시적 Expired date 최우선
    for i, line in enumerate(lines):
        if re.search(r"\bEXPIRED\s+DATE\b|\bEXPIRY\s+DATE\b", upper_text(line)):
            chunk = "\n".join(lines[i: i + 4])
            dates = find_dates(chunk)

            if dates:
                return dates[-1]["date"], dates[-1]["raw"]

    # 2) Effective from ... till ... 구조에서는 마지막 날짜가 만료일
    for i, line in enumerate(lines):
        u = upper_text(line)

        if "EFFECTIVE FROM" in u or " TILL" in u or u.strip() == "TILL":
            chunk = "\n".join(lines[i: i + 6])
            dates = find_dates(chunk)

            if len(dates) >= 2:
                return dates[-1]["date"], dates[-1]["raw"]

    m = re.search(
        r"EFFECTIVE\s+FROM(.+?)(?:REGISTRATION|THIS\s+HALAL|IN\s+ACCORDANCE|$)",
        fixed_text,
        flags=re.I | re.S,
    )

    if m:
        dates = find_dates(m.group(1))

        if len(dates) >= 2:
            return dates[-1]["date"], dates[-1]["raw"]

    # 3) 파일명 보조: Exp. Oct 14, 2026
    fname_dates = find_dates(filename or "")

    if fname_dates:
        return fname_dates[-1]["date"], fname_dates[-1]["raw"]

    return None, ""
