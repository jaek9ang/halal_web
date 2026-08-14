"""문자열·파일명·날짜 정규화와 첨부파일 판정 규칙."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import re


REQUEST_ID_PATTERN = re.compile(
    r"HALAL-REQ-\d{8}-[A-Z0-9]+",
    re.IGNORECASE,
)


HALAL_INBOUND_KEYWORDS = [
    "할랄",
    "halal",
    "certificate",
    "certification",
    "certi",
    "valid",
    "validity",
    "expiry",
    "expired",
    "expiration",
    "bpjph",
    "mui",
    "kmf",
    "jakim",
    "cicot",
    "ifanca",
    "hqc",
    "lhln",
]


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def quote_imap_mailbox(mailbox: str) -> str:
    """
    IMAP SELECT용 메일함 이름 quote 처리.
    공백/한글/modified UTF-7 폴더명을 안전하게 선택하기 위함.
    """
    text = str(mailbox or "").strip()

    if not text:
        text = "Inbox"

    if text.startswith('"') and text.endswith('"'):
        return text

    text = text.replace("\\", "\\\\").replace('"', '\\"')

    return f'"{text}"'


def safe_filename(value: str, default: str = "file") -> str:
    text = str(value or "").strip()

    if not text:
        text = default

    text = re.sub(r'[\\/:*?"<>|]+', "_", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text[:180] if len(text) > 180 else text


def decode_mime_text(value: Any) -> str:
    if not value:
        return ""

    decoded_parts = []

    for part, enc in decode_header(value):
        if isinstance(part, bytes):
            try:
                decoded_parts.append(part.decode(enc or "utf-8", errors="replace"))
            except Exception:
                decoded_parts.append(part.decode("utf-8", errors="replace"))
        else:
            decoded_parts.append(str(part))

    return "".join(decoded_parts).strip()


def parse_received_at(msg) -> str:
    raw_date = msg.get("Date", "")

    try:
        dt = parsedate_to_datetime(raw_date)

        if dt.tzinfo:
            dt = dt.astimezone().replace(tzinfo=None)

        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def find_request_id(*texts: str) -> str:
    for text in texts:
        if not text:
            continue

        m = REQUEST_ID_PATTERN.search(str(text))

        if m:
            return m.group(0).upper()

    return ""


def normalize_candidate_text(value: str) -> str:
    """
    파일명/메일본문/OCR 원문에서 날짜 후보 추출 전에 텍스트를 정리한다.
    """
    text = str(value or "")
    text = text.replace("&nbsp;", " ")
    text = text.replace("\r", "\n")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def to_iso_date(year: str, month: str, day: str) -> str:
    try:
        y = int(year)
        m = int(month)
        d = int(day)

        if y < 2000 or y > 2100:
            return ""

        if m < 1 or m > 12:
            return ""

        if d < 1 or d > 31:
            return ""

        return f"{y:04d}-{m:02d}-{d:02d}"
    except Exception:
        return ""


def normalize_mail_subject(text: str) -> str:
    """
    RE/FW 접두어와 불필요 공백 제거.
    보낸 제목과 받은 제목 유사 비교용.
    """
    value = str(text or "").strip().lower()

    value = re.sub(r"^\s*(re|fw|fwd)\s*:\s*", "", value, flags=re.I)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def strip_html_text(text: str) -> str:
    value = str(text or "")

    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"</p>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def extract_simple_terms(text: str, max_terms: int = 80) -> list[str]:
    """
    발송 로그 본문/제목에서 비교에 쓸 원료명/업체명 후보를 넓게 추출.
    너무 짧은 단어는 제외.
    """
    value = strip_html_text(text)

    chunks = re.split(r"[\n\r,/|;:()\[\]<>]+", value)

    terms = []

    for chunk in chunks:
        t = str(chunk or "").strip()

        if len(t) < 3:
            continue

        if len(t) > 80:
            continue

        low = t.lower()

        stop_words = [
            "안녕하십니까",
            "확인 요청",
            "부탁드립니다",
            "감사합니다",
            "sewoo",
            "halal",
            "certificate",
            "request",
            "valid",
            "until",
        ]

        if any(x in low for x in stop_words):
            continue

        terms.append(t)

    # 중복 제거
    result = []
    seen = set()

    for t in terms:
        key = t.lower()

        if key in seen:
            continue

        seen.add(key)
        result.append(t)

        if len(result) >= max_terms:
            break

    return result


def is_ocr_candidate_attachment(
    filename: str = "",
    ext: str = "",
    file_size: int | None = None,
) -> bool:
    """
    OCR 자동 대상 여부.
    exact 메일이라도 서명 이미지, 로고, 배너류는 제외한다.
    """
    name = str(filename or "").strip().lower()
    suffix = str(ext or "").strip().lower()

    if not suffix and "." in name:
        suffix = "." + name.rsplit(".", 1)[-1].lower()

    allowed_exts = {
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".tif",
        ".tiff",
        ".bmp",
    }

    if suffix not in allowed_exts:
        return False

    block_keywords = [
        "image001",
        "image002",
        "image003",
        "logo",
        "signature",
        "sign",
        "banner",
        "footer",
        "header",
        "facebook",
        "instagram",
        "naver",
        "kakao",
    ]

    if any(x in name for x in block_keywords):
        return False

    try:
        size = int(file_size or 0)
        # 너무 작은 이미지는 서명/아이콘 가능성이 높음
        if suffix in {".jpg", ".jpeg", ".png", ".bmp"} and 0 < size < 20_000:
            return False
    except Exception:
        pass

    return True


def is_exact_pdf_ocr_candidate(filename: str = "", ext: str = "") -> bool:
    """
    EXACT 매칭 메일의 PDF 첨부는 자동 OCR 대상.
    단, PDF만 자동 대상. 이미지/엑셀/워드는 수동 선택.
    """
    name = str(filename or "").strip().lower()
    suffix = str(ext or "").strip().lower()

    if not suffix and "." in name:
        suffix = "." + name.rsplit(".", 1)[-1].lower()

    return suffix == ".pdf"
