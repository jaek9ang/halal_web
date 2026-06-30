from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from app.services.storage_path_service import resolve_raw_material_root

DEFAULT_HALAL_RAW_MATERIAL_ROOT = (
    r"\\홍진우\공유\1) 인증심사관련\4. MUI HALAL"
    r"\2) HALAL 하부원료 서류\1)원재료"
)
WINDOWS_INVALID_CHARS_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
MULTI_SPACE_PATTERN = re.compile(r"\s+")
LEGAL_SUFFIXES = {
    "CO", "COMPANY", "CORP", "CORPORATION", "INC", "LTD", "LIMITED",
    "LLC", "PLC", "PTE", "PT", "GMBH", "SA", "BV",
}

@dataclass(frozen=True)
class FilingNameInput:
    material_no: str
    material_name_en: str
    manufacturer: str
    supplier: str
    cert_org: str
    expiry_date: str = ""
    source_extension: str = ".pdf"

@dataclass(frozen=True)
class FilingNameResult:
    material_no: str
    material_name_en: str
    manufacturer_abbr: str
    supplier_initial: str
    cert_org: str
    expiry_date: str
    folder_name: str
    filename: str
    extension: str

    def to_dict(self) -> dict:
        return asdict(self)

def get_halal_raw_material_root() -> Path:
    return resolve_raw_material_root()

def normalize_text(value: object) -> str:
    return MULTI_SPACE_PATTERN.sub(" ", str(value or "").strip())

def sanitize_windows_component(value: object, replacement: str = "_") -> str:
    text = WINDOWS_INVALID_CHARS_PATTERN.sub(replacement, normalize_text(value))
    return text.rstrip(" .") or "_"

def normalize_extension(value: object) -> str:
    extension = normalize_text(value).lower() or ".pdf"
    return extension if extension.startswith(".") else f".{extension}"

def normalize_org(value: object) -> str:
    return sanitize_windows_component(value).upper().replace(" ", "_")

def normalize_expiry_date(value: object) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    match = re.search(r"\b(20\d{2})[-./](0?[1-9]|1[0-2])[-./](0?[1-9]|[12]\d|3[01])\b", text)
    if not match:
        raise ValueError(f"유효기간 형식을 확인하세요: {text}")
    year, month, day = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"

def supplier_initial(supplier: object) -> str:
    for char in normalize_text(supplier):
        if char.isalnum() or "가" <= char <= "힣":
            return char.upper() if char.isascii() else char
    raise ValueError("공급사명에서 첫 글자를 추출하지 못했습니다.")

def manufacturer_abbreviation(manufacturer: object) -> str:
    tokens = re.findall(r"[A-Z0-9]+", normalize_text(manufacturer).upper())
    for token in tokens:
        if token not in LEGAL_SUFFIXES and len(token) >= 2:
            return sanitize_windows_component(token)[:24]
    raise ValueError("제조사명에서 약어를 생성하지 못했습니다.")

def find_existing_material_folder(root: Path, material_no: object) -> Path | None:
    material = normalize_text(material_no)
    if not material or not root.exists():
        return None
    pattern = re.compile(rf"^{re.escape(material)}\.\s", re.IGNORECASE)
    matches = [p for p in root.iterdir() if p.is_dir() and pattern.search(p.name)]
    return matches[0] if len(matches) == 1 else None

def build_filing_names(data: FilingNameInput) -> FilingNameResult:
    material_no = sanitize_windows_component(data.material_no)
    material_name_en = sanitize_windows_component(data.material_name_en)
    manufacturer_abbr = manufacturer_abbreviation(data.manufacturer)
    supplier_char = supplier_initial(data.supplier)
    cert_org = normalize_org(data.cert_org)
    extension = normalize_extension(data.source_extension)

    if cert_org == "BPJPH":
        expiry_date = ""
        cert_suffix = "[BPJPH]"
    else:
        expiry_date = normalize_expiry_date(data.expiry_date)
        if not expiry_date:
            raise ValueError(f"{cert_org} 인증서는 유효기간이 필요합니다.")
        cert_suffix = f"[{cert_org}_{expiry_date}]"

    folder_name = sanitize_windows_component(
        f"{material_no}. {material_name_en}({manufacturer_abbr})_ⓗ{supplier_char}"
    )
    filename = sanitize_windows_component(
        f"{material_no}. {material_name_en}({manufacturer_abbr}){cert_suffix}{supplier_char}"
    ) + extension

    return FilingNameResult(
        material_no=material_no,
        material_name_en=material_name_en,
        manufacturer_abbr=manufacturer_abbr,
        supplier_initial=supplier_char,
        cert_org=cert_org,
        expiry_date=expiry_date,
        folder_name=folder_name,
        filename=filename,
        extension=extension,
    )

def build_target_path(data: FilingNameInput, root: Path | None = None, reuse_existing_folder: bool = True):
    root = root or get_halal_raw_material_root()
    names = build_filing_names(data)
    existing = find_existing_material_folder(root, names.material_no) if reuse_existing_folder else None
    folder = existing or (root / names.folder_name)
    return names, folder / names.filename, existing is not None
