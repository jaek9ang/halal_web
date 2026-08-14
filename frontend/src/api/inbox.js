import { request } from "./client";

export function getInboxMailboxes() {
  return request("/mail/inbox/mailboxes");
}

export function syncInboxMail({
  mailboxes = ["Inbox", "HALAL &x3jJncEc-"],
  days = 14,
  limit = 30,
  only_with_attachments = true,
} = {}) {
  return request("/mail/inbox/sync", {
    method: "POST",
    body: JSON.stringify({
      user_email: "",
      app_password: "",
      mailboxes,
      days,
      limit,
      only_with_attachments,
    }),
  });
}

export function getInboxMessages({
  match_status = "",
  mailbox = "",
  include_excluded = false,
  limit = 100,
} = {}) {
  const params = new URLSearchParams({
    match_status,
    mailbox,
    include_excluded: String(include_excluded),
    limit: String(limit),
  });

  return request(`/mail/inbox/messages?${params.toString()}`);
}

export function getInboxAttachments({
  request_id = "",
  mailbox = "",
  limit = 200,
} = {}) {
  const params = new URLSearchParams({
    request_id,
    mailbox,
    limit: String(limit),
  });

  return request(`/mail/inbox/attachments?${params.toString()}`);
}

export function openInboxAttachmentFolder(saved_path) {
  return request("/mail/inbox/attachments/open-folder", {
    method: "POST",
    body: JSON.stringify({
      saved_path,
    }),
  });
}

export function getInboxMessageDetail(mailId) {
  return request(`/mail/inbox/messages/${mailId}`);
}

export function excludeInboxMessages({
  mail_ids = [],
  excluded = true,
  reason = "사용자 제외",
} = {}) {
  return request("/mail/inbox/messages/exclude", {
    method: "POST",
    body: JSON.stringify({
      mail_ids,
      excluded,
      reason,
    }),
  });
}

export function selectInboxAttachmentsForOcr({
  attachment_ids = [],
  selected = true,
} = {}) {
  return request("/mail/inbox/attachments/ocr-select", {
    method: "POST",
    body: JSON.stringify({
      attachment_ids,
      selected,
    }),
  });
}

export function autoSelectExactInboxOcrTargets({ mail_id = null } = {}) {
  return request("/mail/inbox/attachments/auto-select-exact", {
    method: "POST",
    body: JSON.stringify({
      mail_id,
    }),
  });
}

export function getInboxOcrTargets({
  limit = 500,
  only_pending = true,
} = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    only_pending: String(only_pending),
  });

  return request(`/mail/inbox/attachments/ocr-targets?${params.toString()}`);
}

export function saveInboxOcrCandidateResult({
  attachment_id,
  ocr_job_id = null,
  status = "",
  filename = "",
  best_expiry = "",
  expiry_candidates = [],
  filename_candidates = [],
  mail_candidates = [],
  ocr_candidates = [],
  message = "",
} = {}) {
  return request("/mail/inbox/ocr-results/save-candidate", {
    method: "POST",
    body: JSON.stringify({
      attachment_id,
      ocr_job_id,
      status,
      filename,
      best_expiry,
      expiry_candidates,
      filename_candidates,
      mail_candidates,
      ocr_candidates,
      message,
    }),
  });
}
