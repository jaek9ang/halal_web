import os
import traceback
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.services.mail_service import (
    get_mail_targets,
    send_selected_mail_requests,
    get_mail_send_logs,
    hide_mail_send_logs,
)

from app.services.mail_receive_service import (
    test_daum_imap_login,
    fetch_recent_messages,
    download_recent_attachments,
    get_received_attachment_logs,
)

from app.services.mail_inbox_service import (
    sync_daum_multiple_mailboxes,
    list_daum_mailboxes,
    list_inbound_mails,
    list_inbound_attachments,
    open_inbound_attachment_folder,
    cleanup_bounced_inbound_records,
    get_inbound_mail_detail,
    set_inbound_mail_excluded,
    set_inbound_attachment_ocr_selected,
    auto_select_exact_inbound_ocr_targets,
    list_selected_inbound_ocr_targets,
    save_inbound_ocr_candidate_result,
)


router = APIRouter()


class MailSendRequest(BaseModel):
    request_ids: list[str] = Field(default_factory=list)
    sender_email: str = ""
    app_password: str = ""
    test_mode: bool = True
    test_receiver: str = "jaek_ing@naver.com"
    allow_duplicate: bool = False
    require_attachment_pdf: bool = False


class MailLogHideRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)
    include_real: bool = False


class InboxCredentialRequest(BaseModel):
    user_email: str
    app_password: str
    mailbox: str = "INBOX"


class InboxPreviewRequest(BaseModel):
    user_email: str
    app_password: str
    mailbox: str = "INBOX"
    limit: int = 30
    keyword: str = ""
    sender_keyword: str = ""
    request_id: str = ""
    mark_seen: bool = False


class InboxDownloadRequest(BaseModel):
    user_email: str
    app_password: str
    mailbox: str = "INBOX"
    limit: int = 30
    keyword: str = ""
    sender_keyword: str = ""
    request_id: str = ""
    allowed_exts: list[str] = Field(default_factory=lambda: [
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".xlsx",
        ".xlsm",
        ".xls",
    ])
    mark_seen: bool = False


class InboxSyncRequest(BaseModel):
    user_email: Optional[str] = None
    app_password: Optional[str] = None
    mailbox: str = "INBOX"
    mailboxes: Optional[list[str]] = None
    days: int = 30
    limit: int = 50
    only_with_attachments: bool = True


class OpenInboundAttachmentFolderRequest(BaseModel):
    saved_path: str


class ExcludeInboundMailRequest(BaseModel):
    mail_ids: list[int]
    excluded: bool = True
    reason: str = "사용자 제외"


class OcrSelectAttachmentRequest(BaseModel):
    attachment_ids: list[int]
    selected: bool = True

class AutoSelectExactOcrRequest(BaseModel):
    mail_id: Optional[int] = None

class SaveOcrCandidateRequest(BaseModel):
    attachment_id: int
    ocr_job_id: Optional[int] = None
    status: str = ""
    filename: str = ""
    best_expiry: str = ""
    expiry_candidates: list[dict] = Field(default_factory=list)
    filename_candidates: list[dict] = Field(default_factory=list)
    mail_candidates: list[dict] = Field(default_factory=list)
    ocr_candidates: list[dict] = Field(default_factory=list)
    message: str = ""

class AutoSelectExactOcrRequest(BaseModel):
    mail_id: Optional[int] = None


class SaveOcrCandidateRequest(BaseModel):
    attachment_id: int
    ocr_job_id: Optional[int] = None
    status: str = ""
    filename: str = ""
    best_expiry: str = ""
    expiry_candidates: list[dict] = Field(default_factory=list)
    message: str = ""

class AutoSelectExactOcrRequest(BaseModel):
    mail_id: int | None = None

def resolve_mail_credential(req_email: str = "", req_password: str = ""):
    email_candidates = [
        req_email,
        os.getenv("DAUM_IMAP_EMAIL", ""),
        os.getenv("DAUM_MAIL_EMAIL", ""),
        os.getenv("DAUM_EMAIL", ""),
        os.getenv("DAUM_SMTP_EMAIL", ""),
        os.getenv("MAIL_SENDER", ""),
        os.getenv("MAIL_EMAIL", ""),
        os.getenv("SMTP_USER", ""),
        os.getenv("SENDER_EMAIL", ""),
    ]

    password_candidates = [
        req_password,
        os.getenv("DAUM_IMAP_PASSWORD", ""),
        os.getenv("DAUM_IMAP_PW", ""),
        os.getenv("DAUM_MAIL_PASSWORD", ""),
        os.getenv("DAUM_MAIL_PW", ""),
        os.getenv("DAUM_APP_PASSWORD", ""),
        os.getenv("DAUM_APP_PW", ""),
        os.getenv("DAUM_SMTP_PASSWORD", ""),
        os.getenv("DAUM_SMTP_PW", ""),
        os.getenv("DAUM_PASSWORD", ""),
        os.getenv("MAIL_PASSWORD", ""),
        os.getenv("MAIL_PW", ""),
        os.getenv("MAIL_APP_PASSWORD", ""),
        os.getenv("SMTP_PASSWORD", ""),
        os.getenv("SMTP_PW", ""),
        os.getenv("SENDER_PASSWORD", ""),
    ]

    user_email = ""
    app_password = ""

    for value in email_candidates:
        value = str(value or "").strip()
        if value and value.lower() != "string":
            user_email = value
            break

    for value in password_candidates:
        value = str(value or "").strip()
        if value and value.lower() != "string":
            app_password = value
            break

    return user_email, app_password


@router.get("/targets")
def mail_targets(
    test_mode: bool = Query(True),
    test_receiver: str = Query("jaek_ing@naver.com"),
):
    return get_mail_targets(
        test_mode=test_mode,
        test_receiver=test_receiver,
    )


@router.post("/send")
def send_mail(payload: MailSendRequest):
    return send_selected_mail_requests(
        request_ids=payload.request_ids,
        sender_email=payload.sender_email,
        app_password=payload.app_password,
        test_mode=payload.test_mode,
        test_receiver=payload.test_receiver,
        allow_duplicate=payload.allow_duplicate,
        require_attachment_pdf=payload.require_attachment_pdf,
    )


@router.get("/logs")
def mail_logs(
    limit: int = Query(100, ge=1, le=500),
    test_mode: bool | None = Query(None),
):
    return get_mail_send_logs(
        limit=limit,
        test_mode=test_mode,
    )


@router.post("/logs/hide")
def hide_logs(payload: MailLogHideRequest):
    return hide_mail_send_logs(
        ids=payload.ids,
        include_real=payload.include_real,
    )


@router.post("/inbox/test")
def inbox_test(payload: InboxCredentialRequest):
    return test_daum_imap_login(
        user_email=payload.user_email,
        app_password=payload.app_password,
        mailbox=payload.mailbox,
    )


@router.post("/inbox/preview")
def inbox_preview(payload: InboxPreviewRequest):
    return fetch_recent_messages(
        user_email=payload.user_email,
        app_password=payload.app_password,
        mailbox=payload.mailbox,
        limit=payload.limit,
        keyword=payload.keyword,
        sender_keyword=payload.sender_keyword,
        request_id=payload.request_id,
        mark_seen=payload.mark_seen,
    )


@router.post("/inbox/download-attachments")
def inbox_download_attachments(payload: InboxDownloadRequest):
    return download_recent_attachments(
        user_email=payload.user_email,
        app_password=payload.app_password,
        mailbox=payload.mailbox,
        limit=payload.limit,
        keyword=payload.keyword,
        sender_keyword=payload.sender_keyword,
        request_id=payload.request_id,
        allowed_exts=payload.allowed_exts,
        mark_seen=payload.mark_seen,
    )


@router.get("/inbox/download-logs")
def inbox_download_logs(limit: int = Query(100, ge=1, le=500)):
    return get_received_attachment_logs(limit=limit)


@router.post("/inbox/sync")
def sync_inbox(req: InboxSyncRequest):
    try:
        user_email, app_password = resolve_mail_credential(
            req_email=req.user_email or "",
            req_password=req.app_password or "",
        )

        target_mailboxes = req.mailboxes if req.mailboxes else [req.mailbox]

        target_mailboxes = [
            str(x).strip()
            for x in target_mailboxes
            if str(x or "").strip()
        ]

        if not target_mailboxes:
            target_mailboxes = ["INBOX"]

        return sync_daum_multiple_mailboxes(
            user_email=user_email,
            app_password=app_password,
            mailboxes=target_mailboxes,
            days=req.days,
            limit_per_mailbox=req.limit,
            only_with_attachments=req.only_with_attachments,
        )

    except Exception as e:
        print("[INBOX SYNC ERROR]")
        print(traceback.format_exc())

        return {
            "ok": False,
            "message": str(e),
            "error_type": type(e).__name__,
            "email_set": bool(locals().get("user_email", "")),
            "password_set": bool(locals().get("app_password", "")),
            "mailbox": getattr(req, "mailbox", ""),
            "mailboxes": getattr(req, "mailboxes", None),
            "days": getattr(req, "days", ""),
            "limit": getattr(req, "limit", ""),
        }


@router.get("/inbox/messages")
def get_inbox_messages(
    match_status: str = "",
    mailbox: str = "",
    include_excluded: bool = False,
    limit: int = 100,
):
    return list_inbound_mails(
        match_status=match_status,
        mailbox=mailbox,
        include_excluded=include_excluded,
        limit=limit,
    )


@router.get("/inbox/messages/{mail_id}")
def get_inbox_message_detail(mail_id: int):
    return get_inbound_mail_detail(mail_id)


@router.post("/inbox/messages/exclude")
def exclude_inbox_messages(req: ExcludeInboundMailRequest):
    return set_inbound_mail_excluded(
        mail_ids=req.mail_ids,
        excluded=req.excluded,
        reason=req.reason,
    )


@router.get("/inbox/attachments")
def get_inbox_attachments(
    request_id: str = "",
    mailbox: str = "",
    limit: int = 200,
):
    return list_inbound_attachments(
        request_id=request_id,
        mailbox=mailbox,
        limit=limit,
    )


@router.post("/inbox/attachments/open-folder")
def open_inbox_attachment_folder(req: OpenInboundAttachmentFolderRequest):
    return open_inbound_attachment_folder(req.saved_path)


@router.post("/inbox/attachments/ocr-select")
def select_inbox_attachments_for_ocr(req: OcrSelectAttachmentRequest):
    return set_inbound_attachment_ocr_selected(
        attachment_ids=req.attachment_ids,
        selected=req.selected,
    )

@router.post("/inbox/attachments/auto-select-exact")
def auto_select_exact_ocr_targets(req: AutoSelectExactOcrRequest):
    """
    관리번호 exact 매칭 메일의 PDF 첨부파일을 자동 OCR 대상으로 지정한다.
    mail_id가 있으면 해당 메일만, 없으면 exact 전체 대상.
    """
    return auto_select_exact_inbound_ocr_targets(
        mail_id=req.mail_id,
    )


@router.get("/inbox/attachments/ocr-targets")
def get_selected_inbox_ocr_targets(
    limit: int = 500,
    only_pending: bool = True,
):
    """
    OCR 대상으로 저장된 수신 첨부파일 목록.
    인증서 판독/일괄 판독에서 사용한다.
    """
    return list_selected_inbound_ocr_targets(
        limit=limit,
        only_pending=only_pending,
    )

@router.post("/inbox/ocr-results/save-candidate")
def save_inbox_ocr_candidate(req: SaveOcrCandidateRequest):
    """
    OCR 실행 후 파일명/메일본문/OCR 원문 날짜 후보를 저장한다.
    """
    return save_inbound_ocr_candidate_result(
        attachment_id=req.attachment_id,
        ocr_job_id=req.ocr_job_id,
        status=req.status,
        filename=req.filename,
        best_expiry=req.best_expiry,
        expiry_candidates=req.expiry_candidates,
        filename_candidates=req.filename_candidates,
        mail_candidates=req.mail_candidates,
        ocr_candidates=req.ocr_candidates,
        message=req.message,
    )


@router.get("/inbox/mailboxes")
def get_inbox_mailboxes():
    try:
        user_email, app_password = resolve_mail_credential()

        return list_daum_mailboxes(
            user_email=user_email,
            app_password=app_password,
        )

    except Exception as e:
        return {
            "ok": False,
            "message": str(e),
            "error_type": type(e).__name__,
        }


@router.post("/inbox/cleanup-bounces")
def cleanup_inbox_bounces():
    return cleanup_bounced_inbound_records()