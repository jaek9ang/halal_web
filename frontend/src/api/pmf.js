import { request } from "./client";

export function getPmfSummary() {
  return request("/pmf/summary");
}

export function syncPmf() {
  return request("/pmf/sync?force=true", {
    method: "POST",
  });
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
