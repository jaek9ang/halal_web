const OCR_RULE_VALIDATION_FILTERS = [
  { value: "ALL", label: "전체" },
  { value: "ISSUE_ONLY", label: "문제 있음" },
  { value: "CERT_NO_MISSING", label: "인증번호 없음" },
  { value: "EXPIRY_MISSING", label: "유효기간 없음" },
  { value: "MANUFACTURER_MISSING", label: "제조사 없음" },
  { value: "PRODUCT_MISSING", label: "제품명 없음" },
  { value: "COUNTRY_MISSING", label: "제조국 없음" },
  { value: "CERT_COUNTRY_MISSING", label: "인증국가 없음" },
  { value: "LOW_CONFIDENCE", label: "LOW_CONFIDENCE" },
  { value: "TESSERACT_ERROR", label: "Tesseract 오류" },
  { value: "SCANNED_NEED_OCR", label: "스캔본" },
  { value: "NO_TEXT", label: "텍스트 없음" },
];

const OCR_RULE_ISSUE_LABELS = {
  RULE_MISSING: "규칙 없음",
  ORG_MISSING: "기관 없음",
  MANUFACTURER_MISSING: "제조사 없음",
  PRODUCT_MISSING: "제품명 없음",
  CERT_NO_MISSING: "인증번호 없음",
  EXPIRY_MISSING: "유효기간 없음",
  COUNTRY_MISSING: "제조국 없음",
  CERT_COUNTRY_MISSING: "인증국가 없음",
  LOW_CONFIDENCE: "저신뢰",
  TESSERACT_ERROR: "Tesseract",
  PDF_RENDER_ERROR: "PDF 오류",
  IMAGE_READ_ERROR: "이미지 오류",
  SCANNED_NEED_OCR: "스캔본",
  NO_TEXT: "텍스트 없음",
  ERROR: "오류",
  RUNNING: "진행 중",
  READY: "대기",
};

function isBlankRuleValue(value) {
  const text = String(value || "").trim();

  return !text || text === "-" || text.toUpperCase() === "UNKNOWN";
}

function getRuleFromItem(item) {
  return (
    item?.certificateRule ||
    item?.certificate_rule ||
    item?.result?.certificate_rule ||
    item?.result?.field_guess?.certificate_rule ||
    null
  );
}

function resolveOcrStatusForValidation(item) {
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

function getRuleProductName(rule) {
  return (
    rule?.best_product_match?.product?.name ||
    rule?.product_name ||
    rule?.englishName ||
    rule?.english_name ||
    ""
  );
}

export function buildRuleValidationRow(item) {
  const rule = getRuleFromItem(item);
  const status = resolveOcrStatusForValidation(item);
  const org = rule?.cert_org || rule?.org || "";

  const expiry =
    org === "BPJPH"
      ? "유지확인"
      : rule?.expiry_date || rule?.expiry || "";

  return {
    id: item?.id,
    filename: item?.name || item?.filename || "-",
    status,
    org,
    manufacturer: rule?.manufacturer || rule?.maker || "",
    productName: getRuleProductName(rule),
    certNo: rule?.cert_no || rule?.certNo || "",
    expiry,
    manufacturingCountry:
      rule?.manufacturing_country ||
      rule?.country ||
      "",
    certCountry:
      rule?.cert_country ||
      rule?.certCountry ||
      "",
    parseStatus:
      rule?.parse_status ||
      rule?.confidence ||
      "",
    rule,
  };
}

function getRuleValidationIssues(row) {
  const issues = [];

  if (!row) return ["RULE_MISSING"];

  if (row.status === "TESSERACT_ERROR") return ["TESSERACT_ERROR"];
  if (row.status === "PDF_RENDER_ERROR") return ["PDF_RENDER_ERROR"];
  if (row.status === "IMAGE_READ_ERROR") return ["IMAGE_READ_ERROR"];
  if (row.status === "SCANNED_NEED_OCR") return ["SCANNED_NEED_OCR"];
  if (row.status === "NO_TEXT") return ["NO_TEXT"];
  if (row.status === "ERROR") return ["ERROR"];
  if (row.status === "RUNNING") return ["RUNNING"];
  if (row.status !== "DONE") return [row.status || "READY"];

  if (!row.rule) issues.push("RULE_MISSING");
  if (isBlankRuleValue(row.org)) issues.push("ORG_MISSING");
  if (isBlankRuleValue(row.manufacturer)) issues.push("MANUFACTURER_MISSING");
  if (isBlankRuleValue(row.productName)) issues.push("PRODUCT_MISSING");
  if (isBlankRuleValue(row.certNo)) issues.push("CERT_NO_MISSING");

  if (row.org !== "BPJPH" && isBlankRuleValue(row.expiry)) {
    issues.push("EXPIRY_MISSING");
  }

  if (isBlankRuleValue(row.manufacturingCountry)) issues.push("COUNTRY_MISSING");
  if (isBlankRuleValue(row.certCountry)) issues.push("CERT_COUNTRY_MISSING");

  const parseText = String(row.parseStatus || "").toUpperCase();
  const confidenceValue = Number(row.parseStatus);

  if (
    parseText.includes("LOW_CONFIDENCE") ||
    (!Number.isNaN(confidenceValue) && confidenceValue > 0 && confidenceValue < 0.6)
  ) {
    issues.push("LOW_CONFIDENCE");
  }

  return issues;
}

export function filterRuleValidationRows(rows, filterValue) {
  if (filterValue === "ALL") return rows;

  return rows.filter((row) => {
    const issues = getRuleValidationIssues(row);

    if (filterValue === "ISSUE_ONLY") {
      return issues.length > 0;
    }

    return issues.includes(filterValue);
  });
}

function formatRuleIssueLabel(issue) {
  return OCR_RULE_ISSUE_LABELS[issue] || issue || "-";
}

function OcrRuleValidationTable({
  rows,
  allRows,
  filterValue,
  onFilterChange,
  onSelectRow,
}) {
  const totalCount = allRows.length;
  const issueCount = allRows.filter((row) => getRuleValidationIssues(row).length > 0).length;
  const okCount = totalCount - issueCount;

  return (
    <section className="ocr-rule-validation-surface">
      <div className="ocr-rule-validation-headbar">
        <div>
          <span>RULE CHECK</span>
          <strong>규칙 판독 검증표</strong>
          <p>
            파일별 기관, 제조사, 제품명, 인증번호, 유효기간, 제조국, 인증국가 추출 상태를 확인합니다.
          </p>
        </div>

        <div className="ocr-rule-validation-actions">
          <div className="ocr-rule-validation-counts">
            <span>전체 {totalCount}</span>
            <span>정상 {okCount}</span>
            <span>확인 {issueCount}</span>
          </div>

          <select
            value={filterValue}
            onChange={(e) => onFilterChange(e.target.value)}
          >
            {OCR_RULE_VALIDATION_FILTERS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="ocr-rule-validation-scroll">
        <div className="ocr-rule-validation-table-head">
          <div>파일명</div>
          <div>상태</div>
          <div>기관</div>
          <div>제조사</div>
          <div>제품명</div>
          <div>인증번호</div>
          <div>유효기간</div>
          <div>제조국</div>
          <div>인증국가</div>
          <div>판정</div>
        </div>

        <div className="ocr-rule-validation-table-body">
          {rows.length === 0 ? (
            <div className="ocr-rule-validation-empty">
              표시할 검증 결과가 없습니다.
            </div>
          ) : (
            rows.map((row) => {
              const issues = getRuleValidationIssues(row);
              const firstIssue = issues[0] || "OK";

              return (
                <button
                  key={row.id || row.filename}
                  type="button"
                  className={
                    issues.length > 0
                      ? "ocr-rule-validation-row warn"
                      : "ocr-rule-validation-row ok"
                  }
                  onClick={() => onSelectRow(row)}
                >
                  <div className="is-left" title={row.filename}>
                    {row.filename}
                  </div>

                  <div title={row.status}>
                    <span className={issues.length > 0 ? "mini-badge warn" : "mini-badge ok"}>
                      {row.status}
                    </span>
                  </div>

                  <div title={row.org || "-"}>
                    {row.org || "-"}
                  </div>

                  <div className="is-left" title={row.manufacturer || "-"}>
                    {row.manufacturer || "-"}
                  </div>

                  <div className="is-left" title={row.productName || "-"}>
                    {row.productName || "-"}
                  </div>

                  <div title={row.certNo || "-"}>
                    {row.certNo || "-"}
                  </div>

                  <div title={row.expiry || "-"}>
                    {row.expiry || "-"}
                  </div>

                  <div title={row.manufacturingCountry || "-"}>
                    {row.manufacturingCountry || "-"}
                  </div>

                  <div title={row.certCountry || "-"}>
                    {row.certCountry || "-"}
                  </div>

                  <div title={issues.map(formatRuleIssueLabel).join(", ") || "정상"}>
                    <span className={issues.length > 0 ? "rule-check-badge warn" : "rule-check-badge ok"}>
                      {issues.length > 0 ? formatRuleIssueLabel(firstIssue) : "정상"}
                    </span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>
    </section>
  );
}

export default OcrRuleValidationTable;
