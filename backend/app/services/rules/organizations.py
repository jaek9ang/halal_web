"""발급기관 판별과 인증국가 보정. 기관 별칭 목록이 여기 있다."""

from __future__ import annotations

from pathlib import Path
import re

from app.services.rules.text import (
    clean_ocr_text,
    upper_text,
)


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
