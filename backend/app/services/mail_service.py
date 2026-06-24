import hashlib
import html
import json
import os
import smtplib
import sqlite3
import ssl
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import pandas as pd

from app.core.config import PMF_APP_DB_PATH, LHLN_GUIDE_PDF_PATH
from app.services.pmf_service import read_pmf_bundle
from app.services.supplier_service import (
    clean,
    nfkc_text,
    get_full_row_data,
    build_email_candidates_from_sheet,
    load_supplier_email_overrides,
    resolve_supplier_email,
)

def parse_date(value: Any):
    text = clean(value)

    if text == "-":
        return None

    try:
        dt = pd.to_datetime(text, errors="coerce")

        if pd.isna(dt):
            return None

        return dt.to_pydatetime().replace(hour=0, minute=0, second=0, microsecond=0)

    except Exception:
        return None


def add_one_year_date(dt: datetime) -> str:
    try:
        return dt.replace(year=dt.year + 1).strftime("%Y-%m-%d")
    except ValueError:
        # 2월 29일 대응
        return dt.replace(year=dt.year + 1, day=28).strftime("%Y-%m-%d")


def format_date(dt: datetime | None) -> str:
    if not dt:
        return "-"
    return dt.strftime("%Y-%m-%d")


def classify_mail_type(org: str, exp_dt: datetime | None, today: datetime) -> str:
    """
    기존 Streamlit 발송 분류 기준 유지.

    - BPJPH:
      유효기간이 이미 지난 경우 → BPJPH 유지확인
    - BPJPH 외:
      D-30 이하 또는 이미 만료 → 만료 통보
      D-60~D-90 → 만료 도래
    """
    if not exp_dt:
        return ""

    diff = (exp_dt - today).days
    org_upper = nfkc_text(org).upper()

    if org_upper == "BPJPH":
        if diff < 0:
            return "BPJPH 유지확인"
        return ""

    if diff <= 30:
        return "만료 통보"

    if 60 <= diff <= 90:
        return "만료 도래"

    return ""


def get_material_name_from_row(row, depth: int) -> str:
    data = get_full_row_data(row, depth)

    if not data:
        return "-"

    return clean(data.get("n", ""))


def get_material_chain_from_row(row, depth: int) -> list[str]:
    """
    메인원료 > 1차하부 > 2차하부 형태의 원료 경로 생성.
    """
    chain = []

    for d in range(depth + 1):
        name = get_material_name_from_row(row, d)

        if name != "-":
            chain.append(name)

    return chain


def format_material_chain_text(chain: list[str]) -> str:
    if not chain:
        return "-"

    if len(chain) == 1:
        return chain[0]

    return " > ".join(chain)


def make_mail_request_id(supplier_name: str, mail_type: str, body_html: str) -> str:
    raw = f"{supplier_name}|{mail_type}|{body_html}"
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:8].upper()
    today = datetime.now().strftime("%Y%m%d")
    return f"HALAL-REQ-{today}-{digest}"


def get_mail_subject_text(supplier_name: str, mail_type: str) -> str:
    """
    제목에는 관리번호를 넣지 않는다.
    """
    supplier_name = nfkc_text(supplier_name)

    if mail_type == "BPJPH 유지확인":
        return f"(주)세우 할랄인증 BPJPH 유지확인 건 ({supplier_name})"

    if mail_type == "만료 도래":
        return f"(주)세우 할랄인증 만료 도래 안내 건 ({supplier_name})"

    return f"(주)세우 할랄인증 만료 통보 건 ({supplier_name})"


def format_material_mail_line(idx: int, rec: dict[str, Any]) -> str:
    chain_text = html.escape(nfkc_text(rec.get("material_path", "-")))
    eng_name = html.escape(nfkc_text(rec.get("english_name", "-")))
    maker = html.escape(nfkc_text(rec.get("maker", "-")))
    maker_country = html.escape(nfkc_text(rec.get("maker_country", "-")))
    org = html.escape(nfkc_text(rec.get("org", "-")))
    cert_no = html.escape(nfkc_text(rec.get("cert_no", "-")))
    exp = html.escape(nfkc_text(rec.get("exp", "-")))
    mail_type = nfkc_text(rec.get("mail_type", ""))

    if mail_type == "BPJPH 유지확인":
        new_exp = html.escape(nfkc_text(rec.get("bpjph_expected_exp", "-")))
        exp_line = f"현재 유효기간: {exp} / 유지 확인 시 적용 예정: {new_exp}"
    else:
        exp_line = f"유효기간: {exp}"

    return f"""
    <div style="margin-bottom:14px; line-height:1.62;">
        <div><b>{idx}. {chain_text}</b></div>
        <div style="margin-left:14px;">- 영문명: {eng_name}</div>
        <div style="margin-left:14px;">- 제조사: {maker}</div>
        <div style="margin-left:14px;">- 제조국: {maker_country}</div>
        <div style="margin-left:14px;">- 인증기관: {org}</div>
        <div style="margin-left:14px;">- 인증번호: {cert_no}</div>
        <div style="margin-left:14px;">- {exp_line}</div>
        <div style="margin-left:14px; color:#555;">- 인증서상 품목명 또는 품목번호: 회신 시 함께 기재 요청</div>
    </div>
    """


def get_mail_template_text(mail_type: str) -> str:
    if mail_type == "BPJPH 유지확인":
        return """
        안녕하십니까. 세우 품질개선팀입니다.<br><br>
        귀사 <b>[SUPPLIER]</b>에서 당사로 공급 중인 아래 품목의 BPJPH 할랄 인증서 유지 현황을 확인드리고자 연락드립니다.<br><br>
        인증서의 변경(종료, 인증기관 등) 또는 유지하지 않을 계획이 있으신 경우, 관련 내용을 본 메일로 회신 부탁드립니다.<br>
        또한 현재 인증을 그대로 유지 중이시더라도 확인을 위해 간단히 회신해 주시면 감사하겠습니다.<br><br>
        ======================================================================================================================<br>
        ★★★ 해당 품목 ★★★<br>
        [ITEMS]
        ======================================================================================================================<br><br>
        ■■■ 해당 문건은 자동으로 발송되므로 일정기간 내 회신이 없을 경우 재발송될 수 있습니다. 이점 양해 부탁드립니다. ■■■<br><br>
        감사합니다.
        """

    if mail_type == "만료 도래":
        return """
        안녕하십니까. 세우 품질개선팀입니다.<br><br>
        귀사 <b>[SUPPLIER]</b>에서 납품 중인 아래 품목의 할랄 인증서 유효기간이 도래하여 사전 확인을 요청드립니다.<br><br>
        갱신 예정 여부 및 갱신 인증서 발급 가능 시점을 회신 부탁드립니다.<br>
        인증서상 품목명 또는 인증서 내 해당 품목 번호도 함께 기재해 주시면 감사하겠습니다.<br><br>
        ======================================================================================================================<br>
        ★★★ 해당 품목 ★★★<br>
        [ITEMS]
        ======================================================================================================================<br><br>
        ■■■ 해당 문건은 자동으로 발송되므로 일정기간 내 회신이 없을 경우 재발송될 수 있습니다. 이점 양해 부탁드립니다. ■■■<br><br>
        감사합니다.
        """

    return """
    안녕하십니까. 세우 품질개선팀입니다.<br><br>
    귀사 <b>[SUPPLIER]</b>에서 납품 중인 아래 품목의 할랄 인증서 유효기간 만료 관련 확인을 요청드립니다.<br><br>
    최신 갱신 인증서 또는 갱신 진행 현황을 회신 부탁드립니다.<br>
    인증서상 품목명 또는 인증서 내 해당 품목 번호도 함께 기재해 주시면 감사하겠습니다.<br><br>
    ======================================================================================================================<br>
    ★★★ 해당 품목 ★★★<br>
    [ITEMS]
    ======================================================================================================================<br><br>
    ■■■ 해당 문건은 자동으로 발송되므로 일정기간 내 회신이 없을 경우 재발송될 수 있습니다. 이점 양해 부탁드립니다. ■■■<br><br>
    감사합니다.
    """


def append_request_id_to_body(body_html: str, request_id: str) -> str:
    """
    본문 하단에 관리번호 1회만 표시.
    """
    return f"""
    {body_html}
    <hr style="border:none; border-top:1px solid #ddd; margin:22px 0;">
    <div style="font-size:12px; color:#666;">
        관리번호: {html.escape(request_id)}<br>
        회신 시 본 관리번호가 유지되면 확인이 빠릅니다.
    </div>
    """


def get_mail_targets(test_mode: bool = True, test_receiver: str = "jaek_ing@naver.com") -> dict[str, Any]:
    """
    PMF 기준 발송 대상 생성.
    실제 메일 발송은 하지 않고 미리보기 데이터만 반환.
    """
    bundle = read_pmf_bundle()

    df_raw = bundle["df_raw"]
    df_email = bundle["df_email"]

    email_candidates_df = build_email_candidates_from_sheet(df_email)
    overrides = load_supplier_email_overrides()

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    item_rows = []

    for _, row in df_raw.iterrows():
        supplier = clean(row.iloc[6]) if len(row) > 6 else "-"

        if supplier == "-":
            continue

        for depth in range(5):
            data = get_full_row_data(row, depth)

            if not data:
                continue

            material_name = clean(data.get("n", ""))

            if material_name == "-":
                continue

            org = clean(data.get("h", ""))
            exp_dt = parse_date(data.get("v", ""))

            if org == "-" or not exp_dt:
                continue

            mail_type = classify_mail_type(org, exp_dt, today)

            if not mail_type:
                continue

            material_chain = get_material_chain_from_row(row, depth)
            material_path = format_material_chain_text(material_chain)

            raw_email = data.get("email", "") if depth == 0 else row.iloc[12] if len(row) > 12 else ""

            resolved = resolve_supplier_email(
                supplier_name=supplier,
                raw_email=raw_email,
                email_candidates_df=email_candidates_df,
                overrides=overrides,
            )

            item_rows.append({
                "supplier": supplier,
                "depth": depth,
                "mail_type": mail_type,
                "material_name": material_name,
                "material_path": material_path,
                "english_name": clean(data.get("e", "")),
                "maker": clean(data.get("m", "")),
                "maker_country": clean(data.get("o", "")),
                "org": org,
                "cert_no": clean(data.get("i", "")),
                "exp": format_date(exp_dt),
                "bpjph_expected_exp": add_one_year_date(exp_dt) if nfkc_text(org).upper() == "BPJPH" else "-",
                "receiver": test_receiver if test_mode else resolved.get("final_to", ""),
                "cc": "" if test_mode else resolved.get("final_cc", ""),
                "mail_status": "테스트모드" if test_mode else resolved.get("status", ""),
                "email_source": resolved.get("source", ""),
                "email_score": resolved.get("score", 0),
            })

    if not item_rows:
        return {
            "summary": {
                "total_targets": 0,
                "total_items": 0,
                "bpjph_keep": 0,
                "expire_notice": 0,
                "expire_upcoming": 0,
            },
            "rows": [],
            "items": [],
            "pmf_meta": bundle["meta"],
        }

    df_items = pd.DataFrame(item_rows)

    target_rows = []

    for (supplier, mail_type), group in df_items.groupby(["supplier", "mail_type"]):
        records = group.to_dict(orient="records")

        items_html = "".join([
            format_material_mail_line(idx=i + 1, rec=rec)
            for i, rec in enumerate(records)
        ])

        body_template = get_mail_template_text(mail_type)
        body_html = (
            body_template
            .replace("[SUPPLIER]", html.escape(str(supplier)))
            .replace("[ITEMS]", items_html)
        )

        request_id = make_mail_request_id(
            supplier_name=str(supplier),
            mail_type=str(mail_type),
            body_html=body_html,
        )

        body_html = append_request_id_to_body(body_html, request_id)

        attach_pdf = "N" if mail_type == "BPJPH 유지확인" else "Y"

        target_rows.append({
            "selected": False,
            "request_id": request_id,
            "supplier": supplier,
            "mail_type": mail_type,
            "item_count": int(len(records)),
            "receiver": records[0].get("receiver", ""),
            "cc": records[0].get("cc", ""),
            "mail_status": records[0].get("mail_status", ""),
            "attach_pdf": attach_pdf,
            "subject": get_mail_subject_text(supplier, mail_type),
            "body_html": body_html,
            "items": records,
        })

    summary = {
        "total_targets": int(len(target_rows)),
        "total_items": int(len(item_rows)),
        "bpjph_keep": int((df_items["mail_type"] == "BPJPH 유지확인").sum()),
        "expire_notice": int((df_items["mail_type"] == "만료 통보").sum()),
        "expire_upcoming": int((df_items["mail_type"] == "만료 도래").sum()),
    }

    return {
        "summary": summary,
        "rows": target_rows,
        "items": item_rows,
        "pmf_meta": bundle["meta"],
    }

def ensure_mail_log_db() -> None:
    PMF_APP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(PMF_APP_DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS mail_send_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT,
        request_id TEXT,
        supplier TEXT,
        mail_type TEXT,
        sender TEXT,
        receiver TEXT,
        cc TEXT,
        subject TEXT,
        body_html TEXT,
        attach_pdf TEXT,
        attachment_paths TEXT,
        test_mode INTEGER,
        success INTEGER,
        send_result TEXT,
        error_message TEXT,
        sent_at TEXT
    )
    """)

    # 기존 테이블에 deleted_at 컬럼이 없으면 추가
    cur.execute("PRAGMA table_info(mail_send_logs)")
    columns = [row[1] for row in cur.fetchall()]

    if "deleted_at" not in columns:
        cur.execute("ALTER TABLE mail_send_logs ADD COLUMN deleted_at TEXT")

    conn.commit()
    conn.close()

def get_mail_log_conn():
    ensure_mail_log_db()
    conn = sqlite3.connect(PMF_APP_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def split_email_recipients(value: str) -> list[str]:
    text = nfkc_text(value)

    if not text:
        return []

    parts = []
    for token in text.replace(",", ";").split(";"):
        token = token.strip()
        if token and "@" in token:
            parts.append(token)

    # 중복 제거
    deduped = []
    for item in parts:
        if item not in deduped:
            deduped.append(item)

    return deduped


def attach_files_to_message(msg: MIMEMultipart, attachment_paths: list[str]) -> None:
    for path in attachment_paths:
        if not path:
            continue

        if not os.path.exists(path):
            continue

        filename = os.path.basename(path)

        with open(path, "rb") as f:
            part = MIMEApplication(f.read(), Name=filename)

        part["Content-Disposition"] = f'attachment; filename="{filename}"'
        msg.attach(part)


def send_halal_mail_smtp(
    sender_email: str,
    app_password: str,
    receiver: str,
    subject: str,
    body_html: str,
    cc: str = "",
    attachments: list[str] | None = None,
) -> tuple[bool, str]:
    """
    Daum SMTP 발송.
    네가 기존에 보내기 성공했던 Daum SMTP 방식 기준.
    """
    sender_email = nfkc_text(sender_email)
    app_password = nfkc_text(app_password)

    if not sender_email:
        return False, "발신자 메일 주소가 없습니다."

    if not app_password:
        return False, "Daum 앱 비밀번호가 없습니다."

    to_list = split_email_recipients(receiver)
    cc_list = split_email_recipients(cc)

    if not to_list:
        return False, "수신자 이메일이 없습니다."

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = ", ".join(to_list)

    if cc_list:
        msg["Cc"] = ", ".join(cc_list)

    msg["Subject"] = subject
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    attach_files_to_message(msg, attachments or [])

    try:
        context = ssl.create_default_context()

        with smtplib.SMTP_SSL("smtp.daum.net", 465, context=context) as server:
            server.login(sender_email, app_password)
            server.send_message(msg, to_addrs=to_list + cc_list)

        return True, "SUCCESS"

    except Exception as e:
        return False, str(e)


def log_mail_send(
    batch_id: str,
    target: dict[str, Any],
    sender: str,
    success: bool,
    send_result: str,
    error_message: str = "",
    attachment_paths: list[str] | None = None,
    test_mode: bool = True,
) -> None:
    ensure_mail_log_db()

    conn = get_mail_log_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO mail_send_logs (
        batch_id,
        request_id,
        supplier,
        mail_type,
        sender,
        receiver,
        cc,
        subject,
        body_html,
        attach_pdf,
        attachment_paths,
        test_mode,
        success,
        send_result,
        error_message,
        sent_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        batch_id,
        target.get("request_id", ""),
        target.get("supplier", ""),
        target.get("mail_type", ""),
        sender,
        target.get("receiver", ""),
        target.get("cc", ""),
        target.get("subject", ""),
        target.get("body_html", ""),
        target.get("attach_pdf", "N"),
        json.dumps(attachment_paths or [], ensure_ascii=False),
        1 if test_mode else 0,
        1 if success else 0,
        send_result,
        error_message,
        datetime.now().isoformat(timespec="seconds"),
    ))

    conn.commit()
    conn.close()


def has_success_log(request_id: str, test_mode: bool) -> bool:
    ensure_mail_log_db()

    conn = get_mail_log_conn()

    row = conn.execute("""
        SELECT COUNT(*) AS cnt
        FROM mail_send_logs
        WHERE request_id = ?
          AND test_mode = ?
          AND success = 1
    """, (
        request_id,
        1 if test_mode else 0,
    )).fetchone()

    conn.close()

    return int(row["cnt"]) > 0


def get_mail_send_logs(limit: int = 100, test_mode: bool | None = None) -> dict[str, Any]:
    ensure_mail_log_db()

    limit = max(1, min(int(limit), 500))

    conn = get_mail_log_conn()

    if test_mode is None:
        rows = conn.execute("""
            SELECT *
            FROM mail_send_logs
            WHERE deleted_at IS NULL
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT *
            FROM mail_send_logs
            WHERE test_mode = ?
              AND deleted_at IS NULL
            ORDER BY id DESC
            LIMIT ?
        """, (1 if test_mode else 0, limit)).fetchall()

    conn.close()

    return {
        "rows": [dict(row) for row in rows]
    }

def send_selected_mail_requests(
    request_ids: list[str],
    sender_email: str = "",
    app_password: str = "",
    test_mode: bool = True,
    test_receiver: str = "jaek_ing@naver.com",
    allow_duplicate: bool = False,
    require_attachment_pdf: bool = False,
) -> dict[str, Any]:
    """
    선택한 request_id 목록을 실제 SMTP로 발송.
    request_id는 현재 PMF 기준 /mail/targets에서 다시 생성해 매칭한다.
    """
    request_ids = [nfkc_text(x).upper() for x in request_ids if nfkc_text(x)]

    if not request_ids:
        raise ValueError("발송할 request_id가 없습니다.")

    sender_email = nfkc_text(sender_email) or os.getenv("DAUM_EMAIL", "").strip()
    app_password = nfkc_text(app_password) or os.getenv("DAUM_APP_PASSWORD", "").strip()

    if not sender_email:
        raise ValueError("발신자 메일 주소가 없습니다.")

    if not app_password:
        raise ValueError("Daum 앱 비밀번호가 없습니다.")

    targets_data = get_mail_targets(
        test_mode=test_mode,
        test_receiver=test_receiver,
    )

    target_map = {
        nfkc_text(row.get("request_id", "")).upper(): row
        for row in targets_data.get("rows", [])
    }

    batch_raw = "|".join(sorted(request_ids)) + "|" + datetime.now().isoformat(timespec="seconds")
    batch_id = "BATCH-" + hashlib.md5(batch_raw.encode("utf-8")).hexdigest()[:10].upper()

    results = []

    for req_id in request_ids:
        target = target_map.get(req_id)

        if not target:
            results.append({
                "request_id": req_id,
                "success": False,
                "result": "대상 없음",
                "supplier": "",
            })
            continue

        if not allow_duplicate and has_success_log(req_id, test_mode=test_mode):
            results.append({
                "request_id": req_id,
                "success": False,
                "result": "SKIP: 이미 성공 발송된 관리번호",
                "supplier": target.get("supplier", ""),
            })
            continue

        attachment_paths = []

        if target.get("attach_pdf") == "Y":
            if os.path.exists(LHLN_GUIDE_PDF_PATH):
                attachment_paths.append(str(LHLN_GUIDE_PDF_PATH))
            elif require_attachment_pdf:
                msg = f"SKIP: 첨부 PDF 없음 - {LHLN_GUIDE_PDF_PATH}"

                log_mail_send(
                    batch_id=batch_id,
                    target=target,
                    sender=sender_email,
                    success=False,
                    send_result=msg,
                    error_message=msg,
                    attachment_paths=[],
                    test_mode=test_mode,
                )

                results.append({
                    "request_id": req_id,
                    "success": False,
                    "result": msg,
                    "supplier": target.get("supplier", ""),
                })
                continue

        success, result_msg = send_halal_mail_smtp(
            sender_email=sender_email,
            app_password=app_password,
            receiver=target.get("receiver", ""),
            subject=target.get("subject", ""),
            body_html=target.get("body_html", ""),
            cc=target.get("cc", ""),
            attachments=attachment_paths,
        )

        log_mail_send(
            batch_id=batch_id,
            target=target,
            sender=sender_email,
            success=success,
            send_result=result_msg,
            error_message="" if success else result_msg,
            attachment_paths=attachment_paths,
            test_mode=test_mode,
        )

        results.append({
            "request_id": req_id,
            "success": success,
            "result": result_msg,
            "supplier": target.get("supplier", ""),
            "receiver": target.get("receiver", ""),
            "subject": target.get("subject", ""),
            "attachment_paths": attachment_paths,
        })

    success_count = sum(1 for r in results if r.get("success"))
    fail_count = len(results) - success_count

    return {
        "batch_id": batch_id,
        "total": len(results),
        "success_count": success_count,
        "fail_count": fail_count,
        "results": results,
    }

def hide_mail_send_logs(ids: list[int], include_real: bool = False) -> dict[str, Any]:
    """
    발송 로그 숨김 처리.
    기본은 테스트 로그만 숨김.
    실발송 로그까지 숨기려면 include_real=True 필요.
    """
    ensure_mail_log_db()

    clean_ids = []

    for x in ids:
        try:
            clean_ids.append(int(x))
        except Exception:
            continue

    if not clean_ids:
        return {
            "ok": False,
            "hidden_count": 0,
            "message": "숨김 처리할 로그 ID가 없습니다.",
        }

    now_ts = datetime.now().isoformat(timespec="seconds")

    conn = get_mail_log_conn()
    cur = conn.cursor()

    if include_real:
        placeholders = ",".join(["?"] * len(clean_ids))
        cur.execute(
            f"""
            UPDATE mail_send_logs
            SET deleted_at = ?
            WHERE id IN ({placeholders})
            """,
            [now_ts] + clean_ids,
        )
    else:
        placeholders = ",".join(["?"] * len(clean_ids))
        cur.execute(
            f"""
            UPDATE mail_send_logs
            SET deleted_at = ?
            WHERE id IN ({placeholders})
              AND test_mode = 1
            """,
            [now_ts] + clean_ids,
        )

    hidden_count = cur.rowcount

    conn.commit()
    conn.close()

    return {
        "ok": True,
        "hidden_count": hidden_count,
        "include_real": include_real,
        "message": f"{hidden_count}건 숨김 처리 완료",
    }