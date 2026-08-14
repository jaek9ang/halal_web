import { request, API_BASE_URL } from "./client";

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
