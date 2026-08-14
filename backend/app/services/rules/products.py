"""제품명 목록 추출과 PMF 제품명 매칭."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from app.services.rules.text import (
    clean_ocr_text,
    lines_of,
    similarity,
    upper_text,
)
from app.services.rules.companies import (
    is_admin_or_address_line,
    is_company_like,
)


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
