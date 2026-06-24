import glob
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import (
    PMF_SOURCE_DIR,
    PMF_FILE_PREFIX,
    PMF_CACHE_DIR,
    PMF_ACTIVE_PATH,
    PMF_META_PATH,
    RAW_MATERIAL_SHEET,
    EMAIL_SHEET,
    MAIL_CONTENTS_SHEET,
)


def ensure_pmf_dirs() -> None:
    PMF_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def find_latest_pmf_file() -> str:
    """
    PMF 원본 폴더에서 Products and Materials File*.xlsm 중 최신 파일 탐색.
    """
    pattern = os.path.join(PMF_SOURCE_DIR, f"{PMF_FILE_PREFIX}*.xlsm")
    files = glob.glob(pattern)

    if not files:
        raise FileNotFoundError(
            f"PMF 원본 파일을 찾지 못했습니다. pattern={pattern}"
        )

    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[0]


def load_pmf_meta() -> dict[str, Any]:
    if not PMF_META_PATH.exists():
        return {}

    with open(PMF_META_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_pmf_meta(meta: dict[str, Any]) -> None:
    ensure_pmf_dirs()

    with open(PMF_META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def sync_latest_pmf_copy(force: bool = False) -> dict[str, Any]:
    """
    최신 PMF 원본을 cache/source_pmf/active_pmf.xlsm 으로 복사.
    PMF 내용은 DB 저장하지 않는다.
    """
    ensure_pmf_dirs()

    source_file = find_latest_pmf_file()
    source_mtime = os.path.getmtime(source_file)

    old_meta = load_pmf_meta()

    need_copy = force or not PMF_ACTIVE_PATH.exists()

    if old_meta:
        if old_meta.get("source_file") != source_file:
            need_copy = True

        old_mtime = float(old_meta.get("source_mtime", 0))
        if old_mtime != float(source_mtime):
            need_copy = True

    if need_copy:
        shutil.copy2(source_file, PMF_ACTIVE_PATH)

        meta = {
            "ok": True,
            "copied": True,
            "source_file": source_file,
            "source_name": os.path.basename(source_file),
            "source_mtime": source_mtime,
            "source_mtime_text": datetime.fromtimestamp(source_mtime).isoformat(timespec="seconds"),
            "active_path": str(PMF_ACTIVE_PATH),
            "synced_at": datetime.now().isoformat(timespec="seconds"),
        }

        save_pmf_meta(meta)
        return meta

    return {
        "ok": True,
        "copied": False,
        **old_meta,
    }


def ensure_active_pmf_exists() -> None:
    if not PMF_ACTIVE_PATH.exists():
        sync_latest_pmf_copy(force=False)


def get_excel_file() -> pd.ExcelFile:
    ensure_active_pmf_exists()
    return pd.ExcelFile(PMF_ACTIVE_PATH, engine="openpyxl")


def find_sheet_name(sheet_names: list[str], target: str) -> str:
    """
    대소문자/공백 차이를 약간 허용해서 시트명 찾기.
    """
    if target in sheet_names:
        return target

    target_norm = target.strip().lower()

    for name in sheet_names:
        if str(name).strip().lower() == target_norm:
            return name

    raise ValueError(f"'{target}' 시트를 찾지 못했습니다. 현재 시트={sheet_names}")


def read_pmf_bundle() -> dict[str, Any]:
    """
    active_pmf.xlsm에서 필요한 시트를 읽는다.
    """
    ensure_active_pmf_exists()

    xls = get_excel_file()
    sheet_names = xls.sheet_names

    raw_sheet = find_sheet_name(sheet_names, RAW_MATERIAL_SHEET)
    email_sheet = find_sheet_name(sheet_names, EMAIL_SHEET)

    mail_contents_sheet = None
    try:
        mail_contents_sheet = find_sheet_name(sheet_names, MAIL_CONTENTS_SHEET)
    except Exception:
        mail_contents_sheet = None

    df_raw = pd.read_excel(
        PMF_ACTIVE_PATH,
        sheet_name=raw_sheet,
        header=None,
        engine="openpyxl",
    )

    df_email = pd.read_excel(
        PMF_ACTIVE_PATH,
        sheet_name=email_sheet,
        header=None,
        engine="openpyxl",
    )

    df_mail_contents = pd.DataFrame()
    if mail_contents_sheet:
        df_mail_contents = pd.read_excel(
            PMF_ACTIVE_PATH,
            sheet_name=mail_contents_sheet,
            header=None,
            engine="openpyxl",
        )

    return {
        "meta": load_pmf_meta(),
        "sheet_names": sheet_names,
        "raw_sheet": raw_sheet,
        "email_sheet": email_sheet,
        "mail_contents_sheet": mail_contents_sheet,
        "raw_rows": int(len(df_raw)),
        "email_rows": int(len(df_email)),
        "mail_contents_rows": int(len(df_mail_contents)),
        "df_raw": df_raw,
        "df_email": df_email,
        "df_mail_contents": df_mail_contents,
    }


def df_preview_records(df: pd.DataFrame, limit: int = 30) -> list[dict[str, Any]]:
    """
    DataFrame을 API 응답용 records로 변환.
    열 이름은 C0, C1, C2... 로 임시 부여.
    """
    view = df.head(limit).copy()
    view = view.fillna("")

    view.columns = [f"C{i}" for i in range(len(view.columns))]

    return view.astype(str).to_dict(orient="records")


def get_pmf_status() -> dict[str, Any]:
    meta = load_pmf_meta()

    return {
        "has_active_pmf": PMF_ACTIVE_PATH.exists(),
        "active_path": str(PMF_ACTIVE_PATH),
        "meta": meta,
    }


def get_pmf_summary() -> dict[str, Any]:
    bundle = read_pmf_bundle()

    return {
        "meta": bundle["meta"],
        "sheet_names": bundle["sheet_names"],
        "raw_sheet": bundle["raw_sheet"],
        "email_sheet": bundle["email_sheet"],
        "mail_contents_sheet": bundle["mail_contents_sheet"],
        "raw_rows": bundle["raw_rows"],
        "email_rows": bundle["email_rows"],
        "mail_contents_rows": bundle["mail_contents_rows"],
    }