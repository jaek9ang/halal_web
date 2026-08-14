import json
import re
import sqlite3
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from app.core.db import connect as db_connect

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

COUNTRY_WORDS = {
    "USA": "USA", "U.S.A": "USA", "UNITED STATES": "USA", "AMERICA": "USA",
    "KOREA": "KOREA", "REPUBLIC OF KOREA": "KOREA",
    "INDONESIA": "INDONESIA",
    "MALAYSIA": "MALAYSIA",
    "SINGAPORE": "SINGAPORE",
    "JAPAN": "JAPAN",
    "THAILAND": "THAILAND",
    "GERMANY": "GERMANY",
    "FRANCE": "FRANCE",
    "SPAIN": "SPAIN",
    "NETHERLANDS": "NETHERLANDS",
    "UNITED KINGDOM": "UK", "ENGLAND": "UK", "U.K": "UK", "UK": "UK",
    "VIETNAM": "VIETNAM",
    "DENMARK": "DENMARK",
    "CHINA": "CHINA",
    "INDIA": "INDIA",
    "HUNGARY": "HUNGARY",
}

REGION_COUNTRY_HINTS = {
    "HEBEI": "CHINA",
    "SHANDONG": "CHINA",
    "JIANGSU": "CHINA",
    "ZHEJIANG": "CHINA",
    "GUANGDONG": "CHINA",
    "HENAN": "CHINA",
    "HUBEI": "CHINA",
    "HUNAN": "CHINA",
    "SHANGHAI": "CHINA",
    "TIANJIN": "CHINA",
    "BEIJING": "CHINA",

    # BPJPH Sonic 계열: 주소 블록에 INDIA가 직접 없거나, 인도 지역명만 있는 경우
    "MADHYA PRADESH": "INDIA",
    "INDORE": "INDIA",
    "PITHAMPUR": "INDIA",
    "DHAR": "INDIA",
    "MANDSOUR": "INDIA",
    "MANDSAUR": "INDIA",
    "NEEMUCH": "INDIA",
}

ORG_ALIASES = [
    ("JUHF", "INDIA", [
        "JUHF CERTIFICATION",
        "JUHF-",
        "HALALHIND",
    ]),
    ("ARA", "CHINA", [
        "ARA HALAL CERTIFICATION SERVICES CENTRE",
        "ARA HALAL CERTIFICATION",
        "ARA-",
    ]),
    ("TQHCC", None, [
        "TOTAL QUALITY HALAL CORRECT CERTIFICATION",
        "HALAL CORRECT CERTIFICATION",
        "HALAL CORRECT GERMANY",
        "HALALCORRECT",
        "TQHCC",
    ]),
    ("HFFIA", "NETHERLANDS", [
        "HALAL FEED AND FOOD INSPECTION AUTHORITY",
        "HALAL VOEDING EN VOEDSEL",
        "HALAL.NL",
        "HFFIA",
    ]),
    ("HFCE", None, [
        "HALAL FOOD COUNCIL OF EUROPE",
        "HFCE",
        "WWW.HFCE.EU",
    ]),
    ("IFANCA", "USA", ["IFANCA", "ISLAMIC FOOD AND NUTRITION COUNCIL OF AMERICA"]),
    ("BPJPH", "INDONESIA", ["BPJPH", "BADAN PENYELENGGARA JAMINAN PRODUK HALAL", "REPUBLIK INDONESIA", "SERTIFIKAT HALAL"]),
    ("MUI", "INDONESIA", ["MAJELIS ULAMA INDONESIA", "LPPOM", "INDONESIA COUNCIL OF ULAMA", "LAMPIRAN KETETAPAN HALAL"]),
    ("HQC", None, ["HALAL QUALITY CONTROL", "HQC", "CONTROL OFFICE OF HALAL SLAUGHTERING"]),
    ("LLS-ISA", "USA", ["LLS-ISA"]),
    ("ISA", "USA", ["ISLAMIC SERVICES OF AMERICA", "ISA", "ISA HALAL"]),
    ("HCE", "UK", ["HALAL CERTIFICATION EUROPE", "HALALCE", "HCE"]),
    ("HFQ", "SPAIN", ["HALAL FOOD & QUALITY", "HALAL FOOD AND QUALITY", "HFQ"]),
    ("HALAL CONTROL", "GERMANY", ["HALAL CONTROL", "HALAL CONTROL GMBH"]),
    ("HCA", "VIETNAM", ["HALAL CERTIFICATION AGENCY", "HALAL.VN", "CERT ID: HCA", "CERT ID HCA"]),
    ("CICOT", "THAILAND", ["THE CENTRAL ISLAMIC COUNCIL OF THAILAND", "CICOT", "SHEIKHUL ISLAM OF THAILAND"]),
    ("JAKIM", "MALAYSIA", ["JAKIM", "JABATAN KEMAJUAN ISLAM MALAYSIA", "MALAYSIAN HALAL STANDARD"]),
    ("MUIS", "SINGAPORE", ["MUIS", "MAJLIS UGAMA ISLAM SINGAPURA", "ISLAMIC RELIGIOUS COUNCIL OF SINGAPORE"]),
    ("JMA", "JAPAN", ["JAPAN MUSLIM ASSOCIATION", "JMA", "JAPAN HALAL"]),
    ("KMF", "KOREA", ["KMF", "KOREA MUSLIM FEDERATION", "한국이슬람", "한국무슬림", "한국 할랄"]),
]

# backend/db/halal_lhln.db가 있으면 인증기관별 인증국가를 보강한다.
# 스키마가 달라도 최대한 안전하게 텍스트 컬럼을 스캔하는 방식.
BACKEND_DIR = Path(__file__).resolve().parents[2]
LHLN_DB_PATH = BACKEND_DIR / "db" / "halal_lhln.db"

# DB가 없거나 다국가 기관이면 아래 고정값만 사용한다.
FIXED_SINGLE_COUNTRY_ORG = {
    "IFANCA": "USA",
    "BPJPH": "INDONESIA",
    "MUI": "INDONESIA",
    "ISA": "USA",
    "LLS-ISA": "USA",
    "HCE": "UK",
    "HFQ": "SPAIN",
    "HALAL CONTROL": "GERMANY",
    "HCA": "VIETNAM",
    "CICOT": "THAILAND",
    "JAKIM": "MALAYSIA",
    "MUIS": "SINGAPORE",
    "JMA": "JAPAN",
    "KMF": "KOREA",
    "ARA": "CHINA",
    "JUHF": "INDIA",
}


def _safe_lhln_country_lookup(org: str) -> str | None:
    org = (org or "").upper().strip()
    if not org or org == "UNKNOWN" or not LHLN_DB_PATH.exists():
        return None

    try:
        conn = db_connect(LHLN_DB_PATH)
        cur = conn.cursor()

        tables = [r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]

        found_countries = set()
        org_key = org.replace("-", " ")

        for table in tables:
            # 내부 sqlite 테이블 제외
            if table.startswith("sqlite_"):
                continue

            cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
            if not cols:
                continue

            text_cols = cols[:]
            sql = f"SELECT * FROM {table} LIMIT 5000"

            for row in cur.execute(sql).fetchall():
                row_text = " ".join(str(row[c] or "") for c in text_cols).upper()
                row_key = row_text.replace("-", " ")

                if org in row_text or org_key in row_key:
                    for country_word, normalized in COUNTRY_WORDS.items():
                        if country_word in row_text:
                            found_countries.add(normalized)

        conn.close()

        if len(found_countries) == 1:
            return next(iter(found_countries))

    except Exception:
        return None

    return None


def resolve_cert_country(org: str, blob: str = "", default_country: str | None = None) -> str | None:
    # 1. 본문 자체에서 HQC 같은 다국가 기관 분기
    by_text = infer_org_country(org, blob, default_country)
    if by_text:
        return by_text

    # 2. LHLN DB에서 해당 기관이 한 국가로만 잡히면 사용
    by_lhln = _safe_lhln_country_lookup(org)
    if by_lhln:
        return by_lhln

    # 3. 단일국가 고정 기관 fallback
    if org in FIXED_SINGLE_COUNTRY_ORG:
        return FIXED_SINGLE_COUNTRY_ORG[org]

    return default_country


def clean_ocr_text(value: str) -> str:
    text = str(value or "")
    text = text.replace("\u00a0", " ").replace("&nbsp;", " ")
    text = text.replace("ⓡ", "®")
    text = re.sub(r"[\uf071\uf077\uf065]+", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def upper_text(value: str) -> str:
    return clean_ocr_text(value).upper()


def norm_key(value: str) -> str:
    value = str(value or "").upper()
    value = value.replace("®", "").replace("™", "")
    value = re.sub(r"\{FAMILY OF PRODUCTS\}|FAMILY OF PRODUCTS", " ", value)
    value = re.sub(r"[^A-Z0-9가-힣]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def similarity(a: str, b: str) -> float:
    a2, b2 = norm_key(a), norm_key(b)
    if not a2 or not b2:
        return 0.0
    if a2 == b2:
        return 1.0
    if a2 in b2 or b2 in a2:
        return 0.92
    return SequenceMatcher(None, a2, b2).ratio()


def lines_of(text: str) -> list[str]:
    return [ln.strip() for ln in clean_ocr_text(text).splitlines() if ln.strip()]

def is_halal_control_noise_line(line: str) -> bool:
    text = clean_ocr_text(line)
    upper = upper_text(text)

    if not text:
        return True

    # Arabic-only / symbol-heavy OCR noise
    if re.fullmatch(r"[\u0600-\u06FF\s\W_]+", text):
        return True

    noise_words = [
        "MANUFACTURED BY",
        "اﻟﻣﺻﻧﻌﺔ",
        "المصنعة",
        "ﻓﻲ",
        "في",
    ]

    return any(word in upper for word in noise_words)


def looks_like_company_name_for_halal_control(line: str) -> bool:
    text = clean_ocr_text(line)
    upper = upper_text(text)

    if len(text) < 4:
        return False

    if is_halal_control_noise_line(text):
        return False

    # 주소줄 제외: Holzmühle 1, 73494 Rosenberg (Germany)
    if re.search(r"\b\d{4,6}\b", text) and re.search(r"\([A-Za-z ]+\)", text):
        return False

    company_tokens = [
        "GMBH",
        "KG",
        "CO.",
        "CO,",
        "LTD",
        "LIMITED",
        "AG",
        "INC",
        "CORPORATION",
        "LLC",
        "S.A.",
        "SAS",
    ]

    return any(token in upper for token in company_tokens)


def extract_country_from_parentheses(line: str) -> str | None:
    text = clean_ocr_text(line)

    m = re.search(
        r"\((Germany|France|Netherlands|China|Korea|USA|Thailand|Vietnam|Spain|Denmark|Hungary)\)",
        text,
        re.I,
    )

    if not m:
        return None

    return extract_country_from_text(m.group(1))



def is_company_like(value: str) -> bool:
    upper = upper_text(value)

    return bool(
        re.search(
            r"\b(CO\.?,?\s*LTD\.?|CO\.?\s*,?\s*LTD\.?|LTD\.?|LIMITED|COMPANY|CORPORATION|CORP\.?|INC\.?|GMBH|B\.?V\.?|S\.A\.|SAS|SDN\s*BHD|PTE\s*LTD)\b",
            upper,
            re.I,
        )
    )


def split_company_country_suffix(value: str) -> tuple[str, str | None]:
    """
    SEWOO CO., LTD-KOREA
    NATURALS FOOD CO.LTD.,-KOREA
    SAMYANG CORPORATION ULSAN PLANT 1- Korea
    같은 제조사-제조국 결합값 분리.
    """
    text = clean_company_value(value)

    if not text or "-" not in text:
        return text, None

    left, right = text.rsplit("-", 1)
    country = extract_country_from_text(right)

    if not country:
        return text, None

    company = clean_company_value(left).rstrip(",")
    return company, country

def strip_address_from_company(value: str) -> str:
    """
    Company Name & Address 라벨에서 회사명+주소가 한 줄로 붙는 경우 회사명만 남긴다.
    제품명/기관명 특정값을 박지 않고, 주소 시작 패턴만 기준으로 자른다.
    """
    text = clean_company_value(value)

    if not text:
        return ""

    # 예: Ingredion Incorporated 5 Westbrook Corporate Center...
    # 예: Bio Springer S.A. 103, rue Jean-Jaurès...
    address_start_patterns = [
        r"\s+\d{1,6}\s+(?:[A-Z][A-Za-z0-9-]*\s+){0,4}(?:Street|St\.?|Road|Rd\.?|Avenue|Ave\.?|Boulevard|Blvd\.?|Drive|Dr\.?|Lane|Ln\.?|Corporate|Center|Centre|rue)\b",
        r"\s+\d{1,6},\s*(?:rue|street|road|avenue|boulevard)\b",
    ]

    for pattern in address_start_patterns:
        m = re.search(pattern, text, re.I)

        if m:
            return clean_company_value(text[:m.start()])

    return text

def is_admin_or_address_line(value: str) -> bool:
    upper = upper_text(value)

    if not upper:
        return True

    admin_patterns = [
        r"THE\s+CENTRAL\s+ISLAMIC\s+COUNCIL",
        r"SHEIKHUL\s+ISLAM",
        r"HALAL\s+STANDARD",
        r"CERTIFICATE",
        r"REGISTRATION",
        r"REGRSUATION",
        r"ENTREPRENEUR",
        r"FACTORY\s+ADDRESS",
        r"ADDRESS",
        r"VALID\s+UNTIL",
        r"EFFECTIVE\s+FROM",
        r"ISSUED\s+ON",
        r"DATE\s+OF\s+ISSUANCE",
        r"PRODUCT\s*TYPE",
        r"PRODUCT\s*NAME",
        r"THIS\s+IS\s+TO\s+CERTIFY",
        r"THE\s+PRODUCTION\s+OF",
        r"FACILITY,\s*PROCESSES,\s*AND\s*PRODUCT",
        r"TAKING\s+PLACE\s+IN",
        r"AX\s+DELFT",
    ]

    return any(re.search(pattern, upper, re.I) for pattern in admin_patterns)



def _clean_product_candidate_name(value: str) -> str:
    """
    제품명 후보 1개를 정리한다.
    특정 제품명을 박지 않고, 줄바꿈 뒤 OCR 찌꺼기 / 아랍어 인증문구 / 날짜꼬리만 제거한다.
    """
    text = clean_ocr_text(value)

    if not text:
        return ""

    # ProductType에서 "RICE BRAN OIL\n'6)I"처럼 OCR 찌꺼기가 붙은 경우
    if "\n" in text:
        parts = [clean_ocr_text(x) for x in text.splitlines()]
        parts = [x for x in parts if x and not looks_like_product_noise(x)]

        if parts:
            text = parts[0]

    # BPJPH 아랍어 인증 문구가 섞인 발급일/발급문장 제거
    # 제품명에 아랍어 문자가 들어가는 케이스는 현재 PMF 매칭 목적상 낮다고 본다.
    if re.search(r"[\u0600-\u06FF]", text):
        return ""

    # 흔한 OCR 꼬리 기호 제거
    text = re.sub(r"^[\s'\"`~|:;,.()\[\]{}<>]+", "", text)
    text = re.sub(r"[\s'\"`~|:;,.()\[\]{}<>]+$", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text





def clean_company_value(value: str) -> str:
    text = clean_ocr_text(value)
    text = re.sub(r"^[：:ㆍ\-\s]+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .:-")
    return text

def looks_like_product_noise(value: str) -> bool:
    text = clean_ocr_text(value)
    upper = upper_text(text)

    # --- PAGE 1 --- 같은 prefix 제거 후 한 번 더 판단
    norm_text = re.sub(r"^[\s\-–—_#|:]+", "", text).strip()
    norm_upper = upper_text(norm_text)

    if not norm_upper:
        return True

    month_words = (
        "JAN|JANUARY|JANUARI|FEB|FEBRUARY|FEBRUARI|MAR|MARCH|MARET|"
        "APR|APRIL|MAY|MEI|MAC|JUN|JUNE|JUL|JULY|AUG|AUGUST|"
        "SEP|SEPTEMBER|OCT|OCTOBER|OKTOBER|NOV|NOVEMBER|DEC|DECEMBER|"
        "ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|"
        "SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE"
    )

    noise_patterns = [
        r"^PAGE\s+\d+",
        r"^CERT(?:IFICATE)?\b",
        r"^DATE\b",
        r"^VALID\b",
        r"^ISSUE\b",
        r"^PRODUCT\s*(NAME|TYPE|CODE)",
        r"^NO\.?$",
        r"QR\s*CODE",
        r"^NAMA\s+PRODUK",
        r"^DAFTAR\s+PRODUK",
        r"^DOKUMEN\b",
        r"^THIS\s+CERTIFICATE\b",
        r"^THIS\s+IS\s+TO\s+CERTIFY\b",
        r"^THE\s+CENTRAL\s+ISLAMIC\b",
        r"^THE\s+PRODUCTION\s+OF\b",
        r"FACILITY,\s*PROCESSES,\s*AND\s*PRODUCT",
        r"TAKING\s+PLACE\s+IN",
        r"AX\s+DELFT",

        # Name: Sensient 같은 라벨형 노이즈
        r"^NAME\s*:",

        # 숫자열 / 코드열
        r"^(?:\d{2,5}\s+){2,}\d{2,5}$",
        r"^\d{1,2}/\d{1,2}/20\d{2}$",

        # April 2026 / November 2025
        rf"^({month_words})\s+20\d{{2}}$",

        # October 15, 2024 / October 8, 2024
        rf"^({month_words})\s+\d{{1,2}},?\s+20\d{{2}}$",

        # 17 Februari 2022 / 24th January 2027
        rf"^\d{{1,2}}(?:ST|ND|RD|TH|RH)?\s+({month_words})\s+20\d{{2}}$",

        # de abril, 2027 / 10 de abril 2027
        rf"^(?:\d{{1,2}}\s+)?DE\s+({month_words}),?\s+20\d{{2}}$",

        # 2026-04-28 / 28.04.2026 / 28/04/2026
        r"^20\d{2}[-./]\d{1,2}[-./]\d{1,2}$",
        r"^\d{1,2}[-./]\d{1,2}[-./]20\d{2}$",
    ]

    if any(re.search(pattern, norm_upper, re.I) for pattern in noise_patterns):
        return True

    # 주소/연락처 계열
    address_patterns = [
        r"\bROAD\b",
        r"\bFLOOR\b",
        r"\bBUILDING\b",
        r"\bBANGKOK\b",
        r"\bTHAILAND\b",
        r"\bNETHERLANDS\b",
        r"\bDELFT\b",
        r"\bMOO\s+\d+",
        r"\bPATHUM\s+THANI\b",
        r"\bSATHORN\b",
        r"\bSILOM\b",
        r"\bFAX\b",
        r"\bTEL\b",
        r"\bE-?MAIL\b",
        r"@",
    ]

    if any(re.search(pattern, norm_upper, re.I) for pattern in address_patterns):
        return True

    # 아랍어 인증 문구가 섞이면 제품명 후보에서 제외
    if re.search(r"[\u0600-\u06FF]", norm_text):
        return True

    if is_admin_or_address_line(norm_text):
        return True

    # 제품명 후보에는 최소 하나 이상의 문자 필요
    if not re.search(r"[A-Za-z가-힣]", norm_text):
        return True

    return False

def finalize_product_candidates(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen = set()

    for item in products or []:
        if not isinstance(item, dict):
            continue

        name = clean_ocr_text(item.get("name") or "")

        if looks_like_product_noise(name):
            continue

        key = re.sub(r"\s+", " ", upper_text(name)).strip()

        if not key or key in seen:
            continue

        seen.add(key)

        next_item = dict(item)
        next_item["name"] = name
        cleaned.append(next_item)

    return cleaned

def normalize_ocr_digits(text: str) -> str:
    # 날짜 주변 OCR 오타만 약하게 보정
    return (
        str(text or "")
        .replace("2O", "20")
        .replace("O9", "09")
        .replace("O8", "08")
        .replace("O7", "07")
        .replace("O6", "06")
        .replace("O5", "05")
        .replace("O4", "04")
        .replace("O3", "03")
        .replace("O2", "02")
        .replace("O1", "01")
        .replace("O0", "00")
    )


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

def detect_org(raw_text: str, filename: str = "", expected_org: str = "") -> tuple[str, str | None, list[str]]:
    blob = upper_text("\n".join([filename or "", expected_org or "", raw_text or ""]))
    hits: list[str] = []

    # 명시 기관 우선순위. ISA와 LLS-ISA 충돌 방지.
    if "LLS-ISA" in blob:
        return "LLS-ISA", "USA", ["LLS-ISA"]

    for org, country, aliases in ORG_ALIASES:
        score = 0
        matched_aliases = []
        for alias in aliases:
            if alias.upper() in blob:
                score += 1
                matched_aliases.append(alias)
        if score:
            hits.append(org)
            # 기관별 강한 키워드가 있으면 즉시 반환
            if org not in {"BPJPH", "MUI", "ISA"} or score >= 2:
                return org, resolve_cert_country(org, blob, country), matched_aliases

    # BPJPH/MUI 동시 출현 시: BPJPH certificate가 있으면 BPJPH, attachment of halal decree면 MUI
    if "BADAN PENYELENGGARA JAMINAN PRODUK HALAL" in blob or "SERTIFIKAT HALAL" in blob and "REPUBLIK INDONESIA" in blob:
        return "BPJPH", "INDONESIA", ["BPJPH"]
    if "MAJELIS ULAMA INDONESIA" in blob or "LPPOM" in blob:
        return "MUI", "INDONESIA", ["MUI/LPPOM"]

    return (hits[0], resolve_cert_country(hits[0], blob, None), hits) if hits else ("UNKNOWN", None, [])


def infer_org_country(org: str, blob: str, default_country: str | None) -> str | None:
    b = upper_text(blob)
    if org == "HQC":
        if "GERMANY" in b or "DE103" in b or "DE104" in b:
            return "GERMANY"
        if "DENMARK" in b:
            return "DENMARK"
        if "NETHERLANDS" in b or "BV NETHERLANDS" in b or "NL" in b:
            return "NETHERLANDS"
    if org == "TQHCC":
        # 문서상 유럽/독일 회사가 반복되지만 인증국가 DB 확인 대상. 임시 미확정.
        return None
    if org == "HFCE":
        return None
    if org == "HFFIA":
        return None
    return default_country


def extract_country_from_text(text: str) -> str | None:
    upper = upper_text(text)

    # 긴 국가명을 먼저
    for key in sorted(COUNTRY_WORDS, key=len, reverse=True):
        if re.search(r"\b" + re.escape(key) + r"\b", upper):
            return COUNTRY_WORDS[key]

    # 국가명이 직접 없고 지역명만 OCR된 경우 보조 추론
    for key in sorted(REGION_COUNTRY_HINTS, key=len, reverse=True):
        if re.search(r"\b" + re.escape(key) + r"\b", upper):
            return REGION_COUNTRY_HINTS[key]

    return None

def extract_after_label(lines: list[str], labels: list[str], max_next: int = 4) -> str:
    labels_u = [x.upper() for x in labels]
    for i, line in enumerate(lines):
        u = line.upper()
        for label in labels_u:
            if label in u:
                # 같은 줄에서 콜론 뒤 추출
                if ":" in line:
                    right = line.split(":", 1)[1].strip(" -")
                    if right:
                        return right
                # 다음 의미 있는 줄
                vals = []
                for j in range(i + 1, min(len(lines), i + 1 + max_next)):
                    nxt = lines[j].strip()
                    if nxt and not nxt.endswith(":"):
                        vals.append(nxt)
                        if len(" ".join(vals)) > 8:
                            return " ".join(vals)
                if vals:
                    return " ".join(vals)
    return ""


def is_bad_manufacturer_candidate(value: str) -> bool:
    text = clean_ocr_text(value)
    upper = upper_text(text)

    if not text:
        return True

    bad_exact = {
        "NAME OF PRODUCTS",
        "PRODUCT NAME",
        "NAME OF THE PRODUCTS",
        "PRODUCTS",
        "PRODUCT LIST",
        "CERTIFICATE NO",
        "ISSUE DATE",
        "EXPIRED DATE",
        "EXPIRY DATE",
        "FACTORY ADDRESS",
        "COMPANY ADDRESS",
        "ADDRESS",
    }

    if upper in bad_exact:
        return True

    if re.search(r"^(PLOT|NO\.?|ROAD|STREET|DISTRICT|SECTOR|VILLAGE|ADDRESS)\b", upper):
        return True

    if re.search(r"\b(TEL|FAX|EMAIL|E-MAIL|WWW|PHONE)\b", upper):
        return True

    return False


def extract_inline_label_value(line: str, label_pattern: str) -> str:
    m = re.search(label_pattern, line, re.I)
    if not m:
        return ""

    right = line[m.end():].strip(" :：-")
    return clean_ocr_text(right)


def extract_company_after_marker(
    lines: list[str],
    marker_pattern: str,
    max_next: int = 8,
) -> str:
    for i, line in enumerate(lines):
        inline = extract_inline_label_value(line, marker_pattern)

        if inline and not is_bad_manufacturer_candidate(inline):
            return strip_address_from_company(clean_company_value(inline))

        if re.search(marker_pattern, line, re.I):
            for j in range(i + 1, min(len(lines), i + 1 + max_next)):
                candidate = clean_company_value(lines[j])

                if is_bad_manufacturer_candidate(candidate):
                    continue

                if is_company_like(candidate):
                    return strip_address_from_company(candidate)

    return ""


def extract_cert_no(text: str, org: str) -> tuple[str, list[str]]:
    t = clean_ocr_text(text)
    u = t.upper()
    candidates: list[str] = []

    org_patterns = {
        "IFANCA": [r"\bHC-[A-Z0-9]{6,}\b", r"DOCUMENT\s*#\s*[:：]?\s*([A-Z0-9./-]+)"],
        "MUI": [r"\bLPPOM[- ]\d{6,}\b"],
        "BPJPH": [
            r"(?<![A-Z0-9])ID00\d{8,}(?![A-Z0-9])",
            r"ID00\d{8,}",
            r"\bID\d{10,}\b",
            r"\bLPPOM[- ]\d{6,}\b",
        ],
        "HQC": [r"CERT\.?\s*NO\s*[:：]?\s*([A-Z]{0,3}\d{6,}[A-Z0-9-]*)", r"CERTIFICATE\s*NO\s*[:：]?\s*([A-Z]{0,3}\d{6,}[A-Z0-9-]*)"],
        "ISA": [r"CERTIFICATE\s*NO\.?\s*[:：]?\s*([0-9]{4}-[0-9]{2}-[0-9]{4,})"],
        "LLS-ISA": [r"CERTIFICATE\s*NO\.?\s*[:：]?\s*([0-9]{4}-[0-9]{2}-[0-9]{4,})"],
        "HCE": [r"CERTIFICATE\s*NO\s*[:：]?\s*([A-Z0-9/.-]+)"],
        "HFCE": [
            r"CERTIFICATE\s*NO\.?\s*[:：]?\s*([A-Z0-9/.-]+)",
            r"\bHC-\d{2}[A-Z0-9]{4,12}\b",
        ],
        "HFQ": [
            r"\bHFQ\s*-\s*\d{1,6}\s*/\s*\d{1,4}\s*/\s*[A-Z]{2,10}\b",
            r"WITH\s+CERTIFICATE\s+NUMBER\s*[:：]?\s*(HFQ\s*-\s*\d{1,6}\s*/\s*\d{1,4}\s*/\s*[A-Z]{2,10})\b",
            r"CON\s+N[ºO]\s+DE\s+CERTIFICADO\s*[:：]?\s*(HFQ\s*-\s*\d{1,6}\s*/\s*\d{1,4}\s*/\s*[A-Z]{2,10})\b",
        ],
        "HALAL CONTROL": [r"CERT\.-NO\.?:?\s*([A-Z0-9/.-]+)", r"CERTIFICATE\s+REGISTRATION\s+NO\.?\s*[:：]?\s*([A-Z0-9/.-]+)", r"\bC-\d{2}-[0-9-]+\b"],
        "HCA": [
            r"CERT\s*[I1L]D\s*[:：]?\s*(HCA\s*[A-Z0-9/ -]+)",
            r"\bHCA\s*\d{2,5}\s*/\s*[A-Z]{2,10}\b",
        ],
        "CICOT": [r"CICOT\s*HL\s*[:：]?\s*([0-9/.-]+)", r"\b\d{3}/\d{4}\b", r"\b\d{3}\s+\d{3}\s+\d{3}\s+\d{2}\s+\d{2}\b"],
        "JAKIM": [r"JAKIM[./A-Z0-9() -]{8,}", r"NO\.\s*RUJ\.?\s*/\s*REF\s*NO\.?\s*[:：]?\s*([A-Z0-9./() -]+)"],
        "MUIS": [
            r"\bPRN[A-Z0-9]{8,20}\b",
            r"CERTIFICATE\s*NO\.?\s*[:?]?\s*([A-Z0-9/.-]+)",
            r"REF\s*NO\.?\s*[:?]?\s*([A-Z0-9/.-]+)",
        ],
        "JMA": [
            r"\bNO\.?\s*[:：]?\s*(\d{1,6}\s*-\s*[A-Z]{2,12}\s*/\s*\d{2,4})",
            r"CERTIFICATE\s*NO\.?\s*[:：]?\s*([0-9A-Z/ -]{5,})",
        ],
        "ARA": [
            r"CERTIFICATE\s*NO[\s\S]{0,220}?(ARA-\d{6,}(?:-\d+)?)",
            r"\bARA-\d{6,}(?:-\d+)?\b",
        ],
        "JUHF": [
            r"CERTIFICATE\s*NO[\s\S]{0,120}?(JUHF-\d{3,6}-\d{3,6})",
            r"\bJUHF-\d{3,6}-\d{3,6}\b",
        ],
        "KMF": [
            r"\bKMFHC\d{2}-\d{2,6}(?:-\d{1,3})?\b",
            r"\bKMFHC\d{2,4}[-\s]?\d{2,6}(?:[-\s]?\d{1,3})?\b",
            r"Certificate\s*No\.?\s*[:：]?\s*([A-Z0-9/.-]+)",
            r"인증\s*번호\s*[:：]?\s*([A-Z0-9가-힣/.-]+)",
        ],
        "TQHCC": [r"HCC[A-Z0-9-]{6,}", r"CERTIFICATE\s*(?:NO|NR)\.?\s*[:：]?\s*([A-Z0-9-]+)"],
        "HFFIA": [
            r"CERTIFICATE\s*NO\.?\s*[:：]?\s*([A-Z0-9/.-]+)",
            r"\bH\d{4,}-\d{2}\b",
            r"\b\d{2}-[A-Z]{2,4}\b",
        ],
    }
    for pat in org_patterns.get(org, []):
        for m in re.finditer(pat, u, re.I):
            val = m.group(1) if m.groups() else m.group(0)
            val = re.sub(r"\s+", " ", val).strip(" .:-")
            if val and val not in candidates:
                candidates.append(val)

    if org == "JMA":
        candidates = [re.sub(r"\s+", "", value) for value in candidates]

    # ARA attachment의 Certificate No가 Ref No보다 더 구체적인 경우(-1 등)
    # 긴 값을 우선하되 후보 전체는 유지한다.
    if org in {"ARA", "JUHF"} and candidates:
        candidates = sorted(
            dict.fromkeys(candidates),
            key=lambda value: (len(value), value.count("-")),
            reverse=True,
        )

    return (candidates[0] if candidates else "", candidates)

def extract_expiry(text: str, filename: str, org: str) -> tuple[str, list[dict[str, str]]]:
    # BPJPH는 유지확인용으로만 사용한다. 발급일/파일명 날짜를 유효기간으로 오인하지 않는다.
    if org == "BPJPH":
        return "", []

    # MUI는 Valid until만 신뢰한다. Issued date / footer 날짜 fallback 금지.
    if org == "MUI":
        date, raw = extract_mui_valid_until_date(text)

        if date:
            return date, [{"date": date, "raw": raw, "source": "MUI_VALID_UNTIL"}]

        # MUI에서 본문 Valid until 실패 시에는 파일명 괄호/물결 날짜만 보조 사용.
        fname = filename or ""
        for raw in re.findall(
            r"(?:\[|\(|~)(?:[A-Z-]+_)?(20\d{2}[-.][0-9]{1,2}[-.][0-9]{1,2}|\d{2}[.]\d{1,2}[.]\d{1,2})(?:\]|\))?",
            fname,
            re.I,
        ):
            d = parse_date_text(raw)

            if d:
                return d, [{"date": d, "raw": raw, "source": "FILENAME"}]

        return "", []

    if org == "CICOT":
        date, raw = extract_cicot_expiry_date(text, filename)

        if date:
            return date, [{"date": date, "raw": raw, "source": "CICOT_EXPIRED_DATE"}]

    if org == "ARA":
        date, raw = extract_latest_date_near_anchors(
            text,
            ["EXPIRED DATE", "EXPIRY DATE"],
            before=40,
            after=700,
        )
        if date:
            return date, [{"date": date, "raw": raw, "source": "ARA_EXPIRED_DATE"}]

    if org == "MUIS":
        date, raw = extract_muis_expiry_date(text, filename)
        if date:
            return date, [{"date": date, "raw": raw, "source": "MUIS_EXPIRY"}]

    anchors_by_org = {
        "IFANCA": ["THIS CERTIFICATE IS VALID UNTIL", "THIS CERTIFICATE IS VALID THROUGH"],
        "MUI": ["VALID UNTIL"],
        "BPJPH": [],
        "HQC": ["EXPIRY DATE", "DATE OF EXPIRY"],
        "ISA": ["VALID UNTIL", "VALID THROUGH"],
        "LLS-ISA": ["VALID UNTIL", "VALID THROUGH"],
        "HCE": ["EXPIRY DATE", "EXPIRY"],
        "HFCE": ["VALID UNTIL"],
        "HFQ": ["CERTIFICATE VALID UNTIL", "CERTIFICADO VÁLIDO HASTA", "VALID UNTIL"],
        "HALAL CONTROL": ["VALID UNTIL", "THIS CERTIFICATE IS VALID UNTIL"],
        "HCA": ["EXPIRED DATE", "EXPIRY DATE", "VALID UNTIL"],
        "CICOT": ["VALID UNTIL", "SAH SEHINGGA", "EFFECTIVE FROM"],
        "JAKIM": ["SAH SEHINGGA", "VALID UNTIL"],
        "MUIS": ["VALID UNTIL", "EXPIRY DATE", "DATE OF EXPIRY"],
        "JMA": ["VALID UNTIL"],
        "KMF": ["유효기간", "인증기간", "VALID UNTIL"],
        "TQHCC": ["CERTIFICATE VALID UNTIL", "VALID UNTIL"],
        "HFFIA": ["VALID UNTIL", "EXPIRY DATE"],
        "ARA": ["EXPIRED DATE", "EXPIRY DATE", "VALID UNTIL"],
        "JUHF": ["DATE OF EXPIRY", "EXPIRY DATE", "VALID UNTIL"],
    }

    candidates: list[dict[str, str]] = []

    for anchor in anchors_by_org.get(org, ["VALID UNTIL", "EXPIRY DATE"]):
        date, raw = extract_date_after(text, [anchor], window=520)

        if date:
            candidates.append({"date": date, "raw": raw, "source": anchor})
            break

    # CICOT/JAKIM처럼 issue date와 expiry date가 연속일 때 anchor 주변 두 번째 날짜를 만료 후보로 사용
    if not candidates and org in {"CICOT", "JAKIM"}:
        all_dates = find_dates(text)

        if len(all_dates) >= 2:
            candidates.append({**all_dates[-1], "source": "LAST_DATE_FALLBACK"})

    # 파일명 보조 규칙: [ORG_YYYY-MM-DD], ORG(YYYY-MM-DD), (~26.12.17)
    fname = filename or ""

    for raw in re.findall(
        r"(?:\[|\(|~)(?:[A-Z-]+_)?(20\d{2}[-.][0-9]{1,2}[-.][0-9]{1,2}|\d{2}[.]\d{1,2}[.]\d{1,2})(?:\]|\))?",
        fname,
        re.I,
    ):
        d = parse_date_text(raw)

        if d:
            candidates.append({"date": d, "raw": raw, "source": "FILENAME"})
            break

    # 전체 날짜 fallback은 위험하므로 MUI/BPJPH는 제외
    if not candidates and org not in {"BPJPH", "MUI"}:
        all_dates = find_dates(text)

        if all_dates:
            candidates.append({**all_dates[-1], "source": "DATE_FALLBACK"})

    seen = set()
    unique = []

    for c in candidates:
        k = (c.get("date"), c.get("source"))

        if c.get("date") and k not in seen:
            seen.add(k)
            unique.append(c)

    return (unique[0]["date"] if unique else "", unique)

def strip_inline_address_tail(value: str) -> str:
    """
    한 줄 안에 회사명 + 주소가 붙은 경우 주소 꼬리를 제거한다.
    예: Zeeland Farm Services 2525 84th Avenue, Zeeland...
    """
    text = clean_company_value(value)

    if not text:
        return ""

    text = re.sub(
        r"\s+\d{1,6}\s+"
        r"(?:[A-Z0-9'.#-]+\s+){0,6}"
        r"(?:STREET|ST\.?|AVENUE|AVE\.?|ROAD|RD\.?|DRIVE|DR\.?|LANE|LN\.?|"
        r"BOULEVARD|BLVD\.?|WAY|COURT|CT\.?|LOOP|PARKWAY|PKWY\.?)\b.*$",
        "",
        text,
        flags=re.I,
    )

    text = re.sub(r"\s+(?:NO\.?\s*)?\d{1,6}[, ]+.*$", "", text, flags=re.I)

    return clean_company_value(text).strip(" ,.-")

def normalize_manufacturer_output(value: str, org: str) -> str:
    text = clean_company_value(value)

    if not text:
        return ""

    text = re.sub(
        r"^(Company\s+Name\s*&\s*Address|Plant\s+Name\s*&\s*Address|Company\s+Name|Name\s+of\s+Company|Company|Manufacturer|Manufactured\s+by|For)\s*[:：]\s*",
        "",
        text,
        flags=re.I,
    )

    # Company Name: A / Facility: A 같이 붙는 OCR 케이스 방지
    text = re.split(
        r"\s+(?:Facility|Plant|Head\s+Office|Factory|Address)\s*[:：]",
        text,
        maxsplit=1,
        flags=re.I,
    )[0]

    text = strip_inline_address_tail(text)
    text = strip_address_from_company(text)
    text = clean_company_value(text).strip(" ,.-")

    company, _country = split_company_country_suffix(text)
    text = clean_company_value(company)

    # TQHCC 일부 OCR 꼬리: OHLY GmbH igual ou!
    if org == "TQHCC":
        text = re.split(r"\s+igual\s+", text, maxsplit=1, flags=re.I)[0]
        text = clean_company_value(text)

    return text

def extract_manufacturer(text: str, org: str) -> str:
    lines = lines_of(text)

    if org == "JUHF":
        candidate = extract_company_after_marker(
            lines,
            r"\bCOMPANY\s+NAME\b",
            max_next=6,
        )
        if candidate:
            return candidate

    if org == "ARA":
        # ARA attachment는 Company Name 다음에 Name of Products가 끼는 OCR 구조가 있어
        # 제품 라벨을 제조사로 오인하지 않도록 company-like 라인을 찾는다.
        candidate = extract_company_after_marker(
            lines,
            r"\bCOMPANY\s+NAME\b",
            max_next=10,
        )
        if candidate:
            return candidate

    if org in {"ISA", "LLS-ISA"}:
        # ISA 구형 문서: 상단에 회사명 단독 라인이 있고 그 아래 주소가 온다.
        # 특정 회사명을 박지 않고, HALAL CERTIFICATION 이후 첫 company-like 라인을 사용.
        for i, line in enumerate(lines[:20]):
            if "HALAL CERTIFICATION" in upper_text(line):
                for j in range(i + 1, min(len(lines), i + 8)):
                    candidate = clean_company_value(lines[j])

                    if not candidate:
                        continue

                    if is_admin_or_address_line(candidate):
                        continue

                    if is_company_like(candidate):
                        return candidate

        for line in lines[:15]:
            candidate = clean_company_value(line)

            if not candidate:
                continue

            if is_admin_or_address_line(candidate):
                continue

            if is_company_like(candidate):
                return candidate

    if org == "CICOT":
        # OCR 오인식 대응:
        # 원문은 CERTIFIES THAT이나, OCR에서 CERTIFIES THAI로 나오는 케이스가 있음.
        for i, line in enumerate(lines):
            upper_line = upper_text(line)

            if "CERTIFIES THAT" in upper_line or "CERTIFIES THAI" in upper_line:
                # 같은 줄 뒤쪽에 회사명이 붙는 경우
                right = re.split(r"CERTIFIES\s+(?:THAT|THAI)", line, flags=re.I)
                if len(right) >= 2:
                    candidate = clean_company_value(right[-1])
                    if candidate and is_company_like(candidate):
                        return candidate

                # 다음 1~8줄 안에서 회사명 탐색
                for j in range(i + 1, min(len(lines), i + 9)):
                    candidate = clean_company_value(lines[j])

                    if not candidate:
                        continue

                    if is_admin_or_address_line(candidate):
                        continue

                    if is_company_like(candidate):
                        return candidate

        # fallback: 상단 30줄에서 회사명 후보만 탐색
        for line in lines[:30]:
            candidate = clean_company_value(line)

            if not candidate:
                continue

            if is_admin_or_address_line(candidate):
                continue

            if is_company_like(candidate):
                return candidate
            
    if org == "BPJPH":
        for i, line in enumerate(lines):
            if "FACTORY'S ADDRESS" in upper_text(line) or "FACTORY ADDRESS" in upper_text(line):
                for j in range(i + 1, min(len(lines), i + 12)):
                    candidate = clean_company_value(lines[j])

                    if not candidate:
                        continue

                    if re.match(r"^ID\d{8,}$", candidate, re.I):
                        continue

                    if re.search(r"KELompok|KELOMPOK|DOKUMEN|DAFTAR|PRODUCT\s+NAME|FACTORY", candidate, re.I):
                        continue

                    next_line = clean_company_value(lines[j + 1]) if j + 1 < len(lines) else ""

                    if next_line and re.search(r"\b(CO\.?,?\s*LTD|LTD|LIMITED|GMBH|INC|CORPORATION|BV|S\.A\.|SAS)\b", next_line, re.I):
                        combined = clean_company_value(f"{candidate} {next_line}")
                        company, _country = split_company_country_suffix(combined)
                        return company

                    if re.search(r"\b(CO\.?,?\s*LTD|LTD|LIMITED|GMBH|INC|CORPORATION|BV|B\.V\.|S\.A\.|SAS|TECHNOLOGY|BIOLOGICAL)\b", candidate, re.I):
                        company, _country = split_company_country_suffix(candidate)
                        return company

                break

    if org == "JAKIM":
        m = re.search(
            r"Manufactured\s*/\s*distributed\s*/\s*managed\s*by\s*[:：]\s*([^\n\r]+)",
            text,
            re.I,
        )

        if m:
            value = clean_company_value(m.group(1))

            if value and not value.upper().startswith("MANUFACTURED"):
                return value

        for i, line in enumerate(lines):
            if "MANUFACTURED / DISTRIBUTED / MANAGED BY" in upper_text(line):
                for j in range(i + 1, min(len(lines), i + 4)):
                    candidate = clean_company_value(lines[j])

                    if candidate and not re.search(r"ADDRESS|ALAMAT|VALID|SAH SEHINGGA", candidate, re.I):
                        return candidate

        if org == "CICOT":
            # 1) 기존 문구형: CERTIFIES THAI THAI EDIBLE OIL CO.,LTD.
            m = re.search(
                r"CERTIFIES\s+THAI\s+([A-Z0-9 .,&'()/-]+?(?:CO\.?,?\s*LTD\.?|LTD\.?|LIMITED))",
                text,
                re.I,
            )

            if m:
                return clean_company_value(m.group(1))

            # 2) KRATION/SIAM 문서형: 상단부에 회사명이 단독 라인으로 존재
            for line in lines[:25]:
                candidate = clean_company_value(line)

                if not candidate:
                    continue

                if re.search(r"CENTRAL\s+ISLAMIC|COUNCIL|SHEIKHUL|HALAL|CERTIFICATE", candidate, re.I):
                    continue

                if re.search(r"\b(CO\.?,?\s*LTD\.?|CO\.?\s*,?\s*LTD\.?|LTD\.?|LIMITED)\b", candidate, re.I):
                    return candidate

    if org == "HFFIA":
        m = re.search(
            r"(DSM\s+Food\s+Specialties\s+BV|[A-Z][A-Z0-9 .,&'()/-]+?\s+(?:BV|B\.V\.|GMBH|LTD\.?|LIMITED|INC\.?|S\.A\.|SAS))",
            text,
            re.I,
        )

        if m:
            return clean_company_value(m.group(1))
        
    if org == "HALAL CONTROL":
        for i, line in enumerate(lines):
            if "MANUFACTURED BY" in upper_text(line):
                for j in range(i + 1, min(len(lines), i + 10)):
                    candidate = clean_ocr_text(lines[j])

                    if not candidate:
                        continue

                    if is_halal_control_noise_line(candidate):
                        continue

                    if looks_like_company_name_for_halal_control(candidate):
                        return candidate.strip()

                break

    labels = {
        "IFANCA": ["Company Name & Address", "Plant Name & Address"],
        "MUI": ["Name of Company", "Facility Name"],
        "BPJPH": ["Nama Pelaku Usaha", "Name of Company", "Factory's Address"],
        "HQC": ["Awarded to", "Manufacturing Site Address"],
        "ISA": ["Company Name", "Company"],
        "LLS-ISA": ["Company Name", "Company"],
        "HCE": ["Company Name", "Manufacture Site"],
        "HFCE": ["For"],
        "HFQ": ["CERTIFY THAT THE COMPANY", "CERTIFICA QUE LA EMPRESA"],
        "HALAL CONTROL": ["manufactured by"],
        "HCA": ["products of the"],
        "CICOT": ["Entrepreneur", "Manufacturer"],
        "JAKIM": ["Manufactured / distributed / managed by", "Manufactured"],
        "MUIS": ["listed in Annex A for", "Name & Address of Company", "Name and Address of Establishment", "Company", "Manufacturer", "Manufactured by"],
        "JMA": ["Name and Address of Company"],
        "KMF": ["Manufacturer", "제조원", "제조사", "업체명", "회사명"],
        "TQHCC": ["Manufacturer"],
        "HFFIA": ["Processing Plant", "Company", "Manufacturer"],
        "JUHF": ["COMPANY NAME"],
        "ARA": ["Company Name"],
    }

    val = extract_after_label(lines, labels.get(org, ["Company", "Manufacturer"]), max_next=5)

    if is_bad_manufacturer_candidate(val):
        val = ""
    val = clean_company_value(val)

    if org in {"BPJPH", "MUI"}:
        company, country = split_company_country_suffix(val)
        if country:
            return company

    if org == "HCE" and "," in val:
        return clean_company_value(val.split(",", 1)[0])

    if org in {"IFANCA", "HFCE"}:
        return strip_address_from_company(val)

    return val

def extract_manufacturing_country(text: str, org: str) -> str | None:
    lines = lines_of(text)
    whole_upper = upper_text(text)

    if org == "HALAL CONTROL":
        for i, line in enumerate(lines):
            if "MANUFACTURED BY" in upper_text(line):
                block_lines = lines[i + 1: i + 10]

                for candidate in block_lines:
                    country = extract_country_from_parentheses(candidate)

                    if country:
                        return country

                block = "\n".join(block_lines)
                country = extract_country_from_text(block)

                if country:
                    return country

    if org == "HCA":
        # HCA Vietnam 문서에는 "does not circulate ... Indonesia states"가 있어
        # 전체 본문 country fallback을 쓰면 제조국이 INDONESIA로 오염된다.
        for i, line in enumerate(lines):
            u = upper_text(line)

            if re.search(r"\b(HEAD\s+OFFICE|FACTORY|ADDRESS)\b", u):
                block = "\n".join(lines[i: i + 5])
                block_u = upper_text(block)

                if re.search(r"\b(VIETNAM|HO\s+CHI\s+MINH|HANOI|DONG\s+NAI|BINH\s+DUONG)\b", block_u):
                    return "VIETNAM"

        # 전체 fallback 전, 유통 제외 문장을 제거하고 Vietnam marker를 우선 확인
        hca_clean_text = re.sub(
            r"THE\s+CERTIFICATE\s+DOES\s+NOT\s+CIRCULATE.+?(?:\.|\n)",
            " ",
            text,
            flags=re.I | re.S,
        )

        hca_upper = upper_text(hca_clean_text)

        if re.search(r"\b(VIETNAM|HO\s+CHI\s+MINH|HANOI|DONG\s+NAI|BINH\s+DUONG)\b", hca_upper):
            return "VIETNAM"

        country = extract_country_from_text(hca_clean_text)

        if country:
            return country

    if org == "BPJPH":
        factory_block = extract_after_label(
            lines,
            ["Alamat Pabrik", "Factory's Address", "Factory Address"],
            max_next=16,
        )

        company_block = extract_after_label(
            lines,
            ["Alamat Pelaku Usaha", "Company's Address", "Company Address"],
            max_next=12,
        )

        bpjph_block = "\n".join([factory_block, company_block])
        bpjph_block_upper = upper_text(bpjph_block)

        korea_markers = [
            "REPUBLIC OF KOREA",
            "GYEONGGI-DO",
            "GYEONGGI DO",
            "ICHEON",
            "PYEONGTAEK",
            "POSEUNG",
            "SEOUL",
            "ULSAN",
            "JINCHEON",
            "CHUNGCHEONGBUK-DO",
            "CHUNGCHEONGBUK DO",
            "GUNSAN",
            "JEONBUK-DO",
        ]

        if any(marker in bpjph_block_upper for marker in korea_markers):
            return "KOREA"

        # factory/company block 안의 국가만 먼저 본다.
        block_country = extract_country_from_text(bpjph_block)

        if block_country and block_country != "INDONESIA":
            return block_country

        # factory block이 짧게 잘려도 전체 본문에 강한 한국 주소 마커가 있으면 제조국 KOREA
        if any(marker in whole_upper for marker in korea_markers):
            return "KOREA"

        for marker, country in [
            ("HEBEI", "CHINA"),
            ("P.R. CHINA", "CHINA"),
            ("CHINA", "CHINA"),
            ("MADHYA PRADESH", "INDIA"),
            ("PITHAMPUR", "INDIA"),
            ("INDIA", "INDIA"),
            ("VIETNAM", "VIETNAM"),
        ]:
            if marker in upper_text(bpjph_block) or marker in whole_upper:
                return country

    if org in {"IFANCA", "HQC", "HCE", "JMA", "TQHCC", "JAKIM", "MUI", "BPJPH"}:
        anchors = [
            "Plant Name & Address",
            "Manufacturing Site Address",
            "Manufacture Site",
            "Address of Plant",
            "Facility Address",
            "Factory Address",
            "Factory's Address",
            "Manufacturer address",
        ]

        block = extract_after_label(lines, anchors, max_next=8)
        c = extract_country_from_text(block)

        if c:
            return c

    return extract_country_from_text(text)

def split_pages(text: str) -> list[str]:
    parts = re.split(r"\n\s*---\s*PAGE\s+\d+\s*---\s*\n", "\n" + clean_ocr_text(text), flags=re.I)
    return [p.strip() for p in parts if p.strip()]


def extract_products(text: str, org: str) -> list[dict[str, Any]]:
    lines = lines_of(text)
    products: list[dict[str, Any]] = []
    if org == "CICOT":
        # 1) ProductType 라벨이 있으면 그 구역만 제품명으로 사용
        product_type_match = re.search(
            r"Product\s*Type\s*[:：]?\s*([\s\S]*?)(?:Factory\s+Address|Undertakes|The\s+Central\s+Islamic|Effective\s+from|Regrsuation|Registration|Issued\s+on|Entrepreneur|$)",
            text,
            re.I,
        )

        if product_type_match:
            raw_block = product_type_match.group(1)
            raw_names = [
                x.strip(" .;")
                for x in re.split(r"[,/]\s*", raw_block)
                if x.strip(" .;")
            ]

            for idx, name in enumerate(raw_names, start=1):
                name = clean_ocr_text(name)

                if (
                    name
                    and not looks_like_product_noise(name)
                    and not is_company_like(name)
                ):
                    products.append({"no": idx, "name": name})

            if products:
                return products

        # 2) Product Name 라벨이 있으면 다음 의미 있는 라인들을 제품 후보로 사용
        for i, line in enumerate(lines):
            if re.search(r"PRODUCT\s+NAME", line, re.I):
                no = 1

                for j in range(i + 1, min(len(lines), i + 12)):
                    candidate = clean_ocr_text(lines[j])

                    if not candidate:
                        continue

                    if is_admin_or_address_line(candidate):
                        break

                    if looks_like_product_noise(candidate):
                        continue

                    if is_company_like(candidate):
                        continue

                    products.append({"no": no, "name": candidate})
                    no += 1

                if products:
                    return products

        # 3) ProductType/Product Name이 없는 구형/스캔형 CICOT:
        # 문서 전체 broad 수집 금지.
        # 숫자 index 라인 바로 다음 라인만 제품명 후보로 본다.
        # 예:
        # 77
        # KREATION® KE8
        # SIAM MODIFIED STARCH
        # 77 051 199 10 57
        table_products: list[dict[str, Any]] = []
        seen = set()

        for i, line in enumerate(lines):
            index_text = clean_ocr_text(line)

            if not re.fullmatch(r"\d{1,4}", index_text):
                continue

            if i + 1 >= len(lines):
                continue

            candidate = clean_ocr_text(lines[i + 1])

            if not candidate:
                continue

            if looks_like_product_noise(candidate):
                continue

            if is_company_like(candidate):
                continue

            if re.search(r"CICOT|SHEIKHUL|ISLAMIC|REGISTRATION|REGRSUATION", candidate, re.I):
                continue

            if not re.search(r"[A-Za-z]{2,}", candidate):
                continue

            key = upper_text(candidate)

            if key in seen:
                continue

            seen.add(key)
            table_products.append({
                "no": int(index_text),
                "name": candidate,
            })

        if table_products:
            return table_products[:50]
            
    if org == "IFANCA":
        i = 0
        while i < len(lines):
            m = re.match(r"^(\d{1,3})\.\s*(.+)?$", lines[i])
            if not m:
                i += 1
                continue
            no = int(m.group(1))
            name = (m.group(2) or "").strip()
            if not name and i + 1 < len(lines):
                name = lines[i + 1].strip()
                i += 1
            # 다음 1~6줄 안에서 HC- 탐색
            chunk = "\n".join(lines[i:i + 8])
            certs = re.findall(r"\bHC-[A-Z0-9]{6,}\b", chunk, re.I)
            halal_ids = re.findall(r"\b[A-Z]\d{4,}\b", chunk)
            if name and not name.upper().startswith(("THIS IS TO", "DATE:", "DOCUMENT")):
                products.append({"no": no, "name": name, "cert_no": certs[0].upper() if certs else "", "halal_id": halal_ids[0] if halal_ids else ""})
            i += 1
        return products

    if org in {"MUI", "BPJPH"}:
        for i, line in enumerate(lines):
            m = re.match(r"^(\d{1,4})\s+(.+)$", line)

            if m:
                name = m.group(2).strip()

                if (
                    name
                    and not re.search(r"QR CODE|PRODUCT TYPE|KODE", name, re.I)
                    and not looks_like_product_noise(name)
                ):
                    products.append({"no": int(m.group(1)), "name": name})

            elif re.match(r"^\d{1,4}$", line) and i + 1 < len(lines):
                nxt = lines[i + 1].strip()

                if (
                    not re.match(r"^\d+$", nxt)
                    and not re.search(r"PRODUCT|TYPE|QR", nxt, re.I)
                    and not looks_like_product_noise(nxt)
                ):
                    products.append({"no": int(line), "name": nxt})

        return products

    if org == "MUIS":

        for line in lines:

            match = re.match(

                r"^\s*[-.\u2022]?\s*(\d{6})\s+(.+?)\s*$",

                line,

            )


            if not match:

                continue


            product_no = int(match.group(1))

            name = clean_ocr_text(

                match.group(2)

            ).strip(" .-")


            if len(name) < 2:

                continue


            if looks_like_product_noise(name):

                continue


            products.append({

                "no": product_no,

                "name": name,

            })


        return products


    if org in {"HQC", "TQHCC", "JAKIM", "JMA", "KMF", "HCA", "HFQ", "HCE", "HFCE"}:
        for i, line in enumerate(lines):
            # 001 제품명 / 1 제품명 / No-line then name
            m = re.match(r"^(\d{1,4})[.)]?\s+(.+)$", line)
            if m:
                name = m.group(2).strip()
                if len(name) >= 2 and not re.search(r"PAGE|CERT|DATE|VALID|ISSUE|PRODUCT\s*(NAME|TYPE|CODE)", name, re.I):
                    products.append({"no": int(m.group(1)), "name": name})
            elif re.match(r"^\d{1,4}$", line) and i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if len(nxt) >= 2 and not re.search(r"PAGE|CERT|DATE|VALID|ISSUE|PRODUCT\s*(NAME|TYPE|CODE)", nxt, re.I):
                    products.append({"no": int(line), "name": nxt})
        return products

    if org == "ISA" or org == "LLS-ISA":
        # Product Code Product Name Product Type 표. 코드 다음의 제품명 부분을 느슨하게 추출
        for line in lines:
            if re.search(r"PRODUCT\s+CODE|PRODUCT\s+NAME|PRODUCT\s+TYPE", line, re.I):
                continue
            m = re.match(r"^([A-Z0-9#-]{2,})\s+(.+?)\s+(Flavorings|Vegetables|Fruits|Ingredients|Flavors|Flavoring)\b", line, re.I)
            if m:
                products.append({"code": m.group(1), "name": m.group(2).strip(), "type": m.group(3)})
        return products

    # 일반 fallback
    for line in lines:
        m = re.match(r"^(\d{1,4}|[0-9]{3})[.)]?\s+(.{2,})$", line)
        if m:
            products.append({"no": int(m.group(1)), "name": m.group(2).strip()})
    return products


def best_product_match(products: list[dict[str, Any]], expected_name: str = "", filename: str = "") -> dict[str, Any]:
    target = expected_name or filename
    # 파일명에서 1차 제품명 후보만 추출: 번호. 제품명-기관 / 제품명(업체)[기관]
    if not expected_name and filename:
        base = Path(filename).stem
        base = re.sub(r"^\d+[-_ .]*", "", base)
        base = re.split(r"[-\[](?:IFANCA|MUI|BPJPH|HQC|ISA|LLS-ISA|HCE|HFCE|HFQ|JAKIM|MUIS|JMA|KMF|TQHCC|HFFIA|CICOT|HCA)\b", base, flags=re.I)[0]
        target = base
    best = {"score": 0.0, "product": None}
    for p in products:
        s = similarity(target, p.get("name", ""))
        if s > best["score"]:
            best = {"score": s, "product": p}
    return best


def country_match(manufacturing_country: str | None, cert_country: str | None) -> str:
    if not manufacturing_country or not cert_country:
        return "확인필요"
    return "일치" if manufacturing_country == cert_country else "불일치"

def is_non_certificate_document(text: str, filename: str = "") -> bool:
    u = upper_text("\n".join([filename or "", text or ""]))

    strong_non_cert_markers = [
        "MATERIAL SAFETY DATA SHEETS",
        "MSDS",
        "CERTIFICATION PROCESS IS CURRENTLY UNDERWAY",
        "CERTIFICATE IS EXPECTED TO BE AWARDED",
        "EXPECTED TO BE AWARDED",
        "NOT CERTIFIED",
        "NOT A HALAL CERTIFICATE",
        "갱신 해당 없음",
        "해당 사항 없음",
        "제출 대상에 해당하지 않습니다",
        "할랄 인증을 취득 또는 유지하고 있는 품목이 아니",
    ]

    return any(marker in u for marker in strong_non_cert_markers)

def _load_certificate_rule_overrides() -> list[dict[str, Any]]:
    """
    AI 규칙 리뷰에서 승인된 override rule을 읽는다.
    import 순환을 피하기 위해 함수 내부 import 사용.
    """
    try:
        from app.services.rule_candidate_service import get_rule_overrides
    except Exception:
        return []

    try:
        data = get_rule_overrides()
    except Exception:
        return []

    rules = data.get("rules") or []

    if not isinstance(rules, list):
        return []

    return [rule for rule in rules if isinstance(rule, dict) and rule.get("enabled", True)]


def _override_find_date_after(
    text: str,
    anchors: list[str],
    stop_before: list[str] | None = None,
    window: int = 650,
) -> tuple[str, str]:
    src = str(text or "")
    upper = upper_text(src)
    stop_before = stop_before or []

    for anchor in anchors or []:
        anchor_u = str(anchor or "").upper().strip()

        if not anchor_u:
            continue

        start = 0

        while True:
            idx = upper.find(anchor_u, start)

            if idx < 0:
                break

            chunk = src[idx: idx + window]
            chunk_upper = upper_text(chunk)
            cut_at = len(chunk)

            for stop in stop_before:
                stop_u = str(stop or "").upper().strip()

                if not stop_u:
                    continue

                stop_idx = chunk_upper.find(stop_u)

                if stop_idx > 0:
                    cut_at = min(cut_at, stop_idx)

            chunk = chunk[:cut_at]
            dates = find_dates(chunk)

            if dates:
                return dates[0].get("date") or "", dates[0].get("raw") or ""

            start = idx + len(anchor_u)

    return "", ""


def _override_cleanup_manufacturer(value: str, org: str) -> str:
    cleanup_func = globals().get("normalize_manufacturer_output")

    if callable(cleanup_func):
        return cleanup_func(value, org)

    text = clean_ocr_text(value)
    text = re.sub(
        r"^(Company\s+Name\s*&\s*Address|Company\s+Name|Name\s+of\s+Company|Company|Manufacturer|Manufactured\s+by|For)\s*[:：]\s*",
        "",
        text,
        flags=re.I,
    )
    return clean_ocr_text(text).strip(" ,.-")


def apply_certificate_rule_overrides(
    result: dict[str, Any],
    text: str,
    filename: str = "",
) -> dict[str, Any]:
    """
    certificate_rule_overrides.json에 승인된 AI 규칙을 최종 parse 결과에 적용한다.
    Python 코드 자동수정이 아니라 JSON override만 적용한다.
    """
    output = dict(result or {})
    rules = _load_certificate_rule_overrides()

    if not rules:
        return output

    haystack = upper_text("\n".join([filename or "", text or ""]))

    for rule in rules:
        target_org = str(rule.get("target_org") or "").upper().strip()
        target_field = str(rule.get("target_field") or "").strip()
        rule_kind = str(rule.get("rule_kind") or "").strip()
        proposed_rule = rule.get("proposed_rule") or {}

        current_org = str(output.get("cert_org") or "").upper().strip()

        if target_org and current_org != target_org:
            continue

        if rule_kind == "date_anchor_rule" and target_field:
            anchors = proposed_rule.get("anchors") or []
            stop_before = proposed_rule.get("stop_before") or []
            window = int(proposed_rule.get("window") or 650)

            date, raw = _override_find_date_after(
                text,
                anchors=anchors,
                stop_before=stop_before,
                window=window,
            )

            if date:
                output[target_field] = date

                if target_field == "expiry_date":
                    output["expiry_candidates"] = [{
                        "date": date,
                        "raw": raw,
                        "source": f"AI_OVERRIDE:{rule.get('rule_candidate_id', '')}",
                    }]

        elif rule_kind == "manufacturer_cleanup_rule":
            field = target_field or "manufacturer"
            before = str(output.get(field) or "")
            after = _override_cleanup_manufacturer(before, current_org)

            if after:
                output[field] = after

        elif rule_kind == "cert_no_pattern_rule":
            field = target_field or "cert_no"
            patterns = proposed_rule.get("patterns") or []

            for pattern in patterns:
                try:
                    match = re.search(pattern, text, re.I)
                except re.error:
                    continue

                if not match:
                    continue

                value = match.group(1) if match.groups() else match.group(0)
                value = re.sub(r"\s+", "", value.strip())

                if value:
                    output[field] = value

                    if field == "cert_no":
                        output["cert_no_candidates"] = [value]

                    break

        elif rule_kind == "non_certificate_doc_rule":
            markers = [upper_text(x) for x in proposed_rule.get("markers") or []]

            if markers and any(marker in haystack for marker in markers):
                output.update({
                    "ok": True,
                    "parse_status": "NON_CERTIFICATE_DOC",
                    "cert_org": "UNKNOWN",
                    "cert_country": "",
                    "org_hits": [],
                    "cert_no": "",
                    "cert_no_candidates": [],
                    "expiry_date": "",
                    "expiry_candidates": [],
                    "manufacturer": "",
                    "manufacturing_country": "",
                    "country_match_status": "",
                    "products_count": 0,
                    "product_candidates": [],
                    "best_product_match": {},
                    "source_rule": "AI_NON_CERTIFICATE_DOC_RULE",
                    "confidence": "HIGH",
                })

    return output

def parse_certificate_rule(raw_text: str, filename: str = "", expected_name: str = "", expected_org: str = "") -> dict[str, Any]:
    text = clean_ocr_text(raw_text)
    blob = upper_text("\n".join([filename or "", expected_org or "", text]))

    if (
        "TESSERACT IS NOT INSTALLED" in blob
        or "NOT IN YOUR PATH" in blob
        or "TESSERACTNOTFOUNDERROR" in blob
        or "[TESSERACT_ERROR]" in blob
    ):
        return {
            "ok": False,
            "parse_status": "TESSERACT_ERROR",
            "cert_org": "UNKNOWN",
            "cert_country": "",
            "org_hits": [],
            "cert_no": "",
            "cert_no_candidates": [],
            "expiry_date": "",
            "expiry_candidates": [],
            "manufacturer": "",
            "manufacturing_country": "",
            "country_match_status": "",
            "products_count": 0,
            "product_candidates": [],
            "best_product_match": {},
            "source_rule": "TESSERACT_ERROR_RULE",
            "confidence": "LOW",
            "has_text": bool(text.strip()),
            "text_length": len(text),
            "message": "Tesseract OCR 엔진이 설치되어 있지 않거나 PATH에 등록되어 있지 않습니다.",
        }

    if is_non_certificate_document(text, filename):
        return {
            "ok": True,
            "parse_status": "NON_CERTIFICATE_DOC",
            "cert_org": "UNKNOWN",
            "cert_country": "",
            "org_hits": [],
            "cert_no": "",
            "cert_no_candidates": [],
            "expiry_date": "",
            "expiry_candidates": [],
            "manufacturer": "",
            "manufacturing_country": "",
            "country_match_status": "",
            "products_count": 0,
            "product_candidates": [],
            "best_product_match": {},
            "source_rule": "NON_CERTIFICATE_DOC_RULE",
            "confidence": "HIGH",
            "has_text": bool(text.strip()),
            "text_length": len(text),
            "message": "MSDS, 갱신 해당 없음 공문 등 인증서가 아닌 문서로 분류되었습니다.",
        }

    org, cert_country, org_hits = detect_org(text, filename=filename, expected_org=expected_org)
    if org == "UNKNOWN":
        # 파일명 기반 기관 힌트
        org, cert_country, org_hits = detect_org("", filename=filename, expected_org=expected_org)

    # 인증기관국가는 본문/LHLN DB/단일국가 fallback 순서로 보정한다.
    cert_country = resolve_cert_country(org, blob, cert_country)

    expiry, expiry_candidates = extract_expiry(text, filename, org)
    cert_no, cert_no_candidates = extract_cert_no(text, org)
    if org == "HFQ":
        hfq_match = (
            re.search(
                r"\b(HFQ\s*-\s*\d{1,6}\s*/\s*\d{1,4}\s*/\s*[A-Z]{2,10})\b",
                text,
                re.I,
            )
            or re.search(
                r"WITH\s+CERTIFICATE\s+NUMBER\s*[:：]?\s*(HFQ\s*-\s*\d{1,6}\s*/\s*\d{1,4}\s*/\s*[A-Z]{2,10})\b",
                text,
                re.I,
            )
            or re.search(
                r"CON\s+N[ºO]\s+DE\s+CERTIFICADO\s*[:：]?\s*(HFQ\s*-\s*\d{1,6}\s*/\s*\d{1,4}\s*/\s*[A-Z]{2,10})\b",
                text,
                re.I,
            )
        )

        cert_no = re.sub(r"\s+", "", hfq_match.group(1).upper()) if hfq_match else ""
        cert_no_candidates = [cert_no] if cert_no else []
    maker = normalize_manufacturer_output(extract_manufacturer(text, org), org)
    manufacturing_country = extract_manufacturing_country(text, org)
    products = finalize_product_candidates(extract_products(text, org))
    product_match = best_product_match(products, expected_name=expected_name, filename=filename)

    # IFANCA는 제품 row의 HC 번호가 있으면 우선 적용
    if org == "IFANCA" and product_match.get("product") and product_match["score"] >= 0.72:
        row_cert = product_match["product"].get("cert_no")
        if row_cert:
            cert_no = row_cert

    has_text = bool(text.strip())
    if not has_text:
        parse_status = "SCANNED_NEED_OCR"
        confidence = "LOW"
    elif org == "BPJPH":
        parse_status = "BPJPH_MAINTENANCE_ONLY"
        confidence = "MEDIUM" if cert_no or products else "LOW"
    elif org in {"HFFIA"} and expiry_candidates and expiry_candidates[0].get("source") == "FILENAME":
        parse_status = "FILENAME_ONLY"
        confidence = "LOW"
    elif org != "UNKNOWN" and expiry and (cert_no or products or maker):
        if products and product_match.get("score", 0) >= 0.72:
            parse_status = "RULE_MATCHED"
            confidence = "HIGH"
        else:
            parse_status = "LOW_CONFIDENCE"
            confidence = "MEDIUM"
    elif org != "UNKNOWN" and (expiry or cert_no):
        parse_status = "LOW_CONFIDENCE"
        confidence = "MEDIUM"
    else:
        parse_status = "MANUAL_REVIEW"
        confidence = "LOW"

    result = {
        "ok": parse_status in {"RULE_MATCHED", "LOW_CONFIDENCE", "BPJPH_MAINTENANCE_ONLY", "FILENAME_ONLY"},
        "parse_status": parse_status,
        "cert_org": org,
        "cert_country": cert_country,
        "org_hits": org_hits,
        "cert_no": cert_no,
        "cert_no_candidates": cert_no_candidates[:20],
        "expiry_date": expiry,
        "expiry_candidates": expiry_candidates[:10],
        "manufacturer": maker,
        "manufacturing_country": manufacturing_country,
        "country_match_status": country_match(manufacturing_country, cert_country),
        "products_count": len(products),
        "product_candidates": products[:80],
        "best_product_match": product_match,
        "source_rule": f"{org}_RULE" if org != "UNKNOWN" else "UNKNOWN_RULE",
        "confidence": confidence,
        "has_text": has_text,
        "text_length": len(text),
    }

    overridden = apply_certificate_rule_overrides(result, text, filename)

    from app.services.certificate_rule_profile_service import (
        finalize_certificate_rule_profile,
    )

    return finalize_certificate_rule_profile(
        overridden,
        raw_text=text,
        filename=filename,
    )



_CONTEXT_ORG_ALIASES = {
    "LLSISA": "ISA",
    "LLS-ISA": "ISA",
    "LPPOMMUI": "MUI",
    "LPPOM-MUI": "MUI",
}


def _context_clean(value: Any) -> str:
    text = clean_ocr_text(str(value or ""))
    if text.strip().lower() in {"", "-", "none", "null", "nan"}:
        return ""
    return text.strip()


def _context_norm(value: Any) -> str:
    text = _context_clean(value).upper()
    text = text.replace("®", "").replace("™", "")
    text = re.sub(r"[^A-Z0-9가-힣]+", "", text)
    return text


def _context_org(value: Any) -> str:
    raw = _context_clean(value).upper()
    key = _context_norm(raw)
    return _CONTEXT_ORG_ALIASES.get(raw) or _CONTEXT_ORG_ALIASES.get(key) or raw


def _context_similarity(left: Any, right: Any) -> float:
    left_key = _context_norm(left)
    right_key = _context_norm(right)

    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    if left_key in right_key or right_key in left_key:
        shorter = min(len(left_key), len(right_key))
        longer = max(len(left_key), len(right_key))
        if shorter >= 4:
            return 0.75 + 0.20 * (shorter / max(longer, 1))
    return SequenceMatcher(None, left_key, right_key).ratio()


def _context_text_match(raw_text: str, expected: Any) -> dict[str, Any]:
    expected_text = _context_clean(expected)
    expected_key = _context_norm(expected_text)
    raw_key = _context_norm(raw_text)

    if not expected_key:
        return {"matched": False, "score": 0.0, "method": "EMPTY"}

    if expected_key in raw_key:
        return {"matched": True, "score": 1.0, "method": "NORMALIZED_SUBSTRING"}

    # OCR 줄 단위로 유사도를 확인한다. 긴 전체문서와 직접 비교하지 않는다.
    best_score = 0.0
    best_line = ""

    for line in lines_of(raw_text):
        score = _context_similarity(expected_text, line)
        if score > best_score:
            best_score = score
            best_line = line

    return {
        "matched": best_score >= 0.74,
        "score": round(best_score, 4),
        "method": "LINE_SIMILARITY",
        "matched_line": best_line[:240],
    }


def reconcile_certificate_rule_with_context(
    rule_result: dict[str, Any],
    raw_text: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    메일 관리번호/첨부 순번/PMF에서 확정된 원료 문맥을 OCR 결과와 교차검증한다.

    원칙:
    - PMF의 기존 인증번호와 유효기간은 새 인증서 값으로 복사하지 않는다.
    - OCR 기관과 메일 기관이 다르면 자동 확정을 차단한다.
    - 제조사/제품명은 실제 OCR 원문에서 확인되는 경우에만 PMF 표준명으로 정규화한다.
    - 원 OCR 값은 ocr_* 필드에 보존한다.
    """
    output = dict(rule_result or {})
    context = dict(context or {})

    reliability = _context_clean(context.get("reliability") or "LOW").upper()
    selection_reason = _context_clean(context.get("selection_reason"))
    expected_org = _context_org(context.get("org"))
    expected_maker = _context_clean(context.get("maker"))
    expected_country = _context_clean(context.get("maker_country")).upper()
    expected_cert_no = _context_clean(context.get("cert_no"))
    current_expiry = _context_clean(context.get("current_expiry"))
    expected_names = [
        _context_clean(context.get("english_name")),
        _context_clean(context.get("material_name")),
    ]
    expected_names = list(dict.fromkeys(name for name in expected_names if name))

    ocr_org = _context_org(output.get("cert_org"))
    ocr_maker = _context_clean(output.get("manufacturer"))
    ocr_country = _context_clean(output.get("manufacturing_country")).upper()
    ocr_cert_no = _context_clean(output.get("cert_no"))
    ocr_expiry = _context_clean(output.get("expiry_date"))

    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    conflicts: list[str] = []

    output["ocr_cert_org"] = ocr_org
    output["ocr_manufacturer"] = ocr_maker
    output["ocr_manufacturing_country"] = ocr_country
    output["ocr_cert_no"] = ocr_cert_no
    output["ocr_expiry_date"] = ocr_expiry

    org_match = False
    if expected_org:
        if ocr_org and ocr_org != "UNKNOWN":
            org_match = ocr_org == expected_org
            checks.append({
                "field": "cert_org",
                "status": "MATCH" if org_match else "CONFLICT",
                "ocr": ocr_org,
                "context": expected_org,
            })
            if not org_match:
                conflicts.append(
                    f"OCR 인증기관({ocr_org})과 메일/PMF 인증기관({expected_org})이 다릅니다."
                )
        elif reliability in {"HIGH", "MEDIUM"}:
            output["cert_org"] = expected_org
            output["cert_org_source"] = "MAIL_PMF_CONTEXT_FALLBACK"
            org_match = True
            checks.append({
                "field": "cert_org",
                "status": "CONTEXT_FALLBACK",
                "ocr": ocr_org or "UNKNOWN",
                "context": expected_org,
            })
        else:
            checks.append({
                "field": "cert_org",
                "status": "UNRESOLVED",
                "ocr": ocr_org or "UNKNOWN",
                "context": expected_org,
            })
    else:
        output["cert_org_source"] = output.get("cert_org_source") or "OCR_RULE"

    maker_text_match = _context_text_match(raw_text, expected_maker)
    maker_value_match = _context_similarity(ocr_maker, expected_maker)
    maker_verified = bool(expected_maker) and (
        maker_text_match.get("matched") or maker_value_match >= 0.72
    )

    if expected_maker:
        checks.append({
            "field": "manufacturer",
            "status": "MATCH" if maker_verified else "NOT_VERIFIED",
            "ocr": ocr_maker,
            "context": expected_maker,
            "value_score": round(maker_value_match, 4),
            "text_match": maker_text_match,
        })

        if maker_verified and not conflicts:
            output["manufacturer"] = expected_maker
            output["manufacturer_source"] = "MAIL_PMF_CONTEXT_VERIFIED_IN_OCR"
            if expected_country:
                output["manufacturing_country"] = expected_country
                output["manufacturing_country_source"] = "MAIL_PMF_CONTEXT"
        elif not ocr_maker:
            warnings.append("메일/PMF 제조사를 OCR 원문에서 확인하지 못했습니다.")
        elif maker_value_match < 0.45:
            warnings.append(
                f"OCR 제조사({ocr_maker})와 메일/PMF 제조사({expected_maker})의 유사도가 낮습니다."
            )

    product_matches: list[dict[str, Any]] = []
    product_candidates = output.get("product_candidates") or []

    for expected_name in expected_names:
        raw_match = _context_text_match(raw_text, expected_name)
        best_candidate: dict[str, Any] | None = None
        best_score = 0.0

        for candidate in product_candidates:
            score = _context_similarity(expected_name, candidate.get("name"))
            if score > best_score:
                best_score = score
                best_candidate = candidate

        matched = bool(raw_match.get("matched") or best_score >= 0.72)
        product_matches.append({
            "expected_name": expected_name,
            "matched": matched,
            "raw_text_match": raw_match,
            "candidate_score": round(best_score, 4),
            "candidate": best_candidate,
        })

    product_verified_rows = [row for row in product_matches if row.get("matched")]
    product_verified = bool(product_verified_rows)

    if expected_names:
        checks.append({
            "field": "product",
            "status": "MATCH" if product_verified else "NOT_VERIFIED",
            "matches": product_matches,
        })

        if product_verified and not conflicts:
            best_row = max(
                product_verified_rows,
                key=lambda row: max(
                    float(row.get("candidate_score") or 0.0),
                    float((row.get("raw_text_match") or {}).get("score") or 0.0),
                ),
            )
            candidate_score = float(best_row.get("candidate_score") or 0.0)
            canonical_product = (
                best_row.get("candidate")
                if candidate_score >= 0.72
                else {
                    "name": best_row.get("expected_name"),
                    "source": "MAIL_PMF_CONTEXT_VERIFIED_IN_OCR",
                }
            )
            output["best_product_match"] = {
                "score": max(
                    float(best_row.get("candidate_score") or 0.0),
                    float((best_row.get("raw_text_match") or {}).get("score") or 0.0),
                ),
                "product": canonical_product,
                "source": "MAIL_PMF_CONTEXT",
            }
        else:
            warnings.append("메일/PMF 제품명을 OCR 원문 또는 제품 목록에서 확인하지 못했습니다.")

    cert_no_match = False
    if expected_cert_no and ocr_cert_no:
        cert_no_match = _context_norm(expected_cert_no) == _context_norm(ocr_cert_no)
        checks.append({
            "field": "cert_no",
            "status": "MATCH" if cert_no_match else "CHANGED_OR_CONFLICT",
            "ocr": ocr_cert_no,
            "context_previous": expected_cert_no,
        })
        if not cert_no_match:
            warnings.append(
                "OCR 인증번호와 PMF의 기존 인증번호가 다릅니다. 갱신으로 번호가 변경된 것인지 확인해야 합니다."
            )

    date_regression = False
    if current_expiry and ocr_expiry and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", current_expiry) and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", ocr_expiry):
        date_regression = ocr_expiry < current_expiry
        checks.append({
            "field": "expiry_date",
            "status": "REGRESSION" if date_regression else "NOT_OLDER",
            "ocr": ocr_expiry,
            "context_previous": current_expiry,
        })
        if date_regression:
            warnings.append(
                f"OCR 유효기간({ocr_expiry})이 PMF 기존 유효기간({current_expiry})보다 과거입니다."
            )

    context_score = 0
    if org_match:
        context_score += 35
    if maker_verified:
        context_score += 30
    if product_verified:
        context_score += 25
    if cert_no_match:
        context_score += 10

    high_reliability = reliability == "HIGH"
    non_bpjph_has_expiry = output.get("cert_org") == "BPJPH" or bool(ocr_expiry)
    profile_blocking_flags = list(output.get("blocking_quality_flags") or [])

    if profile_blocking_flags:
        warnings.append(
            "기관 규칙 품질 검사에서 자동확정 차단 사유가 발견되었습니다: "
            + ", ".join(profile_blocking_flags)
        )

    auto_confirm_eligible = bool(
        high_reliability
        and not conflicts
        and not profile_blocking_flags
        and not date_regression
        and org_match
        and (maker_verified or product_verified)
        and non_bpjph_has_expiry
    )

    if conflicts:
        output["ok"] = False
        output["parse_status"] = "MANUAL_REVIEW"
        output["confidence"] = "LOW"
        context_status = "CONFLICT"
    elif profile_blocking_flags:
        output["ok"] = False
        output["parse_status"] = "MANUAL_REVIEW"
        output["confidence"] = "LOW"
        context_status = "PROFILE_REVIEW"
    elif auto_confirm_eligible:
        output["ok"] = True
        output["parse_status"] = "RULE_MATCHED"
        output["confidence"] = "HIGH"
        context_status = "VERIFIED"
    elif context_score >= 35:
        # 문맥은 도움을 줬지만 자동확정 기준까지는 부족하다.
        if output.get("parse_status") not in {"BPJPH_MAINTENANCE_ONLY", "NON_CERTIFICATE_DOC"}:
            output["parse_status"] = "LOW_CONFIDENCE"
            output["confidence"] = "MEDIUM"
        context_status = "ASSISTED"
    else:
        context_status = "UNVERIFIED"

    output["context_status"] = context_status
    output["context_score"] = context_score
    output["context_reliability"] = reliability
    output["context_selection_reason"] = selection_reason
    output["context_checks"] = checks
    output["context_warnings"] = list(dict.fromkeys(warnings))
    output["context_conflicts"] = list(dict.fromkeys(conflicts))
    output["auto_confirm_eligible"] = auto_confirm_eligible
    output["linked_request_id"] = _context_clean(context.get("request_id"))
    output["linked_item_index"] = context.get("item_index")

    return output


def parse_certificate_rule_with_context(
    raw_text: str,
    filename: str = "",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """기존 규칙 판독 후 메일/PMF 문맥으로 안전하게 교차검증한다."""
    context = dict(context or {})
    expected_name = _context_clean(context.get("english_name") or context.get("material_name"))
    base = parse_certificate_rule(
        raw_text=raw_text,
        filename=filename,
        expected_name=expected_name,
        expected_org="",  # expected_org를 OCR 본문에 섞지 않는다.
    )
    return reconcile_certificate_rule_with_context(base, raw_text, context)

def guess_certificate_fields(raw_text: str, filename: str = "") -> dict[str, Any]:
    parsed = parse_certificate_rule(raw_text=raw_text, filename=filename)
    return {
        "org_candidates": [parsed.get("cert_org")] if parsed.get("cert_org") and parsed.get("cert_org") != "UNKNOWN" else [],
        "has_text": parsed.get("has_text", bool((raw_text or "").strip())),
        "text_length": parsed.get("text_length", len(raw_text or "")),
        "certificate_rule": parsed,
    }
