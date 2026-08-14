export function formatOcrTableDate(value) {
  const text = String(value || "").trim();

  if (!text) return "-";

  return text
    .replace("T", " ")
    .replace(/\.\d+$/, "")
    .slice(0, 16);
}

export function formatFileSize(value) {
  const n = Number(value || 0);
  if (!n) return "-";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
