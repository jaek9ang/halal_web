import { useEffect, useMemo, useRef, useState } from "react";
import { API_BASE_URL as API_BASE } from "../api/client";
import OcrRuleValidationTable, { buildRuleValidationRow, filterRuleValidationRows } from "../components/OcrRuleValidationTable";
import PageHeader from "../components/PageHeader";
import StatLine from "../components/StatLine";
import { formatFileSize } from "../lib/format";
import { getEffectiveOcrStatus } from "../lib/ocrStatus";

function OcrTestPage({ setActive }) {
  const [items, setItems] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [checkedIds, setCheckedIds] = useState([]);
  const [ocrRuleIssueFilter, setOcrRuleIssueFilter] = useState("ALL");
  const [ocrTestStatusFilter, setOcrTestStatusFilter] = useState("ALL");
  const [running, setRunning] = useState(false);

  const [uploadBusy, setUploadBusy] = useState({
    show: false,
    total: 0,
    done: 0,
    currentName: "",
  });

  const [ocrProgress, setOcrProgress] = useState({
    show: false,
    running: false,
    total: 0,
    done: 0,
    success: 0,
    error: 0,
    currentName: "",
  });

  const listRef = useRef(null);

  const selectedItem = items.find((item) => item.id === selectedId) || items[0] || null;

  const filteredItems =
    ocrTestStatusFilter === "ALL"
      ? items
      : items.filter((item) => getEffectiveOcrStatus(item) === ocrTestStatusFilter);

  const selectedStatus = getEffectiveOcrStatus(selectedItem);
  const ruleValidationRows = useMemo(
    () => items.map((item) => buildRuleValidationRow(item)),
    [items]
  );

  const filteredRuleValidationRows = useMemo(
    () => filterRuleValidationRows(ruleValidationRows, ocrRuleIssueFilter),
    [ruleValidationRows, ocrRuleIssueFilter]
  );

  function dbRowToItem(row) {
    const certificateRule =
      row.certificate_rule ||
      row.result?.certificate_rule ||
      row.result?.field_guess?.certificate_rule ||
      null;

    const next = {
      id: row.id,
      dbId: row.id,
      file: null,
      name: row.original_filename || row.saved_filename || "-",
      size: row.size_bytes || 0,
      status: row.status || "READY",
      savedPath: row.saved_path || "",
      jobId: row.ocr_job_id || "",
      rawText: row.raw_text || row.raw_text_preview || "",
      error: row.error_message || row.message || "",
      certificateRule,
      duplicated: Boolean(row.duplicated),
    };

    return {
      ...next,
      status: getEffectiveOcrStatus(next),
    };
  }

  function getOcrTestStatusLabel(status) {
    if (status === "SCANNED_NEED_OCR") return "스캔본";
    if (status === "NO_TEXT") return "텍스트 없음";
    if (status === "TESSERACT_ERROR") return "TESSERACT";
    if (status === "PDF_RENDER_ERROR") return "PDF 오류";
    if (status === "IMAGE_READ_ERROR") return "이미지 오류";
    if (status === "DONE") return "DONE";
    if (status === "RUNNING") return "RUNNING";
    if (status === "ERROR") return "ERROR";
    if (status === "READY") return "READY";
    return status || "READY";
  }

  function getOcrTestStatusClass(status) {
    if (status === "DONE") return "mini-badge ok";
    if (status === "RUNNING") return "mini-badge test";

    if (status === "SCANNED_NEED_OCR" || status === "NO_TEXT") {
      return "mini-badge warn";
    }

    if (
      status === "ERROR" ||
      status === "TESSERACT_ERROR" ||
      status === "PDF_RENDER_ERROR" ||
      status === "IMAGE_READ_ERROR"
    ) {
      return "mini-badge fail";
    }

    return "mini-badge";
  }

  function isErrorStatus(status) {
    return [
      "ERROR",
      "TESSERACT_ERROR",
      "PDF_RENDER_ERROR",
      "IMAGE_READ_ERROR",
    ].includes(status);
  }

  async function loadOcrTestFiles() {
    const response = await fetch(`${API_BASE}/ocr/test-files?limit=300`);

    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `test-files failed: ${response.status}`);
    }

    const data = await response.json();
    const nextItems = (data.rows || []).map(dbRowToItem);

    setItems(nextItems);

    if (nextItems.length > 0) {
      setSelectedId((prev) => prev || nextItems[0].id);
    }
  }

  useEffect(() => {
    loadOcrTestFiles().catch((err) => {
      console.error("OCR 테스트 목록 로드 실패:", err);
    });
  }, []);

  async function appendFiles(fileList) {
    const files = Array.from(fileList || []);

    if (files.length === 0) return;

    setUploadBusy({
      show: true,
      total: files.length,
      done: 0,
      currentName: files[0]?.name || "",
    });

    try {
      const formData = new FormData();

      files.forEach((file) => {
        formData.append("files", file);
      });

      const response = await fetch(`${API_BASE}/ocr/test-upload`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `upload failed: ${response.status}`);
      }

      const data = await response.json();
      const nextItems = (data.rows || [])
        .filter((row) => row.ok !== false)
        .map(dbRowToItem);

      setItems((prev) => {
        const map = new Map(prev.map((item) => [item.id, item]));

        nextItems.forEach((item) => {
          map.set(item.id, {
            ...map.get(item.id),
            ...item,
          });
        });

        return Array.from(map.values());
      });

      setCheckedIds((prev) => {
        const next = new Set(prev);
        nextItems.forEach((item) => next.add(item.id));
        return Array.from(next);
      });

      setSelectedId((prev) => prev || nextItems[0]?.id || null);

      for (let i = 0; i < files.length; i += 1) {
        setUploadBusy((prev) => ({
          ...prev,
          done: i + 1,
          currentName: files[i]?.name || "",
        }));

        await new Promise((resolve) => setTimeout(resolve, 60));
      }
    } finally {
      setUploadBusy({
        show: false,
        total: 0,
        done: 0,
        currentName: "",
      });
    }
  }

  function handleDrop(e) {
    e.preventDefault();
    appendFiles(e.dataTransfer.files);
  }

  function handleDragOver(e) {
    e.preventDefault();
  }

  async function runOne(item) {
    if (!item?.id) {
      throw new Error("OCR 실행 대상 파일 ID가 없습니다.");
    }

    // 1) 실행 시작 상태만 먼저 반영
    setItems((prev) =>
      prev.map((row) =>
        row.id === item.id
          ? {
              ...row,
              status: "RUNNING",
              error: "",
            }
          : row
      )
    );

    try {
      const response = await fetch(`${API_BASE}/ocr/test-files/${item.id}/run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          // Tesseract 연결 후에는 스캔 PDF/이미지 PDF도 실제 OCR 재판독한다.
          // 기존 TESSERACT_ERROR 결과를 새 엔진 상태로 검증해야 하므로 DONE도 필요 시 재실행한다.
          ocr_scanned_pages: true,
          lang: "eng",
          skip_done: false,
        }),
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `OCR 실행 실패: ${response.status}`);
      }

      const result = await response.json();
      const nextItem = dbRowToItem(result);

      const certificateRule =
        result.certificate_rule ||
        result.result?.certificate_rule ||
        result.result?.field_guess?.certificate_rule ||
        nextItem.certificateRule ||
        item.certificateRule ||
        null;

      const mergedItem = {
        ...item,
        ...nextItem,
        certificateRule,
      };

      // 2) OCR 결과 수신 후 최종 반영
      setItems((prev) =>
        prev.map((row) =>
          row.id === item.id
            ? {
                ...row,
                ...mergedItem,
                certificateRule:
                  certificateRule ||
                  row.certificateRule ||
                  null,
              }
            : row
        )
      );

      return mergedItem;
    } catch (err) {
      const message = err?.message || "OCR 실행 중 오류가 발생했습니다.";

      setItems((prev) =>
        prev.map((row) =>
          row.id === item.id
            ? {
                ...row,
                status: "ERROR",
                error: message,
              }
            : row
        )
      );

      throw err;
    }
  }

  function toggleChecked(id) {
    setCheckedIds((prev) =>
      prev.includes(id)
        ? prev.filter((x) => x !== id)
        : [...prev, id]
    );
  }

  function handleSelectAllTestFiles() {
    setCheckedIds(filteredItems.map((item) => item.id));
  }

  function handleClearAllTestFiles() {
    setCheckedIds([]);
  }

  function handleSelectNotDoneTestFiles() {
    setCheckedIds(
      items
        .filter((item) => getEffectiveOcrStatus(item) !== "DONE")
        .map((item) => item.id)
    );
  }

  function handleSelectTesseractErrorFiles() {
    setCheckedIds(
      items
        .filter((item) => getEffectiveOcrStatus(item) === "TESSERACT_ERROR")
        .map((item) => item.id)
    );
  }

  function handleClearTestList() {
    setItems([]);
    setCheckedIds([]);
    setSelectedId(null);
  }

  async function handleRunAll() {
    const targets = items.filter((item) => checkedIds.includes(item.id));

    if (items.length === 0) {
      alert("OCR 테스트할 파일을 먼저 추가하세요.");
      return;
    }

    if (targets.length === 0) {
      alert("OCR 실행할 파일을 체크하세요.");
      return;
    }

    try {
      setRunning(true);

      setOcrProgress({
        show: true,
        running: true,
        total: targets.length,
        done: 0,
        success: 0,
        error: 0,
        currentName: targets[0]?.name || "",
      });

      for (let index = 0; index < targets.length; index += 1) {
        const item = targets[index];

        setItems((prev) =>
          prev.map((row) =>
            row.id === item.id
              ? {
                  ...row,
                  status: "RUNNING",
                  error: "",
                }
              : row
          )
        );

        setOcrProgress((prev) => ({
          ...prev,
          running: true,
          currentName: item.name,
        }));

        try {
          const result = await runOne(item);
          const resultStatus = getEffectiveOcrStatus(result);

          setOcrProgress((prev) => ({
            ...prev,
            done: prev.done + 1,
            success: resultStatus === "DONE" ? prev.success + 1 : prev.success,
            error: isErrorStatus(resultStatus) ? prev.error + 1 : prev.error,
          }));
        } catch (err) {
          setItems((prev) =>
            prev.map((row) =>
              row.id === item.id
                ? {
                    ...row,
                    status: "ERROR",
                    error: err.message,
                  }
                : row
            )
          );

          setOcrProgress((prev) => ({
            ...prev,
            done: prev.done + 1,
            error: prev.error + 1,
          }));
        }
      }

      setOcrProgress((prev) => ({
        ...prev,
        running: false,
        currentName: "선택한 OCR 작업이 완료되었습니다.",
      }));
    } finally {
      setRunning(false);
    }
  }

  function handleListKeyDown(e) {
    if (!filteredItems.length) return;

    const currentIndex = Math.max(
      filteredItems.findIndex((item) => item.id === selectedItem?.id),
      0
    );

    if (e.key === "ArrowDown") {
      e.preventDefault();
      const nextIndex = Math.min(currentIndex + 1, filteredItems.length - 1);
      setSelectedId(filteredItems[nextIndex].id);
    }

    if (e.key === "ArrowUp") {
      e.preventDefault();
      const nextIndex = Math.max(currentIndex - 1, 0);
      setSelectedId(filteredItems[nextIndex].id);
    }

    if (e.key === " " || e.key === "Spacebar") {
      e.preventDefault();

      if (selectedItem?.id) {
        toggleChecked(selectedItem.id);
      }
    }
  }

  function BouncyText({ text = "문서를 분석하고 있습니다" }) {
    return (
      <div className="ocr-bouncy-text" aria-label={text}>
        {text.split("").map((ch, idx) => (
          <span
            key={`${ch}-${idx}`}
            style={{ "--bounce-index": idx }}
          >
            {ch === " " ? "\u00A0" : ch}
          </span>
        ))}
      </div>
    );
  }

  function UploadPanelOverlay() {
    if (!uploadBusy.show) return null;

    const percent =
      uploadBusy.total > 0
        ? Math.round((uploadBusy.done / uploadBusy.total) * 100)
        : 0;

    return (
      <div className="ocr-panel-overlay">
        <div className="ocr-panel-busy-card">
          <div className="ocr-orbit-loader">
            <span />
            <b>{uploadBusy.done || ""}</b>
          </div>

          <div className="ocr-panel-busy-text">
            <strong>파일을 준비하는 중</strong>
            <p>인증서 파일을 목록에 추가하고 있습니다.</p>
            <em>
              {uploadBusy.done} / {uploadBusy.total} 파일 처리 완료
            </em>

            <div className="ocr-thin-progress">
              <i style={{ width: `${percent}%` }} />
            </div>

            {uploadBusy.currentName ? (
              <small>{uploadBusy.currentName}</small>
            ) : null}
          </div>
        </div>
      </div>
    );
  }

  function OcrReadingPanel({ item }) {
    const percent =
      ocrProgress.total > 0
        ? Math.round((ocrProgress.done / ocrProgress.total) * 100)
        : 0;

    return (
      <div className="ocr-reading-panel">
        <div className="ocr-reading-ring">
          <span />
        </div>

        <BouncyText text="문서를 분석하고 있습니다" />

        <p>
          OCR 엔진이 인증서 원문을 읽고 있습니다. 완료된 파일은 왼쪽 목록에서
          바로 확인할 수 있습니다.
        </p>

        <div className="ocr-reading-file">
          <span>현재 파일</span>
          <strong>{item?.name || ocrProgress.currentName || "-"}</strong>
        </div>

        <div className="ocr-reading-progress">
          <div>
            <strong>{ocrProgress.done}</strong>
            <span>/ {ocrProgress.total} 완료</span>
          </div>

          <div className="ocr-thin-progress">
            <i style={{ width: `${percent}%` }} />
          </div>
        </div>
      </div>
    );
  }

  function OcrProgressDock() {
    if (!ocrProgress.show) return null;

    const percent =
      ocrProgress.total > 0
        ? Math.round((ocrProgress.done / ocrProgress.total) * 100)
        : 0;

    return (
      <div className={ocrProgress.running ? "ocr-progress-dock running" : "ocr-progress-dock done"}>
        <div className="ocr-progress-dock-head">
          <div>
            <span>{ocrProgress.running ? "OCR RUNNING" : "OCR COMPLETE"}</span>
            <strong>
              {ocrProgress.running ? "OCR 판독 중" : "OCR 판독 완료"}
            </strong>
          </div>

          <button
            type="button"
            onClick={() =>
              setOcrProgress((prev) => ({
                ...prev,
                show: false,
              }))
            }
          >
            ×
          </button>
        </div>

        <div className="ocr-progress-current">
          {ocrProgress.currentName || "대기 중"}
        </div>

        <div className="ocr-progress-counts">
          <span>{ocrProgress.done} / {ocrProgress.total} 완료</span>
          <span>성공 {ocrProgress.success}</span>
          <span>실패 {ocrProgress.error}</span>
        </div>

        <div className="ocr-thin-progress">
          <i style={{ width: `${percent}%` }} />
        </div>
      </div>
    );
  }

  async function handleCopyOcrText() {
    const text =
      selectedItem?.rawText ||
      selectedItem?.raw_text ||
      selectedItem?.text ||
      "";

    if (!text.trim()) {
      alert("복사할 OCR 원문이 없습니다.");
      return;
    }

    try {
      await navigator.clipboard.writeText(text);
      alert("OCR 원문 복사 완료");
    } catch (err) {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      alert("OCR 원문 복사 완료");
    }
  }

  function getOcrTestRule(item) {
    return (
      item?.certificateRule ||
      item?.certificate_rule ||
      item?.result?.certificate_rule ||
      item?.result?.field_guess?.certificate_rule ||
      null
    );
  }

  function getOcrTestRawText(item) {
    return (
      item?.rawText ||
      item?.raw_text ||
      item?.text ||
      ""
    );
  }

  function addHighlightTerm(rows, label, value, className) {
    const text = String(value || "").trim();

    if (!text || text === "-") return;
    if (text.length < 3) return;

    rows.push({
      label,
      value: text,
      className,
    });
  }

  function buildOcrTestHighlightTerms(item) {
    const rule = getOcrTestRule(item);
    const rows = [];

    const productName =
      rule?.best_product_match?.product?.name ||
      rule?.product_name ||
      rule?.englishName ||
      rule?.english_name ||
      "";

    const manufacturer =
      rule?.manufacturer ||
      rule?.maker ||
      "";

    const certOrg =
      rule?.cert_org ||
      rule?.org ||
      "";

    const certNo =
      rule?.cert_no ||
      rule?.certNo ||
      "";

    const expiry =
      rule?.expiry_date ||
      rule?.expiry ||
      "";

    const manufacturingCountry =
      rule?.manufacturing_country ||
      rule?.country ||
      "";

    const certCountry =
      rule?.cert_country ||
      rule?.certCountry ||
      "";

    addHighlightTerm(rows, "제품명", productName, "hl-product");
    addHighlightTerm(rows, "제조사", manufacturer, "hl-maker");
    addHighlightTerm(rows, "인증기관", certOrg, "hl-org");
    addHighlightTerm(rows, "인증번호", certNo, "hl-cert");

    if (certOrg !== "BPJPH") {
      addHighlightTerm(rows, "유효기간", expiry, "hl-expiry");
    }

    addHighlightTerm(rows, "제조국", manufacturingCountry, "hl-mfg-country");
    addHighlightTerm(rows, "인증국가", certCountry, "hl-cert-country");

    const seen = new Set();

    return rows
      .filter((item) => {
        const key = `${item.label}:${String(item.value || "").toUpperCase()}`;

        if (seen.has(key)) return false;

        seen.add(key);
        return true;
      })
      .sort((a, b) => String(b.value).length - String(a.value).length);
  }

  function escapeOcrRegExp(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function OcrTestHighlightedText({ item }) {
    const source = getOcrTestRawText(item);
    const terms = buildOcrTestHighlightTerms(item);

    if (!source.trim()) {
      return <>추출된 OCR 텍스트가 없습니다.</>;
    }

    if (terms.length === 0) {
      return <>{source}</>;
    }

    const pattern = new RegExp(
      `(${terms.map((term) => escapeOcrRegExp(term.value)).join("|")})`,
      "gi"
    );

    return (
      <>
        {source.split(pattern).map((part, idx) => {
          const found = terms.find(
            (term) => String(term.value).toUpperCase() === String(part).toUpperCase()
          );

          if (!found) {
            return <span key={`ocr-test-text-${idx}`}>{part}</span>;
          }

          return (
            <mark
              key={`ocr-test-mark-${idx}`}
              className={`ocr-highlight ${found.className}`}
              title={found.label}
            >
              {part}
            </mark>
          );
        })}
      </>
    );
  }

  function OcrHighlightLegend() {
    return (
      <div className="ocr-highlight-legend">
        <span className="hl-product">제품명</span>
        <span className="hl-maker">제조사</span>
        <span className="hl-org">인증기관</span>
        <span className="hl-cert">인증번호</span>
        <span className="hl-expiry">유효기간</span>
        <span className="hl-mfg-country">제조국</span>
        <span className="hl-cert-country">인증국가</span>
      </div>
    );
  }


  function OcrTestRuleSummary({ item }) {
    const rule = item?.certificateRule || item?.certificate_rule || null;

    if (!item || getEffectiveOcrStatus(item) !== "DONE") return null;

    return (
      <div className="ocr-test-rule-summary">
        <div className="ocr-test-rule-row">
          <span>업체명</span>
          <strong>{rule?.manufacturer || "-"}</strong>
        </div>

        <div className="ocr-test-rule-row">
          <span>영문명</span>
          <strong>
            {rule?.best_product_match?.product?.name ||
              rule?.product_name ||
              "-"}
          </strong>
        </div>

        <div className="ocr-test-rule-row">
          <span>제조사</span>
          <strong>{rule?.manufacturer || "-"}</strong>
        </div>

        <div className="ocr-test-rule-row">
          <span>인증기관</span>
          <strong>{rule?.cert_org || "-"}</strong>
        </div>

        <div className="ocr-test-rule-row">
          <span>인증번호</span>
          <strong>{rule?.cert_no || "-"}</strong>
        </div>

        <div className="ocr-test-rule-row">
          <span>유효기간</span>
          <strong>
            {rule?.cert_org === "BPJPH"
              ? "유지확인 대상"
              : rule?.expiry_date || "-"}
          </strong>
        </div>

        <div className="ocr-test-rule-row">
          <span>제조국</span>
          <strong>{rule?.manufacturing_country || "-"}</strong>
        </div>

        <div className="ocr-test-rule-row">
          <span>인증국가</span>
          <strong>{rule?.cert_country || "-"}</strong>
        </div>
      </div>
    );
  }

  return (
    <>
      <OcrProgressDock />

      <PageHeader
        eyebrow="OCR TEST"
        title="OCR 테스트"
        desc="인증서 파일을 여러 개 드래그해 OCR 원문이 읽히는지 빠르게 확인합니다."
        onBack={() => setActive("home")}
      />

      <StatLine
        items={[
          { label: "추가 파일", value: items.length },
          {
            label: "완료",
            value: items.filter((item) => getEffectiveOcrStatus(item) === "DONE").length,
          },
          {
            label: "오류",
            value: items.filter((item) => isErrorStatus(getEffectiveOcrStatus(item))).length,
          },
          { label: "선택 Job", value: selectedItem?.jobId || "-" },
        ]}
      />

      <section className="ocr-test-layout">
        <div className="ocr-test-list-panel ocr-test-surface">
          <UploadPanelOverlay />

          <div
            className="ocr-test-dropzone"
            onDrop={handleDrop}
            onDragOver={handleDragOver}
          >
            <strong>파일 드래그앤드랍</strong>
            <span>PDF / PNG / JPG / TIFF 파일을 여러 개 누적 추가합니다.</span>
            <label>
              파일 선택
              <input
                type="file"
                multiple
                accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff"
                onChange={(e) => {
                  appendFiles(e.target.files);
                  e.target.value = "";
                }}
              />
            </label>
          </div>

          <div className="ocr-test-actions">
            <select
              className="ocr-test-status-select"
              value={ocrTestStatusFilter}
              onChange={(e) => setOcrTestStatusFilter(e.target.value)}
              disabled={running}
            >
              <option value="ALL">전체</option>
              <option value="READY">READY</option>
              <option value="RUNNING">RUNNING</option>
              <option value="DONE">DONE</option>
              <option value="SCANNED_NEED_OCR">스캔본</option>
              <option value="NO_TEXT">텍스트 없음</option>
              <option value="ERROR">ERROR</option>
              <option value="TESSERACT_ERROR">Tesseract 오류</option>
              <option value="PDF_RENDER_ERROR">PDF 오류</option>
              <option value="IMAGE_READ_ERROR">이미지 오류</option>
            </select>

            <button
              className="ghost-action"
              type="button"
              onClick={handleSelectAllTestFiles}
              disabled={running || filteredItems.length === 0}
            >
              전체선택
            </button>

            <button
              className="ghost-action"
              type="button"
              onClick={handleClearAllTestFiles}
              disabled={running || checkedIds.length === 0}
            >
              전체해제
            </button>

            <button
              className="ghost-action"
              type="button"
              onClick={handleSelectNotDoneTestFiles}
              disabled={running || items.length === 0}
            >
              미완료선택
            </button>

            <button
              className="ghost-action"
              type="button"
              onClick={handleSelectTesseractErrorFiles}
              disabled={running || items.length === 0}
            >
              Tesseract 오류선택
            </button>

            <button
              className="primary-button"
              type="button"
              onClick={handleRunAll}
              disabled={running || checkedIds.length === 0}
            >
              {running ? "OCR 실행 중." : `선택 OCR 실행 ${checkedIds.length}건`}
            </button>

            <button
              className="ghost-action"
              type="button"
              onClick={handleClearTestList}
              disabled={running || items.length === 0}
            >
              목록 비우기
            </button>
          </div>

          <div className="ocr-history-table-head ocr-test-table-head">
            <div>선택</div>
            <div>상태</div>
            <div>파일명</div>
            <div>크기</div>
            <div>Job</div>
          </div>

          <div
            className="ocr-history-table-body ocr-test-table-body"
            ref={listRef}
            tabIndex={0}
            onKeyDown={handleListKeyDown}
          >
            {filteredItems.length === 0 ? (
              <div className="mail-log-empty">표시할 OCR 테스트 파일이 없습니다.</div>
            ) : (
              filteredItems.map((item) => {
                const effectiveStatus = getEffectiveOcrStatus(item);

                return (
                  <button
                    key={item.id}
                    className={selectedItem?.id === item.id ? "ocr-test-row active" : "ocr-test-row"}
                    onClick={() => {
                      listRef.current?.focus();
                      setSelectedId(item.id);
                    }}
                  >
                    <div>
                      <input
                        type="checkbox"
                        checked={checkedIds.includes(item.id)}
                        onChange={(e) => {
                          e.stopPropagation();
                          toggleChecked(item.id);
                        }}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </div>

                    <div>
                      <span className={getOcrTestStatusClass(effectiveStatus)}>
                        {getOcrTestStatusLabel(effectiveStatus)}
                      </span>
                    </div>

                    <div className="subject-cell">{item.name}</div>
                    <div>{formatFileSize(item.size)}</div>
                    <div>{item.jobId || "-"}</div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        <div className="ocr-test-result-panel">
          <div className="mail-log-preview-head fixed-title-head ocr-test-result-head">
            <div>
              <div className="surface-title fixed-panel-label">OCR 결과</div>
              <div className="ocr-file-title-soft" title={selectedItem?.name || ""}>
                {selectedItem?.name || "파일을 선택하세요"}
              </div>
            </div>

            <button
              type="button"
              className="soft-chip-action"
              onClick={handleCopyOcrText}
              disabled={
                !selectedItem ||
                selectedStatus !== "DONE" ||
                !(
                  selectedItem.rawText ||
                  selectedItem.raw_text ||
                  selectedItem.text
                )
              }
            >
              원문 복사
            </button>
          </div>

          {selectedItem ? (
            <>
              <div className="ocr-test-meta-line">
                <span>
                  상태 ㅣ <b>{getOcrTestStatusLabel(selectedStatus)}</b>
                </span>
                <span>Job ㅣ <b>{selectedItem.jobId || "-"}</b></span>
                <span>저장경로 ㅣ <b>{selectedItem.savedPath || "-"}</b></span>
              </div>

              {selectedItem.error ? (
                <div className="error-box">{selectedItem.error}</div>
              ) : null}

              <div className="ocr-test-result-stage">
                {selectedStatus === "RUNNING" ? (
                  <OcrReadingPanel item={selectedItem} />
                ) : selectedStatus === "TESSERACT_ERROR" ? (
                  <div className="ocr-test-error-panel tesseract">
                    <strong>Tesseract OCR 엔진 오류</strong>
                    <p>{selectedItem?.name || "-"}</p>
                    <em>
                      {selectedItem?.error ||
                        "Tesseract OCR 처리 중 오류가 발생했습니다. 과거 실패 이력일 수 있으므로, Tesseract 연결 후 선택 OCR 실행으로 재판독하세요."}
                    </em>
                  </div>
                ) : selectedStatus === "SCANNED_NEED_OCR" || selectedStatus === "NO_TEXT" ? (
                  <div className="ocr-test-scan-panel">
                    <strong>스캔본 분류</strong>
                    <p>{selectedItem?.name || "-"}</p>
                    <em>
                      텍스트 레이어가 없어 빠른 판독에서는 원문을 추출하지 않았습니다.
                      스캔 OCR 엔진 연결 단계에서 별도 처리합니다.
                    </em>
                  </div>
                ) : isErrorStatus(selectedStatus) ? (
                  <div className="ocr-test-error-panel">
                    <strong>OCR 실패</strong>
                    <p>{selectedItem?.name || "-"}</p>
                    <em>{selectedItem?.error || "OCR 처리 중 오류가 발생했습니다."}</em>
                  </div>
                ) : selectedStatus === "DONE" ? (
                  <>
                    <OcrTestRuleSummary item={selectedItem} />

                    <OcrHighlightLegend />

                    <div className="ocr-text-box refined ocr-test-result-text highlighted">
                      <OcrTestHighlightedText item={selectedItem} />
                    </div>
                  </>
                ) : (
                  <div className="ocr-test-idle-panel">
                    <strong>OCR 대기 중</strong>
                    <p>파일을 체크한 뒤 선택 OCR 실행을 누르면 원문 판독을 시작합니다.</p>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="mail-log-empty">선택된 파일이 없습니다.</div>
          )}
        </div>
      </section>

      <OcrRuleValidationTable
        rows={filteredRuleValidationRows}
        allRows={ruleValidationRows}
        filterValue={ocrRuleIssueFilter}
        onFilterChange={setOcrRuleIssueFilter}
        onSelectRow={(row) => {
          setSelectedId(row.id);
          listRef.current?.focus();
        }}
      />
    </>
  );
}

export default OcrTestPage;
