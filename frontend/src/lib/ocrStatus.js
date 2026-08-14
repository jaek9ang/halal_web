export function getEffectiveOcrStatus(item) {
  if (!item) return "READY";

  const status = String(item.status || "READY").toUpperCase();

  const blob = [
    item.status,
    item.error,
    item.error_message,
    item.message,
    item.rawText,
    item.raw_text,
    item.raw_text_preview,
    item.text,
    item.result?.raw_text,
    item.result?.raw_text_preview,
    item.result?.error,
    item.result?.error_message,
    item.result?.message,
  ]
    .filter(Boolean)
    .join("\n")
    .toLowerCase();

  if (
    blob.includes("tesseract is not installed") ||
    blob.includes("not in your path") ||
    blob.includes("tesseractnotfounderror") ||
    blob.includes("[tesseract_error]")
  ) {
    return "TESSERACT_ERROR";
  }

  if (
    blob.includes("pdfinfo") ||
    blob.includes("unable to get page count") ||
    blob.includes("[pdf_render_error]")
  ) {
    return "PDF_RENDER_ERROR";
  }

  if (
    blob.includes("cannot identify image file") ||
    blob.includes("[image_read_error]")
  ) {
    return "IMAGE_READ_ERROR";
  }

  if (
    blob.includes("scanned_need_ocr") ||
    blob.includes("[scanned_need_ocr]") ||
    blob.includes("text layer is empty") ||
    blob.includes("텍스트 레이어")
  ) {
    return "SCANNED_NEED_OCR";
  }

  if (
    blob.includes("[no_text]") ||
    blob.includes("no text") ||
    blob.includes("추출된 텍스트가 없습니다")
  ) {
    return "NO_TEXT";
  }

  if (
    status === "EXCLUDED" ||
    blob.includes("관리자 판정값이 excluded") ||
    blob.includes("ocr을 실행하지 않았습니다")
  ) {
    return "EXCLUDED";
  }

  if (status === "DONE" && (item.error || item.error_message)) {
    return "ERROR";
  }

  return status;
}
