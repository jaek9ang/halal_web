"""Daum IMAP 동기화 진입점."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any
import email
import imaplib
import json

from app.services.mail_inbox.text import (
    decode_mime_text,
    is_exact_pdf_ocr_candidate,
    parse_received_at,
    quote_imap_mailbox,
    safe_filename,
    strip_html_text,
)
from app.services.mail_inbox.parsing import (
    extract_body_text,
    extract_date_candidates_from_text,
    get_attachment_parts,
    is_bounce_mail,
)
from app.services.mail_inbox.store import (
    init_inbox_tables,
    insert_attachment,
    insert_inbound_mail,
    make_download_dir,
    save_message_files,
)
from app.services.mail_inbox.matching import (
    evaluate_inbound_mail_candidate,
    get_sent_mail_reference_context,
)


def sync_daum_inbox_attachments(
    user_email: str,
    app_password: str,
    mailbox: str = "INBOX",
    days: int = 30,
    limit: int = 50,
    only_with_attachments: bool = True,
) -> dict[str, Any]:
    """
    Daum IMAP 받은메일 동기화.
    첨부파일을 관리번호 기준 폴더에 저장한다.
    """
    if not user_email:
        raise ValueError("user_email이 없습니다.")

    if not app_password:
        raise ValueError("app_password가 없습니다.")

    init_inbox_tables()

    result = {
        "ok": True,
        "provider": "daum",
        "mailbox": mailbox,
        "days": days,
        "limit": limit,
        "checked": 0,
        "inserted_mails": 0,
        "skipped_existing": 0,
        "downloaded_attachments": 0,
        "exact_matched": 0,
        "unmatched": 0,
        "rows": [],
        "skipped_bounce": 0,
        "skipped_non_candidate": 0,
        "probable": 0,
        "unmatched_candidate": 0,
    }

    imap = imaplib.IMAP4_SSL("imap.daum.net", 993)

    try:
        imap.login(user_email, app_password)

        select_mailbox = quote_imap_mailbox(mailbox)
        status, select_data = imap.select(select_mailbox)
        reference_context = get_sent_mail_reference_context(limit=500)

        if status != "OK":
            raise RuntimeError(f"메일함 선택 실패: {mailbox} / {select_data}")

        since_date = (datetime.now() - timedelta(days=int(days))).strftime("%d-%b-%Y")
        status, data = imap.search(None, "SINCE", since_date)

        if status != "OK":
            raise RuntimeError("IMAP 검색에 실패했습니다.")

        msg_nums = data[0].split()
        msg_nums = list(reversed(msg_nums))[: int(limit)]

        for msg_num in msg_nums:
            result["checked"] += 1

            status, fetched = imap.fetch(msg_num, "(RFC822)")

            if status != "OK" or not fetched or not fetched[0]:
                continue

            raw_msg = fetched[0][1]
            msg = email.message_from_bytes(raw_msg)

            subject = decode_mime_text(msg.get("Subject", ""))
            sender = decode_mime_text(msg.get("From", ""))
            received_at = parse_received_at(msg)
            message_id = msg.get("Message-ID", "")

            message_uid = message_id.strip() or f"{mailbox}-{msg_num.decode(errors='ignore')}-{received_at}-{subject}"

            body_text = extract_body_text(msg)

            if is_bounce_mail(
                subject=subject,
                sender=sender,
                body_text=body_text,
                msg=msg,
            ):
                result["skipped_bounce"] += 1
                continue

            attachments = get_attachment_parts(msg)

            if only_with_attachments and not attachments:
                continue

            attachment_names = " ".join([x["filename"] for x in attachments])

            candidate = evaluate_inbound_mail_candidate(
                subject=subject,
                sender=sender,
                body_text=body_text,
                attachment_names=attachment_names,
                reference_context=reference_context,
            )

            if not candidate["should_collect"]:
                result["skipped_non_candidate"] += 1
                continue

            request_id = candidate.get("matched_request_id", "")
            match_status = candidate.get("match_status", "unmatched_candidate")
            match_reason = candidate.get("match_reason", "")

            if match_status == "exact":
                result["exact_matched"] += 1
            elif match_status == "probable":
                result["probable"] += 1
            else:
                result["unmatched_candidate"] += 1

            download_dir = make_download_dir(request_id, received_at, sender)
            attach_dir = download_dir / "attachments"
            attach_dir.mkdir(parents=True, exist_ok=True)

            mail_date_candidates = extract_date_candidates_from_text(
                f"{subject}\n{body_text}",
                source="mail",
            )

            meta = {
                "provider": "daum",
                "mailbox": mailbox,
                "message_uid": message_uid,
                "subject": subject,
                "sender": sender,
                "received_at": received_at,
                "body_text": body_text,
                "body_preview": strip_html_text(body_text)[:1000],
                "date_candidates_json": json.dumps(mail_date_candidates, ensure_ascii=False),
                "matched_request_id": request_id,
                "match_status": match_status,
                "match_reason": match_reason,
                "attachment_count": len(attachments),
                "download_dir": str(download_dir),
                "is_excluded": 0,
                "exclude_reason": "",
            }

            mail_id, inserted_new = insert_inbound_mail(meta)

            if not inserted_new:
                result["skipped_existing"] += 1
                continue

            save_message_files(download_dir, meta, body_text)

            saved_files = []

            for idx, att in enumerate(attachments, start=1):
                original_name = safe_filename(att["filename"], f"attachment_{idx}")
                prefix = request_id if request_id else "UNMATCHED"
                saved_name = safe_filename(f"{prefix}__{idx:03d}__{original_name}")

                saved_path = attach_dir / saved_name
                saved_path.write_bytes(att["payload"])

                auto_ocr_selected = 1 if (
                    match_status == "exact"
                    and is_exact_pdf_ocr_candidate(
                        filename=saved_name,
                        ext=Path(saved_name).suffix.lower(),
                    )
                ) else 0

                insert_attachment(
                    mail_id=mail_id,
                    request_id=request_id,
                    original_filename=original_name,
                    saved_filename=saved_name,
                    saved_path=str(saved_path),
                    file_size=len(att["payload"]),
                    match_status=match_status,
                )

                result["downloaded_attachments"] += 1
                saved_files.append(str(saved_path))

            result["inserted_mails"] += 1
            result["rows"].append({
                "mail_id": mail_id,
                "subject": subject,
                "sender": sender,
                "received_at": received_at,
                "matched_request_id": request_id,
                "match_status": match_status,
                "attachment_count": len(attachments),
                "download_dir": str(download_dir),
                "saved_files": saved_files,
            })

    finally:
        try:
            imap.logout()
        except Exception:
            pass

    return result


def sync_daum_multiple_mailboxes(
    user_email: str,
    app_password: str,
    mailboxes: list[str],
    days: int = 30,
    limit_per_mailbox: int = 50,
    only_with_attachments: bool = True,
) -> dict[str, Any]:
    """
    받은메일함 + HALAL 인증서 등 여러 메일함을 순차 동기화.
    """
    final = {
        "ok": True,
        "provider": "daum",
        "mailboxes": mailboxes,
        "days": days,
        "limit_per_mailbox": limit_per_mailbox,
        "checked": 0,
        "inserted_mails": 0,
        "skipped_existing": 0,
        "downloaded_attachments": 0,
        "exact_matched": 0,
        "unmatched": 0,
        "results": [],
        "skipped_bounce": 0,
        "skipped_non_candidate": 0,
        "probable": 0,
        "unmatched_candidate": 0,
    }

    for mailbox in mailboxes:
        try:
            result = sync_daum_inbox_attachments(
                user_email=user_email,
                app_password=app_password,
                mailbox=mailbox,
                days=days,
                limit=limit_per_mailbox,
                only_with_attachments=only_with_attachments,
            )

            final["checked"] += int(result.get("checked", 0))
            final["inserted_mails"] += int(result.get("inserted_mails", 0))
            final["skipped_existing"] += int(result.get("skipped_existing", 0))
            final["downloaded_attachments"] += int(result.get("downloaded_attachments", 0))
            final["exact_matched"] += int(result.get("exact_matched", 0))
            final["unmatched"] += int(result.get("unmatched", 0))
            final["skipped_bounce"] += int(result.get("skipped_bounce", 0))
            final["results"].append({
                "mailbox": mailbox,
                "ok": True,
                "result": result,
            })
            final["skipped_non_candidate"] += int(result.get("skipped_non_candidate", 0))
            final["probable"] += int(result.get("probable", 0))
            final["unmatched_candidate"] += int(result.get("unmatched_candidate", 0))

        except Exception as e:
            final["results"].append({
                "mailbox": mailbox,
                "ok": False,
                "message": str(e),
            })

    return final


def list_daum_mailboxes(user_email: str, app_password: str) -> dict[str, Any]:
    """
    Daum IMAP 메일함 목록 조회.
    한글 폴더명 확인용.
    """
    if not user_email:
        raise ValueError("user_email이 없습니다.")

    if not app_password:
        raise ValueError("app_password가 없습니다.")

    imap = imaplib.IMAP4_SSL("imap.daum.net", 993)

    rows = []

    try:
        imap.login(user_email, app_password)

        status, data = imap.list()

        if status != "OK":
            raise RuntimeError("IMAP 메일함 목록 조회에 실패했습니다.")

        for raw in data:
            line = raw.decode("utf-8", errors="replace")

            mailbox_name = line

            if ' "/" ' in line:
                mailbox_name = line.split(' "/" ')[-1].strip().strip('"')
            elif ' "." ' in line:
                mailbox_name = line.split(' "." ')[-1].strip().strip('"')
            else:
                parts = line.split(" ")
                if parts:
                    mailbox_name = parts[-1].strip().strip('"')

            rows.append({
                "raw": line,
                "mailbox": mailbox_name,
            })

    finally:
        try:
            imap.logout()
        except Exception:
            pass

    return {
        "ok": True,
        "rows": rows,
        "count": len(rows),
    }
