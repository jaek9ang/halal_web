"""제조사명 추출. 주소·행정문구를 걸러내는 규칙이 대부분이다."""

from __future__ import annotations

import re

from app.services.rules.text import (
    clean_ocr_text,
    lines_of,
    upper_text,
)
from app.services.rules.organizations import (
    extract_country_from_parentheses,
    extract_country_from_text,
)


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


def clean_company_value(value: str) -> str:
    text = clean_ocr_text(value)
    text = re.sub(r"^[：:ㆍ\-\s]+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .:-")
    return text


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
