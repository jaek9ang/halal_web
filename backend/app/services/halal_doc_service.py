import os
import re
from pathlib import Path
from typing import Any

from app.core.config import HALAL_DOC_ROOT
from app.services.pmf_service import read_pmf_bundle
from app.services.supplier_service import clean, get_full_row_data


CERT_EXTS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
}


def display_value(value: Any) -> str:
    text = clean(value)

    if not text:
        return ""

    norm = str(text).strip().lower()

    if norm in {"-", "nan", "none", "null"}:
        return ""

    return str(text).strip()


def normalize_token(value: Any) -> str:
    text = display_value(value).lower()

    if not text:
        return ""

    # 경로/파일명 매칭용. 공백, 특수문자 차이를 줄인다.
    text = text.replace("ⓗ", "")
    text = re.sub(r"[\s\-_./\\()\[\]{}:,;~`'\"|+&]+", "", text)
    return text


def is_valid_material_name(value: Any) -> bool:
    text = display_value(value)

    if not text:
        return False

    norm = text.lower().replace(" ", "")

    blocked = {
        "supplier",
        "nameofmaterial(korean)",
        "nameofmaterial(english)",
        "nameofmaterial",
        "halalby",
        "1차",
        "2차",
        "3차",
        "4차",
        "원료명",
        "영문명",
    }

    if norm in blocked:
        return False

    if "nameofmaterial" in norm:
        return False

    return True


def get_row_number(row) -> str:
    """
    PMF A열 번호.
    예: 1, 102_1, 102_2 등
    """
    if len(row) <= 0:
        return ""

    return display_value(row.iloc[0])


def build_material_levels(row) -> list[dict[str, Any]]:
    row_no = get_row_number(row)
    levels = []

    for depth in range(5):
        data = get_full_row_data(row, depth)

        if not data:
            continue

        material_name = display_value(data.get("n", ""))
        english_name = display_value(data.get("e", ""))
        maker = display_value(data.get("m", ""))
        maker_country = display_value(data.get("o", ""))
        org = display_value(data.get("h", ""))
        cert_no = display_value(data.get("i", ""))
        exp = display_value(data.get("v", ""))

        if not is_valid_material_name(material_name):
            continue

        levels.append({
            "depth": depth,
            "row_no": row_no,
            "material_name": material_name,
            "english_name": english_name,
            "maker": maker,
            "maker_country": maker_country,
            "org": org,
            "cert_no": cert_no,
            "exp": exp,
        })

    return levels


def parse_doc_name(name: str) -> dict[str, Any]:
    """
    예:
    102_2. TONSIL OPTIMUM 230LM(CLARIANT)_ⓗ롯.pdf
    102_2. TONSIL OPTIMUM 230LM(CLARIANT)[BPJPH_2026-09-23]롯.pdf
    """
    stem = Path(name).stem

    prefix = ""
    title_part = stem

    m = re.match(r"^([0-9]+(?:_[0-9]+)?)\.\s*(.+)$", stem)
    if m:
        prefix = m.group(1)
        title_part = m.group(2)

    bracket_org = ""
    bracket_date = ""

    m2 = re.search(r"\[([A-Za-z0-9]+)_([0-9]{4}-[0-9]{2}-[0-9]{2})\]", stem)
    if m2:
        bracket_org = m2.group(1)
        bracket_date = m2.group(2)

    maker = ""
    m3 = re.search(r"\(([^()]*)\)", title_part)
    if m3:
        maker = m3.group(1)

    return {
        "prefix": prefix,
        "title_part": title_part,
        "maker_hint": maker,
        "org_hint": bracket_org,
        "expiry_hint": bracket_date,
        "has_halal_marker": "ⓗ" in name,
    }


def safe_resolve_doc_path(path_text: str) -> Path:
    if not path_text:
        raise ValueError("파일 경로가 없습니다.")

    root = Path(HALAL_DOC_ROOT)
    path = Path(path_text)

    try:
        root_resolved = root.resolve()
        path_resolved = path.resolve()
        path_resolved.relative_to(root_resolved)
        return path_resolved
    except Exception:
        # UNC 경로에서 resolve/relative_to가 실패하는 경우 문자열 기준으로 2차 방어
        root_s = str(root).replace("/", "\\").rstrip("\\").lower()
        path_s = str(path).replace("/", "\\").rstrip("\\").lower()

        if path_s.startswith(root_s):
            return path

    raise ValueError(f"허용되지 않은 경로입니다: {path_text}")


def iter_halal_doc_paths(max_items: int = 12000):
    root = Path(HALAL_DOC_ROOT)

    if not root.exists():
        return

    count = 0

    for current, dirs, files in os.walk(root):
        current_path = Path(current)

        for dirname in dirs:
            count += 1
            if count > max_items:
                return

            yield current_path / dirname

        for filename in files:
            ext = Path(filename).suffix.lower()

            if ext not in CERT_EXTS:
                continue

            count += 1
            if count > max_items:
                return

            yield current_path / filename


def is_probably_cert_file(path: Path) -> bool:
    """
    매칭된 원료 폴더 안에서 인증서 파일 후보를 판단한다.
    전체 네트워크 폴더가 아니라 선택된 폴더 내부만 보므로 기준을 넓게 잡는다.
    """
    if not path.is_file():
        return False

    name = path.name.strip()

    if not name:
        return False

    # 임시파일 제외
    if name.startswith("~$") or name.startswith("."):
        return False

    ext = path.suffix.lower()

    # 일반 인증서 파일 확장자
    if ext in CERT_EXTS:
        return True

    # 확장자가 없거나 특이해도 파일명에 인증기관/유효기간 패턴이 있으면 포함
    cert_keywords = [
        "MUI",
        "BPJPH",
        "JAKIM",
        "CICOT",
        "IFANCA",
        "HQC",
        "HCA",
        "LHLN",
        "KMF",
        "ISA",
    ]

    upper_name = name.upper()

    if any(keyword in upper_name for keyword in cert_keywords):
        return True

    # [MUI_2026-10-11] 같은 패턴
    if re.search(r"\[[A-Z0-9]+[_\-\s]*[0-9]{4}-[0-9]{2}-[0-9]{2}\]", upper_name):
        return True

    return False

def list_child_cert_files(folder_path: Path, max_files: int = 50) -> list[dict[str, Any]]:
    """
    매칭된 폴더 바로 아래의 인증서 파일만 조회한다.
    하위 폴더까지 내려가지 않는다.
    """
    if not folder_path.is_dir():
        return []

    rows = []

    try:
        for child in folder_path.iterdir():
            if not child.is_file():
                continue

            if not is_probably_cert_file(child):
                continue

            meta = parse_doc_name(child.name)

            try:
                size_bytes = child.stat().st_size
            except Exception:
                size_bytes = 0

            rows.append({
                "name": child.name,
                "path": str(child),
                "folder": str(child.parent),
                "ext": child.suffix.lower(),
                "has_halal_marker": meta["has_halal_marker"],
                "org_hint": meta["org_hint"],
                "expiry_hint": meta["expiry_hint"],
                "size_bytes": size_bytes,
            })

            if len(rows) >= max_files:
                break

    except Exception:
        return rows

    return rows

def score_doc_path(path: Path, row_no: str, levels: list[dict[str, Any]]) -> tuple[int, list[str]]:
    name = path.name
    full_text = str(path)

    meta = parse_doc_name(name)

    name_norm = normalize_token(name)
    full_norm = normalize_token(full_text)
    prefix_norm = normalize_token(meta.get("prefix", ""))

    score = 0
    reasons = []

    row_no_norm = normalize_token(row_no)

    # A열 번호 매칭: 가장 강한 신호
    if row_no_norm and prefix_norm == row_no_norm:
        score += 90
        reasons.append(f"A열번호:{row_no}")

    elif row_no_norm and name_norm.startswith(row_no_norm):
        score += 70
        reasons.append(f"A열번호시작:{row_no}")

    if meta.get("has_halal_marker"):
        score += 10
        reasons.append("ⓗ표시")

    if path.is_file() and path.suffix.lower() in CERT_EXTS:
        score += 8
        reasons.append("인증서파일")

    for level in levels:
        depth = level.get("depth", 0)

        eng = level.get("english_name", "")
        mat = level.get("material_name", "")
        maker = level.get("maker", "")
        org = level.get("org", "")
        cert_no = level.get("cert_no", "")

        eng_norm = normalize_token(eng)
        mat_norm = normalize_token(mat)
        maker_norm = normalize_token(maker)
        org_norm = normalize_token(org)
        cert_norm = normalize_token(cert_no)

        if cert_norm and cert_norm in full_norm:
            score += 80
            reasons.append(f"인증번호:{cert_no}")

        if eng_norm and eng_norm in full_norm:
            score += 45
            reasons.append(f"{depth}단계영문명:{eng}")

        if mat_norm and mat_norm in full_norm:
            score += 22
            reasons.append(f"{depth}단계원료명:{mat}")

        if maker_norm and maker_norm in full_norm:
            score += 24
            reasons.append(f"{depth}단계제조사:{maker}")

        if org_norm and org_norm in full_norm:
            score += 12
            reasons.append(f"{depth}단계기관:{org}")

        if meta.get("org_hint") and org and meta["org_hint"].lower() == org.lower():
            score += 18
            reasons.append(f"파일명기관:{meta['org_hint']}")

    return score, reasons


def get_material_halal_docs(row_pos: int, limit: int = 50) -> dict[str, Any]:
    root = Path(HALAL_DOC_ROOT)

    if not root.exists():
        return {
            "ok": False,
            "message": f"HALAL_DOC_ROOT 경로에 접근할 수 없습니다: {root}",
            "root": str(root),
            "rows": [],
            "count": 0,
        }

    bundle = read_pmf_bundle()
    df_raw = bundle["df_raw"]

    if row_pos < 0 or row_pos >= len(df_raw):
        return {
            "ok": False,
            "message": "row_pos 범위를 벗어났습니다.",
            "root": str(root),
            "rows": [],
            "count": 0,
        }

    row = df_raw.iloc[row_pos]
    row_no = get_row_number(row)
    levels = build_material_levels(row)

    candidates = []

    for path in iter_halal_doc_paths():
        score, reasons = score_doc_path(path, row_no=row_no, levels=levels)

        if score <= 0:
            continue

        meta = parse_doc_name(path.name)

        child_files = list_child_cert_files(path, max_files=20) if path.is_dir() else []

        # 폴더 자체가 매칭됐는데 내부에 인증서 파일이 있으면 가산
        if child_files:
            score += 12
            reasons.append(f"하위파일:{len(child_files)}건")

        candidates.append({
            "type": "folder" if path.is_dir() else "file",
            "name": path.name,
            "path": str(path),
            "parent": str(path.parent),
            "ext": path.suffix.lower() if path.is_file() else "",
            "score": score,
            "reasons": reasons[:10],
            "has_halal_marker": meta["has_halal_marker"],
            "prefix": meta["prefix"],
            "maker_hint": meta["maker_hint"],
            "org_hint": meta["org_hint"],
            "expiry_hint": meta["expiry_hint"],
            "child_files": child_files,
            "child_file_count": len(child_files),
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)

    return {
        "ok": True,
        "root": str(root),
        "row_pos": row_pos,
        "row_no": row_no,
        "levels": levels,
        "rows": candidates[:limit],
        "count": min(len(candidates), limit),
        "total_matched": len(candidates),
    }

import subprocess
import platform

def find_child_by_prefix(parent: Path, prefix: str) -> Path | None:
    """
    특정 폴더 바로 아래에서 '102.' 또는 '102_1.' 같은 prefix로 시작하는 폴더/파일을 찾는다.
    """
    prefix = display_value(prefix)

    if not prefix:
        return None

    if not parent.exists() or not parent.is_dir():
        return None

    patterns = [
        f"{prefix}.",
        f"{prefix} ",
        f"{prefix}_",
    ]

    try:
        children = list(parent.iterdir())

        # 폴더 우선
        children.sort(key=lambda p: (0 if p.is_dir() else 1, p.name.lower()))

        for child in children:
            name = child.name.strip()

            if any(name.startswith(pattern) for pattern in patterns):
                return child

    except Exception:
        return None

    return None

def get_effective_row_number(df_raw, row_pos: int) -> str:
    """
    PMF A열 번호 보정.
    일부 하부원료 행은 A열이 비어 있을 수 있으므로 위쪽 행에서 가장 가까운 번호를 가져온다.
    """
    if row_pos < 0 or row_pos >= len(df_raw):
        return ""

    current = get_row_number(df_raw.iloc[row_pos])

    if current:
        return current

    # 병합셀/빈칸 대응: 위쪽 50행 안에서 가장 가까운 A열 번호 사용
    start = max(0, row_pos - 50)

    for pos in range(row_pos - 1, start - 1, -1):
        prev_no = get_row_number(df_raw.iloc[pos])

        if prev_no:
            return prev_no

    return ""


def resolve_folder_by_row_no(root: Path, row_no: str) -> tuple[Path | None, Path | None]:
    """
    A열 번호 기준 폴더 탐색.

    예:
    5       -> root / '5. ...'
    102_2   -> root / '102. ...' / '102_2. ...'
    102_2_1 -> root / '102. ...' / '102_2. ...' / '102_2_1. ...'

    반환:
    - target folder/file
    - parent folder
    """
    row_no = display_value(row_no)

    if not row_no:
        return None, None

    parts = row_no.split("_")

    current_parent = root
    parent_folder = None
    target = None

    # 계층 prefix 생성: 102 → 102_2 → 102_2_1
    prefixes = []

    for idx in range(len(parts)):
        prefixes.append("_".join(parts[: idx + 1]))

    for prefix in prefixes:
        found = find_child_by_prefix(current_parent, prefix)

        if not found:
            break

        target = found
        parent_folder = current_parent

        if found.is_dir():
            current_parent = found
        else:
            break

    if target:
        return target, parent_folder

    # fallback: root 바로 아래에서 전체 row_no로 한 번 더 찾기
    target = find_child_by_prefix(root, row_no)

    if target:
        return target, root

    return None, parent_folder


def has_halal_marker_in_folder_name(path: Path | None) -> bool:
    if not path:
        return False

    return "ⓗ" in path.name

def get_material_halal_folder_fast(row_pos: int) -> dict[str, Any]:
    """
    PMF A열 번호 기준으로 하부원료 서류 폴더를 빠르게 찾는다.

    개선점:
    - A열 빈칸이면 위쪽 행에서 번호 보정
    - 102_2_1 같은 다단 번호를 계층적으로 탐색
    - 폴더명에 ⓗ가 있을 때만 폴더 내 인증서 파일을 자동 조회
    """
    root = Path(HALAL_DOC_ROOT)

    if not root.exists():
        return {
            "ok": False,
            "message": f"HALAL_DOC_ROOT 경로에 접근할 수 없습니다: {root}",
            "root": str(root),
            "row_pos": row_pos,
            "row_no": "",
            "folder": None,
        }

    bundle = read_pmf_bundle()
    df_raw = bundle["df_raw"]

    if row_pos < 0 or row_pos >= len(df_raw):
        return {
            "ok": False,
            "message": "row_pos 범위를 벗어났습니다.",
            "root": str(root),
            "row_pos": row_pos,
            "row_no": "",
            "folder": None,
        }

    row_no = get_effective_row_number(df_raw, row_pos)

    if not row_no:
        return {
            "ok": False,
            "message": "PMF A열 번호를 찾지 못했습니다.",
            "root": str(root),
            "row_pos": row_pos,
            "row_no": "",
            "folder": None,
        }

    target, parent_folder = resolve_folder_by_row_no(root, row_no)

    if not target:
        return {
            "ok": True,
            "message": "매칭되는 폴더를 찾지 못했습니다.",
            "root": str(root),
            "row_pos": row_pos,
            "row_no": row_no,
            "parent_folder": str(parent_folder) if parent_folder else "",
            "folder": None,
        }

    parsed = parse_doc_name(target.name)
    has_marker = has_halal_marker_in_folder_name(target)

    # 핵심:
    # 폴더명에 ⓗ가 있는 경우만 인증서 보유 폴더로 보고 파일 자동 조회
    child_files = (
        list_child_cert_files(target, max_files=50)
        if target.is_dir() and has_marker
        else []
    )

    return {
        "ok": True,
        "message": "matched",
        "root": str(root),
        "row_pos": row_pos,
        "row_no": row_no,
        "parent_folder": str(parent_folder) if parent_folder else "",
        "folder": {
            "name": target.name,
            "path": str(target),
            "type": "folder" if target.is_dir() else "file",
            "has_halal_marker": has_marker,
            "auto_file_lookup": has_marker,
            "prefix": parsed.get("prefix", ""),
            "maker_hint": parsed.get("maker_hint", ""),
            "org_hint": parsed.get("org_hint", ""),
            "expiry_hint": parsed.get("expiry_hint", ""),
            "file_count": len(child_files),
            "files": child_files,
        },
    }

def open_folder_in_explorer(path_text: str) -> dict[str, Any]:
    """
    백엔드가 실행되는 Windows PC에서 탐색기로 폴더를 연다.
    원격 서버에 배포하면 사용자 PC가 아니라 서버 PC에서 열린다.
    """
    path = safe_resolve_doc_path(path_text)

    if path.is_file():
        folder = path.parent
    else:
        folder = path

    if not folder.exists():
        return {
            "ok": False,
            "message": f"폴더를 찾을 수 없습니다: {folder}",
            "path": str(folder),
        }

    try:
        if platform.system().lower().startswith("win"):
            os.startfile(str(folder))
        else:
            subprocess.Popen(["xdg-open", str(folder)])

        return {
            "ok": True,
            "message": "폴더를 열었습니다.",
            "path": str(folder),
        }

    except Exception as e:
        return {
            "ok": False,
            "message": str(e),
            "path": str(folder),
        }