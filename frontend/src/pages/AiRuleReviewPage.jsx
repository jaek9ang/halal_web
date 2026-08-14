import { useEffect, useMemo, useState } from "react";
import {
  analyzeAiRuleExport,
  applyAiRuleCandidate,
  getAiRuleCandidates,
  getAiRuleProblemCases,
  getAiRuleReviewStatus,
  rejectAiRuleCandidate,
  validateAiRuleCandidate,
} from "../api";
import AiRuleRecognitionChart from "../components/AiRuleRecognitionChart";
import PageHeader from "../components/PageHeader";

function getReportSummary(report, candidate) {
  return report?.summary || candidate?.validation_summary || {};
}

function AiRuleReviewPage({ setActive }) {
  const [status, setStatus] = useState(null);
  const [problemCases, setProblemCases] = useState([]);
  const [candidates, setCandidates] = useState([]);
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [validationReport, setValidationReport] = useState(null);
  const [validationReportsByCandidate, setValidationReportsByCandidate] = useState({});
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [validating, setValidating] = useState(false);
  const [batchTesting, setBatchTesting] = useState(false);
  const [batchProgress, setBatchProgress] = useState({ done: 0, total: 0, failed: 0 });
  const [applying, setApplying] = useState(false);
  const [candidateStatusFilter, setCandidateStatusFilter] = useState("");
  const [candidateOrgFilter, setCandidateOrgFilter] = useState("");
  const [candidateFieldFilter, setCandidateFieldFilter] = useState("");
  const [aiMaxCases, setAiMaxCases] = useState(20);

  function getErrorMessage(err) {
    if (!err) return "알 수 없는 오류가 발생했습니다.";
    return err.message || String(err);
  }

  function formatCount(value) {
    const n = Number(value || 0);
    return Number.isFinite(n) ? n.toLocaleString() : "-";
  }

  function decisionLabel(decision) {
    const key = String(decision || "").toUpperCase();

    const map = {
      IMPROVED: "개선",
      REGRESSION: "악화",
      UNCHANGED: "유지",
      MANUAL_REVIEW: "수동검토",
      CHANGED_REVIEW: "변경검토",
    };

    return map[key] || key || "-";
  }

  function statusLabel(value) {
    const key = String(value || "").toUpperCase();

    const map = {
      PENDING: "대기",
      VALIDATED: "검증완료",
      APPLIED: "적용완료",
      REJECTED: "반려",
      ERROR: "오류",
    };

    return map[key] || key || "-";
  }

  function getDecisionClass(decision) {
    const key = String(decision || "").toUpperCase();

    if (key === "IMPROVED") return "improved";
    if (key === "REGRESSION") return "regression";
    if (key === "MANUAL_REVIEW" || key === "CHANGED_REVIEW") return "review";
    return "neutral";
  }

  function percent(value, total) {
    const n = Number(value || 0);
    const d = Math.max(Number(total || 0), 1);
    return Math.max(0, Math.min(100, Math.round((n / d) * 100)));
  }

  function cleanProblemReasons(reasons = []) {
    return (reasons || []).filter((reason) => {
      const text = String(reason || "");

      if (!text.trim()) return false;
      if (text.includes("규칙 판정 신뢰도 낮음")) return false;
      if (text.includes("OCR 원문 확인 필요")) return false;

      return true;
    });
  }

  function getProblemReasonText(row) {
    const reasons = cleanProblemReasons(row.problem_reasons || []);

    if (reasons.length > 0) {
      return reasons.join(" / ");
    }

    const fallback = String(row.problem_summary || "").trim();

    if (fallback && !fallback.includes("규칙 판정 신뢰도 낮음")) {
      return fallback;
    }

    return "규칙 보정 필요";
  }

  function isWildcardOrg(value) {
    const org = String(value || "").toUpperCase().trim();
    return ["", "ALL", "ANY", "*"].includes(org);
  }

  function isVisibleCandidate(candidate) {
    return !isWildcardOrg(candidate?.target_org);
  }

  function getCandidateScope(candidate) {
    return isWildcardOrg(candidate?.target_org) ? "전체기관" : "기관별";
  }

  function getCandidateReport(candidate) {
    if (!candidate?.rule_candidate_id) return null;
    return validationReportsByCandidate[candidate.rule_candidate_id] || null;
  }

  function getCandidateValidationSummary(candidate) {
    return getReportSummary(getCandidateReport(candidate), candidate);
  }

  function getCandidateTestLabel(candidate) {
    const summary = getCandidateValidationSummary(candidate);

    if (!summary || Object.keys(summary).length === 0) {
      return "미검증";
    }

    const improved = Number(summary.improved_count || 0);
    const regression = Number(summary.regression_count || 0);
    const delta = Number(summary.delta_recognition_rate || 0);

    return `개선 ${improved} / 악화 ${regression} / ${delta > 0 ? "+" : ""}${delta.toFixed(1)}%`;
  }

  function getCandidateShortSummary(candidate) {
    const text = String(candidate?.problem_summary || "").replace(/\s+/g, " ").trim();

    if (!text) return "요약 없음";
    if (text.length <= 58) return text;

    return `${text.slice(0, 58)}...`;
  }

  function getFieldLabel(field) {
    const key = String(field || "");
    const map = {
      cert_no: "인증번호",
      expiry_date: "유효기간",
      manufacturer: "제조사",
      manufacturing_country: "제조국",
      cert_country: "인증국가",
      cert_org: "인증기관",
      parse_status: "판정상태",
    };

    return map[key] || key || "필드";
  }

  function isPlausibleAfterValue(row) {
    const field = String(row.field || selectedCandidate?.target_field || "");
    const after = String(row.after_value || "").trim();

    if (!after || after === "-") return false;

    if (field === "cert_no") {
      return /(?:PRN|HC|ID\d|MUI|LPPOM|JAKIM|CICOT|KMF|HAL|[A-Z]{2,}[-/]?\d|\d{3,}[-/]\d{2,})/i.test(after);
    }

    if (field === "expiry_date") {
      return /^20\d{2}-\d{2}-\d{2}$/.test(after);
    }

    if (field === "manufacturer") {
      return after.length >= 3 && !/^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$/.test(after);
    }

    return true;
  }

  function getAfterQualityText(row) {
    const before = String(row.before_value ?? "").trim();
    const after = String(row.after_value ?? "").trim();

    if (!after || after === "-") return "개선 후 값 없음";
    if (!isPlausibleAfterValue(row)) return "형식 의심 · 수동확인";
    if (!before || before === "-") return "누락값 신규 추출";
    if (before !== after) return "기존값 변경 · 수동확인";
    return "값 유지";
  }

  function dedupeValidationRows(rows) {
    const seen = new Set();
    const result = [];

    for (const row of rows || []) {
      const key = [
        row.filename || "",
        row.cert_org || "",
        row.field || "",
        row.before_value || "",
        row.after_value || "",
        row.decision || "",
      ].join("||");

      if (seen.has(key)) continue;
      seen.add(key);
      result.push(row);
    }

    return result;
  }

  function getSelectedCandidateIndex() {
    return visibleCandidates.findIndex(
      (row) => row.rule_candidate_id === selectedCandidateId
    );
  }

  function selectCandidate(candidateId) {
    setSelectedCandidateId(candidateId);
    setValidationReport(validationReportsByCandidate[candidateId] || null);

    window.setTimeout(() => {
      const target = document.querySelector(`[data-ai-candidate-id="${candidateId}"]`);
      target?.scrollIntoView({ block: "nearest", inline: "nearest" });
    }, 0);
  }

  function moveCandidate(delta) {
    if (!visibleCandidates.length) return;

    const currentIndex = Math.max(0, getSelectedCandidateIndex());
    const nextIndex = (currentIndex + delta + visibleCandidates.length) % visibleCandidates.length;
    const nextCandidate = visibleCandidates[nextIndex];

    if (nextCandidate?.rule_candidate_id) {
      selectCandidate(nextCandidate.rule_candidate_id);
    }
  }

  function getChangeKind(row) {
    const before = String(row.before_value ?? "").trim();
    const after = String(row.after_value ?? "").trim();
    const decision = String(row.decision || "").toUpperCase();

    if (!before && after) {
      return { label: "미추출 → 신규 추출", className: "improved" };
    }

    if (before && after && before !== after) {
      if (decision === "REGRESSION") {
        return { label: "기존값 변경 · 악화 가능", className: "regression" };
      }

      return { label: "기존값 보정", className: getDecisionClass(decision) };
    }

    if (before && !after) {
      return { label: "기존값 제거 · 악화 가능", className: "regression" };
    }

    return { label: "변경 없음", className: getDecisionClass(decision) };
  }

  function getEvidenceText(row) {
    const candidates = [
      row.evidence,
      row.matched_text,
      row.source_text,
      row.source_excerpt,
      row.anchor_text,
      row.reason,
      row.note,
      row.source_rule,
    ];

    const found = candidates.find((value) => String(value || "").trim());

    if (found) {
      return String(found);
    }

    return "리포트에 원문 근거가 별도로 제공되지 않았습니다. Before/After 값과 파일명을 기준으로 확인해야 합니다.";
  }

  async function loadStatus() {
    const data = await getAiRuleReviewStatus();
    setStatus(data);
  }

  async function loadCandidates(next = {}) {
    const data = await getAiRuleCandidates({
      limit: 200,
      apply_status: next.apply_status ?? candidateStatusFilter,
      target_org: next.target_org ?? candidateOrgFilter,
      target_field: next.target_field ?? candidateFieldFilter,
    });

    const rows = Array.isArray(data?.rows) ? data.rows : [];
    setCandidates(rows);

    setSelectedCandidateId((prev) => {
      if (prev && rows.some((row) => row.rule_candidate_id === prev)) {
        return prev;
      }

      const firstVisible = rows.find(isVisibleCandidate);
      return firstVisible?.rule_candidate_id || "";
    });

    return rows;
  }

  async function loadInitial() {
    try {
      setLoading(true);
      await Promise.all([
        loadStatus(),
        loadCandidates(),
      ]);
    } catch (err) {
      alert(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadInitial();
  }, []);

  const visibleCandidates = candidates.filter(isVisibleCandidate);

  const selectedCandidate = useMemo(() => {
    if (!visibleCandidates.length) return null;

    return (
      visibleCandidates.find((row) => row.rule_candidate_id === selectedCandidateId) ||
      visibleCandidates[0]
    );
  }, [visibleCandidates, selectedCandidateId]);

  useEffect(() => {
    if (!selectedCandidate?.rule_candidate_id) {
      setValidationReport(null);
      return;
    }

    const cached = validationReportsByCandidate[selectedCandidate.rule_candidate_id];

    if (cached) {
      setValidationReport(cached);
      return;
    }

    setValidationReport(null);
  }, [selectedCandidate?.rule_candidate_id, validationReportsByCandidate]);

  const validationSummary = getReportSummary(validationReport, selectedCandidate);
  const validationRowsRaw = Array.isArray(validationReport?.rows) ? validationReport.rows : [];
  const validationRows = dedupeValidationRows(validationRowsRaw);

  const validationRecordTotal = Number(validationSummary.total_records || validationRows.length || 0);
  const validationImpactedTotal = Number(
    validationSummary.impacted_count ??
      (
        Number(validationSummary.improved_count || 0) +
        Number(validationSummary.regression_count || 0) +
        Number(validationSummary.changed_review_count || 0) +
        Number(validationSummary.manual_review_count || 0)
      )
  );

  const validationChangedTotal =
    Number(validationSummary.improved_count || 0) +
    Number(validationSummary.regression_count || 0) +
    Number(validationSummary.changed_review_count || 0) +
    Number(validationSummary.manual_review_count || 0);

  const selectedValidationRows = validationRows
    .filter((row) => {
      if (!selectedCandidate?.target_field) return true;
      return row.field === selectedCandidate.target_field;
    })
    .slice(0, 12);

  const applyAllowed =
    Boolean(validationSummary.auto_apply_allowed) &&
    Number(validationSummary.regression_count || 0) === 0 &&
    Number(validationSummary.improved_count || 0) > 0 &&
    !isWildcardOrg(selectedCandidate?.target_org) &&
    !["cert_org", "cert_country"].includes(String(selectedCandidate?.target_field || ""));

  async function handleLoadProblemCases() {
    try {
      setLoading(true);

      const result = await getAiRuleProblemCases({
        limit: 10000,
        max_cases: Number(aiMaxCases || 20),
      });

      const rows = Array.isArray(result?.rows)
        ? result.rows
        : Array.isArray(result?.problem_cases)
          ? result?.problem_cases
          : [];

      setProblemCases(rows);
    } catch (err) {
      alert(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleAnalyzeExport() {
    const ok = window.confirm(
      "현재 export.jsonl 기준으로 OpenAI 규칙 후보를 생성합니다. API 비용이 발생할 수 있습니다. 계속할까요?"
    );

    if (!ok) return;

    try {
      setAnalyzing(true);

      const result = await analyzeAiRuleExport({
        limit: 10000,
        max_cases: Number(aiMaxCases || 20),
        save_candidates: true,
      });

      const problemCaseRows = Array.isArray(result?.problem_cases)
        ? result?.problem_cases
        : Array.isArray(result?.rows)
          ? result.rows
          : [];

      const createdCandidates = Array.isArray(result?.candidates)
        ? result.candidates
        : Array.isArray(result?.created_candidates)
          ? result.created_candidates
          : [];

      setProblemCases(problemCaseRows);
      await loadStatus();
      const rows = await loadCandidates();
      const nextVisible = rows.filter(isVisibleCandidate);
      const firstCreatedVisible = createdCandidates.find(isVisibleCandidate);

      setSelectedCandidateId(
        firstCreatedVisible?.rule_candidate_id ||
        nextVisible[0]?.rule_candidate_id ||
        ""
      );

      alert(`AI 규칙 후보 생성 완료: ${Number(result?.created_count || createdCandidates.length || 0)}건`);
    } catch (err) {
      alert(getErrorMessage(err));
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleValidateCandidate(candidate = selectedCandidate, { silent = false } = {}) {
    if (!candidate?.rule_candidate_id) {
      if (!silent) alert("검증할 규칙 후보가 없습니다.");
      return null;
    }

    try {
      if (!silent) setValidating(true);

      const report = await validateAiRuleCandidate(candidate.rule_candidate_id, {
        limit: 10000,
      });

      setValidationReportsByCandidate((prev) => ({
        ...prev,
        [candidate.rule_candidate_id]: report,
      }));

      if (!silent || candidate.rule_candidate_id === selectedCandidate?.rule_candidate_id) {
        setValidationReport(report);
        setSelectedCandidateId(candidate.rule_candidate_id);
      }

      if (!silent) {
        await loadStatus();
        await loadCandidates();
        alert("테스트 적용 및 before/after 비교 완료");
      }

      return report;
    } catch (err) {
      if (!silent) alert(getErrorMessage(err));
      return null;
    } finally {
      if (!silent) setValidating(false);
    }
  }

  async function handleBatchValidateCandidates() {
    const targets = visibleCandidates.filter((candidate) => {
      const statusText = String(candidate.apply_status || "PENDING").toUpperCase();
      return !["APPLIED", "REJECTED"].includes(statusText);
    });

    if (!targets.length) {
      alert("일괄 테스트할 규칙 후보가 없습니다.");
      return;
    }

    const ok = window.confirm(
      `현재 표시된 후보 ${targets.length}건을 순차 테스트합니다. 시간이 걸릴 수 있습니다. 계속할까요?`
    );

    if (!ok) return;

    let failed = 0;

    try {
      setBatchTesting(true);
      setBatchProgress({ done: 0, total: targets.length, failed: 0 });

      for (let i = 0; i < targets.length; i += 1) {
        const candidate = targets[i];
        const report = await handleValidateCandidate(candidate, { silent: true });

        if (!report) {
          failed += 1;
        }

        setBatchProgress({ done: i + 1, total: targets.length, failed });
      }

      await loadStatus();
      await loadCandidates();

      alert(`일괄 테스트 완료: ${targets.length - failed}건 성공 / ${failed}건 실패`);
    } finally {
      setBatchTesting(false);
    }
  }

  async function handleApplyCandidate() {
    if (!selectedCandidate?.rule_candidate_id) {
      alert("적용할 규칙 후보가 없습니다.");
      return;
    }

    if (!applyAllowed) {
      alert("현재 검증 결과는 자동 적용 조건을 충족하지 않습니다.");
      return;
    }

    const ok = window.confirm(
      "검증 통과 규칙을 certificate_rule_overrides.json에 반영합니다. 계속할까요?"
    );

    if (!ok) return;

    try {
      setApplying(true);

      const reportId =
        validationReport?.validation_report_id ||
        selectedCandidate.validation_report_id ||
        "";

      await applyAiRuleCandidate(selectedCandidate.rule_candidate_id, {
        validation_report_id: reportId,
        actor: "user",
      });

      await loadStatus();
      await loadCandidates();

      alert("규칙 적용 완료");
    } catch (err) {
      alert(getErrorMessage(err));
    } finally {
      setApplying(false);
    }
  }

  async function handleRejectCandidate(candidate = selectedCandidate) {
    if (!candidate?.rule_candidate_id) {
      alert("반려할 규칙 후보가 없습니다.");
      return;
    }

    const reason = window.prompt("반려 사유를 입력하세요.", "수동 반려");

    if (reason === null) return;

    try {
      setApplying(true);

      await rejectAiRuleCandidate(candidate.rule_candidate_id, {
        reason,
        actor: "user",
      });

      await loadStatus();
      await loadCandidates();

      setValidationReportsByCandidate((prev) => {
        const next = { ...prev };
        delete next[candidate.rule_candidate_id];
        return next;
      });

      if (selectedCandidateId === candidate.rule_candidate_id) {
        setValidationReport(null);
      }

      alert("규칙 후보 반려 완료");
    } catch (err) {
      alert(getErrorMessage(err));
    } finally {
      setApplying(false);
    }
  }

  async function handleRefreshCandidates() {
    try {
      setLoading(true);
      await loadStatus();
      await loadCandidates();
    } catch (err) {
      alert(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  function handleCandidateFilterChange(type, value) {
    if (type === "status") {
      setCandidateStatusFilter(value);
      loadCandidates({ apply_status: value });
    }

    if (type === "org") {
      loadCandidates({ target_org: value });
    }

    if (type === "field") {
      loadCandidates({ target_field: value });
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="ADMIN / AI RULE REVIEW"
        title="AI 규칙 리뷰"
        desc="export.jsonl을 기준으로 기관별 OCR 규칙 후보를 생성하고 before/after 검증 후 승인 반영합니다."
        onBack={() => setActive("home")}
      />

      <section className="ai-rule-analysis-section">
        <div className="ai-rule-card ai-rule-control-card full">
          <div className="ai-rule-panel-head">
            <div>
              <div className="surface-title">분석 실행</div>
              <p>OCR 오류성 케이스를 제외하고 규칙 보정 대상만 추출합니다.</p>
            </div>
          </div>

          <div className="ai-rule-compact-status">
            <div>
              <span>API</span>
              <strong>{status?.openai_api_key_configured ? "SET" : "NONE"}</strong>
            </div>

            <div>
              <span>MODEL</span>
              <strong>{status?.model || "gpt-4.1"}</strong>
            </div>

            <div>
              <span>후보</span>
              <strong>{formatCount(status?.candidate_count)}</strong>
            </div>

            <div>
              <span>적용</span>
              <strong>{formatCount(status?.override_rule_count)}</strong>
            </div>
          </div>

          <div className="ai-rule-control-row">
            <label>
              <span>문제 케이스 최대 수</span>
              <input
                type="number"
                min="1"
                max="100"
                value={aiMaxCases}
                onChange={(e) => setAiMaxCases(e.target.value)}
              />
            </label>

            <button
              type="button"
              className="ghost-action"
              onClick={handleLoadProblemCases}
              disabled={loading || analyzing || batchTesting}
            >
              규칙 보정 대상 추출
            </button>

            <button
              type="button"
              className="primary-button"
              onClick={handleAnalyzeExport}
              disabled={analyzing || loading || batchTesting}
            >
              {analyzing ? "분석 중..." : "AI 규칙 후보 생성"}
            </button>

            <button
              type="button"
              className="ghost-action"
              onClick={handleRefreshCandidates}
              disabled={loading || analyzing || batchTesting}
            >
              새로고침
            </button>
          </div>

          {problemCases.length > 0 ? (
            <div className="ai-rule-problem-list table-mode compact-height">
              <div className="ai-rule-subtitle">규칙 보정 대상 {problemCases.length}건</div>

              <div className="ai-rule-mini-table-shell">
                <table className="ai-rule-mini-table problem">
                  <thead>
                    <tr>
                      <th>기관</th>
                      <th>상태</th>
                      <th>누락/이상 사유</th>
                      <th>현재값</th>
                      <th>파일명</th>
                    </tr>
                  </thead>

                  <tbody>
                    {problemCases.map((row) => (
                      <tr key={`${row.source_type}-${row.source_id}-${row.filename}`}>
                        <td>{row.cert_org || "UNKNOWN"}</td>
                        <td>{row.parse_status || "-"}</td>
                        <td className="reason">{getProblemReasonText(row)}</td>
                        <td className="filename">
                          expiry {row.expiry_date || "-"} / cert {row.cert_no || "-"}
                        </td>
                        <td className="filename" title={row.filename || "-"}>
                          {row.filename || "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="ai-rule-empty compact">
              규칙 보정 대상 추출 또는 AI 규칙 후보 생성을 실행하세요.
            </div>
          )}
        </div>
      </section>

      <section className="ai-rule-workspace-grid">
        <div className="ai-rule-card ai-rule-candidate-card">
          <div className="ai-rule-panel-head with-actions">
            <div>
              <div className="surface-title">규칙 후보</div>
              <p>후보를 표에서 선택합니다. 화살표로 이전/다음 후보를 이동할 수 있습니다.</p>
            </div>

            <div className="ai-rule-nav-actions">
              <button type="button" className="ghost-action" onClick={() => moveCandidate(-1)} disabled={!visibleCandidates.length}>
                ◀ 이전
              </button>
              <button type="button" className="ghost-action" onClick={() => moveCandidate(1)} disabled={!visibleCandidates.length}>
                다음 ▶
              </button>
            </div>
          </div>

          <div className="ai-rule-filter-row">
            <select
              value={candidateStatusFilter}
              onChange={(e) => handleCandidateFilterChange("status", e.target.value)}
            >
              <option value="">전체 상태</option>
              <option value="PENDING">PENDING</option>
              <option value="VALIDATED">VALIDATED</option>
              <option value="APPLIED">APPLIED</option>
              <option value="REJECTED">REJECTED</option>
            </select>

            <input
              value={candidateOrgFilter}
              onChange={(e) => setCandidateOrgFilter(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  handleCandidateFilterChange("org", candidateOrgFilter);
                }
              }}
              placeholder="기관: MUI / HCE / KMF"
            />

            <input
              value={candidateFieldFilter}
              onChange={(e) => setCandidateFieldFilter(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  handleCandidateFilterChange("field", candidateFieldFilter);
                }
              }}
              placeholder="필드: expiry_date / cert_no"
            />
          </div>

          <div className="ai-rule-action-row compact">
            <button
              type="button"
              className="primary-button"
              onClick={handleBatchValidateCandidates}
              disabled={batchTesting || validating || applying || visibleCandidates.length === 0}
            >
              {batchTesting ? `일괄 테스트 ${batchProgress.done}/${batchProgress.total}` : "표시 후보 일괄 테스트"}
            </button>

            <span className="ai-rule-inline-note">
              실패 {batchProgress.failed || 0}건 · 표시 후보 {visibleCandidates.length}건
            </span>
          </div>

          <div className="ai-rule-candidate-list compact-list-mode">
            {visibleCandidates.length === 0 ? (
              <div className="ai-rule-empty">생성된 기관별 규칙 후보가 없습니다.</div>
            ) : (
              <div className="ai-rule-candidate-scroll-list">
                {visibleCandidates.map((candidate, index) => {
                  const isActive =
                    candidate.rule_candidate_id === selectedCandidate?.rule_candidate_id;
                  const report = getCandidateReport(candidate);
                  const summary = getCandidateValidationSummary(candidate);
                  const improved = Number(summary.improved_count || 0);
                  const regression = Number(summary.regression_count || 0);
                  const delta = Number(summary.delta_recognition_rate || 0);

                  return (
                    <button
                      type="button"
                      key={candidate.rule_candidate_id}
                      data-ai-candidate-id={candidate.rule_candidate_id}
                      className={[
                        "ai-rule-candidate-row-v4",
                        isActive ? "selected" : "",
                        report ? "tested" : "untested",
                        regression > 0 ? "has-regression" : "",
                        `status-${String(candidate.apply_status || "PENDING").toLowerCase()}`,
                      ].join(" ")}
                      onClick={() => selectCandidate(candidate.rule_candidate_id)}
                      title={candidate.problem_summary || ""}
                    >
                      <div className="candidate-rank">{index + 1}</div>

                      <div className="candidate-main-v4">
                        <strong>{candidate.target_org || "ORG"} / {getFieldLabel(candidate.target_field)}</strong>
                        <span>{candidate.rule_kind || "-"}</span>
                      </div>

                      <div className="candidate-test-v4">
                        {report ? (
                          <>
                            <b>+{improved}</b>
                            <em>악화 {regression}</em>
                            <span>{delta > 0 ? "+" : ""}{delta.toFixed(1)}%</span>
                          </>
                        ) : (
                          <>
                            <b>-</b>
                            <em>미검증</em>
                            <span>{statusLabel(candidate.apply_status)}</span>
                          </>
                        )}
                      </div>

                      <p>{getCandidateShortSummary(candidate)}</p>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <div className="ai-rule-card ai-rule-detail-card wide">
          <div className="ai-rule-panel-head with-actions">
            <div>
              <div className="surface-title">선택 규칙 상세</div>
              <p>{selectedCandidate?.rule_candidate_id || "선택된 규칙 후보가 없습니다."}</p>
            </div>

            {selectedCandidate ? (
              <span className={`ai-rule-status ${String(selectedCandidate.apply_status || "").toLowerCase()}`}>
                {statusLabel(selectedCandidate.apply_status)} · {getCandidateScope(selectedCandidate)}
              </span>
            ) : null}
          </div>

          {selectedCandidate ? (
            <>
              <div className="ai-rule-action-row sticky-actions">
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => handleValidateCandidate(selectedCandidate)}
                  disabled={validating || applying || batchTesting}
                >
                  {validating ? "검증 중..." : "선택 후보 테스트"}
                </button>

                <button
                  type="button"
                  className={applyAllowed ? "primary-button" : "ghost-action"}
                  onClick={handleApplyCandidate}
                  disabled={!applyAllowed || applying || validating || batchTesting}
                >
                  {applying ? "처리 중..." : "승인 후 반영"}
                </button>

                <button
                  type="button"
                  className="danger-action"
                  onClick={() => handleRejectCandidate(selectedCandidate)}
                  disabled={applying || validating || batchTesting}
                >
                  반려
                </button>
              </div>

              <div className="ai-rule-detail-top-grid">
                <div className="ai-rule-before-after-preview emphasized">
                  <div className="ai-rule-preview-head">
                    <span>Before → After</span>
                    <strong>
                      {selectedValidationRows.length > 0
                        ? `표시 ${selectedValidationRows.length}건`
                        : "테스트 적용 전"}
                    </strong>
                  </div>

                  {selectedValidationRows.length === 0 ? (
                    <div className="ai-rule-empty small">
                      선택 후보 테스트 또는 일괄 테스트를 실행하면 “무엇이 어떻게 바뀌는지”가 표시됩니다.
                    </div>
                  ) : (
                    <div className="ai-rule-preview-list detailed">
                      {selectedValidationRows.map((row, idx) => {
                        const change = getChangeKind(row);

                        return (
                          <div className="ai-rule-preview-row detailed" key={`${row.filename}-${idx}`}>
                            <div className="ai-rule-change-meta">
                              <span className={`ai-rule-change-badge ${change.className}`}>{change.label}</span>
                              <strong title={row.filename || "-"}>{row.filename || "-"}</strong>
                              <em>{row.cert_org || "-"} / {row.field || "-"} / {decisionLabel(row.decision)}</em>
                            </div>

                            <div className="before-after-values expanded">
                              <div>
                                <span>개선 전</span>
                                <em className="before">{row.before_value || "-"}</em>
                              </div>
                              <b>→</b>
                              <div>
                                <span>개선 후</span>
                                <em className="after">{row.after_value || "-"}</em>
                              </div>
                            </div>

                            <div className="ai-rule-evidence-box">
                              <span>추출 근거 / 확인 포인트</span>
                              <p>{getEvidenceText(row)}</p>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                <div className="ai-rule-side-summary">
                  <div className="ai-rule-summary-grid compact-boxes">
                    <div>
                      <span>전체</span>
                      <strong>{formatCount(validationRecordTotal)}</strong>
                    </div>
                    <div>
                      <span>영향</span>
                      <strong>{formatCount(validationImpactedTotal)}</strong>
                    </div>
                    <div>
                      <span>개선</span>
                      <strong>{formatCount(validationSummary.improved_count)}</strong>
                    </div>
                    <div>
                      <span>악화</span>
                      <strong>{formatCount(validationSummary.regression_count)}</strong>
                    </div>
                    <div>
                      <span>자동적용</span>
                      <strong>{applyAllowed ? "YES" : "NO"}</strong>
                    </div>
                    <div>
                      <span>리포트</span>
                      <strong>{validationReport?.validation_report_id ? "YES" : "-"}</strong>
                    </div>
                  </div>

                  <div className="ai-rule-meter">
                    <div
                      className="improved"
                      style={{ width: `${percent(validationSummary.improved_count, validationChangedTotal)}%` }}
                    />
                    <div
                      className="regression"
                      style={{ width: `${percent(validationSummary.regression_count, validationChangedTotal)}%` }}
                    />
                    <div
                      className="review"
                      style={{
                        width: `${percent(
                          Number(validationSummary.changed_review_count || 0) +
                          Number(validationSummary.manual_review_count || 0),
                          validationChangedTotal
                        )}%`,
                      }}
                    />
                  </div>
                </div>
              </div>

              <details className="ai-rule-json-fold">
                <summary>규칙 원문 보기</summary>
                <pre>{JSON.stringify(selectedCandidate.proposed_rule || {}, null, 2)}</pre>
              </details>
            </>
          ) : (
            <div className="ai-rule-empty">규칙 후보를 선택하세요.</div>
          )}
        </div>
      </section>

      {validationReport ? (
        <section className="ai-rule-card ai-rule-chart-bottom-card">
          <div className="ai-rule-panel-head">
            <div>
              <div className="surface-title">기관별 인식률 비교</div>
              <p>현재 선택 후보의 테스트 결과 기준입니다. Before와 After 필드 충족률을 비교합니다.</p>
            </div>
          </div>
          <AiRuleRecognitionChart report={validationReport} />
        </section>
      ) : null}

      {validationRows.length > 0 ? (
        <section className="ai-rule-card ai-rule-report-card">
          <div className="ai-rule-panel-head">
            <div>
              <div className="surface-title">Before / After 전체 상세</div>
              <p>선택 후보의 전체 변경 행입니다. 상단 상세에는 대상 필드 기준으로 일부만 표시합니다.</p>
            </div>
          </div>

          <div className="ai-rule-report-table-v4">
            <table>
              <thead>
                <tr>
                  <th>파일</th>
                  <th>기관</th>
                  <th>필드</th>
                  <th>Before</th>
                  <th>After</th>
                  <th>판정</th>
                  <th>확인</th>
                </tr>
              </thead>
              <tbody>
                {validationRows.slice(0, 100).map((row, idx) => (
                  <tr
                    className={getDecisionClass(row.decision)}
                    key={`${row.filename}-${row.field}-${row.before_value}-${row.after_value}-${idx}`}
                  >
                    <td className="filename" title={row.filename || "-"}>{row.filename || "-"}</td>
                    <td>{row.cert_org || "-"}</td>
                    <td>{getFieldLabel(row.field)}</td>
                    <td className="value before">{row.before_value || "-"}</td>
                    <td className="value after">{row.after_value || "-"}</td>
                    <td>{decisionLabel(row.decision)}</td>
                    <td>{getAfterQualityText(row)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </>
  );
}

export default AiRuleReviewPage;
