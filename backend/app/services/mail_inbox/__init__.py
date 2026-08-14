"""수신메일 처리.

원래 mail_inbox_service.py 한 파일(2,057줄)이었다.

의존 방향:
    text -> parsing -> store -> matching -> sync -> queries -> ocr_targets"""

from __future__ import annotations

from app.services.mail_inbox.text import (
    HALAL_INBOUND_KEYWORDS,
    REQUEST_ID_PATTERN,
    decode_mime_text,
    extract_simple_terms,
    find_request_id,
    is_exact_pdf_ocr_candidate,
    is_ocr_candidate_attachment,
    normalize_candidate_text,
    normalize_mail_subject,
    now_text,
    parse_received_at,
    quote_imap_mailbox,
    safe_filename,
    strip_html_text,
    to_iso_date,
)
from app.services.mail_inbox.parsing import (
    extract_body_text,
    extract_date_candidates_from_text,
    get_attachment_parts,
    is_bounce_mail,
    merge_expiry_candidates,
)
from app.services.mail_inbox.store import (
    get_db_conn,
    init_inbound_ocr_candidate_table,
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
from app.services.mail_inbox.sync import (
    list_daum_mailboxes,
    sync_daum_inbox_attachments,
    sync_daum_multiple_mailboxes,
)
from app.services.mail_inbox.queries import (
    cleanup_bounced_inbound_records,
    get_inbound_mail_detail,
    list_inbound_attachments,
    list_inbound_mails,
    open_inbound_attachment_folder,
    set_inbound_attachment_ocr_selected,
    set_inbound_mail_excluded,
)
from app.services.mail_inbox.ocr_targets import (
    auto_select_exact_inbound_ocr_targets,
    list_selected_inbound_ocr_targets,
    save_inbound_ocr_candidate_result,
)

__all__ = [
    "HALAL_INBOUND_KEYWORDS",
    "REQUEST_ID_PATTERN",
    "auto_select_exact_inbound_ocr_targets",
    "cleanup_bounced_inbound_records",
    "decode_mime_text",
    "evaluate_inbound_mail_candidate",
    "extract_body_text",
    "extract_date_candidates_from_text",
    "extract_simple_terms",
    "find_request_id",
    "get_attachment_parts",
    "get_db_conn",
    "get_inbound_mail_detail",
    "get_sent_mail_reference_context",
    "init_inbound_ocr_candidate_table",
    "init_inbox_tables",
    "insert_attachment",
    "insert_inbound_mail",
    "is_bounce_mail",
    "is_exact_pdf_ocr_candidate",
    "is_ocr_candidate_attachment",
    "list_daum_mailboxes",
    "list_inbound_attachments",
    "list_inbound_mails",
    "list_selected_inbound_ocr_targets",
    "make_download_dir",
    "merge_expiry_candidates",
    "normalize_candidate_text",
    "normalize_mail_subject",
    "now_text",
    "open_inbound_attachment_folder",
    "parse_received_at",
    "quote_imap_mailbox",
    "safe_filename",
    "save_inbound_ocr_candidate_result",
    "save_message_files",
    "set_inbound_attachment_ocr_selected",
    "set_inbound_mail_excluded",
    "strip_html_text",
    "sync_daum_inbox_attachments",
    "sync_daum_multiple_mailboxes",
    "to_iso_date",
]
