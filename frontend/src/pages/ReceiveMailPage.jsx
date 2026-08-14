import { useEffect, useRef, useState } from "react";
import {
  autoSelectExactInboxOcrTargets,
  createOcrJob,
  excludeInboxMessages,
  getInboxAttachments,
  getInboxMessageDetail,
  getInboxMessages,
  getInboxOcrTargets,
  getOcrJob,
  openInboxAttachmentFolder,
  saveInboxOcrCandidateResult,
  selectInboxAttachmentsForOcr,
  syncInboxMail,
} from "../api";
import PageHeader from "../components/PageHeader";
import StatLine from "../components/StatLine";

function ReceiveMailPage({ setActive }) {
  const HALAL_MAILBOX = "HALAL &x3jJncEc-";

  const [days, setDays] = useState(30);
  const [limit, setLimit] = useState(100);
  const [matchStatus, setMatchStatus] = useState("");
  const [includeExcluded, setIncludeExcluded] = useState(false);

  const [mails, setMails] = useState([]);
  const [attachments, setAttachments] = useState([]);
  const [selectedMail, setSelectedMail] = useState(null);
  const [selectedMailDetail, setSelectedMailDetail] = useState(null);

  const [checkedMailIds, setCheckedMailIds] = useState([]);
  const [ocrSelectedIds, setOcrSelectedIds] = useState([]);
  const [ocrRunning, setOcrRunning] = useState(false);
  const [ocrResults, setOcrResults] = useState([]);
  const [ocrError, setOcrError] = useState("");

  const [loading, setLoading] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const mailListRef = useRef(null);

  function displayMailboxName(name) {
    if (name === HALAL_MAILBOX) return "HALAL 인증서";
    if (name === "Inbox") return "받은메일함";
    return name || "-";
  }

  function getStatusLabel(status) {
    if (status === "exact") return "exact";
    if (status === "probable") return "probable";
    return "candidate";
  }

  function getReasonShort(reason) {
    const text = String(reason || "").trim();

    if (!text) return "-";
    if (text.includes("관리번호 직접")) return "관리번호 직접 발견";
    if (text.includes("발송 제목")) return "발송 제목 유사";
    if (text.includes("할랄 키워드")) return "할랄 키워드";
    if (text.length > 34) return `${text.slice(0, 34)}...`;

    return text;
  }

  function cleanMailBody(value) {
    return String(value || "")
      .replace(/p\{margin-top:0;margin-bottom:0\}/gi, "")
      .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "")
      .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, "")
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/p>/gi, "\n")
      .replace(/<[^>]+>/g, " ")
      .replace(/&lt;/gi, "<")
      .replace(/&gt;/gi, ">")
      .replace(/&amp;/gi, "&")
      .replace(/&quot;/gi, '"')
      .replace(/&#39;/gi, "'")
      .replace(/&nbsp;/gi, " ")
      .replace(/---------\s*원본 메일\s*---------/g, "\n--------- 원본 메일 ---------\n")
      .replace(/(보낸사람\s*:)/g, "\n$1")
      .replace(/(받는사람\s*:)/g, "\n$1")
      .replace(/(날짜\s*:)/g, "\n$1")
      .replace(/(제목\s*:)/g, "\n$1")
      .replace(/(첨부파일\s*:)/g, "\n$1")
      .replace(/[ \t]+/g, " ")
      .replace(/\n\s+/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function parseCandidateJson(value) {
    try {
      if (!value) return [];
      if (Array.isArray(value)) return value;

      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return [];
    }
  }

  function normalizeOcrText(value) {
    return String(value || "")
      .replace(/&nbsp;/gi, " ")
      .replace(/\r/g, "\n")
      .replace(/[ \t]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function toIsoDate(year, month, day) {
    const y = Number(year);
    const m = Number(month);
    const d = Number(day);

    if (!y || !m || !d) return "";
    if (y < 2000 || y > 2100) return "";
    if (m < 1 || m > 12) return "";
    if (d < 1 || d > 31) return "";

    return `${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  }

  function extractExpiryCandidatesFromText(rawText, source = "ocr") {
    const text = normalizeOcrText(rawText);
    const low = text.toLowerCase();

    const monthMap = {
      jan: 1, january: 1,
      feb: 2, february: 2,
      mar: 3, march: 3,
      apr: 4, april: 4,
      may: 5,
      jun: 6, june: 6,
      jul: 7, july: 7,
      aug: 8, august: 8,
      sep: 9, sept: 9, september: 9,
      oct: 10, october: 10,
      nov: 11, november: 11,
      dec: 12, december: 12,
    };

    const candidates = [];

    function addCandidate(dateText, index, raw, pattern) {
      if (!dateText) return;

      const start = Math.max(0, index - 100);
      const end = Math.min(low.length, index + 140);
      const around = low.slice(start, end);

      const anchors = [
        "valid",
        "validity",
        "until",
        "expiry",
        "expired",
        "expiration",
        "expire",
        "berlaku",
        "hingga",
        "sampai",
        "유효",
        "만료",
        "유효기간",
        "기간",
        "~",
      ];

      const hasAnchor = anchors.some((a) => around.includes(a));

      candidates.push({
        date: dateText,
        raw,
        source,
        pattern,
        score: hasAnchor ? 90 : source === "filename" ? 58 : 50,
        reason: hasAnchor ? "anchor 주변 날짜" : "일반 날짜 후보",
      });
    }

    for (const m of text.matchAll(/(20\d{2})[.\-/년\s]+(0?[1-9]|1[0-2])[.\-/월\s]+(0?[1-9]|[12]\d|3[01])/g)) {
      addCandidate(
        toIsoDate(m[1], m[2], m[3]),
        m.index || 0,
        m[0],
        "YYYY-MM-DD"
      );
    }

    for (const m of text.matchAll(/\b(0?[1-9]|[12]\d|3[01])\s+(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+(20\d{2})\b/gi)) {
      const monthNo = monthMap[m[2].toLowerCase()];

      addCandidate(
        toIsoDate(m[3], monthNo, m[1]),
        m.index || 0,
        m[0],
        "DD Month YYYY"
      );
    }

    for (const m of text.matchAll(/\b(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+(0?[1-9]|[12]\d|3[01]),?\s+(20\d{2})\b/gi)) {
      const monthNo = monthMap[m[1].toLowerCase()];

      addCandidate(
        toIsoDate(m[3], monthNo, m[2]),
        m.index || 0,
        m[0],
        "Month DD YYYY"
      );
    }

    const unique = new Map();

    for (const item of candidates) {
      if (!item.date) continue;

      const prev = unique.get(item.date);

      if (!prev || Number(item.score || 0) > Number(prev.score || 0)) {
        unique.set(item.date, item);
      }
    }

    return Array.from(unique.values())
      .sort((a, b) => Number(b.score || 0) - Number(a.score || 0) || a.date.localeCompare(b.date))
      .slice(0, 10);
  }

  function mergeExpiryCandidates(...candidateLists) {
    const unique = new Map();

    for (const list of candidateLists) {
      for (const item of list || []) {
        if (!item?.date) continue;

        const prev = unique.get(item.date);

        if (!prev || Number(item.score || 0) > Number(prev.score || 0)) {
          unique.set(item.date, item);
        }
      }
    }

    return Array.from(unique.values())
      .sort((a, b) => Number(b.score || 0) - Number(a.score || 0) || a.date.localeCompare(b.date))
      .slice(0, 10);
  }

  function isOcrCapableAttachment(file) {
    const filename = String(file?.saved_filename || file?.original_filename || "").toLowerCase();
    const ext = String(file?.ext || filename.split(".").pop() || "").replace(".", "").toLowerCase();

    if (ext === "pdf") return true;

    const imageExts = ["jpg", "jpeg", "png", "tif", "tiff", "bmp"];
    if (!imageExts.includes(ext)) return false;

    const blocked = [
      "image001",
      "image002",
      "image003",
      "logo",
      "signature",
      "sign",
      "banner",
      "footer",
      "header",
    ];

    if (blocked.some((x) => filename.includes(x))) return false;

    const size = Number(file?.file_size || 0);
    if (size > 0 && size < 20000) return false;

    return true;
  }

  async function handleCopyText(label, value) {
    const text = String(value ?? "").trim();

    if (!text) {
      alert(`${label} 값이 없습니다.`);
      return;
    }

    try {
      await navigator.clipboard.writeText(text);
      alert(`${label} 복사 완료`);
    } catch (err) {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      alert(`${label} 복사 완료`);
    }
  }

  async function handleOpenAttachmentFolder(pathOrFile) {
    const savedPath =
      typeof pathOrFile === "string"
        ? pathOrFile
        : pathOrFile?.saved_path || pathOrFile?.download_dir;

    if (!savedPath) {
      alert("열 수 있는 저장경로가 없습니다.");
      return;
    }

    try {
      const result = await openInboxAttachmentFolder(savedPath);

      if (!result.ok) {
        alert(result.message || "폴더 열기에 실패했습니다.");
      }
    } catch (err) {
      alert(err.message);
    }
  }

  async function loadMailDetail(mail) {
    try {
      if (!mail?.id) {
        setSelectedMailDetail(null);
        return;
      }

      const data = await getInboxMessageDetail(mail.id);
      setSelectedMailDetail(data.mail || null);
    } catch (err) {
      console.error(err);
      setSelectedMailDetail(null);
    }
  }

  async function loadAttachments(mail) {
    try {
      if (!mail) {
        setAttachments([]);
        setOcrSelectedIds([]);
        setOcrResults([]);
        return;
      }

      if (mail.match_status === "exact") {
        try {
          await autoSelectExactInboxOcrTargets({
            mail_id: mail.id,
          });
        } catch (err) {
          console.error("EXACT PDF OCR 자동선택 실패:", err);
        }
      }

      const data = await getInboxAttachments({
        request_id: mail.matched_request_id || "",
        mailbox: mail.mailbox || HALAL_MAILBOX,
        limit: 200,
      });

      const rows = data.rows || [];
      const filtered = mail.matched_request_id
        ? rows
        : rows.filter((x) => Number(x.mail_id) === Number(mail.id));

      setAttachments(filtered);

      const selectedIds = filtered
        .filter((x) => Number(x.ocr_selected) === 1)
        .map((x) => x.id);

      setOcrSelectedIds(selectedIds);
      setOcrResults([]);
    } catch (err) {
      alert(err.message);
    }
  }

  async function loadMessages(
    nextStatus = matchStatus,
    nextIncludeExcluded = includeExcluded
  ) {
    try {
      setLoading(true);

      const data = await getInboxMessages({
        match_status: nextStatus,
        mailbox: HALAL_MAILBOX,
        include_excluded: nextIncludeExcluded,
        limit: 200,
      });

      const rows = data.rows || [];
      setMails(rows);
      setCheckedMailIds([]);

      if (rows.length > 0) {
        const first = rows[0];
        setSelectedMail(first);
        await loadMailDetail(first);
        await loadAttachments(first);
      } else {
        setSelectedMail(null);
        setSelectedMailDetail(null);
        setAttachments([]);
        setOcrSelectedIds([]);
        setOcrResults([]);
      }
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleSelectMail(mail) {
    setSelectedMail(mail);
    await loadMailDetail(mail);
    await loadAttachments(mail);
  }

  async function handleSyncInbox() {
    const ok = window.confirm("HALAL 인증서 메일함을 동기화합니다. 계속할까요?");

    if (!ok) return;

    try {
      setLoading(true);

      const result = await syncInboxMail({
        mailboxes: [HALAL_MAILBOX],
        days: Number(days || 14),
        limit: Number(limit || 100),
        only_with_attachments: true,
      });

      setSyncResult(result);

      if (!result.ok) {
        alert(result.message || "동기화 실패");
        return;
      }

      const autoResult = await autoSelectExactInboxOcrTargets({
        mail_id: null,
      });

      await loadMessages(matchStatus, includeExcluded);

      alert(
        `동기화 완료\n` +
          `확인: ${result.checked || 0}건\n` +
          `신규 저장: ${result.inserted_mails || 0}건\n` +
          `첨부 저장: ${result.downloaded_attachments || 0}건\n` +
          `EXACT PDF OCR 자동선택: ${autoResult.selected || 0}건`
      );
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  function toggleMailChecked(mailId) {
    setCheckedMailIds((prev) => {
      if (prev.includes(mailId)) {
        return prev.filter((id) => id !== mailId);
      }

      return [...prev, mailId];
    });
  }

  function handleSelectAllMails() {
    setCheckedMailIds(mails.map((mail) => mail.id).filter(Boolean));
  }

  function handleClearAllMails() {
    setCheckedMailIds([]);
  }

  async function handleExcludeChecked() {
    if (checkedMailIds.length === 0) {
      alert("제외할 메일을 선택하세요.");
      return;
    }

    const ok = window.confirm(
      `선택한 메일 ${checkedMailIds.length}건을 제외 처리합니다. 계속할까요?`
    );

    if (!ok) return;

    try {
      await excludeInboxMessages({
        mail_ids: checkedMailIds,
        excluded: true,
        reason: "수신메일 화면에서 사용자 제외",
      });

      alert("제외 처리 완료");
      await loadMessages(matchStatus, includeExcluded);
    } catch (err) {
      alert(err.message);
    }
  }

  function handleMailListKeyDown(e) {
    if (!mails.length) return;

    const currentIndex = Math.max(
      mails.findIndex((mail) => mail.id === selectedMail?.id),
      0
    );

    if (e.key === "ArrowDown") {
      e.preventDefault();
      const nextIndex = Math.min(currentIndex + 1, mails.length - 1);
      handleSelectMail(mails[nextIndex]);
      return;
    }

    if (e.key === "ArrowUp") {
      e.preventDefault();
      const nextIndex = Math.max(currentIndex - 1, 0);
      handleSelectMail(mails[nextIndex]);
      return;
    }

    if (e.key === " " || e.key === "Spacebar") {
      e.preventDefault();
      const current = mails[currentIndex];
      if (current?.id) {
        toggleMailChecked(current.id);
      }
    }
  }

  function toggleAttachmentOcrSelected(attachmentId) {
    setOcrSelectedIds((prev) => {
      if (prev.includes(attachmentId)) {
        return prev.filter((id) => id !== attachmentId);
      }

      return [...prev, attachmentId];
    });
  }

  function handleSelectAllAttachmentOcr() {
    const ids = attachments
      .filter((file) => isOcrCapableAttachment(file))
      .map((file) => file.id);

    setOcrSelectedIds(ids);
  }

  function handleClearAllAttachmentOcr() {
    setOcrSelectedIds([]);
  }

  async function handleSaveOcrSelection(options = {}) {
    const silent = Boolean(options.silent);

    if (attachments.length === 0) {
      if (!silent) alert("첨부파일이 없습니다.");
      return false;
    }

    try {
      const allIds = attachments.map((file) => file.id);
      const selectedIds = ocrSelectedIds;

      if (allIds.length > 0) {
        await selectInboxAttachmentsForOcr({
          attachment_ids: allIds,
          selected: false,
        });
      }

      if (selectedIds.length > 0) {
        await selectInboxAttachmentsForOcr({
          attachment_ids: selectedIds,
          selected: true,
        });
      }

      if (!silent) {
        alert("OCR 대상 선택 저장 완료");
      }

      if (selectedMail) {
        await loadAttachments(selectedMail);
      }

      return true;
    } catch (err) {
      alert(err.message);
      return false;
    }
  }

  async function safeSaveOcrCandidateResult(payload) {
    try {
      return await saveInboxOcrCandidateResult(payload);
    } catch (err) {
      console.error("save-candidate failed:", err);
      return {
        ok: false,
        message: err.message || "save-candidate failed",
      };
    }
  }

  async function runOcrForTargetFiles(targets) {
    const results = [];

    for (const file of targets) {
      const filename = file.saved_filename || file.original_filename || "-";
      const filenameCandidates = parseCandidateJson(file.filename_date_candidates_json);
      const mailCandidates = parseCandidateJson(file.mail_date_candidates_json);

      const fallbackCandidates = mergeExpiryCandidates(
        filenameCandidates,
        mailCandidates
      );

      if (!file.saved_path) {
        const failResult = {
          attachment_id: file.id,
          filename,
          status: "ERROR",
          ocr_job_id: null,
          best_expiry: fallbackCandidates[0]?.date || "",
          candidates: fallbackCandidates,
          message: "saved_path 없음",
        };

        await safeSaveOcrCandidateResult({
          attachment_id: file.id,
          ocr_job_id: null,
          status: "ERROR",
          filename,
          best_expiry: failResult.best_expiry,
          expiry_candidates: fallbackCandidates,
          filename_candidates: filenameCandidates,
          mail_candidates: mailCandidates,
          ocr_candidates: [],
          message: failResult.message,
        });

        results.push(failResult);
        setOcrResults([...results]);
        continue;
      }

      try {
        const job = await createOcrJob({
          source_path: file.saved_path,
          ocr_scanned_pages: true,
          lang: "eng",
        });

        const detailJob = await getOcrJob(job.id);

        const rawText =
          detailJob.raw_text ||
          detailJob.raw_text_preview ||
          detailJob.result?.raw_text ||
          "";

        const ocrCandidates = extractExpiryCandidatesFromText(rawText, "ocr");

        const mergedCandidates = mergeExpiryCandidates(
          ocrCandidates,
          filenameCandidates,
          mailCandidates
        );

        const bestExpiry = mergedCandidates[0]?.date || "";

        const oneResult = {
          attachment_id: file.id,
          filename,
          status: detailJob.status || "DONE",
          ocr_job_id: detailJob.id || job.id,
          best_expiry: bestExpiry,
          candidates: mergedCandidates,
          message: detailJob.error_message || "",
        };

        await safeSaveOcrCandidateResult({
          attachment_id: file.id,
          ocr_job_id: oneResult.ocr_job_id,
          status: oneResult.status,
          filename,
          best_expiry: bestExpiry,
          expiry_candidates: mergedCandidates,
          filename_candidates: filenameCandidates,
          mail_candidates: mailCandidates,
          ocr_candidates: ocrCandidates,
          message: oneResult.message,
        });

        results.push(oneResult);
        setOcrResults([...results]);
      } catch (err) {
        const message = err?.message || "OCR 실행 중 오류가 발생했습니다.";

        const failResult = {
          attachment_id: file.id,
          filename,
          status: "ERROR",
          ocr_job_id: null,
          best_expiry: fallbackCandidates[0]?.date || "",
          candidates: fallbackCandidates,
          message,
        };

        await safeSaveOcrCandidateResult({
          attachment_id: file.id,
          ocr_job_id: null,
          status: "ERROR",
          filename,
          best_expiry: failResult.best_expiry,
          expiry_candidates: fallbackCandidates,
          filename_candidates: filenameCandidates,
          mail_candidates: mailCandidates,
          ocr_candidates: [],
          message,
        });

        results.push(failResult);
        setOcrResults([...results]);
      }
    }

    return results;
  }

  async function handleRunSelectedAttachmentOcr() {
    const selectedFiles = attachments.filter((file) =>
      ocrSelectedIds.includes(file.id)
    );

    if (selectedFiles.length === 0) {
      alert("OCR 실행할 첨부파일을 선택하세요.");
      return;
    }

    const ok = window.confirm(
      `선택한 첨부파일 ${selectedFiles.length}건을 OCR 처리합니다. 계속할까요?`
    );

    if (!ok) return;

    try {
      setOcrRunning(true);
      setOcrResults([]);
      setOcrError("");

      await handleSaveOcrSelection({ silent: true });

      const results = await runOcrForTargetFiles(selectedFiles);
      const successCount = results.filter((x) => x.status !== "ERROR").length;
      const errorCount = results.length - successCount;

      if (selectedMail) {
        await loadAttachments(selectedMail);
      }

      alert(`OCR 처리 완료\n성공 ${successCount}건 / 오류 ${errorCount}건`);
    } catch (err) {
      console.error("선택 OCR 실행 실패:", err);
      setOcrError(err.message || "Failed to fetch");
      alert(err.message || "Failed to fetch");
    } finally {
      setOcrRunning(false);
    }
  }

  async function handleRunBatchOcrTargets() {
    const ok = window.confirm(
      "OCR 대상으로 저장된 첨부파일을 일괄 판독합니다. 계속할까요?"
    );

    if (!ok) return;

    try {
      setOcrRunning(true);
      setOcrResults([]);
      setOcrError("");

      const targetData = await getInboxOcrTargets({
        limit: 500,
        only_pending: true,
      });

      const targets = targetData.rows || [];

      if (targets.length === 0) {
        alert("OCR 대상으로 저장된 pending 첨부파일이 없습니다.");
        return;
      }

      const results = await runOcrForTargetFiles(targets);
      const successCount = results.filter((x) => x.status !== "ERROR").length;
      const errorCount = results.length - successCount;

      if (selectedMail) {
        await loadAttachments(selectedMail);
      }

      alert(`일괄 OCR 완료\n성공 ${successCount}건 / 오류 ${errorCount}건`);
    } catch (err) {
      console.error("일괄 OCR 실행 실패:", err);
      setOcrError(err.message || "Failed to fetch");
      alert(err.message || "Failed to fetch");
    } finally {
      setOcrRunning(false);
    }
  }
  useEffect(() => {
    loadMessages("", false);
  }, []);

  const exactCount = mails.filter((x) => x.match_status === "exact").length;
  const probableCount = mails.filter((x) => x.match_status === "probable").length;
  const candidateCount = mails.filter((x) =>
    ["unmatched", "unmatched_candidate"].includes(x.match_status)
  ).length;
  const bodyText = cleanMailBody(
    selectedMailDetail?.body_text ||
      selectedMailDetail?.body_preview ||
      selectedMail?.body_preview ||
      ""
  );

  return (
    <>
      <PageHeader
        eyebrow="RECEIVE MAIL"
        title="수신메일"
        desc="HALAL 인증서 메일함에서 후보 메일만 수집하고 OCR 대상 첨부파일을 관리합니다."
        onBack={() => setActive("home")}
      />

      <StatLine
        items={[
          { label: "메일 목록", value: mails.length },
          { label: "관리번호 매칭", value: exactCount },
          { label: "유사 매칭", value: probableCount },
          { label: "후보/미매칭", value: candidateCount },
        ]}
      />

      <section className="inbox-control-panel compact-inbox-control">
        <div className="inbox-control-head inbox-control-head-inline">
          <div>
            <span>MAILBOX SYNC</span>
            <h3>수신메일 동기화</h3>
          </div>

          <div className="inbox-main-actions">
            <button
              className="ghost-action"
              type="button"
              onClick={async () => {
                const result = await autoSelectExactInboxOcrTargets({ mail_id: null });

                if (selectedMail) {
                  await loadAttachments(selectedMail);
                }

                alert(`EXACT PDF OCR 자동선택 완료: ${result.selected || 0}건`);
              }}
              disabled={loading || ocrRunning}
            >
              EXACT PDF 자동선택
            </button>

            <button
              className="primary-button"
              type="button"
              onClick={handleRunBatchOcrTargets}
              disabled={ocrRunning}
            >
              {ocrRunning ? "일괄 판독 중..." : "OCR 대상 일괄 판독"}
            </button>

            <button
              className="primary-button"
              onClick={handleSyncInbox}
              disabled={loading || ocrRunning}
            >
              {loading ? "동기화 중..." : "메일 동기화"}
            </button>
          </div>
        </div>

        <div className="inbox-sync-options compact-sync-options">
          <div className="inbox-option-box">
            <span>동기화 메일함</span>
            <div className="inbox-mailbox-fixed">HALAL 인증서</div>
          </div>

          <div className="inbox-option-box small">
            <span>최근 일수</span>
            <input
              type="number"
              value={days}
              min="1"
              max="365"
              onChange={(e) => setDays(e.target.value)}
            />
          </div>

          <div className="inbox-option-box small">
            <span>메일함 제한</span>
            <input
              type="number"
              value={limit}
              min="1"
              max="500"
              onChange={(e) => setLimit(e.target.value)}
            />
          </div>
        </div>

        {syncResult ? (
          <div className="inbox-sync-result compact-sync-result">
            <span>최근 동기화 결과</span>
            <strong>
              확인 {syncResult.checked || 0}건 · 신규 {syncResult.inserted_mails || 0}건 ·
              첨부 {syncResult.downloaded_attachments || 0}건 · exact {syncResult.exact_matched || 0}건 ·
              후보 {syncResult.unmatched_candidate || 0}건 · 제외 {syncResult.skipped_non_candidate || 0}건
            </strong>
          </div>
        ) : null}
      </section>

      <section className="inbox-filter-row aligned-filter-row">
        <div className="filter-button-group">
          <button
            className={matchStatus === "" ? "active" : ""}
            onClick={() => {
              setMatchStatus("");
              loadMessages("", includeExcluded);
            }}
          >
            전체
          </button>

          <button
            className={matchStatus === "exact" ? "active" : ""}
            onClick={() => {
              setMatchStatus("exact");
              loadMessages("exact", includeExcluded);
            }}
          >
            관리번호 매칭
          </button>

          <button
            className={matchStatus === "probable" ? "active" : ""}
            onClick={() => {
              setMatchStatus("probable");
              loadMessages("probable", includeExcluded);
            }}
          >
            유사 매칭
          </button>

          <button
            className={matchStatus === "unmatched_candidate" ? "active" : ""}
            onClick={() => {
              setMatchStatus("unmatched_candidate");
              loadMessages("unmatched_candidate", includeExcluded);
            }}
          >
            후보/미매칭
          </button>
        </div>

        <label className="check-pill compact">
          <input
            type="checkbox"
            checked={includeExcluded}
            onChange={(e) => {
              const checked = e.target.checked;
              setIncludeExcluded(checked);
              loadMessages(matchStatus, checked);
            }}
          />
          <span>제외 메일 포함</span>
        </label>
      </section>

      <section className="inbox-layout balanced-inbox-layout">
        <div className="inbox-mail-list compact-mail-list">
          <div className="panel-title-row inbox-panel-title-row">
            <div className="surface-title">수신메일 목록</div>

            <div className="panel-actions">
              <button type="button" className="soft-chip-action" onClick={handleSelectAllMails}>
                전체선택
              </button>
              <button type="button" className="soft-chip-action" onClick={handleClearAllMails}>
                전체해제
              </button>
              <button
                type="button"
                className="danger-action strong"
                onClick={handleExcludeChecked}
                disabled={checkedMailIds.length === 0}
              >
                선택제외
              </button>
            </div>
          </div>

          {mails.length === 0 ? (
            <div className="mail-log-empty">
              수신메일 동기화 결과가 없습니다.
            </div>
          ) : (
            <div
              className="inbox-mail-scroll compact-inbox-scroll"
              ref={mailListRef}
              tabIndex={0}
              onKeyDown={handleMailListKeyDown}
            >
              {mails.map((mail) => {
                const checked = checkedMailIds.includes(mail.id);
                const isSelected = selectedMail?.id === mail.id;

                return (
                  <button
                    type="button"
                    key={mail.id}
                    className={isSelected ? "inbox-mail-row compact active" : "inbox-mail-row compact"}
                    onClick={() => handleSelectMail(mail)}
                  >
                    <div className="inbox-mail-line-one">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => {
                          e.stopPropagation();
                          toggleMailChecked(mail.id);
                        }}
                        onClick={(e) => e.stopPropagation()}
                      />
                      <strong>{mail.subject || "(제목 없음)"}</strong>
                      <span className={`match-badge ${mail.match_status}`}>
                        {getStatusLabel(mail.match_status)}
                      </span>
                    </div>

                    <div className="inbox-mail-line-two">
                      <span>{mail.sender || "-"}</span>
                      <span>{mail.received_at || "-"}</span>
                    </div>

                    <div className="inbox-mail-line-three">
                      <span>관리번호: {mail.matched_request_id || "-"}</span>
                      <span>첨부 {mail.attachment_count || 0}건</span>
                      <span>{getReasonShort(mail.match_reason)}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="inbox-attachment-panel compact-attachment-panel">
          <div className="surface-title">메일 본문 / 첨부파일</div>

          {!selectedMail ? (
            <div className="mail-log-empty">
              메일을 선택하면 본문과 첨부파일이 표시됩니다.
            </div>
          ) : (
            <>
              <div className="inbox-selected-mail compact inbox-selected-mail-row">
                <div>
                  <span>선택 메일</span>
                  <strong>{selectedMail.subject || "(제목 없음)"}</strong>
                </div>

                <button
                  type="button"
                  onClick={() => handleOpenAttachmentFolder(selectedMail.download_dir)}
                >
                  저장폴더 열기
                </button>
              </div>

              <div className="inbox-mail-body-panel readable-mail-body-panel">
                <div className="inbox-mail-body-head">
                  <span>MAIL BODY</span>
                  <strong>메일 본문</strong>
                </div>

                <div className="inbox-mail-body-meta">
                  <span>{selectedMail.sender || "-"}</span>
                  <span>{selectedMail.received_at || "-"}</span>
                  <span>{getReasonShort(selectedMail.match_reason)}</span>
                </div>

                <div className="inbox-mail-body-text readable-mail-body-text">
                  {bodyText || "본문을 불러오지 못했습니다."}
                </div>
              </div>

              <div className="inbox-attachment-toolbar">
                <span>
                  첨부파일 {attachments.length}건 · OCR 대상 {ocrSelectedIds.length}건
                </span>

                <div className="inbox-attachment-toolbar-actions">
                  <button
                    type="button"
                    onClick={handleSelectAllAttachmentOcr}
                    disabled={attachments.length === 0}
                  >
                    OCR 전체선택
                  </button>

                  <button
                    type="button"
                    onClick={handleClearAllAttachmentOcr}
                    disabled={attachments.length === 0}
                  >
                    OCR 전체해제
                  </button>

                  <button
                    type="button"
                    onClick={() => handleSaveOcrSelection()}
                    disabled={attachments.length === 0}
                  >
                    OCR 대상 저장
                  </button>

                  <button
                    type="button"
                    className="primary-mini-action"
                    onClick={handleRunSelectedAttachmentOcr}
                    disabled={ocrRunning || ocrSelectedIds.length === 0}
                  >
                    {ocrRunning ? "OCR 처리 중..." : "선택 OCR 실행"}
                  </button>
                </div>
              </div>

              {attachments.length === 0 ? (
                <div className="mail-log-empty">
                  표시할 첨부파일이 없습니다.
                </div>
              ) : (
                <div className="inbox-attachment-list">
                  {attachments.map((file) => (
                    <div className="inbox-attachment-row compact" key={file.id}>
                      <label className="ocr-check-mini">
                        <input
                          type="checkbox"
                          checked={ocrSelectedIds.includes(file.id)}
                          onChange={() => toggleAttachmentOcrSelected(file.id)}
                        />
                        <span>OCR</span>
                      </label>

                      <span className="inbox-attachment-label">파일명</span>

                      <strong
                        className="inbox-attachment-filename"
                        title={file.saved_filename || file.original_filename || ""}
                      >
                        {file.saved_filename || file.original_filename || "-"}
                      </strong>

                      <span className={`mini-badge ${Number(file.ocr_selected) === 1 ? "ok" : "test"}`}>
                        {Number(file.ocr_selected) === 1 ? "OCR 대상" : "수동"}
                      </span>

                      <span className={file.ocr_status === "done" ? "mini-badge ok" : "mini-badge test"}>
                        {file.ocr_status || "pending"}
                      </span>

                      <div className="inbox-attachment-actions compact">
                        <button
                          type="button"
                          onClick={() => handleCopyText("파일명", file.saved_filename || file.original_filename)}
                        >
                          복사
                        </button>

                        <button
                          type="button"
                          onClick={() => handleOpenAttachmentFolder(file)}
                        >
                          폴더 열기
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {ocrError ? (
                <div className="error-box">
                  OCR 실행 오류: {ocrError}
                </div>
              ) : null}

              {ocrResults.length > 0 ? (
                <div className="inbox-ocr-result-panel">
                  <div className="inbox-ocr-result-head">
                    <span>OCR RESULT</span>
                    <strong>유효기간 후보</strong>
                  </div>

                  <div className="inbox-ocr-result-list">
                    {ocrResults.map((result) => (
                      <div
                        className="inbox-ocr-result-row"
                        key={`${result.attachment_id}-${result.ocr_job_id || result.status}`}
                      >
                        <div className="inbox-ocr-result-file">
                          <strong>{result.filename}</strong>
                          <span>
                            상태 {result.status}
                            {result.ocr_job_id ? ` · Job ${result.ocr_job_id}` : ""}
                          </span>
                        </div>

                        {result.best_expiry ? (
                          <div className="inbox-ocr-expiry-best">
                            <span>1순위 후보</span>
                            <strong>{result.best_expiry}</strong>
                            <em>
                              {result.candidates?.[0]?.source || "-"} · {result.candidates?.[0]?.reason || "-"}
                            </em>
                          </div>
                        ) : (
                          <div className="inbox-ocr-expiry-empty">
                            유효기간 후보를 찾지 못했습니다.
                            {result.message ? ` (${result.message})` : ""}
                          </div>
                        )}

                        {result.candidates?.length > 1 ? (
                          <div className="inbox-ocr-expiry-candidates">
                            {result.candidates.slice(1).map((candidate) => (
                              <span
                                key={`${result.attachment_id}-${candidate.date}-${candidate.source}-${candidate.raw}`}
                              >
                                {candidate.date} · {candidate.source || "-"}
                              </span>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </>
          )}
        </div>
      </section>
    </>
  );
}

export default ReceiveMailPage;
