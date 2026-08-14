
from __future__ import annotations

import re
from typing import Any

UNKNOWN = "UNKNOWN"
PROFILE_VERSION = "certificate_rule_profile_v1"
EXPIRY_OPTIONAL_ORGS = {"BPJPH"}

ORG_COUNTRIES = {
    "BPJPH": "INDONESIA",
    "MUI": "INDONESIA",
    "IFANCA": "USA",
    "HFFIA": "NETHERLANDS",
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

HARD_QUALITY_FLAGS = {
    "FILENAME_ORG_CONFLICT",
    "CERT_NO_MISSING",
    "CERT_NO_OCR_UNCERTAIN",
    "EXPIRY_MISSING",
    "EXPIRY_LABEL_UNREADABLE",
    "MANUFACTURER_UNRELIABLE",
}

# 본문 기관 판정은 파일명을 섞지 않는다.
# 기관명이 다른 기관의 승인목록/설명문에 등장하는 경우를 막기 위해
# 발급기관 고유 문구에는 높은 점수를, 약어·번호 형식에는 낮은 점수를 준다.
ORG_MARKERS: dict[str, list[tuple[str, int]]] = {
    "BPJPH": [
        (r"\bBADAN\s+PENYELENGGARA\s+JAMINAN\s+PRODUK\s+HALAL\b", 150),
        (r"\bHEAD\s+OF\s+HALAL\s+PRODUCT\s+ASSURANCE\s+BODY\b", 150),
        (r"\bBPJPH\b", 25),
        (r"\bID00\d{8,}\b", 20),
    ],
    "MUI": [
        (r"\bMAJELIS\s+ULAMA\s+INDONESIA\b", 100),
        (r"\bINDONESIA(?:N)?\s+COUNCIL\s+OF\s+ULAMA\b", 90),
        (r"\bLPPOM(?:\s*[-/]?\s*MUI)?\b", 25),
        (r"\bLAMPIRAN\s+KETETAPAN\s+HALAL\b", 60),
    ],
    "IFANCA": [
        (r"\bISLAMIC\s+FOOD\s+AND\s+NUTRITION\s+COUNCIL\s+OF\s+AMERICA\b", 120),
        (r"\bIFANCA\b", 80),
    ],
    "HQC": [
        (r"\bHALAL\s+QUALITY\s+CONTROL\b", 120),
        (r"\bCONTROL\s+OFFICE\s+OF\s+HALAL\s+SLAUGHTERING\b", 100),
        (r"\b(?:DE|NL)\d{10,}\b", 20),
    ],
    "LLS-ISA": [
        (r"\bLLS[\s-]*ISA\b", 140),
    ],
    "ISA": [
        (r"\bISLAMIC\s+SERVICES\s+OF\s+AMERICA\b", 120),
        (r"\bISA\s+HALAL\b", 90),
        (r"\bCERTIFICATE\s+NO\.?\s*[:：]?\s*\d{4}-\d{2}-\d{4,}\b", 15),
    ],
    "HCE": [
        (r"\bHALAL\s+CERTIFICATION\s+EUROPE\b", 120),
        (r"\bHALALCE\b", 100),
    ],
    "HFCE": [
        (r"\bHALAL\s+FOOD\s+COUNCIL\s+OF\s+EUROPE\b", 120),
        (r"\bWWW\.?HFCE\.(?:EU|CU)\b", 100),
        (r"\bHFCE\b", 50),
    ],
    "HFQ": [
        (r"\bHALAL\s+FOOD\s*(?:&|AND)\s*QUALITY\b", 120),
        (r"\bHFQ\s*-\s*\d", 60),
    ],
    "HALAL CONTROL": [
        (r"\bHALAL\s+CONTROL\s+CERTIFICATION\s+DECISION\s+COMMITTEE\b", 160),
        (r"\bHALAL\s+CONTROL\s+IS\s+A\s+GLOBALLY\s+RECOGNIZED\b", 160),
        (r"\bHALAL\s+CONTROL(?:\s+GMBH)?\b", 100),
        (r"\bC-\d{2}-\d", 20),
    ],
    "HCA": [
        (r"\bHALAL\s+CERTIFICATION\s+AGENCY\b", 140),
        (r"\bHALAL\.VN\b", 120),
        (r"\bCERT\s*[I1L]D\s*[:：]?\s*HCA\b", 70),
        (r"\bHCA\s+\d{2,5}\s*/", 40),
    ],
    "CICOT": [
        (r"\bTHE\s+CENTRAL\s+ISLAMIC\s+COUNCIL\s+OF\s+THAILAND\b", 140),
        (r"\bSHEIKHUL\s+ISLAM\s+OF\s+THAILAND\b", 120),
        (r"\bCICOT\.?\s*HL\b", 70),
        (r"\bCICOT\b", 40),
    ],
    "JAKIM": [
        (r"\bJABATAN\s+KEMAJUAN\s+ISLAM\s+MALAYSIA\b", 140),
        (r"\bDEPARTMENT\s+OF\s+ISLAMIC\s+DEVELOPMENT\s+(?:OF\s+)?MALAYSIA\b", 120),
        (r"\bJAKIM(?:\.|/)\d", 60),
        (r"\bJAKIM\b", 35),
    ],
    "MUIS": [
        (r"\bMAJLIS\s+UGAMA\s+ISLAM\s+SINGAPURA\b", 140),
        (r"\bISLAMIC\s+RELIGIOUS\s+COUNCIL\s+OF\s+SINGAPORE\b", 140),
        (r"\bPRN[A-Z0-9]{8,20}\b", 60),
        (r"\bMUIS\b", 30),
    ],
    "JMA": [
        (r"\bJAPAN\s+MUSLIM\s+ASSOCIATION\b", 140),
        (r"\bTAKUSHOKU\s+UNIVERSITY\b", 100),
        (r"\bJMA\b", 30),
    ],
    "KMF": [
        (r"\bKOREA\s+MUSLIM\s+FEDERATION\b", 140),
        (r"한국\s*(?:이슬람|무슬림)", 120),
        (r"\bKMFHC\d", 70),
    ],
    "ARA": [
        (r"\bARA\s+HALAL\s+CERTIFICATION(?:\s+SERVICES\s+CENTRE)?\b", 140),
        (r"\bARA-\d{5,}\b", 60),
    ],
    "JUHF": [
        (r"\bJUHF\s+CERTIFICATION\b", 140),
        (r"\bHALALHIND\b", 120),
        (r"\bJUHF-\d", 60),
    ],
    "TQHCC": [
        (r"\bTOTAL\s+QUALITY\s+HALAL\s+CORRECT\s+CERTIFICATION\b", 150),
        (r"\bHALAL\s+CORRECT\s+CERTIFICATION\b", 130),
        (r"\bHALALCORRECT\b", 110),
        (r"\bHCC[A-Z0-9-]{6,}\b", 50),
        (r"\bTQHCC\b", 40),
    ],
    "HFFIA": [
        (r"\bHALAL\s+FEED\s+.{0,8}FOOD\s+INSPECTION\s+(?:AUTHORITY|GUTHORITY)\b", 150),
        (r"\bHALAL\s+VOEDING\s+EN\s+VOEDSEL\b", 140),
        (r"\b(?:CERTIFICATION@)?HALAL\.NL\b", 120),
        (r"\bHFFIA\b", 50),
    ],
}

FILENAME_MARKERS: list[tuple[str, str]] = [
    ("HALAL CONTROL", r"HALAL[\s_-]*CONTROL"),
    ("LLS-ISA", r"LLS[\s_-]*ISA"),
    ("BPJPH", r"(?<![A-Z0-9])BPJPH(?=[^A-Z0-9]|$)"),
    ("IFANCA", r"(?<![A-Z0-9])IFANCA(?=[^A-Z0-9]|$)"),
    ("TQHCC", r"(?<![A-Z0-9])TQHCC(?=[^A-Z0-9]|$)"),
    ("HFFIA", r"(?<![A-Z0-9])HFFIA(?=[^A-Z0-9]|$)"),
    ("HFCE", r"(?<![A-Z0-9])HFCE(?=[^A-Z0-9]|$)"),
    ("CICOT", r"(?<![A-Z0-9])CICOT(?=[^A-Z0-9]|$)"),
    ("JAKIM", r"(?<![A-Z0-9])JAKIM(?=[^A-Z0-9]|$)"),
    ("MUIS", r"(?<![A-Z0-9])MUIS(?=[^A-Z0-9]|$)"),
    ("JUHF", r"(?<![A-Z0-9])JUHF(?=[^A-Z0-9]|$)"),
    ("HQC", r"(?<![A-Z0-9])HQC(?=[^A-Z0-9]|$)"),
    ("HCE", r"(?<![A-Z0-9])HCE(?=[^A-Z0-9]|$)"),
    ("HFQ", r"(?<![A-Z0-9])HFQ(?=[^A-Z0-9]|$)"),
    ("HCA", r"(?<![A-Z0-9])HCA(?=[^A-Z0-9]|$)"),
    ("KMF", r"(?<![A-Z0-9])KMF(?=[^A-Z0-9]|$)"),
    ("JMA", r"(?<![A-Z0-9])JMA(?=[^A-Z0-9]|$)"),
    ("MUI", r"(?<![A-Z0-9])MUI(?=[^A-Z0-9]|$)"),
    ("ISA", r"(?<!LLS[-_\s])(?<![A-Z0-9])ISA(?=[^A-Z0-9]|$)"),
    ("ARA", r"(?<![A-Z0-9])ARA(?=[^A-Z0-9]|$)"),
]

COMPANY_SUFFIX_RE = re.compile(
    r"\b(?:"
    r"PTE\.?\s*LTD\.?|SDN\.?\s*BHD\.?|CO\.?\s*,?\s*LTD\.?|"
    r"LTD\.?|LIMITED|LLC|INC\.?|CORPORATION|CORP\.?|"
    r"GMBH(?:\s*(?:&|\+)\s*CO\.?\s*KG)?|B\.?V\.?|S\.?A\.?|SAS|"
    r"A/?S|AG|PLC|COMPANY"
    r")\b",
    re.I,
)

MANUFACTURER_LABELS: dict[str, list[str]] = {
    "IFANCA": [r"COMPANY\s+NAME\s*&\s*ADDRESS", r"PLANT\s+NAME\s*&\s*ADDRESS"],
    "MUI": [r"NAME\s+OF\s+COMPANY", r"FACILITY\s+NAME"],
    "BPJPH": [r"NAMA\s+PELAKU\s+USAHA", r"NAME\s+OF\s+COMPANY", r"FACTORY'?S\s+ADDRESS"],
    "HQC": [r"AWARDED\s+TO", r"MANUFACTURING\s+SITE\s+ADDRESS"],
    "ISA": [r"COMPANY\s+NAME", r"COMPANY"],
    "LLS-ISA": [r"COMPANY\s+NAME", r"COMPANY"],
    "HCE": [r"COMPANY\s+NAME", r"MANUFACTURE\s+SITE"],
    "HFCE": [r"COMPANY\s+NAME\s*&\s*ADDRESS"],
    "HFQ": [r"CERTIFY\s+THAT\s+THE\s+COMPANY", r"CERTIFICA\s+QUE\s+LA\s+EMPRESA"],
    "HALAL CONTROL": [r"MANUFACTURED\s+BY"],
    "HCA": [r"PRODUCTS?\s+OF\s+THE"],
    "CICOT": [r"CERTIFIES\s+(?:THAT|THAI)", r"ENTREPRENEUR", r"MANUFACTURER"],
    "JAKIM": [r"MANUFACTURED\s*/\s*DISTRIBUTED\s*/\s*MANAGED\s+BY", r"MANUFACTURED"],
    "MUIS": [r"NAME\s+(?:AND|&)\s+ADDRESS\s+OF\s+(?:COMPANY|ESTABLISHMENT)", r"MANUFACTURED\s+BY"],
    "JMA": [r"NAME\s+AND\s+ADDRESS\s+OF\s+COMPANY"],
    "KMF": [r"MANUFACTURER", r"제조원", r"제조사", r"업체명", r"회사명"],
    "TQHCC": [r"MANUFACTURER"],
    "HFFIA": [r"PROCESSING\s+PLANT", r"COMPANY", r"MANUFACTURER"],
    "JUHF": [r"COMPANY\s+NAME"],
    "ARA": [r"COMPANY\s+NAME"],
}

EXPIRY_ANCHORS: dict[str, list[str]] = {
    "MUIS": [r"DATE\s+OF\s+EXPIRY", r"EXPIRY\s+DATE"],
    "MUI": [r"VALID\s+UNTIL"],
    "CICOT": [r"EXPIRED\s+DATE", r"EFFECTIVE\s+FROM[\s\S]{0,180}\bTILL\b"],
    "JAKIM": [r"SAH\s+SEHINGGA", r"VALID\s+UNTIL"],
    "HFFIA": [r"EXPIRY\s+DATE", r"VALIDITY[\s\S]{0,100}EXPIRY"],
    "HQC": [r"EXPIRY\s+DATE", r"DATE\s+OF\s+EXPIRY"],
    "HCE": [r"EXPIRY"],
    "HFCE": [r"CERTIFICATE\s+IS\s+VALID\s+UNTIL"],
    "HFQ": [r"VALID\s+UNTIL", r"V[ÁA]LIDO\s+HASTA"],
    "HALAL CONTROL": [r"VALID\s+UNTIL"],
    "HCA": [r"EXPIRED\s+DATE", r"EXPIRY\s+DATE", r"VALID\s+UNTIL"],
    "ISA": [r"VALID\s+(?:UNTIL|THROUGH)"],
    "LLS-ISA": [r"VALID\s+(?:UNTIL|THROUGH)"],
    "IFANCA": [r"CERTIFICATE\s+IS\s+VALID\s+(?:UNTIL|THROUGH)"],
    "JMA": [r"VALID\s+UNTIL"],
    "KMF": [r"유효기간", r"인증기간", r"VALID\s+UNTIL"],
    "TQHCC": [r"CERTIFICATE\s+VALID\s+UNTIL", r"VALID\s+UNTIL"],
    "ARA": [r"EXPIRED\s+DATE", r"EXPIRY\s+DATE"],
    "JUHF": [r"DATE\s+OF\s+EXPIRY", r"EXPIRY\s+DATE"],
}


def _clean(value: Any) -> str:
    text = str(value or "").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _upper(value: Any) -> str:
    return _clean(value).upper()


def detect_body_org(raw_text: str) -> tuple[str, dict[str, int]]:
    text = _upper(raw_text)
    scores: dict[str, int] = {}

    for org, markers in ORG_MARKERS.items():
        score = 0
        for pattern, weight in markers:
            if re.search(pattern, text, re.I | re.S):
                score += int(weight)
        if score:
            scores[org] = score

    if not scores:
        return UNKNOWN, {}

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    best_org, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0

    if best_score < 40:
        return UNKNOWN, scores

    if second_score and best_score - second_score < 25:
        return UNKNOWN, scores

    return best_org, scores


def detect_filename_org(filename: str) -> str:
    text = _upper(filename)
    found: list[tuple[int, int, str]] = []

    for org, pattern in FILENAME_MARKERS:
        match = re.search(pattern, text, re.I)
        if match:
            found.append((match.start(), -(match.end() - match.start()), org))

    if not found:
        return UNKNOWN

    found.sort()
    return found[0][2]


def _org_compatible(left: str, right: str) -> bool:
    pair = {_upper(left), _upper(right)}
    return len(pair) <= 1 or pair == {"ISA", "LLS-ISA"}


def _manufacturer_suspicious(value: str) -> bool:
    text = _clean(value)

    if not text or len(text) < 4:
        return True

    if re.search(
        r"NAME\s+(?:AND|&)\s+ADDRESS\s+OF\s+(?:COMPANY|ESTABLISHMENT)",
        text,
        re.I,
    ):
        return True

    if re.search(
        r"(?:^|[(/\s])(?:COMPANY|MANUFACTURER|MANUFACTURED\s+BY|"
        r"NAME\s+(?:AND|&)\s+ADDRESS\s+OF\s+(?:COMPANY|ESTABLISHMENT)|"
        r"DISTRIBUTED|MANAGED\s+BY)(?:$|[)/\s])",
        text,
        re.I,
    ) and not COMPANY_SUFFIX_RE.search(text):
        return True

    if re.search(
        r"(?:LISTED\s+ON\s+THE\s+ATTACHED|CERTIFIED\s+HALAL|"
        r"VALID\s+(?:UNTIL|THROUGH)|DATE\s+OF\s+(?:ISSUE|EXPIRY)|"
        r"HALAL\s+CERTIFICATE|CERTIFICATE\s+NO|PAGE\s+\d+|"
        r"\bP\.?O\.?\s+BOX\b)",
        text,
        re.I,
    ):
        return True

    if re.search(
        r"^\d{1,6}\b.*\b(?:LOOP|ROAD|RD\.?|STREET|ST\.?|"
        r"AVENUE|AVE\.?|DRIVE|DR\.?|LANE|BOULEVARD)\b",
        text,
        re.I,
    ):
        return True

    if text[:1].islower() and len(text) < 16:
        return True

    letters = len(re.findall(r"[A-Za-z가-힣]", text))
    return letters / max(len(text), 1) < 0.45

def _cleanup_existing_manufacturer(value: str) -> str:
    text = _clean(value).strip(" ,.;:-_")

    text = re.sub(
        r"^(?:FACTORY\s*\(NAME\)|COMPANY\s+NAME(?:\s*&\s*ADDRESS)?|"
        r"NAME\s+(?:AND|&)\s+ADDRESS\s+OF\s+(?:COMPANY|ESTABLISHMENT)|"
        r"MANUFACTURER|MANUFACTURED\s+BY)\s*[:：-]\s*",
        "",
        text,
        flags=re.I,
    )

    if COMPANY_SUFFIX_RE.search(text):
        text = re.sub(r"^\d{1,4}[.)]?\s+(?=[A-Z])", "", text)

    text = re.sub(
        r"\s*,?\s*(?:P\.?O\.?\s+BOX|POST\s+BOX)\b.*$",
        "",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"\s+\d{1,6}\s+(?:[A-Z0-9'.#-]+\s+){0,6}"
        r"(?:STREET|ST\.?|AVENUE|AVE\.?|ROAD|RD\.?|DRIVE|DR\.?|"
        r"LANE|LN\.?|BOULEVARD|BLVD\.?|WAY|COURT|CT\.?|LOOP|"
        r"PARKWAY|PKWY\.?)\b.*$",
        "",
        text,
        flags=re.I,
    )

    # TQHCC / HFFIA 등에서 회사명 뒤에 붙은 아랍어·OCR 문장 제거.
    text = re.split(r"[\u0600-\u06FF]", text, maxsplit=1)[0]
    text = re.split(r"\s+(?:IGUAL|SADA|RALAALL|POU)[A-Z! ]*$", text, maxsplit=1, flags=re.I)[0]

    # 한 글자 OCR 찌꺼기: 's J.Rettenmaier ...'
    if COMPANY_SUFFIX_RE.search(text):
        text = re.sub(r"^[a-z]\s+(?=[A-Z])", "", text)

    # 회사 법인형태 뒤에 주소·국가·OCR 문장이 이어진 경우 회사명까지만 유지한다.
    suffix_matches = list(COMPANY_SUFFIX_RE.finditer(text))
    if suffix_matches:
        end = suffix_matches[-1].end()
        while end < len(text) and text[end] in ".)":
            end += 1
        text = text[:end]

    return _clean(text).strip(" ,;:-_")

def _company_candidate_from_line(line: str) -> str:
    text = _clean(line)

    text = re.sub(
        r"^(?:THIS\s+IS\s+TO\s+CERTIFY\s+THAT|"
        r"HALAL\s+PRODUCTION\s+CAN\s+ONLY\s+BE\s+REQUESTED\s+FROM|"
        r"CERTIFIES\s+(?:THAT|THAI)|PRODUCTS?\s+OF\s+THE|"
        r"FACTORY\s*\(NAME\)|COMPANY\s+NAME(?:\s*&\s*ADDRESS)?|"
        r"NAME\s+(?:AND|&)\s+ADDRESS\s+OF\s+(?:COMPANY|ESTABLISHMENT)|"
        r"MANUFACTURER|MANUFACTURED\s+BY)\s*[:：-]?\s*",
        "",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"^[/\s-]*(?:DISTRIBUTED|MANAGED)\s+BY\s*[:：-]?\s*",
        "",
        text,
        flags=re.I,
    )

    text = _cleanup_existing_manufacturer(text)

    return _clean(text).strip(" ,.;:-_|“”'\"")

def repair_manufacturer(
    org: str,
    raw_text: str,
    current: str,
) -> tuple[str, str]:
    current_clean = _cleanup_existing_manufacturer(current)

    if current_clean and not _manufacturer_suspicious(current_clean):
        return current_clean, (
            "CLEANED"
            if current_clean != _clean(current)
            else "BASE"
        )

    lines = [
        _clean(line)
        for line in str(raw_text or "").splitlines()
        if _clean(line)
    ]

    labels = MANUFACTURER_LABELS.get(org, [])
    candidates: list[tuple[int, str]] = []

    for index, line in enumerate(lines):
        for label_pattern in labels:
            match = re.search(label_pattern, line, re.I)

            if not match:
                continue

            inline = line[match.end():].strip(" :：-")
            if inline:
                candidates.append((30, inline))

            # MUIS는 회사명이 라벨 위에 있는 양식도 많다.
            if org == "MUIS":
                for offset in range(1, 5):
                    if index - offset >= 0:
                        candidates.append((28 - offset, lines[index - offset]))

            for offset in range(1, 6):
                if index + offset < len(lines):
                    candidates.append((28 - offset, lines[index + offset]))

    # 기관별 라벨 OCR이 깨진 경우를 위한 제한적 fallback.
    for line in lines:
        if COMPANY_SUFFIX_RE.search(line):
            candidates.append((12, line))

    scored: list[tuple[int, str]] = []

    for base_score, raw_candidate in candidates:
        candidate = _company_candidate_from_line(raw_candidate)

        if not candidate or len(candidate) < 4:
            continue

        if re.search(
            r"\b(?:CERTIFICATE|VALID|ISSUED|HALAL\s+STANDARD|"
            r"REGISTRATION|PRODUCT\s+NAME|PAGE|CONFIDENTIAL|PROPRIETARY)\b|"
            r"NAME\s+(?:AND|&)\s+ADDRESS\s+OF\s+(?:COMPANY|ESTABLISHMENT)|©",
            candidate,
            re.I,
        ):
            continue

        if _upper(candidate) in {"THE COMPANY", "COMPANY", "THE MANUFACTURER"}:
            continue

        if org in {"ISA", "LLS-ISA"} and re.search(
            r"\b(?:ISLAMIC\s+SERVICES\s+OF\s+AMERICA|ISA\s+INC)\b",
            candidate,
            re.I,
        ):
            continue

        has_company_suffix = bool(COMPANY_SUFFIX_RE.search(candidate))

        if org == "MUIS" and not has_company_suffix:
            continue

        score = int(base_score)

        if has_company_suffix:
            score += 18

        if 5 <= len(candidate) <= 100:
            score += 5

        if candidate[:1].isdigit():
            score -= 20

        if len(candidate.split()) > 14:
            score -= 12

        scored.append((score, candidate))

    if not scored:
        return ("", "UNRESOLVED") if _manufacturer_suspicious(current_clean) else (current_clean, "BASE")

    scored.sort(key=lambda item: (item[0], -len(item[1])), reverse=True)
    best_score, best = scored[0]

    if best_score < 20:
        return ("", "UNRESOLVED") if _manufacturer_suspicious(current_clean) else (current_clean, "BASE")

    return best, "REPAIRED"


def repair_cert_no(
    org: str,
    raw_text: str,
    current: str,
    best_product_match: dict[str, Any] | None = None,
) -> tuple[str, str]:
    text = str(raw_text or "")
    value = _clean(current).strip(" .,:;_-")
    source = "BASE" if value else ""

    if org == "HFFIA":
        patterns = [
            r"REGISTRATION\s+NUMBER[\s\S]{0,220}?"
            r"\b([A-Z]{1,8}/\d{3,8}/H\d{4,6}/\d{2,5})\b",
            r"\bD\s*:\s*(\d{3}/H\d{4,6}/\d{3,5})\b",
            r"\b([A-Z]{1,8}/\d{3,8}/H\d{4,6}/\d{2,5})\b",
            r"\b(H\d{4,6}-\d{2}\s*\d{2,4})\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                value = re.sub(r"\s+", "", match.group(1))
                source = "HFFIA_REGISTRATION"
                break

    elif org == "JAKIM":
        match = re.search(
            r"\b(JAKIM(?:\.|/)[A-Z0-9()/. -]*?"
            r"\d{3}-\d{2}/\d{4}(?:\s+JLD\.?\s*\d+)?)\b",
            text,
            re.I,
        )
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" .,:;_-")
            source = "JAKIM_REFERENCE"

    elif org == "JMA":
        patterns = [
            r"(?:\bNO?|\b0)\.?\s*[:：]?\s*"
            r"(\d{2,5}\s*-\s*[A-Z]{2,12}\s*[/V]\s*\d{2,4})",
            r"\b(\d{2,5}\s*-\s*[A-Z]{2,12}\s*/\s*\d{2,4})\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                value = re.sub(r"\s+", "", match.group(1))
                value = re.sub(r"(?<=[A-Z])V(?=\d)", "/", value, flags=re.I)
                source = "JMA_OCR_TOLERANT"
                break

    elif org == "CICOT" and not value:
        full = re.search(
            r"(?:REGISTRATION\s+NO\.?\s*,?\s*)?CICOT\.?\s*HL\.?\s*"
            r"[:：]?\s*[^0-9]{0,4}(\d{2,4}/\d{4})\b",
            text,
            re.I,
        )
        if full:
            value = full.group(1)
            source = "CICOT_REGISTRATION"
        else:
            uncertain = re.search(
                r"CICOT\.?\s*HL\.?\s*[:：]?\s*[^0-9]{0,4}"
                r"(\d{2,4}/\d{3}[0-9_?])",
                text,
                re.I,
            )
            if uncertain:
                value = uncertain.group(1)
                source = "CICOT_OCR_UNCERTAIN"

    elif org == "HFCE" and not value:
        product = (best_product_match or {}).get("product") or {}
        row_value = _clean(product.get("cert_no"))
        if row_value:
            value = row_value
            source = "HFCE_PRODUCT_ROW"

    elif org == "MUIS" and not value:
        match = re.search(r"\b(PRN[A-Z0-9]{8,20})\b", text, re.I)
        if match:
            value = match.group(1).upper()
            source = "MUIS_PRN"

    return value, source

def finalize_certificate_rule_profile(
    base: dict[str, Any],
    raw_text: str,
    filename: str = "",
) -> dict[str, Any]:
    output = dict(base or {})
    parse_status = _upper(output.get("parse_status"))

    if parse_status in {
        "TESSERACT_ERROR",
        "NON_CERTIFICATE_DOC",
        "SCANNED_NEED_OCR",
    }:
        output.setdefault("quality_flags", [])
        output.setdefault("auto_confirm_eligible", False)
        return output

    body_org, body_scores = detect_body_org(raw_text)
    filename_org = detect_filename_org(filename)
    base_org = _upper(output.get("cert_org")) or UNKNOWN
    base_source_rule = output.get("source_rule") or ""

    if body_org != UNKNOWN:
        resolved_org = body_org
        org_source = "TEXT_STRONG"
    elif filename_org != UNKNOWN:
        resolved_org = filename_org
        org_source = "FILENAME_FALLBACK"
    else:
        resolved_org = base_org
        org_source = "BASE_RULE"

    if body_org == "ISA" and filename_org == "LLS-ISA":
        resolved_org = "LLS-ISA"
        org_source = "TEXT_FILENAME_ALIAS"

    org_conflict = bool(
        body_org != UNKNOWN
        and filename_org != UNKNOWN
        and not _org_compatible(body_org, filename_org)
    )

    output["body_org"] = body_org
    output["body_org_scores"] = body_scores
    output["filename_org"] = filename_org
    output["org_source"] = org_source
    output["filename_org_conflict"] = org_conflict
    output["cert_org"] = resolved_org
    output["base_source_rule"] = base_source_rule
    output["profile_version"] = PROFILE_VERSION

    if resolved_org in ORG_COUNTRIES:
        output["cert_country"] = ORG_COUNTRIES[resolved_org]

    manufacturing_country = _upper(output.get("manufacturing_country"))
    cert_country = _upper(output.get("cert_country"))
    if manufacturing_country and cert_country:
        output["country_match_status"] = (
            "일치" if manufacturing_country == cert_country else "불일치"
        )

    if resolved_org != base_org and not _org_compatible(resolved_org, base_org):
        output["source_rule"] = f"{resolved_org}_PROFILED_RULE"

    cert_no, cert_no_source = repair_cert_no(
        resolved_org,
        raw_text,
        output.get("cert_no") or "",
        output.get("best_product_match") or {},
    )

    output["cert_no"] = cert_no

    if cert_no:
        output["cert_no_candidates"] = list(
            dict.fromkeys(
                [cert_no]
                + list(output.get("cert_no_candidates") or [])
            )
        )[:20]

    manufacturer, manufacturer_source = repair_manufacturer(
        resolved_org,
        raw_text,
        output.get("manufacturer") or "",
    )

    output["manufacturer"] = manufacturer

    expiry_candidates = list(output.get("expiry_candidates") or [])
    expiry_source = ""

    if expiry_candidates and isinstance(expiry_candidates[0], dict):
        expiry_source = _upper(expiry_candidates[0].get("source"))

    flags: list[str] = []

    if org_conflict:
        flags.append("FILENAME_ORG_CONFLICT")

    if resolved_org != base_org and not _org_compatible(resolved_org, base_org):
        flags.append("ORG_CHANGED_FROM_BASE_RULE")

    if org_source == "FILENAME_FALLBACK":
        flags.append("FILENAME_DEPENDENT_ORG")

    if not cert_no and resolved_org not in EXPIRY_OPTIONAL_ORGS:
        flags.append("CERT_NO_MISSING")

    if cert_no_source.endswith("OCR_UNCERTAIN"):
        flags.append("CERT_NO_OCR_UNCERTAIN")

    if (
        resolved_org not in EXPIRY_OPTIONAL_ORGS
        and not output.get("expiry_date")
    ):
        flags.append("EXPIRY_MISSING")

    if _manufacturer_suspicious(manufacturer):
        flags.append("MANUFACTURER_UNRELIABLE")

    expiry_anchors = EXPIRY_ANCHORS.get(
        resolved_org,
        [r"VALID\s+UNTIL", r"EXPIRY\s+DATE"],
    )

    expiry_anchor_present = any(
        re.search(pattern, _upper(raw_text), re.I | re.S)
        for pattern in expiry_anchors
    )

    if expiry_source == "FILENAME":
        flags.append("EXPIRY_FROM_FILENAME")

        if (
            resolved_org not in EXPIRY_OPTIONAL_ORGS
            and expiry_anchor_present
        ):
            # 값은 화면 표시용으로 유지하되 자동 확정은 차단한다.
            flags.append("EXPIRY_LABEL_UNREADABLE")

    output["field_sources"] = {
        "org": org_source,
        "cert_no": cert_no_source or "BASE",
        "expiry_date": expiry_source or "BASE",
        "manufacturer": manufacturer_source,
    }

    output["quality_flags"] = list(dict.fromkeys(flags))

    blocking_flags = set(HARD_QUALITY_FLAGS)
    output["blocking_quality_flags"] = sorted(
        blocking_flags.intersection(flags)
    )

    if org_conflict:
        output["ok"] = False
        output["parse_status"] = "MANUAL_REVIEW"
        output["confidence"] = "LOW"
        output["auto_confirm_eligible"] = False

    elif blocking_flags.intersection(flags):
        if _upper(output.get("parse_status")) not in {
            "BPJPH_MAINTENANCE_ONLY",
            "NON_CERTIFICATE_DOC",
        }:
            output["parse_status"] = "LOW_CONFIDENCE"
            output["confidence"] = "LOW"

        output["auto_confirm_eligible"] = False

    elif org_source == "FILENAME_FALLBACK":
        output["parse_status"] = "LOW_CONFIDENCE"
        output["confidence"] = "MEDIUM"
        output["auto_confirm_eligible"] = False

    return output



# 이전 실험 코드와의 호환용 별칭.
finalize_certificate_rule_v3 = finalize_certificate_rule_profile

def get_blocking_quality_flags(result: dict[str, Any]) -> list[str]:
    flags = set(result.get("quality_flags") or [])
    return sorted(flags.intersection(HARD_QUALITY_FLAGS))
