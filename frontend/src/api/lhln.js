import { request } from "./client";

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
