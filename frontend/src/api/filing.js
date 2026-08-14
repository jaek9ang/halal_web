import { request } from "./client";

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
