const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API Error ${res.status}: ${text}`);
  }

  return res.json();
}

export function getHealth() {
  return request("/health");
}

export function getPmfSummary() {
  return request("/pmf/summary");
}

export function syncPmf() {
  return request("/pmf/sync?force=true", {
    method: "POST",
  });
}

export function getSupplierEmailReview() {
  return request("/suppliers/email-review");
}

export function saveSupplierEmailOverride(payload) {
  return request("/suppliers/email-overrides", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getMailTargets({
  testMode = true,
  testReceiver = "jaek_ing@naver.com",
} = {}) {
  const params = new URLSearchParams({
    test_mode: String(testMode),
    test_receiver: testReceiver,
  });

  return request(`/mail/targets?${params.toString()}`);
}

export function sendMailRequests(payload) {
  return request("/mail/send", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getMailLogs({ limit = 100, testMode = null } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
  });

  if (testMode !== null) {
    params.set("test_mode", String(testMode));
  }

  return request(`/mail/logs?${params.toString()}`);
}

export function hideMailLogs({ ids, includeReal = false }) {
  return request("/mail/logs/hide", {
    method: "POST",
    body: JSON.stringify({
      ids,
      include_real: includeReal,
    }),
  });
}

export function getLhlnStatus() {
  return request("/lhln/status");
}

export function syncLhln() {
  return request("/lhln/sync", {
    method: "POST",
  });
}

export function getLhlnRecords({ country = "", keyword = "", limit = 300 } = {}) {
  const params = new URLSearchParams({
    country,
    keyword,
    limit: String(limit),
  });

  return request(`/lhln/records?${params.toString()}`);
}

export function createLhlnPdf() {
  return request("/lhln/create-pdf", {
    method: "POST",
  });
}

export function getOcrFiles({ limit = 300 } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
  });

  return request(`/ocr/files?${params.toString()}`);
}

export function createOcrJob(payload) {
  return request("/ocr/jobs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getOcrJobs({
  limit = 100,
  status = "",
  org = "",
  keyword = "",
  include_test = false,
} = {}) {
  const params = new URLSearchParams();

  params.set("limit", String(limit));

  if (status) params.set("status", status);
  if (org) params.set("org", org);
  if (keyword) params.set("keyword", keyword);
  if (include_test) params.set("include_test", "true");

  return request(`/ocr/jobs?${params.toString()}`);
}

export function getOcrJob(jobId) {
  return request(`/ocr/jobs/${jobId}`);
}

export async function downloadOcrDataExport({
  limit = 10000,
  includeOcrJobs = true,
  includeOcrTests = true,
  saveLatestForAi = false,
} = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    include_ocr_jobs: String(includeOcrJobs),
    include_ocr_tests: String(includeOcrTests),
    save_latest_for_ai: String(saveLatestForAi),
  });

  const res = await fetch(`${API_BASE_URL}/ocr/data-export?${params.toString()}`);

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API Error ${res.status}: ${text}`);
  }

  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") || "";

  const filenameMatch =
    disposition.match(/filename\*=UTF-8''([^;]+)/) ||
    disposition.match(/filename="?([^"]+)"?/);

  const filename = filenameMatch
    ? decodeURIComponent(filenameMatch[1])
    : "ocr_data_export.zip";

  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");

  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();

  window.URL.revokeObjectURL(url);

  return {
    ok: true,
    filename,
    recordCount: res.headers.get("x-export-record-count") || "",
    exportVersion: res.headers.get("x-export-version") || "",
    savedLatestForAi: res.headers.get("x-saved-latest-for-ai") === "true",
    latestExportPath: res.headers.get("x-latest-export-path") || "",
  };
}

export function searchPmfMaterials({ keyword = "", limit = 100 } = {}) {
  const params = new URLSearchParams({
    keyword,
    limit: String(limit),
  });

  return request(`/pmf/materials/search?${params.toString()}`);
}

export function getPmfMaterialDetail(rowPos) {
  return request(`/pmf/materials/${rowPos}`);
}

export function getPmfMaterialRelatedFiles(rowPos, { limit = 30 } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
  });

  return request(`/pmf/materials/${rowPos}/related-files?${params.toString()}`);
}

export function getPmfMaterialHalalDocs(rowPos, { limit = 50 } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
  });

  return request(`/pmf/materials/${rowPos}/halal-docs?${params.toString()}`);
}

export function makeHalalDocFileUrl(path) {
  return `${API_BASE_URL}/pmf/halal-docs/file?path=${encodeURIComponent(path)}`;
}


export function getPmfMaterialHalalFolder(rowPos) {
  return request(`/pmf/materials/${rowPos}/halal-folder`);
}

export function openHalalDocFolder(path) {
  const params = new URLSearchParams({
    path,
  });

  return request(`/pmf/halal-docs/open-folder?${params.toString()}`, {
    method: "POST",
  });
}

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

export async function uploadOcrManualFiles(files) {
  const formData = new FormData();

  Array.from(files || []).forEach((file) => {
    formData.append("files", file);
  });

  const res = await fetch(`${API_BASE_URL}/ocr/manual-upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API Error ${res.status}: ${text}`);
  }

  return res.json();
}

export function deleteOcrJobs(jobIds) {
  return request("/ocr/jobs", {
    method: "DELETE",
    body: JSON.stringify({
      job_ids: jobIds,
    }),
  });
}

export function getOcrFailureSummary({
  limit = 300,
  keyword = "",
  include_test = true,
  hide_stale_tesseract = true,
  latest_only = false,
} = {}) {
  const params = new URLSearchParams();

  params.set("limit", String(limit));
  params.set("include_test", String(include_test));
  params.set("hide_stale_tesseract", String(hide_stale_tesseract));
  params.set("latest_only", String(latest_only));

  if (keyword) {
    params.set("keyword", keyword);
  }

  return request(`/ocr/failure-summary?${params.toString()}`);
}

export function deleteStaleTesseractHistory({
  include_test = true,
} = {}) {
  const params = new URLSearchParams({
    include_test: String(include_test),
  });

  return request(`/ocr/failure-summary/stale-tesseract?${params.toString()}`, {
    method: "DELETE",
  });
}

export function getAiRuleReviewStatus() {
  return request("/ai-rule-review/status");
}

export function analyzeAiRuleExport({
  export_path = "",
  limit = 10000,
  max_cases = 20,
  model = "",
  save_candidates = true,
} = {}) {
  return request("/ai-rule-review/analyze-export", {
    method: "POST",
    body: JSON.stringify({
      export_path,
      limit,
      max_cases,
      model,
      save_candidates,
    }),
  });
}

export function getAiRuleProblemCases({
  export_path = "",
  limit = 10000,
  max_cases = 40,
} = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    max_cases: String(max_cases),
  });

  if (export_path) {
    params.set("export_path", export_path);
  }

  return request(`/ai-rule-review/problem-cases?${params.toString()}`);
}

export function getAiRuleCandidates({
  limit = 100,
  apply_status = "",
  target_org = "",
  target_field = "",
} = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
  });

  if (apply_status) params.set("apply_status", apply_status);
  if (target_org) params.set("target_org", target_org);
  if (target_field) params.set("target_field", target_field);

  return request(`/ai-rule-review/candidates?${params.toString()}`);
}

export function getAiRuleCandidateDetail(rule_candidate_id) {
  return request(`/ai-rule-review/candidates/${encodeURIComponent(rule_candidate_id)}`);
}

export function validateAiRuleCandidate(rule_candidate_id, {
  export_path = "",
  limit = 10000,
} = {}) {
  return request(`/ai-rule-review/candidates/${encodeURIComponent(rule_candidate_id)}/validate`, {
    method: "POST",
    body: JSON.stringify({
      export_path,
      limit,
    }),
  });
}

export function applyAiRuleCandidate(rule_candidate_id, {
  validation_report_id = "",
  actor = "user",
} = {}) {
  return request(`/ai-rule-review/candidates/${encodeURIComponent(rule_candidate_id)}/apply`, {
    method: "POST",
    body: JSON.stringify({
      validation_report_id,
      actor,
    }),
  });
}

export function rejectAiRuleCandidate(rule_candidate_id, {
  reason = "",
  actor = "user",
} = {}) {
  return request(`/ai-rule-review/candidates/${encodeURIComponent(rule_candidate_id)}/reject`, {
    method: "POST",
    body: JSON.stringify({
      reason,
      actor,
    }),
  });
}

export function getAiRuleValidationReports({ limit = 100 } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
  });

  return request(`/ai-rule-review/reports?${params.toString()}`);
}

export function getAiRuleValidationReport(validation_report_id) {
  return request(`/ai-rule-review/reports/${encodeURIComponent(validation_report_id)}`);
}

export function getAiRuleHistory({ limit = 200 } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
  });

  return request(`/ai-rule-review/history?${params.toString()}`);
}

export function getAiRuleOverrides() {
  return request("/ai-rule-review/overrides");
}

export function getFilingStatus() {
  return request("/certificate-filing/status");
}

export function getFilingCandidates({ limit = 10 } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
  });

  return request(`/certificate-filing/candidates?${params.toString()}`);
}

export function previewCertificateFiling({
  ocr_job_id,
  pmf_row_pos,
  pmf_depth = 0,
} = {}) {
  return request("/certificate-filing/preview", {
    method: "POST",
    body: JSON.stringify({
      ocr_job_id,
      pmf_row_pos,
      pmf_depth,
    }),
  });
}

export function confirmCertificateFiling({
  ocr_job_id,
  pmf_row_pos,
  pmf_depth = 0,
  overwrite = false,
  force = false,
  allow_date_regression = false,
  change_action = "",
} = {}) {
  return request("/certificate-filing/confirm", {
    method: "POST",
    body: JSON.stringify({
      ocr_job_id,
      pmf_row_pos,
      pmf_depth,
      overwrite,
      force,
      allow_date_regression,
      change_action,
    }),
  });
}
