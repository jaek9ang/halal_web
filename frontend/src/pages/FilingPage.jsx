import React, { useEffect, useMemo, useState } from "react";
import {
  getFilingCandidates,
  getFilingStatus,
  previewCertificateFiling,
  confirmCertificateFiling,
} from "../api";
import "./FilingPage.css";

function normalizeCandidate(row) {
  const job = row?.job || row?.ocr_job || {};
  const requestContext = row?.request_context || {};
  const matchValidation = requestContext?.match_validation || row?.match_validation || {};
  const selectedMailItem =
    requestContext?.matched_mail_item
    || row?.matched_mail_item
    || matchValidation?.selected_mail_item
    || row?.selected_mail_item
    || {};

  const selectedMatch =
    requestContext?.selected_pmf_match
    || row?.selected_pmf_match
    || row?.top_pmf_match
    || row?.selected_pmf_matches?.[0]
    || row?.top_match
    || row?.pmf_match
    || row?.pmf_material
    || {};

  const certificate = row?.certificate || row?.cert_values || {};
  const rawRowPos =
    selectedMatch?.row_pos
    ?? selectedMatch?.pmf_row_pos
    ?? row?.pmf_row_pos
    ?? row?.row_pos
    ?? null;

  const rawDepth =
    selectedMatch?.depth
    ?? selectedMatch?.pmf_depth
    ?? row?.pmf_depth
    ?? row?.depth
    ?? 0;

  const ocrJobId = Number(
    row?.ocr_job_id
    ?? job?.id
    ?? row?.job_id
    ?? row?.id
    ?? 0,
  );

  return {
    raw: row,
    ocrJobId,
    filename: String(job?.filename || row?.filename || "OCR 인증서"),
    rowPos:
      rawRowPos === null || rawRowPos === undefined || rawRowPos === ""
        ? null
        : Number(rawRowPos),
    depth: Number(rawDepth || 0),
    materialNo: String(
      selectedMatch?.material_no
      || row?.material_no
      || selectedMailItem?.material_no
      || "-",
    ),
    materialName: String(
      selectedMatch?.material_name
      || row?.material_name
      || selectedMailItem?.material_name
      || "",
    ),
    englishName: String(
      selectedMatch?.english_name
      || row?.english_name
      || selectedMailItem?.english_name
      || "PMF 원료 확인 필요",
    ),
    maker: String(
      selectedMatch?.maker
      || selectedMatch?.manufacturer
      || row?.maker
      || row?.manufacturer
      || selectedMailItem?.maker
      || "-",
    ),
    supplier: String(
      selectedMatch?.supplier
      || row?.supplier
      || selectedMailItem?.supplier
      || requestContext?.mail_log?.supplier
      || "-",
    ),
    certOrg: String(certificate?.cert_org || certificate?.org || row?.cert_org || "-"),
    certNo: String(certificate?.cert_no || certificate?.certificate_no || row?.cert_no || "-"),
    canPreview: Boolean(
      ocrJobId
      && rawRowPos !== null
      && rawRowPos !== undefined
      && rawRowPos !== "",
    ),
  };
}

function decisionLabel(code) {
  const labels = {
    SAME_AUTHORITY_RENEWAL: "동일 인증서 갱신",
    DUPLICATE: "기존 인증서와 동일",
    NEW_CERTIFICATE: "신규 인증서 검토",
    CERTIFICATE_NUMBER_CHANGED: "인증번호 변경 검토",
    AUTHORITY_CHANGE_REVIEW: "인증기관 변경 검토",
    SAME_AUTHORITY_UPDATE_REVIEW: "동일 기관 변경 검토",
    OLDER_CERTIFICATE: "기존보다 이전 인증서",
    INCOMPLETE_CERTIFICATE_REVIEW: "인증서 정보 보완 필요",
    MANUFACTURER_CHANGED: "제조사 변경 검토",
    WRONG_CERTIFICATE: "대상 원료 불일치",
    OCR_REVIEW_REQUIRED: "OCR 수동 검토",
  };

  return labels[code] || code || "판정 대기";
}

function reasonLabel(reason) {
  const value = String(reason || "").replace(/^판정 사유:\s*/i, "").trim();
  const labels = {
    "The same certificate was renewed with a later expiry date.":
      "동일 인증번호의 갱신 인증서로 확인되었습니다.",
    "Authority, certificate number and expiry date are unchanged.":
      "인증기관·인증번호·유효기간이 기존 정보와 동일합니다.",
    "The manufacturer differs from the current PMF manufacturer.":
      "인증서 제조사와 PMF 제조사 확인이 필요합니다.",
    "Required certificate fields are missing.":
      "인증서 필수 정보 일부가 누락되었습니다.",
  };

  return labels[value] || value || "검토 사유가 없습니다.";
}

function Header({ onBack }) {
  return (
    <div className="page-header">
      <button className="back-button" type="button" onClick={onBack}>
        ← 홈
      </button>
      <div>
        <div className="eyebrow">CERTIFICATE FILING</div>
        <h1>인증서 자동분류</h1>
        <p>
          OCR 판독 결과를 메일 요청 정보와 PMF 관리대장에 연결하여 인증서 파일을
          자동 분류하고 인증기관·인증번호·유효기간을 PMF에 반영합니다.
        </p>
      </div>
    </div>
  );
}

export default function FilingPage({ setActive }) {
  const [status, setStatus] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [selected, setSelected] = useState(null);
  const [preview, setPreview] = useState(null);
  const [loadingCandidates, setLoadingCandidates] = useState(true);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmResult, setConfirmResult] = useState(null);
  const [error, setError] = useState("");
  const [keyword, setKeyword] = useState("");

  const visibleCandidates = useMemo(() => {
    const query = keyword.trim().toLowerCase();
    if (!query) return candidates;

    return candidates.filter((item) => (
      item.filename.toLowerCase().includes(query)
      || item.englishName.toLowerCase().includes(query)
      || item.materialName.toLowerCase().includes(query)
      || item.maker.toLowerCase().includes(query)
      || item.supplier.toLowerCase().includes(query)
      || String(item.materialNo).toLowerCase().includes(query)
      || String(item.ocrJobId).includes(query)
    ));
  }, [candidates, keyword]);

  const previewableCount = useMemo(
    () => candidates.filter((item) => item.canPreview).length,
    [candidates],
  );

  async function runPreview(candidate) {
    if (!candidate?.canPreview) {
      setError("선택 후보에 PMF 행 위치가 없어 미리보기를 실행할 수 없습니다.");
      return;
    }

    try {
      setSelected(candidate);
      setConfirmResult(null);
      setLoadingPreview(true);
      setError("");

      const data = await previewCertificateFiling({
        ocr_job_id: candidate.ocrJobId,
        pmf_row_pos: candidate.rowPos,
        pmf_depth: candidate.depth,
      });

      setPreview(data);
    } catch (err) {
      setPreview(null);
      setError(err.message);
    } finally {
      setLoadingPreview(false);
    }
  }

  async function loadData() {
    try {
      setLoadingCandidates(true);
      setError("");

      const [statusResult, candidateResult] = await Promise.all([
        getFilingStatus().catch(() => null),
        getFilingCandidates({ limit: 10 }),
      ]);

      const rows =
        candidateResult?.rows
        || candidateResult?.items
        || candidateResult?.candidates
        || [];

      const normalized = rows
        .map(normalizeCandidate)
        .filter((item) => item.ocrJobId);

      setStatus(statusResult);
      setCandidates(normalized);

      const preferred =
        normalized.find((item) => item.ocrJobId === 498 && item.canPreview)
        || normalized.find((item) => item.canPreview)
        || null;

      if (preferred) {
        await runPreview(preferred);
      } else {
        setSelected(null);
        setPreview(null);
        setConfirmResult(null);
      }
    } catch (err) {
      setCandidates([]);
      setSelected(null);
      setPreview(null);
      setConfirmResult(null);
      setError(err.message);
    } finally {
      setLoadingCandidates(false);
    }
  }

  async function handleConfirmFiling() {
    if (!selected?.canPreview || !preview?.ok) {
      setError("파일 분류를 실행할 수 있는 후보가 아닙니다.");
      return;
    }

    const confirmed = window.confirm(
      "인증서 파일을 원료 폴더로 복사하고 PMF 관리대장을 실제로 갱신합니다.\n계속 진행하시겠습니까?",
    );

    if (!confirmed) return;

    try {
      setConfirming(true);
      setConfirmResult(null);
      setError("");

      const result = await confirmCertificateFiling({
        ocr_job_id: selected.ocrJobId,
        pmf_row_pos: selected.rowPos,
        pmf_depth: selected.depth,
        overwrite: false,
        force: false,
        allow_date_regression: false,
        change_action: preview?.change_decision?.auto_action || "",
      });

      setConfirmResult(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setConfirming(false);
    }
  }

  useEffect(() => {
    // 초기 화면 진입 시 후보와 대표 미리보기를 한 번 불러온다.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const decision = preview?.change_decision || {};
  const filingPreview = preview?.filing_preview || {};
  const pmfPreview = preview?.pmf_update_preview || {};
  const snapshot = pmfPreview?.snapshot || {};
  const pmfChanges = pmfPreview?.changes || {};
  const decisionChanges = decision?.changes || {};
  const expiryChange = pmfChanges?.expiry_date || decisionChanges?.expiry_date || {};
  const manufacturerChange = decisionChanges?.manufacturer || {};
  const warnings = preview?.warnings || [];
  const blockers = preview?.blockers || [];
  const hardBlockers = preview?.hard_blockers || [];
  const uniqueBlockers = [...new Set([...hardBlockers, ...blockers])];
  const canUpdate = decision?.can_update_pmf === true;
  const isReady = Boolean(preview?.ok && uniqueBlockers.length === 0);

  return (
    <>
      <Header onBack={() => setActive("home")} />

      <section className="filing-flow-strip">
        {[
          ["01", "OCR 판독", "기관·번호·제조사 추출"],
          ["02", "PMF 매칭", "요청 원료와 관리대장 연결"],
          ["03", "파일 자동분류", "폴더 생성·표준명으로 파일 복사"],
          ["04", "PMF 자동갱신", "기관·번호·유효기간 실제 반영"],
        ].map(([number, title, desc], index) => (
          <React.Fragment key={title}>
            <div className={preview ? "filing-flow-step done" : "filing-flow-step"}>
              <span>{number}</span>
              <div>
                <strong>{title}</strong>
                <small>{desc}</small>
              </div>
            </div>
            {index < 3 && <div className="filing-flow-arrow">→</div>}
          </React.Fragment>
        ))}
      </section>

      <section className="filing-stat-grid">
        <article className="filing-stat-card">
          <span>조회 후보</span>
          <strong>{loadingCandidates ? "…" : candidates.length}</strong>
          <small>OCR 완료 건</small>
        </article>
        <article className="filing-stat-card">
          <span>PMF 매칭</span>
          <strong>{loadingCandidates ? "…" : previewableCount}</strong>
          <small>자동분류 가능</small>
        </article>
        <article className={isReady ? "filing-stat-card success" : "filing-stat-card"}>
          <span>자동 판정</span>
          <strong>{preview ? (isReady ? "정상" : "검토") : "-"}</strong>
          <small>{decisionLabel(decision?.decision_code)}</small>
        </article>
        <article className={uniqueBlockers.length ? "filing-stat-card danger" : "filing-stat-card success"}>
          <span>차단 항목</span>
          <strong>{preview ? uniqueBlockers.length : "-"}</strong>
          <small>{uniqueBlockers.length ? "확인 필요" : "확정 가능"}</small>
        </article>
      </section>

      {error && (
        <div className="filing-error-banner">
          <strong>처리 중 확인이 필요합니다.</strong>
          <span>{error}</span>
        </div>
      )}

      <section className="filing-workspace">
        <article className="filing-candidate-panel">
          <div className="filing-panel-header">
            <div>
              <span className="filing-panel-kicker">OCR CANDIDATES</span>
              <h2>분류 대기 인증서</h2>
              <p>후보를 선택해 파일 분류 경로와 PMF 반영 내용을 확인한 뒤 실행합니다.</p>
            </div>
            <button
              type="button"
              className="filing-refresh-button"
              onClick={loadData}
              disabled={loadingCandidates}
            >
              {loadingCandidates ? "조회 중" : "새로고침"}
            </button>
          </div>

          <div className="filing-search-row">
            <input
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="파일명, 원료명, 제조사, 업체 검색"
            />
            <span>{visibleCandidates.length}건</span>
          </div>

          <div className="filing-candidate-list">
            {loadingCandidates ? (
              <div className="filing-empty-state">
                <span className="filing-spinner" />
                <strong>OCR 후보와 PMF 정보를 연결하는 중</strong>
                <p>관리대장 크기에 따라 수 초 정도 걸릴 수 있습니다.</p>
              </div>
            ) : visibleCandidates.length === 0 ? (
              <div className="filing-empty-state">
                <strong>조회된 후보가 없습니다.</strong>
                <p>검색어를 지우거나 OCR 완료 건을 확인하세요.</p>
              </div>
            ) : (
              visibleCandidates.map((item) => {
                const active = selected?.ocrJobId === item.ocrJobId;
                return (
                  <button
                    type="button"
                    key={`${item.ocrJobId}-${item.rowPos}-${item.depth}`}
                    className={active ? "filing-candidate-item active" : "filing-candidate-item"}
                    onClick={() => runPreview(item)}
                    disabled={!item.canPreview}
                  >
                    <div className="filing-candidate-top">
                      <span className="filing-job-badge">JOB {item.ocrJobId}</span>
                      <span className={item.canPreview ? "filing-match-badge ready" : "filing-match-badge"}>
                        {item.canPreview ? "PMF 매칭" : "매칭 확인"}
                      </span>
                    </div>
                    <strong title={item.filename}>{item.filename}</strong>
                    <div className="filing-candidate-material">
                      <b>{item.materialNo}</b>
                      <span>{item.englishName}</span>
                    </div>
                    <div className="filing-candidate-meta">
                      <span>{item.supplier}</span>
                      <span>{item.maker}</span>
                      <span>{item.certOrg}</span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </article>

        <article className="filing-preview-panel">
          <div className="filing-panel-header preview">
            <div>
              <span className="filing-panel-kicker">AUTOMATED FILING</span>
              <h2>인증서 분류 및 PMF 갱신</h2>
              <p>검증 결과를 확인하고 실제 파일 분류와 PMF 반영을 실행합니다.</p>
            </div>
            {selected?.canPreview && (
              <button
                type="button"
                className="filing-refresh-button dark"
                onClick={() => runPreview(selected)}
                disabled={loadingPreview}
              >
                {loadingPreview ? "분석 중" : "다시 검증"}
              </button>
            )}
          </div>

          {loadingPreview ? (
            <div className="filing-preview-loading">
              <span className="filing-spinner large" />
              <strong>인증서와 PMF 관리대장을 비교하고 있습니다.</strong>
              <p>기관, 인증번호, 제조사, 유효기간 및 저장 경로를 검증합니다.</p>
            </div>
          ) : !preview ? (
            <div className="filing-empty-state preview">
              <strong>왼쪽에서 인증서 후보를 선택하세요.</strong>
              <p>선택 건의 저장 경로와 PMF 변경값이 여기에 표시됩니다.</p>
            </div>
          ) : (
            <div className="filing-preview-content">
              <div className={isReady ? "filing-decision-card ready" : "filing-decision-card review"}>
                <div>
                  <span>자동 판정 결과</span>
                  <h3>{decisionLabel(decision?.decision_code)}</h3>
                  <p>
                    {isReady
                      ? "인증서 파일 분류와 PMF 갱신을 진행할 수 있는 상태입니다."
                      : "확정 전에 표시된 검토 항목을 확인해야 합니다."}
                  </p>
                </div>
                <div className="filing-decision-status">
                  <strong>{isReady ? "READY" : "REVIEW"}</strong>
                  <span>{decision?.auto_action || "-"}</span>
                </div>
              </div>

              <div className="filing-material-summary">
                <div>
                  <span>원료번호</span>
                  <strong>{snapshot?.material_no || selected?.materialNo || "-"}</strong>
                </div>
                <div className="wide">
                  <span>대상 원료</span>
                  <strong>{snapshot?.english_name || selected?.englishName || "-"}</strong>
                </div>
                <div>
                  <span>공급사</span>
                  <strong>{snapshot?.supplier || selected?.supplier || "-"}</strong>
                </div>
                <div>
                  <span>인증기관</span>
                  <strong>{snapshot?.org || preview?.certificate?.cert_org || "-"}</strong>
                </div>
                <div className="wide">
                  <span>인증번호</span>
                  <strong>{snapshot?.cert_no || preview?.certificate?.cert_no || "-"}</strong>
                </div>
              </div>

              <div className="filing-section-card">
                <div className="filing-section-title">
                  <div><span>01</span><strong>파일 자동분류</strong></div>
                  <em>{confirmResult ? "파일 분류 완료" : "분류 경로 준비"}</em>
                </div>
                <dl className="filing-path-list">
                  <div><dt>대상 폴더</dt><dd>{filingPreview?.target_folder || "-"}</dd></div>
                  <div><dt>표준 파일명</dt><dd>{filingPreview?.target_filename || "-"}</dd></div>
                  <div><dt>최종 경로</dt><dd>{filingPreview?.target_path || "-"}</dd></div>
                </dl>
              </div>

              <div className="filing-section-card">
                <div className="filing-section-title">
                  <div><span>02</span><strong>PMF 관리대장 반영 내용</strong></div>
                  <em>{confirmResult ? "PMF 반영 완료" : (canUpdate ? "반영 준비" : "검토 필요")}</em>
                </div>
                <div className="filing-change-table">
                  <div className="head"><span>항목</span><span>현재값</span><span /><span>적용 예정값</span></div>
                  <div>
                    <b>인증기관</b>
                    <span>{pmfChanges?.org?.before || snapshot?.org || "-"}</span>
                    <i>→</i>
                    <strong>{pmfChanges?.org?.after || preview?.effective_certificate?.cert_org || "-"}</strong>
                  </div>
                  <div>
                    <b>인증번호</b>
                    <span>{pmfChanges?.cert_no?.before || snapshot?.cert_no || "-"}</span>
                    <i>→</i>
                    <strong>{pmfChanges?.cert_no?.after || preview?.effective_certificate?.cert_no || "-"}</strong>
                  </div>
                  <div className="highlight">
                    <b>유효기간</b>
                    <span>{expiryChange?.before || snapshot?.expiry_date || "-"}</span>
                    <i>→</i>
                    <strong>{expiryChange?.after || preview?.effective_certificate?.expiry_date || "-"}</strong>
                  </div>
                </div>
              </div>

              <div className="filing-section-card">
                <div className="filing-section-title">
                  <div><span>03</span><strong>제조사 동일성 검토</strong></div>
                  <em>
                    {manufacturerChange?.equivalent
                      ? "동일 업체"
                      : (manufacturerChange?.changed ? "변경 검토" : "변경 없음")}
                  </em>
                </div>
                <div className="filing-maker-compare">
                  <div><span>PMF 제조사</span><strong>{manufacturerChange?.before || snapshot?.maker || "-"}</strong></div>
                  <i>↔</i>
                  <div><span>인증서 제조사</span><strong>{manufacturerChange?.after || preview?.certificate?.manufacturer || "-"}</strong></div>
                </div>
                {manufacturerChange?.equivalent && (
                  <p className="filing-equivalent-note">
                    법인 표기와 철자 차이는 있으나 제조사 핵심 명칭을 기준으로 동일 업체로 판정했습니다.
                  </p>
                )}
              </div>

              {(warnings.length > 0 || uniqueBlockers.length > 0) && (
                <div className="filing-message-stack">
                  {warnings.map((warning, index) => (
                    <div className="filing-message warning" key={`warning-${index}`}>
                      <span>안내</span><p>{reasonLabel(warning)}</p>
                    </div>
                  ))}
                  {uniqueBlockers.map((blocker, index) => (
                    <div className="filing-message blocker" key={`blocker-${index}`}>
                      <span>차단</span><p>{blocker}</p>
                    </div>
                  ))}
                </div>
              )}

              {confirmResult ? (
                <div className="filing-confirm-result">
                  <div className="filing-confirm-result-head">
                    <div>
                      <span>AUTOMATED FILING COMPLETE</span>
                      <strong>인증서 파일 분류 및 PMF 갱신 완료</strong>
                      <p>백엔드 처리 결과를 기준으로 파일 복사, PMF 반영, 이력 저장이 완료되었습니다.</p>
                    </div>
                    <b>{confirmResult?.status || "CONFIRMED"}</b>
                  </div>

                  <div className="filing-execution-grid">
                    <div className="complete">
                      <span>01</span>
                      <div><small>파일 분류</small><strong>{confirmResult?.copy?.status || "완료"}</strong></div>
                    </div>
                    <div className="complete">
                      <span>02</span>
                      <div><small>PMF 갱신</small><strong>{confirmResult?.pmf_update?.status || "완료"}</strong></div>
                    </div>
                    <div className="complete">
                      <span>03</span>
                      <div><small>처리 이력</small><strong>#{confirmResult?.history_id || "저장 완료"}</strong></div>
                    </div>
                  </div>

                  <dl className="filing-confirm-paths">
                    <div>
                      <dt>분류된 인증서</dt>
                      <dd>{confirmResult?.copy?.target_path || filingPreview?.target_path || "-"}</dd>
                    </div>
                    <div>
                      <dt>갱신된 PMF</dt>
                      <dd>{confirmResult?.pmf_update?.pmf_path || pmfPreview?.pmf_path || status?.pmf_update_path || "-"}</dd>
                    </div>
                    <div>
                      <dt>반영 유효기간</dt>
                      <dd>{confirmResult?.expiry_date || expiryChange?.after || preview?.effective_certificate?.expiry_date || "-"}</dd>
                    </div>
                  </dl>

                  <button type="button" onClick={loadData}>
                    처리 완료 건 제외하고 다음 후보 조회
                  </button>
                </div>
              ) : (
                <div className={isReady ? "filing-ready-action ready" : "filing-ready-action"}>
                  <div>
                    <span>{isReady ? "READY TO APPLY" : "MANUAL REVIEW"}</span>
                    <strong>{isReady ? "인증서 파일 분류 및 PMF 갱신 준비 완료" : "실행 전 수동 검토 필요"}</strong>
                    <p>
                      {isReady
                        ? "실행하면 인증서가 원료 폴더에 표준 파일명으로 복사되고 PMF 유효기간이 즉시 갱신됩니다."
                        : "차단 항목을 해결한 뒤 다시 검증하세요."}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleConfirmFiling}
                    disabled={!isReady || confirming}
                  >
                    {confirming ? "파일 분류·PMF 갱신 중..." : (isReady ? "파일 분류 및 PMF 갱신 실행" : "실행 불가")}
                  </button>
                </div>
              )}
            </div>
          )}
        </article>
      </section>

      <section className="filing-system-footnote">
        <div>
          <span>파일 분류 루트</span>
          <strong>{status?.filing_root || filingPreview?.root_path || "-"}</strong>
        </div>
        <div>
          <span>PMF 업데이트 파일</span>
          <strong>{status?.pmf_update_path || status?.pmf_path || pmfPreview?.pmf_path || "-"}</strong>
        </div>
      </section>
    </>
  );
}
