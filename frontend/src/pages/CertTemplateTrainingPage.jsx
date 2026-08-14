import { useEffect, useMemo, useState } from "react";
import { API_BASE_URL as API_BASE } from "../api/client";
import PageHeader from "../components/PageHeader";
import StatLine from "../components/StatLine";

function CertTemplateTrainingPanel({ setActive }) {
  const DEFAULT_ROOT_DIR =
    "C:\\Users\\user\\Desktop\\DT교육\\할랄인증서\\할랄인증서 양식";
  const DEFAULT_TEST_FOLDER =
    "C:\\Users\\user\\Desktop\\DT교육\\할랄인증서\\할랄인증서 양식\\새 폴더";

  const DEFAULT_ORG_OPTIONS = [
    "BPJPH",
    "MUI",
    "JAKIM",
    "CICOT",
    "IFANCA",
    "ISA",
    "HCA",
    "HCE",
    "HFCE",
    "HFQ",
    "HQC",
    "HALAL CONTROL",
    "HFFIA",
    "JMA",
    "MUIS",
    "TQHCC",
  ];

  const [status, setStatus] = useState(null);
  const [rootDir, setRootDir] = useState(DEFAULT_ROOT_DIR);
  const [testFolder, setTestFolder] = useState(DEFAULT_TEST_FOLDER);
  const [maxPages, setMaxPages] = useState(1);
  const [rebuild, setRebuild] = useState(false);
  const [enhancedRetry, setEnhancedRetry] = useState(true);

  const [loadingStatus, setLoadingStatus] = useState(false);
  const [importing, setImporting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [savingDecision, setSavingDecision] = useState(false);

  const [importResult, setImportResult] = useState(null);
  const [testResult, setTestResult] = useState(null);
  const [decisionFilter, setDecisionFilter] = useState("ALL");
  const [keyword, setKeyword] = useState("");
  const [error, setError] = useState("");

  const [checkedHashes, setCheckedHashes] = useState([]);
  const [correctionOrg, setCorrectionOrg] = useState("");
  const [decisionMemo, setDecisionMemo] = useState("");

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });

    const text = await response.text();
    let data = null;

    try {
      data = text ? JSON.parse(text) : null;
    } catch (err) {
      data = { raw: text };
    }

    if (!response.ok) {
      throw new Error(data?.detail || data?.message || text || `HTTP ${response.status}`);
    }

    return data;
  }

  async function loadStatus() {
    try {
      setLoadingStatus(true);
      setError("");
      const data = await fetchJson(`${API_BASE}/cert-template/status`);
      setStatus(data);
    } catch (err) {
      setError(err.message || "양식 DB 상태 조회 실패");
    } finally {
      setLoadingStatus(false);
    }
  }

  async function runImport(forceRebuild = false) {
    if (!rootDir.trim()) {
      setError("학습 폴더 경로를 입력하세요.");
      return;
    }

    try {
      setImporting(true);
      setError("");
      setImportResult(null);

      const data = await fetchJson(`${API_BASE}/cert-template/import`, {
        method: "POST",
        body: JSON.stringify({
          root_dir: rootDir.trim(),
          rebuild: Boolean(forceRebuild || rebuild),
          max_pages: Number(maxPages) || 1,
        }),
      });

      setImportResult(data);
      await loadStatus();
    } catch (err) {
      setError(err.message || "양식 DB 업데이트 실패");
    } finally {
      setImporting(false);
    }
  }

  async function runTest() {
    if (!testFolder.trim()) {
      setError("테스트 폴더 경로를 입력하세요.");
      return;
    }

    try {
      setTesting(true);
      setError("");
      setTestResult(null);
      setDecisionFilter("ALL");
      setCheckedHashes([]);

      const data = await fetchJson(`${API_BASE}/cert-template/test-folder`, {
        method: "POST",
        body: JSON.stringify({
          folder_path: testFolder.trim(),
          enhanced_retry: Boolean(enhancedRetry),
        }),
      });

      setTestResult({
        ...data,
        rows: (data.rows || []).map(normalizeDecisionRow),
      });
    } catch (err) {
      setError(err.message || "테스트 실행 실패");
    } finally {
      setTesting(false);
    }
  }

  useEffect(() => {
    loadStatus();
  }, []);

  const rows = testResult?.rows || [];

  const IMAGE_DECISION_TYPES = ["AUTO_IMAGE", "REVIEW", "MANUAL_REVIEW", "NO_REFERENCE", "ERROR"];
  const ADMIN_DECISION_TYPES = [
    "AUTO_CONFIRMED",
    "MANUAL_CONFIRMED",
    "MANUAL_CORRECTED",
    "EXCLUDED",
    "RESTORED",
  ];

  function inferImageDecision(row) {
    const rawCandidates = [
      row.image_decision,
      row.original_decision,
      row.template_decision,
      row.base_decision,
      row.decision,
    ]
      .filter(Boolean)
      .map((value) => String(value).toUpperCase());

    const fromRow = rawCandidates.find((value) => IMAGE_DECISION_TYPES.includes(value));

    if (fromRow) return fromRow;

    const manualDecision = row.manual_decision || row.admin_decision || null;
    const fromManual = String(manualDecision?.original_decision || "").toUpperCase();

    if (IMAGE_DECISION_TYPES.includes(fromManual)) return fromManual;

    const score = Number(row.score || row.image_score || 0);
    const margin = Number(row.margin || 0);

    if (score >= 0.82 && margin >= 0.07) return "AUTO_IMAGE";
    if (score < 0.70 || margin < 0.04) return "MANUAL_REVIEW";

    return "REVIEW";
  }

  function normalizeDecisionRow(row) {
    const rawDecision = String(row.decision || "").toUpperCase();

    let manualDecision =
      row.manual_decision ||
      row.admin_decision ||
      null;

    if (!manualDecision && ADMIN_DECISION_TYPES.includes(rawDecision)) {
      manualDecision = {
        decision_type: rawDecision,
        final_org: row.final_org || row.predicted_org || "-",
        predicted_org: row.predicted_org || "-",
        original_decision: row.original_decision || "",
        is_excluded: rawDecision === "EXCLUDED" ? 1 : 0,
      };
    }

    const imageDecision = inferImageDecision({
      ...row,
      manual_decision: manualDecision,
    });

    return {
      ...row,
      decision: imageDecision,
      image_decision: imageDecision,
      manual_decision: manualDecision,
    };
  }

  const normalizedRows = useMemo(() => {
    return rows.map(normalizeDecisionRow);
  }, [rows]);

  const summary = useMemo(() => {
    const next = {
      total: normalizedRows.length,
      AUTO_IMAGE: 0,
      REVIEW: 0,
      MANUAL_REVIEW: 0,
      EXCLUDED: 0,
      CONFIRMED: 0,
      CORRECTED: 0,
    };

    normalizedRows.forEach((row) => {
      const manualType = String(
        row.manual_decision?.decision_type ||
        row.admin_decision?.decision_type ||
        ""
      ).toUpperCase();

      if (row.decision === "AUTO_IMAGE") next.AUTO_IMAGE += 1;
      else if (row.decision === "REVIEW") next.REVIEW += 1;
      else if (row.decision === "MANUAL_REVIEW") next.MANUAL_REVIEW += 1;

      if (["AUTO_CONFIRMED", "MANUAL_CONFIRMED"].includes(manualType)) {
        next.CONFIRMED += 1;
      }

      if (manualType === "MANUAL_CORRECTED") {
        next.CORRECTED += 1;
      }

      if (manualType === "EXCLUDED" || Number(row.manual_decision?.is_excluded || 0) === 1) {
        next.EXCLUDED += 1;
      }
    });

    return next;
  }, [normalizedRows]);

  const orgOptions = useMemo(() => {
    const values = new Set(DEFAULT_ORG_OPTIONS);

    normalizedRows.forEach((row) => {
      if (row.predicted_org && row.predicted_org !== "-") values.add(row.predicted_org);
      if (row.second_org && row.second_org !== "-") values.add(row.second_org);
      if (row.manual_decision?.final_org && row.manual_decision.final_org !== "-") {
        values.add(row.manual_decision.final_org);
      }

      (row.top_candidates || []).forEach((item) => {
        if (item.org && item.org !== "-") values.add(item.org);
      });
    });

    return Array.from(values).sort();
  }, [normalizedRows]);

  const filteredRows = useMemo(() => {
    const q = keyword.trim().toLowerCase();

    return normalizedRows.filter((row) => {
      const manualType = String(
        row.manual_decision?.decision_type ||
        row.admin_decision?.decision_type ||
        ""
      ).toUpperCase();

      const isConfirmed = ["AUTO_CONFIRMED", "MANUAL_CONFIRMED"].includes(manualType);
      const isCorrected = manualType === "MANUAL_CORRECTED";
      const isExcluded =
        manualType === "EXCLUDED" ||
        Number(row.manual_decision?.is_excluded || 0) === 1;

      if (decisionFilter === "CONFIRMED" && !isConfirmed) return false;
      if (decisionFilter === "CORRECTED" && !isCorrected) return false;
      if (decisionFilter === "EXCLUDED" && !isExcluded) return false;

      if (
        !["ALL", "CONFIRMED", "CORRECTED", "EXCLUDED"].includes(decisionFilter) &&
        row.decision !== decisionFilter
      ) {
        return false;
      }

      if (!q) return true;

      return [
        row.filename,
        row.predicted_org,
        row.second_org,
        row.decision,
        row.feature_kind,
        row.file_path,
        manualType,
        row.manual_decision?.final_org,
        row.admin_decision?.final_org,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(q);
    });
  }, [normalizedRows, decisionFilter, keyword]);

  const selectedRows = useMemo(() => {
    const selected = new Set(checkedHashes);
    return normalizedRows.filter((row) => selected.has(row.file_hash));
  }, [normalizedRows, checkedHashes]);

  function formatScore(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "-";
    return n.toFixed(4);
  }

  function getDecisionLabel(value) {
    if (value === "AUTO_IMAGE") return "자동";
    if (value === "REVIEW") return "검토";
    if (value === "MANUAL_REVIEW") return "수동";
    if (value === "EXCLUDED") return "제외";
    if (value === "AUTO_CONFIRMED") return "확정";
    if (value === "MANUAL_CONFIRMED") return "확정";
    if (value === "MANUAL_CORRECTED") return "정정";
    if (value === "RESTORED") return "복구";
    return value || "-";
  }

  function getAdminDecision(row) {
    return row.manual_decision || row.admin_decision || null;
  }

  function getFinalOrg(row) {
    const decision = getAdminDecision(row);
    const finalOrg = String(decision?.final_org || "").trim();

    if (finalOrg && finalOrg !== "-") return finalOrg;

    return row.predicted_org || "-";
  }

  function getAdminDecisionType(row) {
    return String(getAdminDecision(row)?.decision_type || "").toUpperCase();
  }

  function toggleChecked(fileHash) {
    if (!fileHash) return;

    setCheckedHashes((prev) => {
      if (prev.includes(fileHash)) return prev.filter((hash) => hash !== fileHash);
      return [...prev, fileHash];
    });
  }

  function checkAllFiltered() {
    setCheckedHashes(filteredRows.map((row) => row.file_hash).filter(Boolean));
  }

  function clearChecked() {
    setCheckedHashes([]);
  }

  function buildDecisionPayload(row, decisionType, finalOrg) {
    const imageDecision = inferImageDecision(row);
    const currentFinalOrg = getFinalOrg(row);
    const nextFinalOrg = String(finalOrg || currentFinalOrg || row.predicted_org || "-").trim();

    return {
      file_hash: row.file_hash,
      predicted_org: row.predicted_org || "-",
      final_org: nextFinalOrg || "-",
      decision_type: decisionType,
      decision_score: Number(row.score || 0),
      image_score: Number(row.score || 0),
      margin: Number(row.margin || 0),
      original_decision: imageDecision,
      original_filename: row.filename || "",
      file_path: row.file_path || "",
      memo: decisionMemo || "",
      decision_reason: decisionMemo || decisionType,
      confirmed_by: "admin",
    };
  }

  function patchRowsWithDecisions(savedRows) {
    const savedMap = new Map((savedRows || []).map((row) => [row.file_hash, row]));

    setTestResult((prev) => {
      if (!prev?.rows) return prev;

      return {
        ...prev,
        rows: prev.rows.map((row) => {
          const saved = savedMap.get(row.file_hash);
          if (!saved) return normalizeDecisionRow(row);

          const savedType = String(saved.decision_type || "").toUpperCase();
          const imageDecision = inferImageDecision(row);

          return normalizeDecisionRow({
            ...row,
            decision: imageDecision,
            image_decision: imageDecision,
            manual_decision: {
              ...(row.manual_decision || {}),
              ...saved,
              decision_type: savedType || saved.decision_type,
              final_org: saved.final_org || getFinalOrg(row),
              predicted_org: saved.predicted_org || row.predicted_org,
              original_decision: saved.original_decision || imageDecision,
              is_excluded: savedType === "EXCLUDED" ? 1 : 0,
            },
          });
        }),
      };
    });
  }


  function patchRowsClearDecisions(fileHashes) {
    const clearSet = new Set((fileHashes || []).filter(Boolean));

    setTestResult((prev) => {
      if (!prev?.rows) return prev;

      return {
        ...prev,
        rows: prev.rows.map((row) => {
          if (!clearSet.has(row.file_hash)) return normalizeDecisionRow(row);

          const imageDecision = inferImageDecision({
            ...row,
            manual_decision: null,
            admin_decision: null,
          });

          return normalizeDecisionRow({
            ...row,
            decision: imageDecision,
            image_decision: imageDecision,
            manual_decision: null,
            admin_decision: null,
            final_org: "",
          });
        }),
      };
    });
  }

  async function saveSelectedDecision(decisionType, finalOrgResolver) {
    if (selectedRows.length === 0) {
      alert("저장할 행을 선택하세요.");
      return;
    }

    const items = selectedRows.map((row) => {
      const finalOrg =
        typeof finalOrgResolver === "function"
          ? finalOrgResolver(row)
          : finalOrgResolver;

      return buildDecisionPayload(row, decisionType, finalOrg);
    });

    try {
      setSavingDecision(true);
      setError("");

      const data = await fetchJson(`${API_BASE}/cert-template/decisions/bulk`, {
        method: "POST",
        body: JSON.stringify({
          confirmed_by: "admin",
          items,
        }),
      });

      if (data.error_count > 0) {
        setError(`일부 저장 실패: ${data.error_count}건`);
      }

      patchRowsWithDecisions(data.saved || []);
      setCheckedHashes([]);
      await loadStatus();
    } catch (err) {
      setError(err.message || "판정 저장 실패");
    } finally {
      setSavingDecision(false);
    }
  }

  function handleConfirmSelected() {
    saveSelectedDecision("MANUAL_CONFIRMED", (row) => getFinalOrg(row));
  }

  function handleExcludeSelected() {
    const ok = window.confirm(`선택한 ${selectedRows.length}건을 판독 제외로 저장합니다. 계속할까요?`);
    if (!ok) return;

    saveSelectedDecision("EXCLUDED", (row) => getFinalOrg(row));
  }

  function handleRestoreSelected() {
    const hasExcluded = selectedRows.some((row) => getAdminDecisionType(row) === "EXCLUDED");

    if (!hasExcluded) {
      alert("제외 상태인 행을 선택했을 때만 제외 해제할 수 있습니다.");
      return;
    }

    saveSelectedDecision("MANUAL_CONFIRMED", (row) => getFinalOrg(row));
  }

  function handleCorrectSelected() {
    if (!correctionOrg.trim()) {
      alert("정정할 최종 기관을 선택하세요.");
      return;
    }

    saveSelectedDecision("MANUAL_CORRECTED", correctionOrg.trim());
  }


  async function handleClearDecisionSelected() {
    if (selectedRows.length === 0) {
      alert("초기화할 행을 선택하세요.");
      return;
    }

    const hasAdminDecision = selectedRows.some((row) => Boolean(getAdminDecision(row)));

    if (!hasAdminDecision) {
      alert("관리자 판정이 저장된 행을 선택했을 때만 초기화할 수 있습니다.");
      return;
    }

    const ok = window.confirm(
      `선택한 ${selectedRows.length}건의 관리자 판정값을 초기화합니다. 계속할까요?`
    );

    if (!ok) return;

    const fileHashes = selectedRows.map((row) => row.file_hash).filter(Boolean);

    try {
      setSavingDecision(true);
      setError("");

      const data = await fetchJson(`${API_BASE}/cert-template/decisions/clear`, {
        method: "POST",
        body: JSON.stringify({
          confirmed_by: "admin",
          file_hashes: fileHashes,
        }),
      });

      if (data.error_count > 0) {
        setError(`일부 초기화 실패: ${data.error_count}건`);
      }

      const clearedHashes = (data.cleared || [])
        .map((row) => row.file_hash)
        .filter(Boolean);

      patchRowsClearDecisions(clearedHashes.length ? clearedHashes : fileHashes);
      setCheckedHashes([]);
      await loadStatus();
    } catch (err) {
      setError(err.message || "판정 초기화 실패");
    } finally {
      setSavingDecision(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="ADMIN / CERT TEMPLATE"
        title="할랄 인증서 양식 학습"
        desc="기관별 인증서 양식을 DB화하고, 테스트 폴더 기준으로 이미지 유사도 판정 결과를 검증합니다."
        onBack={() => setActive("home")}
      />

      <StatLine
        items={[
          { label: "등록 기관", value: status?.org_count ?? "-" },
          { label: "기준 파일", value: status?.template_file_count ?? status?.file_count ?? "-" },
          { label: "Feature", value: status?.feature_count ?? status?.page_feature_count ?? "-" },
          { label: "테스트 파일", value: rows.length || "-" },
        ]}
      />

      {error ? <div className="cert-template-error">{error}</div> : null}

      <section className="cert-template-admin-grid">
        <div className="detail-surface cert-template-admin-card">
          <div className="detail-top">
            <div>
              <div className="surface-title">양식 DB 업데이트</div>
              <h2>기관별 폴더 학습</h2>
            </div>

            <button className="ghost-action" onClick={loadStatus} disabled={loadingStatus}>
              {loadingStatus ? "조회 중..." : "상태 새로고침"}
            </button>
          </div>

          <div className="form-grid cert-template-form-grid">
            <label className="wide">
              <span>학습 폴더 경로</span>
              <input
                value={rootDir}
                onChange={(e) => setRootDir(e.target.value)}
                placeholder="C:\\Users\\user\\Desktop\\DT교육\\할랄인증서\\할랄인증서 양식"
              />
            </label>

            <label>
              <span>PDF 페이지 수</span>
              <input
                type="number"
                min="1"
                max="5"
                value={maxPages}
                onChange={(e) => setMaxPages(e.target.value)}
              />
            </label>

            <label className="cert-template-check-row">
              <input
                type="checkbox"
                checked={rebuild}
                onChange={(e) => setRebuild(e.target.checked)}
              />
              <span>기존 DB 초기화 후 재구축</span>
            </label>
          </div>

          <div className="toolbar right cert-template-action-row">
            <button
              className="primary-button"
              onClick={() => runImport(false)}
              disabled={importing}
            >
              {importing ? "업데이트 중..." : "양식 DB 업데이트"}
            </button>

            <button
              className="danger-action"
              onClick={() => runImport(true)}
              disabled={importing}
            >
              전체 재구축
            </button>
          </div>

          {importResult ? (
            <div className="cert-template-result-line">
              <span>파일 {importResult.file_count ?? "-"}건</span>
              <span>Feature {importResult.page_feature_count ?? "-"}건</span>
              <span>오류 {importResult.error_count ?? 0}건</span>
              <span>소요 {importResult.elapsed_sec ?? "-"}초</span>
            </div>
          ) : null}
        </div>

        <div className="detail-surface cert-template-admin-card">
          <div className="detail-top">
            <div>
              <div className="surface-title">테스트 폴더 검증</div>
              <h2>기관 후보 판정 테스트</h2>
            </div>

            <span className="badge ok">
              {testResult?.count ? `${testResult.count}건` : "READY"}
            </span>
          </div>

          <div className="form-grid cert-template-form-grid">
            <label className="wide">
              <span>테스트 폴더 경로</span>
              <input
                value={testFolder}
                onChange={(e) => setTestFolder(e.target.value)}
                placeholder="...\\할랄인증서 양식\\새 폴더"
              />
            </label>

            <label className="cert-template-check-row">
              <input
                type="checkbox"
                checked={enhancedRetry}
                onChange={(e) => setEnhancedRetry(e.target.checked)}
              />
              <span>저신뢰 파일 enhanced 재시도</span>
            </label>
          </div>

          <div className="toolbar right cert-template-action-row">
            <button className="primary-button" onClick={runTest} disabled={testing}>
              {testing ? "테스트 중..." : "테스트 실행"}
            </button>
          </div>
        </div>
      </section>

      <section className="detail-surface cert-template-result-panel">
        <div className="detail-top">
          <div>
            <div className="surface-title">테스트 결과</div>
            <h2>이미지 유사도 판정 결과</h2>
          </div>
        </div>

        <div className="cert-template-summary-row">
          <button
            className={decisionFilter === "ALL" ? "cert-template-summary active" : "cert-template-summary"}
            onClick={() => setDecisionFilter("ALL")}
          >
            <span>전체</span>
            <strong>{summary.total}</strong>
          </button>

          <button
            className={decisionFilter === "AUTO_IMAGE" ? "cert-template-summary active" : "cert-template-summary"}
            onClick={() => setDecisionFilter("AUTO_IMAGE")}
          >
            <span>자동</span>
            <strong>{summary.AUTO_IMAGE}</strong>
          </button>

          <button
            className={decisionFilter === "REVIEW" ? "cert-template-summary active" : "cert-template-summary"}
            onClick={() => setDecisionFilter("REVIEW")}
          >
            <span>검토</span>
            <strong>{summary.REVIEW}</strong>
          </button>

          <button
            className={decisionFilter === "MANUAL_REVIEW" ? "cert-template-summary active" : "cert-template-summary"}
            onClick={() => setDecisionFilter("MANUAL_REVIEW")}
          >
            <span>수동</span>
            <strong>{summary.MANUAL_REVIEW}</strong>
          </button>

          <button
            className={decisionFilter === "CONFIRMED" ? "cert-template-summary active" : "cert-template-summary"}
            onClick={() => setDecisionFilter("CONFIRMED")}
          >
            <span>확정</span>
            <strong>{summary.CONFIRMED}</strong>
          </button>

          <button
            className={decisionFilter === "CORRECTED" ? "cert-template-summary active" : "cert-template-summary"}
            onClick={() => setDecisionFilter("CORRECTED")}
          >
            <span>정정</span>
            <strong>{summary.CORRECTED}</strong>
          </button>

          <button
            className={decisionFilter === "EXCLUDED" ? "cert-template-summary active" : "cert-template-summary"}
            onClick={() => setDecisionFilter("EXCLUDED")}
          >
            <span>제외</span>
            <strong>{summary.EXCLUDED}</strong>
          </button>
        </div>

        <div className="log-toolbar cert-template-toolbar cert-template-decision-toolbar">
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="파일명 / 기관 / 상태 검색"
          />

          <select
            value={correctionOrg}
            onChange={(e) => setCorrectionOrg(e.target.value)}
            title="선택 행 기관 정정"
          >
            <option value="">정정 기관 선택</option>
            {orgOptions.map((org) => (
              <option key={org} value={org}>{org}</option>
            ))}
          </select>

          <input
            value={decisionMemo}
            onChange={(e) => setDecisionMemo(e.target.value)}
            placeholder="저장 메모"
          />

          <button type="button" className="soft-chip-action" onClick={checkAllFiltered} disabled={filteredRows.length === 0}>
            표시행 선택
          </button>

          <button type="button" className="soft-chip-action" onClick={clearChecked} disabled={checkedHashes.length === 0}>
            선택해제
          </button>

          <button type="button" className="primary-button" onClick={handleConfirmSelected} disabled={checkedHashes.length === 0 || savingDecision}>
            확정
          </button>

          <button type="button" className="ghost-action" onClick={handleCorrectSelected} disabled={checkedHashes.length === 0 || !correctionOrg || savingDecision}>
            기관 정정
          </button>

          <button type="button" className="danger-action" onClick={handleExcludeSelected} disabled={checkedHashes.length === 0 || savingDecision}>
            선택 제외
          </button>

          <button type="button" className="soft-chip-action" onClick={handleRestoreSelected} disabled={checkedHashes.length === 0 || savingDecision}>
            제외 해제
          </button>

          <span className="cert-template-count-text">
            선택 {checkedHashes.length} / 표시 {filteredRows.length} / 전체 {rows.length}
          </span>
        </div>

        <div className="cert-template-table-shell">
          <table className="cert-template-table">
            <colgroup>
              <col style={{ width: "4%" }} />
              <col style={{ width: "7%" }} />
              <col style={{ width: "8%" }} />
              <col style={{ width: "9%" }} />
              <col style={{ width: "8%" }} />
              <col style={{ width: "8%" }} />
              <col style={{ width: "8%" }} />
              <col style={{ width: "8%" }} />
              <col style={{ width: "8%" }} />
              <col style={{ width: "20%" }} />
              <col style={{ width: "12%" }} />
            </colgroup>

            <thead>
              <tr>
                <th>선택</th>
                <th>상태</th>
                <th>관리자</th>
                <th>최종기관</th>
                <th>1순위</th>
                <th>점수</th>
                <th>2순위</th>
                <th>Margin</th>
                <th>Feature</th>
                <th className="is-left">파일명</th>
                <th className="is-left">Top 후보</th>
              </tr>
            </thead>

            <tbody>
              {filteredRows.length === 0 ? (
                <tr>
                  <td colSpan={11} className="cert-template-empty">
                    테스트 결과가 없습니다.
                  </td>
                </tr>
              ) : (
                filteredRows.map((row, idx) => {
                  const adminDecision = getAdminDecision(row);
                  const adminType = adminDecision?.decision_type || "";
                  const checked = checkedHashes.includes(row.file_hash);

                  return (
                    <tr key={`${row.file_hash}-${idx}`}>
                      <td>
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleChecked(row.file_hash)}
                        />
                      </td>
                      <td>
                        <span className={`cert-template-badge ${row.decision || ""}`}>
                          {getDecisionLabel(row.decision)}
                        </span>
                      </td>
                      <td>
                        <span className={`cert-template-badge ${adminType || "NONE"}`}>
                          {adminType ? getDecisionLabel(adminType) : "-"}
                        </span>
                      </td>
                      <td>{getFinalOrg(row)}</td>
                      <td>{row.predicted_org || "-"}</td>
                      <td>{formatScore(row.score)}</td>
                      <td>{row.second_org || "-"}</td>
                      <td>{formatScore(row.margin)}</td>
                      <td>{row.feature_kind || "-"}</td>
                      <td className="is-left">
                        <span className="cert-template-ellipsis" title={row.filename || ""}>
                          {row.filename || "-"}
                        </span>
                      </td>
                      <td className="is-left">
                        <span
                          className="cert-template-ellipsis"
                          title={(row.top_candidates || [])
                            .map((item) => `${item.org}: ${formatScore(item.score)}`)
                            .join(" / ")}
                        >
                          {(row.top_candidates || [])
                            .slice(0, 3)
                            .map((item) => `${item.org} ${formatScore(item.score)}`)
                            .join(" · ") || "-"}
                        </span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

export default CertTemplateTrainingPanel;
