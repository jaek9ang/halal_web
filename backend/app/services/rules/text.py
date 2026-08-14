"""OCR 원문 정규화와 문자열 비교 유틸."""

from __future__ import annotations

import re


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
