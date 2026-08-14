from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse

import app.services.pmf_service as pmf_service
from app.services.pmf_service import read_pmf_bundle
from app.services.supplier_service import clean, get_full_row_data
from app.services.material_link_service import get_material_related_files
from app.services.halal_doc_service import (
    get_material_halal_docs,
    get_material_halal_folder_fast,
    open_folder_in_explorer,
    safe_resolve_doc_path,
)

router = APIRouter()


def run_pmf_sync(force: bool = True):
    """
    기존 pmf_service.py에 실제 존재하는 동기화 함수를 찾아 실행한다.
    함수명이 프로젝트마다 달라서 직접 import하지 않는다.
    """
    candidate_names = [
        "sync_latest_pmf_copy",
        "sync_active_pmf",
        "sync_pmf",
        "prepare_active_pmf",
        "ensure_active_pmf",
        "copy_active_pmf",
        "copy_latest_pmf",
        "copy_latest_pmf_to_cache",
    ]

    for name in candidate_names:
        fn = getattr(pmf_service, name, None)

        if callable(fn):
            try:
                return fn(force=force)
            except TypeError:
                return fn()

    # 동기화 함수가 없어도 서버는 죽지 않게 한다.
    bundle = read_pmf_bundle()
    return {
        "ok": True,
        "message": "pmf_service.py에서 동기화 전용 함수를 찾지 못했습니다. 기존 active PMF를 그대로 읽었습니다.",
        "available_sync_functions": [
            name for name in dir(pmf_service)
            if "sync" in name.lower() or "pmf" in name.lower()
        ],
        "meta": bundle.get("meta", {}),
    }

def is_valid_material_name(value: str) -> bool:
    """
    PMF 상단 빈 행/다단 헤더 행/불완전 행 제외용.
    실제 원료명이 아닌 '1차', 'Name of Material (KOREAN)' 같은 헤더성 값은 제외한다.
    """
    text = clean(value)

    if not text:
        return False

    norm = str(text).strip().lower()
    norm_no_space = norm.replace(" ", "")

    if norm in {"-", "nan", "none", "null"}:
        return False

    # PMF 다단 헤더 행 방어
    blocked_exact = {
        "원료명",
        "원료",
        "품명",
        "영문명",
        "제조사",
        "제조국",
        "인증기관",
        "인증번호",
        "유효기간",
        "halal by",
        "supplier",
        "main material",
        "raw material",
        "material",
        "name of material",
        "name of material (korean)",
        "name of material (english)",
        "nameofmaterial(korean)",
        "nameofmaterial(english)",
        "1차",
        "2차",
        "3차",
        "4차",
        "1st",
        "2nd",
        "3rd",
        "4th",
    }

    if norm in blocked_exact or norm_no_space in blocked_exact:
        return False

    # '1차 원료', '4차 하부 원료' 같은 헤더성 텍스트 방어
    header_patterns = [
        "1차",
        "2차",
        "3차",
        "4차",
        "하부원료",
        "하부 원료",
        "name of material",
        "nameofmaterial",
        "halalby",
    ]

    # 단, 실제 원료명에 우연히 '하부' 같은 단어가 들어가는 경우는 희박하지만,
    # name of material / 차수 표현은 확실히 헤더로 본다.
    if any(pattern in norm_no_space for pattern in header_patterns):
        return False

    return True

def normalize_query(value: str) -> str:
    """
    검색어는 clean()을 쓰면 안 된다.
    clean("")이 "-"를 반환하면 빈 검색이 '-' 검색으로 오작동한다.
    """
    text = str(value or "").strip().lower()

    if text in {"-", "nan", "none", "null"}:
        return ""

    return text


def display_value(value: str) -> str:
    """
    화면 표시용 값 정리.
    '-' / nan / None은 빈값으로 본다.
    """
    text = clean(value)

    if not text:
        return ""

    if text.strip().lower() in {"-", "nan", "none", "null"}:
        return ""

    return text

def is_header_supplier(value: str) -> bool:
    text = clean(value)
    norm = str(text).strip().lower()

    if norm in {"supplier", "공급사", "업체", "업체명"}:
        return True

    return False

def get_depth_label(depth: int) -> str:
    depth = int(depth or 0)

    if depth <= 0:
        return "메인 원료"

    return f"{depth}차 하부"


def get_material_levels_from_row(row) -> list[dict]:
    levels = []

    for depth in range(5):
        data = get_full_row_data(row, depth)

        if not data:
            continue

        name = display_value(data.get("n", ""))

        if not is_valid_material_name(name):
            continue

        levels.append({
            "depth": depth,
            "depth_label": get_depth_label(depth),
            "material_name": name,
            "english_name": display_value(data.get("e", "")),
            "maker": display_value(data.get("m", "")),
            "maker_country": display_value(data.get("o", "")),
            "org": display_value(data.get("h", "")),
            "cert_no": display_value(data.get("i", "")),
            "exp": display_value(data.get("v", "")),
            "raw": data,
        })

    return levels

@router.get("/summary")
def pmf_summary():
    bundle = read_pmf_bundle()
    meta = bundle.get("meta", {})

    df_raw = bundle.get("df_raw")
    df_email = bundle.get("df_email")

    return {
        "meta": meta,
        "raw_rows": int(len(df_raw)) if df_raw is not None else 0,
        "email_rows": int(len(df_email)) if df_email is not None else 0,
    }


@router.post("/sync")
def pmf_sync(force: bool = Query(True)):
    return run_pmf_sync(force=force)


@router.get("/materials/search")
def search_materials(
    keyword: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
):
    """
    PMF Raw material management 시트 기준 원료 검색.
    구분 컬럼은 검색 매칭 단계가 아니라 해당 row의 최종 하부 단계를 표시한다.
    """
    bundle = read_pmf_bundle()
    df_raw = bundle["df_raw"]

    keyword_norm = normalize_query(keyword)
    rows = []

    for row_pos, (_, row) in enumerate(df_raw.iterrows()):
        supplier = display_value(row.iloc[6]) if len(row) > 6 else ""
        if is_header_supplier(supplier):
            continue

        levels = get_material_levels_from_row(row)

        # 메인 원료명이 없는 행/상단 빈 행/헤더성 행 제외
        if not levels:
            continue

        main_level = levels[0]
        final_level = levels[-1]

        matched_level = None

        for level in levels:
            search_fields = [
                level.get("material_name", ""),
                level.get("english_name", ""),
                level.get("maker", ""),
                level.get("org", ""),
                level.get("cert_no", ""),
                supplier,
            ]

            search_blob = " ".join([x for x in search_fields if x]).lower()

            if keyword_norm and keyword_norm in search_blob:
                matched_level = level
                break

        # 검색어가 있는데 매칭 안 되면 제외
        if keyword_norm and matched_level is None:
            continue

        # 빈 검색이면 메인 원료 기준 표시
        if matched_level is None:
            matched_level = main_level

        display_depth = int(final_level.get("depth", 0))

        rows.append({
            "row_pos": row_pos,
            "supplier": supplier or "-",

            "main_material": main_level.get("material_name", "-") or "-",
            "main_english": main_level.get("english_name", "-") or "-",
            "main_maker": main_level.get("maker", "-") or "-",
            "main_country": main_level.get("maker_country", "-") or "-",
            "main_org": main_level.get("org", "-") or "-",
            "main_cert_no": main_level.get("cert_no", "-") or "-",
            "main_exp": main_level.get("exp", "-") or "-",

            # 검색어가 하부 원료에 걸렸을 때 표의 원료명으로 표시할 값
            "matched_depth": int(matched_level.get("depth", 0)),
            "matched_name": matched_level.get("material_name", "-") or "-",
            "matched_english": matched_level.get("english_name", "-") or "-",
            "matched_org": matched_level.get("org", "-") or "-",

            # 구분/단계 표시는 이 값을 사용해야 함
            "display_depth": display_depth,
            "display_depth_label": get_depth_label(display_depth),
            "display_sub_material": final_level.get("material_name", "") if display_depth > 0 else "-",
            "display_sub_english": final_level.get("english_name", "") if display_depth > 0 else "-",
            "display_org": final_level.get("org", "") or main_level.get("org", "-") or "-",

            "chain_text": " > ".join([x["material_name"] for x in levels]),
            "depth_count": len(levels),
        })

        if len(rows) >= limit:
            break

    return {
        "rows": rows,
        "count": len(rows),
    }


@router.get("/materials/{row_pos}")
def material_detail(row_pos: int):
    """
    특정 PMF row의 메인/하부 원료 상세 구조 반환.
    """
    bundle = read_pmf_bundle()
    df_raw = bundle["df_raw"]

    if row_pos < 0 or row_pos >= len(df_raw):
        return {
            "ok": False,
            "message": "row_pos 범위를 벗어났습니다.",
            "row_pos": row_pos,
            "levels": [],
        }

    row = df_raw.iloc[row_pos]
    supplier = display_value(row.iloc[6]) if len(row) > 6 else "-"

    levels = get_material_levels_from_row(row)

    if not levels:
        return {
            "ok": False,
            "message": "유효한 메인 원료명이 없는 행입니다.",
            "row_pos": row_pos,
            "supplier": supplier,
            "chain_text": "",
            "levels": [],
        }

    return {
        "ok": True,
        "row_pos": row_pos,
        "supplier": supplier,
        "chain_text": " > ".join([x["material_name"] for x in levels]),
        "levels": levels,
    }

@router.get("/materials/{row_pos}/related-files")
def material_related_files(
    row_pos: int,
    limit: int = Query(30, ge=1, le=100),
):
    """
    선택 원료와 관련 가능성이 있는 수신첨부/OCR 결과 후보 조회.
    인증번호, 영문명, 원료명, 제조사, 인증기관 기준으로 단순 점수화한다.
    """
    return get_material_related_files(
        row_pos=row_pos,
        limit=limit,
    )

@router.get("/materials/{row_pos}/halal-docs")
def material_halal_docs(
    row_pos: int,
    limit: int = Query(50, ge=1, le=200),
):
    """
    선택 PMF row와 매칭되는 네트워크 하부원료 인증서 폴더/파일 후보 조회.
    A열 번호, 영문명, 제조사, 인증기관, ⓗ 표시를 기준으로 점수화한다.
    """
    return get_material_halal_docs(row_pos=row_pos, limit=limit)


@router.get("/halal-docs/file")
def halal_doc_file(path: str):
    """
    네트워크 폴더의 인증서 파일을 브라우저에서 열기/다운로드.
    HALAL_DOC_ROOT 하위 경로만 허용한다.
    """
    try:
        file_path = safe_resolve_doc_path(path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    if not file_path.is_file():
        raise HTTPException(status_code=400, detail="파일 경로가 아닙니다.")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/octet-stream",
    )

@router.get("/materials/{row_pos}/halal-folder")
def material_halal_folder(row_pos: int):
    """
    PMF A열 번호 기준으로 기존 하부원료 서류 폴더를 빠르게 찾는다.
    전체 파일 스캔을 하지 않는다.
    """
    return get_material_halal_folder_fast(row_pos=row_pos)


@router.post("/halal-docs/open-folder")
def open_halal_doc_folder(path: str):
    """
    백엔드 PC에서 Windows 탐색기로 네트워크 폴더를 연다.
    """
    result = open_folder_in_explorer(path)

    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message"))

    return result