import re
import sqlite3
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

import pandas as pd

from app.core.config import PMF_APP_DB_PATH
from app.services.pmf_service import read_pmf_bundle
from app.core.db import connect as db_connect


EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
)


def ensure_db_dir() -> None:
    PMF_APP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_conn():
    return db_connect(PMF_APP_DB_PATH)


def init_supplier_email_db() -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS supplier_email_overrides (
        supplier_key TEXT PRIMARY KEY,
        supplier_name TEXT,
        final_to TEXT,
        final_cc TEXT,
        memo TEXT,
        updated_at TEXT
    )
    """)

    conn.commit()
    conn.close()


def clean(value: Any) -> str:
    if value is None:
        return "-"

    try:
        if pd.isna(value):
            return "-"
    except Exception:
        pass

    text = str(value).strip()

    if not text or text.lower() in {"nan", "none", "nat"}:
        return "-"

    return text


def nfkc_text(value: Any) -> str:
    if value is None:
        return ""

    text = unicodedata.normalize("NFKC", str(value))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_supplier_key(value: Any) -> str:
    """
    업체명 매칭용 key.
    (주), 주식회사, 공백, 특수문자를 최대한 제거해 유사 매칭 안정화.
    """
    text = nfkc_text(value).lower()

    if not text:
        return ""

    remove_words = [
        "주식회사",
        "(주)",
        "㈜",
        "co.,ltd",
        "co.ltd",
        "co ltd",
        "co., ltd",
        "coltd",
        "ltd.",
        "ltd",
        "inc.",
        "inc",
        "corp.",
        "corp",
        "company",
    ]

    for word in remove_words:
        text = text.replace(word, "")

    text = re.sub(r"[^0-9a-zA-Z가-힣]", "", text)
    return text.strip()


def extract_email_list(value: Any) -> list[str]:
    text = nfkc_text(value)

    if not text:
        return []

    emails = EMAIL_PATTERN.findall(text)

    clean_emails = []
    seen = set()

    for email in emails:
        email = email.strip().lower()

        if email not in seen:
            clean_emails.append(email)
            seen.add(email)

    return clean_emails


def join_emails(emails: list[str]) -> str:
    if not emails:
        return ""

    seen = []
    for email in emails:
        email = email.strip().lower()
        if email and email not in seen:
            seen.append(email)

    return "; ".join(seen)


def looks_like_header_or_noise(text: str) -> bool:
    t = nfkc_text(text).lower()

    if not t:
        return True

    noise_tokens = [
        "email",
        "e-mail",
        "mail",
        "메일",
        "주소",
        "담당",
        "contact",
        "supplier",
        "업체",
        "비고",
        "remark",
    ]

    if t in noise_tokens:
        return True

    if EMAIL_PATTERN.search(t):
        return True

    if len(t) <= 1:
        return True

    return False


def pick_supplier_from_row(row_values: list[Any], email_col_idx: int) -> str:
    """
    E-mail 시트에서 이메일이 발견된 행의 업체명 후보를 추정.
    1순위: 이메일 셀 왼쪽의 가장 가까운 텍스트
    2순위: 같은 행의 첫 번째 의미 있는 텍스트
    """
    # 왼쪽에서 가까운 후보 우선
    for idx in range(email_col_idx - 1, -1, -1):
        text = clean(row_values[idx])

        if text != "-" and not looks_like_header_or_noise(text):
            return text

    # 전체 행에서 첫 의미 텍스트
    for cell in row_values:
        text = clean(cell)

        if text != "-" and not looks_like_header_or_noise(text):
            return text

    return "-"


def build_email_candidates_from_sheet(df_email_raw: pd.DataFrame) -> pd.DataFrame:
    """
    E-mail 시트를 전수 스캔해서 업체명/이메일 후보를 만든다.
    기존 Streamlit에서 쓰던 candidate DataFrame을 API용으로 재구성.
    """
    rows = []

    for r_idx, row in df_email_raw.iterrows():
        row_values = row.tolist()

        for c_idx, cell in enumerate(row_values):
            emails = extract_email_list(cell)

            if not emails:
                continue

            supplier = pick_supplier_from_row(row_values, c_idx)
            supplier_key = normalize_supplier_key(supplier)

            if not supplier_key:
                continue

            rows.append({
                "supplier_key": supplier_key,
                "supplier": supplier,
                "emails": join_emails(emails),
                "source_cell": f"R{int(r_idx) + 1}C{int(c_idx) + 1}",
            })

    if not rows:
        return pd.DataFrame(columns=["supplier_key", "supplier", "emails", "source_cell"])

    df = pd.DataFrame(rows)

    # 같은 supplier_key는 이메일/출처 병합
    merged_rows = []

    for supplier_key, group in df.groupby("supplier_key"):
        supplier = clean(group.iloc[0]["supplier"])

        all_emails = []
        source_cells = []

        for _, g in group.iterrows():
            all_emails.extend(extract_email_list(g.get("emails", "")))
            source_cells.append(str(g.get("source_cell", "")))

        merged_rows.append({
            "supplier_key": supplier_key,
            "supplier": supplier,
            "emails": join_emails(all_emails),
            "source_cell": ", ".join([x for x in source_cells if x]),
        })

    return pd.DataFrame(merged_rows).sort_values("supplier").reset_index(drop=True)


def get_full_row_data(row: pd.Series, depth: int) -> dict[str, str] | None:
    """
    기존 Streamlit PMF 매핑 그대로 이식.
    depth 0: 메인 원료
    depth 1~4: O열부터 9열 간격 반복
    """
    try:
        if depth == 0:
            return {
                "id": str(row.iloc[0]),
                "code": str(row.iloc[1]),
                "n": str(row.iloc[2]),
                "e": str(row.iloc[3]),
                "m": str(row.iloc[4]),
                "o": str(row.iloc[5]),
                "s": str(row.iloc[6]),
                "h": str(row.iloc[7]),
                "i": str(row.iloc[8]),
                "v": str(row.iloc[9]),
                "email": str(row.iloc[12]) if len(row) > 12 else "",
            }

        base = 15 + (depth - 1) * 9

        return {
            "n": str(row.iloc[base]),
            "e": str(row.iloc[base + 1]),
            "m": str(row.iloc[base + 2]),
            "o": str(row.iloc[base + 3]),
            "h": str(row.iloc[base + 4]),
            "i": str(row.iloc[base + 5]),
            "v": str(row.iloc[base + 6]),
        }

    except Exception:
        return None


def build_supplier_halal_summary(df_raw: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """
    Raw material management 기준 업체별 할랄 인증 보유 여부 집계.
    메인/1~4차 하부원료 중 인증기관이 있으면 할랄 보유로 판단.
    """
    summary: dict[str, dict[str, Any]] = {}

    for _, row in df_raw.iterrows():
        supplier = clean(row.iloc[6]) if len(row) > 6 else "-"

        if supplier == "-":
            continue

        supplier_key = normalize_supplier_key(supplier)

        if not supplier_key:
            continue

        if supplier_key not in summary:
            summary[supplier_key] = {
                "supplier": supplier,
                "has_halal": False,
                "cert_count": 0,
                "orgs": set(),
            }

        for depth in range(5):
            data = get_full_row_data(row, depth)

            if not data:
                continue

            material_name = clean(data.get("n", ""))
            org = clean(data.get("h", ""))
            cert_no = clean(data.get("i", ""))
            exp = clean(data.get("v", ""))

            if material_name == "-":
                continue

            # 인증기관이 있으면 인증 건으로 판단
            if org != "-":
                summary[supplier_key]["has_halal"] = True
                summary[supplier_key]["cert_count"] += 1
                summary[supplier_key]["orgs"].add(org)

            # 인증번호/유효기간만 있는데 기관이 누락된 경우도 보수적으로 인증 보유로 표시
            elif cert_no != "-" or exp != "-":
                summary[supplier_key]["has_halal"] = True
                summary[supplier_key]["cert_count"] += 1

    normalized = {}

    for key, val in summary.items():
        normalized[key] = {
            "supplier": val["supplier"],
            "has_halal": bool(val["has_halal"]),
            "cert_count": int(val["cert_count"]),
            "orgs_text": ", ".join(sorted(val["orgs"])),
        }

    return normalized


def load_supplier_email_overrides() -> dict[str, dict[str, Any]]:
    init_supplier_email_db()

    conn = get_conn()
    rows = conn.execute("""
        SELECT supplier_key, supplier_name, final_to, final_cc, memo, updated_at
        FROM supplier_email_overrides
    """).fetchall()
    conn.close()

    return {
        row["supplier_key"]: dict(row)
        for row in rows
    }


def upsert_supplier_email_override(
    supplier_name: str,
    supplier_key: str,
    final_to: str,
    final_cc: str = "",
    memo: str = "",
) -> dict[str, Any]:
    init_supplier_email_db()

    supplier_key = normalize_supplier_key(supplier_key or supplier_name)

    if not supplier_key:
        raise ValueError("supplier_key 또는 supplier_name이 필요합니다.")

    now_ts = datetime.now().isoformat(timespec="seconds")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO supplier_email_overrides (
        supplier_key, supplier_name, final_to, final_cc, memo, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(supplier_key) DO UPDATE SET
        supplier_name = excluded.supplier_name,
        final_to = excluded.final_to,
        final_cc = excluded.final_cc,
        memo = excluded.memo,
        updated_at = excluded.updated_at
    """, (
        supplier_key,
        nfkc_text(supplier_name),
        nfkc_text(final_to),
        nfkc_text(final_cc),
        nfkc_text(memo),
        now_ts,
    ))

    conn.commit()
    conn.close()

    return {
        "ok": True,
        "supplier_key": supplier_key,
        "supplier_name": supplier_name,
        "final_to": final_to,
        "final_cc": final_cc,
        "memo": memo,
        "updated_at": now_ts,
    }


def resolve_supplier_email(
    supplier_name: str,
    raw_email: str,
    email_candidates_df: pd.DataFrame,
    overrides: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    supplier_key = normalize_supplier_key(supplier_name)

    # 1순위: 사용자 확정 override
    override = overrides.get(supplier_key)

    if override and nfkc_text(override.get("final_to", "")):
        return {
            "final_to": nfkc_text(override.get("final_to", "")),
            "final_cc": nfkc_text(override.get("final_cc", "")),
            "status": "수동확정",
            "source": "override",
            "candidate": nfkc_text(override.get("final_to", "")),
            "score": 1.0,
        }

    # 2순위: Raw M열 이메일
    raw_emails = extract_email_list(raw_email)

    if raw_emails:
        return {
            "final_to": join_emails(raw_emails),
            "final_cc": "",
            "status": "Raw M열",
            "source": "raw_material_m_col",
            "candidate": join_emails(raw_emails),
            "score": 0.95,
        }

    # 3순위: E-mail 시트 exact
    if not email_candidates_df.empty:
        exact = email_candidates_df[email_candidates_df["supplier_key"] == supplier_key]

        if not exact.empty:
            emails = nfkc_text(exact.iloc[0].get("emails", ""))

            if emails:
                return {
                    "final_to": emails,
                    "final_cc": "",
                    "status": "E-Mail exact",
                    "source": "email_sheet_exact",
                    "candidate": f"{exact.iloc[0].get('supplier', '')} / {emails}",
                    "score": 0.90,
                }

        # 4순위: E-mail 시트 fuzzy
        best_row = None
        best_score = 0.0

        for _, cand in email_candidates_df.iterrows():
            cand_key = nfkc_text(cand.get("supplier_key", ""))
            score = SequenceMatcher(None, supplier_key, cand_key).ratio()

            if score > best_score:
                best_score = score
                best_row = cand

        if best_row is not None and best_score >= 0.82:
            emails = nfkc_text(best_row.get("emails", ""))

            if emails:
                return {
                    "final_to": emails,
                    "final_cc": "",
                    "status": "E-Mail 유사매칭",
                    "source": "email_sheet_fuzzy",
                    "candidate": f"{best_row.get('supplier', '')} / {emails}",
                    "score": round(best_score, 3),
                }

    return {
        "final_to": "",
        "final_cc": "",
        "status": "확인필요",
        "source": "missing",
        "candidate": "",
        "score": 0.0,
    }


def get_supplier_email_review() -> dict[str, Any]:
    """
    Raw PMF + E-mail sheet + override DB를 합쳐
    메일주소 정리 화면용 데이터를 반환.
    """
    bundle = read_pmf_bundle()

    df_raw = bundle["df_raw"]
    df_email = bundle["df_email"]

    email_candidates_df = build_email_candidates_from_sheet(df_email)
    halal_summary = build_supplier_halal_summary(df_raw)
    overrides = load_supplier_email_overrides()

    supplier_rows = []

    for _, row in df_raw.iterrows():
        supplier = clean(row.iloc[6]) if len(row) > 6 else "-"

        if supplier == "-":
            continue

        supplier_key = normalize_supplier_key(supplier)

        if not supplier_key:
            continue

        raw_email = clean(row.iloc[12]) if len(row) > 12 else ""

        resolved = resolve_supplier_email(
            supplier_name=supplier,
            raw_email=raw_email,
            email_candidates_df=email_candidates_df,
            overrides=overrides,
        )

        halal_info = halal_summary.get(supplier_key, {
            "has_halal": False,
            "cert_count": 0,
            "orgs_text": "",
        })

        supplier_rows.append({
            "apply": bool(nfkc_text(resolved.get("final_to", ""))),
            "has_halal": bool(halal_info.get("has_halal", False)),
            "cert_count": int(halal_info.get("cert_count", 0)),
            "orgs": halal_info.get("orgs_text", ""),
            "supplier": supplier,
            "supplier_key": supplier_key,
            "raw_email": join_emails(extract_email_list(raw_email)),
            "email_candidate": resolved.get("candidate", ""),
            "final_to": resolved.get("final_to", ""),
            "final_cc": resolved.get("final_cc", ""),
            "status": resolved.get("status", ""),
            "source": resolved.get("source", ""),
            "score": float(resolved.get("score", 0.0)),
        })

    df_review = pd.DataFrame(supplier_rows)

    if not df_review.empty:
        df_review = df_review.drop_duplicates(subset=["supplier_key"], keep="first")
        df_review = df_review.sort_values(["has_halal", "supplier"], ascending=[False, True])
    else:
        df_review = pd.DataFrame()

    total = int(len(df_review))
    halal_count = int(df_review["has_halal"].sum()) if not df_review.empty else 0
    confirmed_count = int((df_review["apply"] == True).sum()) if not df_review.empty else 0
    halal_unconfirmed_count = int(
        ((df_review["has_halal"] == True) & (df_review["apply"] == False)).sum()
    ) if not df_review.empty else 0

    return {
        "summary": {
            "total_suppliers": total,
            "halal_suppliers": halal_count,
            "confirmed_emails": confirmed_count,
            "halal_unconfirmed": halal_unconfirmed_count,
            "email_candidates": int(len(email_candidates_df)),
        },
        "rows": df_review.to_dict(orient="records"),
        "email_candidates": email_candidates_df.to_dict(orient="records"),
        "pmf_meta": bundle["meta"],
    }