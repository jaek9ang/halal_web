import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  getHealth,
  getPmfSummary,
  getSupplierEmailReview,
  syncPmf,
  saveSupplierEmailOverride,
  getMailTargets,
  sendMailRequests,
  getMailLogs,
  hideMailLogs,
  getLhlnStatus,
  syncLhln,
  getLhlnRecords,
  createLhlnPdf,
  getOcrFiles,
  createOcrJob,
  getOcrJobs,
  getOcrJob,
  getOcrFailureSummary,
  uploadOcrManualFiles,
  deleteOcrJobs,
  deleteStaleTesseractHistory,
  searchPmfMaterials,
  downloadOcrDataExport,
  getPmfMaterialDetail,
  getPmfMaterialRelatedFiles,
  getPmfMaterialHalalFolder,
  openHalalDocFolder,
  getInboxMailboxes,
  syncInboxMail,
  getInboxMessages,
  getInboxAttachments,
  openInboxAttachmentFolder,
  getInboxMessageDetail,
  excludeInboxMessages,
  selectInboxAttachmentsForOcr,
  autoSelectExactInboxOcrTargets,
  getInboxOcrTargets,
  saveInboxOcrCandidateResult,
  getAiRuleReviewStatus,
  analyzeAiRuleExport,
  getAiRuleProblemCases,
  getAiRuleCandidates,
  validateAiRuleCandidate,
  applyAiRuleCandidate,
  rejectAiRuleCandidate,
  getAiRuleValidationReport,
} from "./api";
import "./App.css";

class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
    };
  }

  static getDerivedStateFromError(error) {
    return {
      hasError: true,
      error,
    };
  }

  componentDidCatch(error, info) {
    console.error("[APP_RENDER_ERROR]", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="app-crash-panel">
          <strong>화면 렌더링 오류</strong>
          <p>
            OCR 실행 후 화면 구성 중 오류가 발생했습니다. 브라우저 Console의
            빨간 오류 메시지를 확인하세요.
          </p>
          <pre>{String(this.state.error?.message || this.state.error || "")}</pre>
          <button
            type="button"
            onClick={() => window.location.reload()}
          >
            새로고침
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

const MAIL_MENU_ITEMS = [
  { key: "mail", label: "메일주소 정리", icon: "✉" },
  { key: "send", label: "발송관리", icon: "↗" },
  { key: "logs", label: "발송로그", icon: "☰" },
  { key: "receive", label: "수신메일", icon: "↓" },
];

const REF_MENU_ITEMS = [
  { key: "lhln", label: "BPJPH / LHLN", icon: "◎" },
  { key: "ocr", label: "인증서 판독", icon: "◌" },
  { key: "ocr_test", label: "OCR 테스트", icon: "▣" },
];

const ADMIN_MENU_ITEMS = [
  { key: "admin", label: "인증서양식학습", icon: "▧" },
  { key: "ocr_data_export", label: "OCR 데이터 추출", icon: "⇩" },
  { key: "ai_rule_review", label: "AI 규칙 리뷰", icon: "◇" },
];

function Shell({ active, setActive, children }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [openGroups, setOpenGroups] = useState({
    mail: ["mail", "send", "logs", "receive"].includes(active),
    ref: ["lhln", "ocr", "ocr_test"].includes(active),
    admin: ["admin", "ocr_data_export", "ai_rule_review"].includes(active),
  });

  useEffect(() => {
    if (["mail", "send", "logs", "receive"].includes(active)) {
      setOpenGroups((prev) => ({ ...prev, mail: true }));
    }

    if (["lhln", "ocr", "ocr_test"].includes(active)) {
      setOpenGroups((prev) => ({ ...prev, ref: true }));
    }

    if (["admin", "ocr_data_export", "ai_rule_review"].includes(active)) {
      setOpenGroups((prev) => ({ ...prev, admin: true }));
    }
  }, [active]);

  function toggleGroup(key) {
    setOpenGroups((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  }

  const mailActive = ["mail", "send", "logs", "receive"].includes(active);
  const refActive = ["lhln", "ocr", "ocr_test"].includes(active);
  const adminActive = ["admin", "ocr_data_export", "ai_rule_review"].includes(active);
  
  return (
    <div className={sidebarCollapsed ? "app-shell sidebar-collapsed" : "app-shell"}>
      <button
        type="button"
        className="sidebar-collapse-toggle"
        onClick={() => setSidebarCollapsed((prev) => !prev)}
        title={sidebarCollapsed ? "사이드바 펼치기" : "사이드바 접기"}
      >
        {sidebarCollapsed ? "☰" : "‹"}
      </button>

      <aside className="sidebar">
        <button className="brand-block brand-logo-button" onClick={() => setActive("home")}>
          <img className="brand-logo-img" src="/sewoo-logo.png" alt="SEWOO" />
        </button>

        <nav className="nav-list">
          <button
            className={active === "home" ? "nav-button active" : "nav-button"}
            onClick={() => setActive("home")}
          >
            <span className="nav-icon">⌂</span>
            <span>홈</span>
          </button>

          <button
            className={active === "pmf" ? "nav-button active" : "nav-button"}
            onClick={() => setActive("pmf")}
          >
            <span className="nav-icon">◧</span>
            <span>PMF / 원료</span>
          </button>

          <div className={mailActive ? "nav-folder active" : "nav-folder"}>
            <button
              className="nav-folder-button"
              onClick={() => toggleGroup("mail")}
            >
              <span className="nav-icon">✉</span>
              <span>메일발송</span>
              <b>{openGroups.mail ? "−" : "+"}</b>
            </button>

            {openGroups.mail && (
              <div className="nav-child-list">
                {MAIL_MENU_ITEMS.map((item) => (
                  <button
                    key={item.key}
                    className={active === item.key ? "nav-child active" : "nav-child"}
                    onClick={() => setActive(item.key)}
                  >
                    <span>{item.icon}</span>
                    <em>{item.label}</em>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className={refActive ? "nav-folder active" : "nav-folder"}>
            <button
              className="nav-folder-button"
              onClick={() => toggleGroup("ref")}
            >
              <span className="nav-icon">◎</span>
              <span>자료 / 판독</span>
              <b>{openGroups.ref ? "−" : "+"}</b>
            </button>

            {openGroups.ref && (
              <div className="nav-child-list">
                {REF_MENU_ITEMS.map((item) => (
                  <button
                    key={item.key}
                    className={active === item.key ? "nav-child active" : "nav-child"}
                    onClick={() => setActive(item.key)}
                  >
                    <span>{item.icon}</span>
                    <em>{item.label}</em>
                  </button>
                ))}
              </div>
            )}
          </div>

                    <div className={adminActive ? "nav-folder active" : "nav-folder"}>
            <button
              className="nav-folder-button"
              onClick={() => toggleGroup("admin")}
            >
              <span className="nav-icon">⚙</span>
              <span>관리</span>
              <b>{openGroups.admin ? "−" : "+"}</b>
            </button>

            {openGroups.admin && (
              <div className="nav-child-list">
                {ADMIN_MENU_ITEMS.map((item) => (
                  <button
                    key={item.key}
                    className={active === item.key ? "nav-child active" : "nav-child"}
                    onClick={() => setActive(item.key)}
                  >
                    <span>{item.icon}</span>
                    <em>{item.label}</em>
                  </button>
                ))}
              </div>
            )}
          </div>
        </nav>

        <div className="sidebar-footer">
          <span className="dot online" />
          <span>API Online</span>
        </div>
      </aside>

      <main className="content">
        {children}
      </main>
    </div>
  );
}

function PageHeader({ eyebrow, title, desc, onBack }) {
  return (
    <div className="page-header">
      <button className="back-button" onClick={onBack}>
        ← 홈
      </button>

      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{desc}</p>
      </div>
    </div>
  );
}

function StatLine({ items }) {
  return (
    <div className="stat-line">
      {items.map((item) => (
        <div className="stat-cell" key={item.label}>
          <strong>{item.value}</strong>
          <span>{item.label}</span>
        </div>
      ))}
    </div>
  );
}

function HomePage({ setActive, health, pmfSummary, emailReview }) {
  const cards = [
    { key: "pmf", title: "PMF / 원료", desc: "최신 PMF 원본과 원료 데이터를 확인합니다.", icon: "◧" },
    { key: "mail", title: "메일주소 정리", desc: "업체별 발송 주소를 확정합니다.", icon: "✉" },
    { key: "send", title: "발송관리", desc: "만료 통보와 유지확인 메일을 검토합니다.", icon: "↗" },
    { key: "logs", title: "발송로그", desc: "발송 이력과 본문을 확인합니다.", icon: "☰" },
    { key: "receive", title: "수신메일", desc: "회신 메일과 첨부파일을 수집합니다.", icon: "↓" },
    { key: "lhln", title: "BPJPH / LHLN", desc: "교차인정기관 자료를 관리합니다.", icon: "◎" },
    { key: "ocr", title: "인증서 판독", desc: "인증서를 OCR로 판독합니다.", icon: "◌" },
    { key: "ocr_test", title: "OCR 테스트", desc: "여러 인증서를 드래그해 OCR 원문을 확인합니다.", icon: "▣" },
    { key: "admin", title: "관리", desc: "설정과 시스템 상태를 확인합니다.", icon: "⚙" },
  ];

  return (
    <>
      <section className="sewoo-home-hero">
        <div className="sewoo-hero-copy">
          <div className="sewoo-hero-kicker">
            <span>SEWOO HALAL OPERATIONS</span>
          </div>

          <h1>
            Halal
            <br />
            Certificate
            <br />
            Console
          </h1>

          <p>
            PMF 원료 정보, 업체 메일주소, 인증서 만료관리, 수신 첨부파일,
            BPJPH/LHLN 자료를 하나의 흐름으로 관리합니다.
          </p>
        </div>

        <div className="sewoo-hero-summary">
          <div>
            <span>API</span>
            <strong>{health?.ok ? "Online" : "-"}</strong>
          </div>
          <div>
            <span>PMF Raw</span>
            <strong>{pmfSummary?.raw_rows ?? "-"}</strong>
          </div>
          <div>
            <span>Mail Confirmed</span>
            <strong>{emailReview?.summary?.confirmed_emails ?? "-"}</strong>
          </div>
        </div>
      </section>

      <section className="sewoo-module-head">
        <div>
          <span>WORK MODULES</span>
          <h2>작업 모듈</h2>
        </div>
        <p>필요한 업무 모듈을 선택하세요.</p>
      </section>

      <section className="sewoo-module-grid">
        {cards.map((card) => (
          <button
            key={card.key}
            className="sewoo-module-card"
            onClick={() => setActive(card.key)}
          >
            <div className="sewoo-module-top">
              <div className="sewoo-module-icon">{card.icon}</div>
            </div>

            <h2>{card.title}</h2>
            <p>{card.desc}</p>

            <div className="sewoo-module-action">
              <span>열기</span>
              <b>→</b>
            </div>
          </button>
        ))}
      </section>
    </>
  );
}

function PmfPage({ setActive }) {
  const [summary, setSummary] = useState(null);
  const [keyword, setKeyword] = useState("");
  const [materials, setMaterials] = useState([]);
  const [selectedRowPos, setSelectedRowPos] = useState(null);
  const [detail, setDetail] = useState(null);
  const [collapsedLevels, setCollapsedLevels] = useState({});

  const [halalFolder, setHalalFolder] = useState(null);
  const [halalFolderLoading, setHalalFolderLoading] = useState(false);

  const [detailLoading, setDetailLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const pmfListRef = useRef(null);
  
  function getDepthLabel(depth) {
    const d = Number(depth ?? 0);
    if (d <= 0) return "메인 원료";
    return `${d}차 하부`;
  }

  function safeText(value) {
    const text = String(value ?? "").trim();

    if (!text) return "";
    if (text === "-") return "";
    if (text.toLowerCase() === "nan") return "";
    if (text.toLowerCase() === "none") return "";
    if (text.toLowerCase() === "null") return "";

    return text;
  }
  
  function toggleLevelCard(depth) {
    setCollapsedLevels((prev) => ({
      ...prev,
      [depth]: !prev[depth],
    }));
  }
  
  async function loadSummary() {
    try {
      const data = await getPmfSummary();
      setSummary(data);
    } catch (err) {
      alert(err.message);
    }
  }

  async function searchMaterials(nextKeyword = keyword) {
    try {
      setLoading(true);

      const data = await searchPmfMaterials({
        keyword: nextKeyword,
        limit: 120,
      });

      setMaterials(data.rows || []);

      if (data.rows?.length > 0) {
        const stillExists = data.rows.some((row) => row.row_pos === selectedRowPos);

        if (!stillExists) {
          setSelectedRowPos(null);
          setDetail(null);
          setHalalFolder(null);
        }
      } else {
        setSelectedRowPos(null);
        setDetail(null);
        setHalalFolder(null);
      }
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }
  
  async function loadHalalFolder(rowPos) {
    try {
      setHalalFolderLoading(true);
      setHalalFolder(null);

      const data = await getPmfMaterialHalalFolder(rowPos);
      setHalalFolder(data);
    } catch (err) {
      console.error("halal folder load failed:", err);
      setHalalFolder(null);
    } finally {
      setHalalFolderLoading(false);
    }
  }

  async function loadDetail(rowPos) {
    try {
      setSelectedRowPos(rowPos);
      setDetail(null);
      setHalalFolder(null);
      setCollapsedLevels({});

      setDetailLoading(true);

      const detailData = await getPmfMaterialDetail(rowPos);
      setDetail(detailData);

    } catch (err) {
      console.error("detail load failed:", err);
      alert(err.message || "원료 상세 정보를 불러오지 못했습니다.");
    } finally {
      setDetailLoading(false);
    }
  }

  function handlePmfListKeyDown(e) {
    if (!materials.length) return;

    const currentIndex = Math.max(
      materials.findIndex((row) => row.row_pos === selectedRowPos),
      0
    );

    if (e.key === "ArrowDown") {
      e.preventDefault();
      const nextIndex = Math.min(currentIndex + 1, materials.length - 1);
      loadDetail(materials[nextIndex].row_pos);
    }

    if (e.key === "ArrowUp") {
      e.preventDefault();
      const nextIndex = Math.max(currentIndex - 1, 0);
      loadDetail(materials[nextIndex].row_pos);
    }
  }

  async function handleOpenHalalFolder(path) {
    if (!path) {
      alert("폴더 경로가 없습니다.");
      return;
    }

    try {
      const result = await openHalalDocFolder(path);

      if (!result.ok) {
        alert(result.message || "폴더 열기에 실패했습니다.");
      }
    } catch (err) {
      alert(err.message);
    }
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
        : pathOrFile?.saved_path;

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

  async function handleSyncPmf() {
    const ok = window.confirm("PMF 원본을 다시 동기화합니다. 계속할까요?");
    if (!ok) return;

    try {
      setLoading(true);
      await syncPmf();
      await loadSummary();
      await searchMaterials(keyword);
      alert("PMF 동기화 완료");
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSummary();
    searchMaterials("");
  }, []);

  const levels = detail?.levels || [];

  return (
    <>
      <PageHeader
        eyebrow="PMF / MATERIAL"
        title="PMF / 원료"
        desc="PMF 원본을 기준으로 메인 원료와 하부 원료 상세 구성을 확인합니다."
        onBack={() => setActive("home")}
      />

      <StatLine
        items={[
          { label: "Raw rows", value: summary?.raw_rows ?? "-" },
          { label: "E-mail rows", value: summary?.email_rows ?? "-" },
          { label: "검색 결과", value: materials.length },
          { label: "선택 단계", value: levels.length },
        ]}
      />

      <div className="pmf-search-bar">
        <input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") searchMaterials(keyword);
          }}
          placeholder="검색어: 업체명 / 원료명 / 영문명 / 제조사 / 인증기관 / 인증번호"
        />

        <button className="primary-button" onClick={() => searchMaterials(keyword)} disabled={loading}>
          {loading ? "검색 중..." : "검색"}
        </button>

        <button className="ghost-action" onClick={handleSyncPmf} disabled={loading}>
          PMF 동기화
        </button>
      </div>

      <section className="pmf-material-layout">
        <div className="pmf-material-list">
          <div className="surface-title">원료 검색 결과</div>

          <div className="pmf-search-table-shell">
            <div
              className="pmf-search-table-scroll"
              ref={pmfListRef}
              tabIndex={0}
              onKeyDown={handlePmfListKeyDown}
            >
              <table className="pmf-search-table">
                <colgroup>
                  <col style={{ width: "19%" }} />
                  <col style={{ width: "28%" }} />
                  <col style={{ width: "14%" }} />
                  <col style={{ width: "28%" }} />
                  <col style={{ width: "11%" }} />
                </colgroup>

                <thead>
                  <tr>
                    <th>공급사</th>
                    <th className="is-left">메인 원료</th>
                    <th>구분</th>
                    <th className="is-left">하부 원료</th>
                    <th>인증기관</th>
                  </tr>
                </thead>

                <tbody>
                  {materials.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="pmf-search-empty">
                        검색 결과가 없습니다.
                      </td>
                    </tr>
                  ) : (
                    materials.map((item) => {
                      const isSelected = selectedRowPos === item.row_pos;
                      const depthValue = Number(
                        item.display_depth ??
                        Math.max(Number(item.depth_count ?? 1) - 1, 0)
                      );

                      const mainMaterialName =
                        safeText(item.main_material) || "-";

                      const mainMaterialEnglish =
                        safeText(item.main_english) || "-";

                      const subMaterialName =
                        safeText(item.display_sub_material) || "-";

                      const subMaterialEnglish =
                        safeText(item.display_sub_english) || "";

                      const orgName =
                        safeText(item.display_org) ||
                        safeText(item.main_org) ||
                        "-";

                      return (
                        <tr
                          key={item.row_pos}
                          className={isSelected ? "is-selected" : ""}
                          onClick={() => {
                            pmfListRef.current?.focus();
                            loadDetail(item.row_pos);
                          }}
                        >
                          <td>{item.supplier || "-"}</td>

                          <td className="is-left">
                            <div className="pmf-cell-material">
                              <strong>{mainMaterialName}</strong>
                              <span>{mainMaterialEnglish}</span>
                            </div>
                          </td>

                          <td>
                            <span className="pmf-depth-badge">
                              {item.display_depth_label || getDepthLabel(depthValue)}
                            </span>
                          </td>

                          <td className="is-left">
                            <div className="pmf-cell-material">
                              <strong>{subMaterialName}</strong>
                              {subMaterialEnglish ? <span>{subMaterialEnglish}</span> : null}
                            </div>
                          </td>

                          <td>{orgName}</td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className="pmf-material-detail">
          <div className="surface-title">하부 원료 상세 구성</div>

          {detailLoading ? (
            <div className="mail-log-empty">
              원료 상세 정보를 불러오는 중입니다.
            </div>
          ) : detail ? (
            <>
              <div className="pmf-chain-box">
                <span>원료 경로</span>
                <strong>{detail.chain_text || "-"}</strong>
              </div>

              <div className="pmf-level-stack">
                {levels.map((level) => {
                  const isCollapsed = collapsedLevels[level.depth] === true;

                  return (
                    <div
                      className={isCollapsed ? "pmf-level-card collapsed" : "pmf-level-card"}
                      key={`${level.depth}-${level.material_name}`}
                    >
                      <div className="pmf-level-top">
                        <div>
                          <span>{level.depth_label}</span>
                          <h3>{level.material_name}</h3>
                        </div>

                        <div className="pmf-level-actions">
                          {safeText(level.org) ? (
                            <em>{level.org}</em>
                          ) : null}

                          <button
                            type="button"
                            className="pmf-level-toggle"
                            onClick={() => toggleLevelCard(level.depth)}
                            title={isCollapsed ? "펼치기" : "접기"}
                          >
                            {isCollapsed ? "+" : "−"}
                          </button>
                        </div>
                      </div>

                      {!isCollapsed ? (
                        <div className="pmf-level-grid">
                          <div>
                            <span>영문명</span>
                            <strong>{level.english_name || "-"}</strong>
                          </div>
                          <div>
                            <span>제조사</span>
                            <strong>{level.maker || "-"}</strong>
                          </div>
                          <div>
                            <span>제조국</span>
                            <strong>{level.maker_country || "-"}</strong>
                          </div>
                          <div>
                            <span>인증번호</span>
                            <strong>{level.cert_no || "-"}</strong>
                          </div>
                          <div>
                            <span>유효기간</span>
                            <strong>{level.exp || "-"}</strong>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>

              <div className="pmf-folder-panel">
                <div className="pmf-folder-head">
                  <div>
                    <span>HALAL FOLDER</span>
                    <h3>기존 하부원료 서류 폴더</h3>
                  </div>

                  <button
                    type="button"
                    className="soft-chip-action"
                    onClick={() => {
                      if (!selectedRowPos) {
                        alert("원료를 먼저 선택하세요.");
                        return;
                      }

                      loadHalalFolder(selectedRowPos);
                    }}
                    disabled={halalFolderLoading || !selectedRowPos}
                  >
                    {halalFolderLoading ? "확인 중..." : "폴더 정보 확인"}
                  </button>
                </div>

                {halalFolderLoading ? (
                  <div className="pmf-related-empty">
                    폴더명을 확인하는 중입니다.
                  </div>
                ) : !halalFolder ? (
                  <div className="pmf-related-empty">
                    폴더 정보는 필요할 때만 조회합니다. 상단의 “폴더 정보 확인”을 누르세요.
                  </div>
                ) : !halalFolder.folder ? (
                  <div className="pmf-folder-empty">
                    <span>매칭 폴더 없음</span>
                    <strong>{halalFolder.message || "A열 번호와 일치하는 폴더를 찾지 못했습니다."}</strong>
                    <p>{halalFolder.parent_folder || halalFolder.root || "-"}</p>
                  </div>
                ) : (
                  <div className="pmf-folder-card pmf-folder-compact-card">
                    <div className="pmf-folder-line-row">
                      <span className="pmf-folder-line-label">폴더명</span>
                      <strong className="pmf-folder-line-value">
                        {halalFolder.folder.name}
                      </strong>
                      <div className="pmf-folder-line-actions">
                        <button
                          type="button"
                          onClick={() => handleCopyText("폴더명", halalFolder.folder.name)}
                        >
                          복사
                        </button>
                      </div>
                    </div>

                    <div className="pmf-folder-line-row">
                      <span className="pmf-folder-line-label">폴더경로</span>
                      <strong className="pmf-folder-line-value">
                        {halalFolder.folder.path}
                      </strong>
                      <div className="pmf-folder-line-actions">
                        <button
                          type="button"
                          onClick={() => handleCopyText("폴더경로", halalFolder.folder.path)}
                        >
                          복사
                        </button>

                        <button
                          type="button"
                          onClick={() => handleOpenHalalFolder(halalFolder.folder.path)}
                        >
                          폴더 열기
                        </button>
                      </div>
                    </div>

                    <div className="pmf-folder-file-list compact">
                      <div className="pmf-folder-file-title">
                        {halalFolder.folder.has_halal_marker
                          ? "폴더 내 인증서 파일"
                          : "폴더 내 인증관련 파일"}
                      </div>

                      {!halalFolder.folder.has_halal_marker ? (
                        <div className="pmf-folder-cert-notice">
                          <strong>인증서 표시 없음</strong>
                          <span>
                            폴더명에 ⓗ 표시가 없어 자동 파일 조회를 생략했습니다.
                            필요 시 폴더 열기로 직접 확인하세요.
                          </span>
                        </div>
                      ) : halalFolder.folder.files?.length > 0 ? (
                        halalFolder.folder.files.map((file) => (
                          <div className="pmf-folder-line-row file-row" key={file.path}>
                            <span className="pmf-folder-line-label">파일명</span>
                            <strong className="pmf-folder-line-value">
                              {file.name}
                            </strong>
                            <div className="pmf-folder-line-actions">
                              <button
                                type="button"
                                onClick={() => handleCopyText("파일명", file.name)}
                              >
                                복사
                              </button>
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="pmf-related-empty">
                          해당 폴더 바로 아래에서 인증서 파일을 찾지 못했습니다.
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>

            </>
          ) : (
            <div className="mail-log-empty">
              원료를 선택하면 하부 원료 상세 구성이 표시됩니다.
            </div>
          )}
        </div>
      </section>
    </>
  );
}

function MailAddressPage({ setActive, emailReview, reloadAll }) {
  const rows = emailReview?.rows || [];
  const summary = emailReview?.summary || {};

  const [keyword, setKeyword] = useState("");
  const [showHalalOnly, setShowHalalOnly] = useState(true);
  const [selectedKey, setSelectedKey] = useState("");
  const [edit, setEdit] = useState({
    final_to: "",
    final_cc: "",
    memo: "",
  });
  const [saving, setSaving] = useState(false);

  const filteredRows = useMemo(() => {
    const q = keyword.trim().toLowerCase();

    return rows.filter((row) => {
      if (showHalalOnly && !row.has_halal) return false;

      if (!q) return true;

      const text = [
        row.supplier,
        row.supplier_key,
        row.orgs,
        row.final_to,
        row.email_candidate,
        row.status,
      ]
        .join(" ")
        .toLowerCase();

      return text.includes(q);
    });
  }, [rows, keyword, showHalalOnly]);

  const selectedRow = useMemo(() => {
    if (!filteredRows.length) return null;

    if (!selectedKey) return filteredRows[0];

    return (
      filteredRows.find((row) => row.supplier_key === selectedKey) ||
      filteredRows[0]
    );
  }, [filteredRows, selectedKey]);

  useEffect(() => {
    if (!selectedRow) return;

    setSelectedKey(selectedRow.supplier_key);
    setEdit({
      final_to: selectedRow.final_to || "",
      final_cc: selectedRow.final_cc || "",
      memo: "",
    });
  }, [selectedRow?.supplier_key]);

  async function handleSave() {
    if (!selectedRow) return;

    if (!edit.final_to.trim()) {
      alert("최종 TO를 입력해야 합니다.");
      return;
    }

    try {
      setSaving(true);

      await saveSupplierEmailOverride({
        supplier_name: selectedRow.supplier,
        supplier_key: selectedRow.supplier_key,
        final_to: edit.final_to,
        final_cc: edit.final_cc,
        memo: edit.memo,
      });

      await reloadAll();

      alert("수동확정 저장 완료");
    } catch (err) {
      alert(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="MAIL ADDRESS"
        title="메일주소 정리"
        desc="PMF와 E-mail 시트 후보를 기준으로 업체별 최종 발송 주소를 확정합니다."
        onBack={() => setActive("home")}
      />

      <StatLine
        items={[
          { label: "전체 공급사", value: summary.total_suppliers ?? "-" },
          { label: "할랄 보유", value: summary.halal_suppliers ?? "-" },
          { label: "메일 확정", value: summary.confirmed_emails ?? "-" },
          { label: "확인 필요", value: summary.halal_unconfirmed ?? "-" },
        ]}
      />

      <div className="control-bar">
        <input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="업체명, 인증기관, 이메일 검색"
        />

        <label className="check-pill">
          <input
            type="checkbox"
            checked={showHalalOnly}
            onChange={(e) => setShowHalalOnly(e.target.checked)}
          />
          <span>할랄 보유 업체만</span>
        </label>
      </div>

      <section className="split-layout">
        <div className="list-surface">
          <div className="surface-title">업체 목록</div>

          <div className="supplier-list">
            {filteredRows.map((row) => (
              <button
                key={row.supplier_key}
                className={
                  selectedRow?.supplier_key === row.supplier_key
                    ? "mail-supplier-row active"
                    : "mail-supplier-row"
                }
                onClick={() => setSelectedKey(row.supplier_key)}
              >
                <div className="mail-supplier-name">
                  <strong>{row.supplier}</strong>
                </div>

                <div className="mail-supplier-orgs">
                  {row.orgs || "-"}
                </div>

                <em>{row.status}</em>
              </button>
            ))}
          </div>
        </div>

        <div className="detail-surface">
          {selectedRow ? (
            <>
              <div className="detail-top">
                <div>
                  <div className="surface-title">최종 발송 주소</div>
                  <h2>{selectedRow.supplier}</h2>
                </div>

                <span className={selectedRow.apply ? "badge ok" : "badge warn"}>
                  {selectedRow.status}
                </span>
              </div>

              <div className="form-grid">
                <label>
                  <span>Supplier Key</span>
                  <input value={selectedRow.supplier_key} disabled />
                </label>

                <label>
                  <span>인증기관</span>
                  <input value={selectedRow.orgs || ""} disabled />
                </label>

                <label>
                  <span>Raw M열 이메일</span>
                  <input value={selectedRow.raw_email || ""} disabled />
                </label>

                <label>
                  <span>E-mail 후보</span>
                  <input value={selectedRow.email_candidate || ""} disabled />
                </label>

                <label>
                  <span>최종 TO</span>
                  <input
                    value={edit.final_to}
                    onChange={(e) =>
                      setEdit((prev) => ({ ...prev, final_to: e.target.value }))
                    }
                  />
                </label>

                <label>
                  <span>최종 CC</span>
                  <input
                    value={edit.final_cc}
                    onChange={(e) =>
                      setEdit((prev) => ({ ...prev, final_cc: e.target.value }))
                    }
                  />
                </label>

                <label className="wide">
                  <span>메모</span>
                  <input
                    value={edit.memo}
                    onChange={(e) =>
                      setEdit((prev) => ({ ...prev, memo: e.target.value }))
                    }
                    placeholder="수정 사유 또는 확인 내용"
                  />
                </label>
              </div>

              <div className="toolbar right">
                <button
                  className="primary-button"
                  onClick={handleSave}
                  disabled={saving}
                >
                  {saving ? "저장 중..." : "수동확정 저장"}
                </button>
              </div>
            </>
          ) : (
            <div className="empty">선택된 업체가 없습니다.</div>
          )}
        </div>
      </section>
    </>
  );
}

function SendPage({ setActive }) {
  const [testMode, setTestMode] = useState(true);
  const [testReceiver, setTestReceiver] = useState("jaek_ing@naver.com");
  const [mailTargets, setMailTargets] = useState(null);
  const [selectedRequestId, setSelectedRequestId] = useState("");
  const [checkedRequestIds, setCheckedRequestIds] = useState([]);
  const [mailTypeFilter, setMailTypeFilter] = useState("all");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const sendListRef = useRef(null);

  async function loadTargets() {
    try {
      setLoading(true);

      const data = await getMailTargets({
        testMode,
        testReceiver,
      });

      const nextRows = data.rows || [];
      setMailTargets(data);

      if (nextRows.length > 0) {
        setSelectedRequestId(nextRows[0].request_id);
      } else {
        setSelectedRequestId("");
      }

      setCheckedRequestIds([]);
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadTargets();
  }, []);

  const rows = mailTargets?.rows || [];
  const summary = mailTargets?.summary || {};
  const mailTypeOptions = useMemo(() => {
    const values = Array.from(new Set(rows.map((row) => row.mail_type).filter(Boolean)));
    return values;
  }, [rows]);

  const filteredSendRows = useMemo(() => {
    if (mailTypeFilter === "all") return rows;
    return rows.filter((row) => row.mail_type === mailTypeFilter);
  }, [rows, mailTypeFilter]);

  const selected =
    filteredSendRows.find((row) => row.request_id === selectedRequestId) ||
    filteredSendRows[0] ||
    rows[0];

  function toggleTargetChecked(requestId) {
    if (!requestId) return;

    setCheckedRequestIds((prev) => {
      if (prev.includes(requestId)) {
        return prev.filter((id) => id !== requestId);
      }

      return [...prev, requestId];
    });
  }

  function handleSelectAllTargets() {
    setCheckedRequestIds(filteredSendRows.map((row) => row.request_id).filter(Boolean));
  }

  function handleClearTargets() {
    setCheckedRequestIds([]);
  }

  function handleSendListKeyDown(e) {
    if (!filteredSendRows.length) return;

    const currentIndex = Math.max(
      filteredSendRows.findIndex((row) => row.request_id === selectedRequestId),
      0
    );

    if (e.key === "ArrowDown") {
      e.preventDefault();
      const nextIndex = Math.min(currentIndex + 1, filteredSendRows.length - 1);
      setSelectedRequestId(filteredSendRows[nextIndex].request_id);
      return;
    }

    if (e.key === "ArrowUp") {
      e.preventDefault();
      const nextIndex = Math.max(currentIndex - 1, 0);
      setSelectedRequestId(filteredSendRows[nextIndex].request_id);
      return;
    }

    if (e.key === " " || e.key === "Spacebar") {
      e.preventDefault();
      const current = filteredSendRows[currentIndex];
      if (current?.request_id) {
        toggleTargetChecked(current.request_id);
      }
    }
  }

  async function handleSendSelected() {
    if (checkedRequestIds.length === 0) {
      alert("발송할 메일을 체크하세요.");
      return;
    }

    const ok = window.confirm(
      `체크한 메일 ${checkedRequestIds.length}건을 ${testMode ? "테스트" : "실발송"}으로 발송합니다. 계속할까요?`
    );

    if (!ok) return;

    try {
      setSending(true);

      const result = await sendMailRequests({
        requestIds: checkedRequestIds,
        request_ids: checkedRequestIds,
        senderEmail: "",
        sender_email: "",
        appPassword: "",
        app_password: "",
        testMode,
        test_mode: testMode,
        testReceiver,
        test_receiver: testReceiver,
        allowDuplicate: false,
        allow_duplicate: false,
        requireAttachmentPdf: false,
        require_attachment_pdf: false,
      });

      const sentCount = result?.sent_count ?? result?.success_count ?? result?.success ?? checkedRequestIds.length;
      alert(`발송 요청 완료: ${sentCount}건`);
      setCheckedRequestIds([]);
      await loadTargets();
    } catch (err) {
      alert(err.message);
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="MAIL SEND"
        title="발송관리"
        desc="PMF 기준으로 BPJPH 유지확인, 만료 통보, 만료 도래 대상 메일을 생성하고 검토한 뒤 체크한 대상만 발송합니다."
        onBack={() => setActive("home")}
      />

      <StatLine
        items={[
          { label: "발송 묶음", value: summary.total_targets ?? "-" },
          { label: "대상 품목", value: summary.total_items ?? "-" },
          { label: "BPJPH 유지확인", value: summary.bpjph_keep ?? "-" },
          { label: "체크 대상", value: checkedRequestIds.length },
        ]}
      />

      <div className="control-bar send-control-bar">
        <label className="check-pill">
          <input
            type="checkbox"
            checked={testMode}
            onChange={(e) => setTestMode(e.target.checked)}
          />
          <span>테스트 모드</span>
        </label>

        <input
          value={testReceiver}
          onChange={(e) => setTestReceiver(e.target.value)}
          placeholder="테스트 수신자"
        />

        <button className="ghost-action" onClick={loadTargets} disabled={loading || sending}>
          {loading ? "생성 중..." : "대상 다시 생성"}
        </button>


        <button
          className="primary-button send-submit-button"
          onClick={handleSendSelected}
          disabled={checkedRequestIds.length === 0 || loading || sending}
        >
          {sending ? "발송 중..." : `체크 메일 발송 ${checkedRequestIds.length}건`}
        </button>
      </div>

      <section className="split-layout send-layout-balanced">
        <div className="list-surface send-list-surface">
          <div className="panel-title-row send-panel-title-row">
            <div className="surface-title">발송 대상</div>
            <div className="panel-actions">
              <select
                className="send-type-filter-select"
                value={mailTypeFilter}
                onChange={(e) => {
                  setMailTypeFilter(e.target.value);
                  setCheckedRequestIds([]);
                  const first = e.target.value === "all"
                    ? rows[0]
                    : rows.find((row) => row.mail_type === e.target.value);
                  setSelectedRequestId(first?.request_id || "");
                }}
              >
                <option value="all">전체 유형</option>
                {mailTypeOptions.map((type) => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>

              <button
                type="button"
                className="soft-chip-action"
                onClick={handleSelectAllTargets}
                disabled={filteredSendRows.length === 0 || sending}
              >
                전체선택
              </button>

              <button
                type="button"
                className="soft-chip-action"
                onClick={handleClearTargets}
                disabled={checkedRequestIds.length === 0 || sending}
              >
                전체해제
              </button>
            </div>
          </div>

          <div
            className="supplier-list send-target-list"
            ref={sendListRef}
            tabIndex={0}
            onKeyDown={handleSendListKeyDown}
          >
            {filteredSendRows.length === 0 ? (
              <div className="mail-log-empty">발송 대상이 없습니다.</div>
            ) : (
              filteredSendRows.map((row) => {
                const checked = checkedRequestIds.includes(row.request_id);
                const isSelected = selected?.request_id === row.request_id;

                return (
                  <button
                    key={row.request_id}
                    className={isSelected ? "send-target-row active" : "send-target-row"}
                    onClick={() => setSelectedRequestId(row.request_id)}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => {
                        e.stopPropagation();
                        toggleTargetChecked(row.request_id);
                      }}
                      onClick={(e) => e.stopPropagation()}
                    />

                    <div className="send-target-main">
                      <strong>{row.supplier || "-"}</strong>
                      <span>{row.subject || "(제목 없음)"}</span>
                    </div>

                    <div className="send-target-meta">
                      <span>{row.mail_type || "-"}</span>
                      <span>{row.item_count || 0}개</span>
                      <span>{row.attach_pdf === "Y" ? "PDF" : "No PDF"}</span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        <div className="detail-surface">
          {selected ? (
            <>
              <div className="detail-top">
                <div>
                  <div className="surface-title">메일 미리보기</div>
                  <h2>{selected.supplier}</h2>
                </div>

                <span className="badge ok">{selected.mail_type}</span>
              </div>

              <div className="send-preview-strip">
                <div>
                  <span>관리번호</span>
                  <strong>{selected.request_id}</strong>
                </div>

                <div>
                  <span>수신자</span>
                  <strong>{selected.receiver || "-"}</strong>
                </div>

                <div>
                  <span>참조</span>
                  <strong>{selected.cc || "-"}</strong>
                </div>

                <div>
                  <span>첨부PDF</span>
                  <strong>{selected.attach_pdf}</strong>
                </div>
              </div>

              <div className="send-subject-line">
                <span>제목</span>
                <strong>{selected.subject}</strong>
              </div>

              <div
                className="mail-preview"
                dangerouslySetInnerHTML={{ __html: selected.body_html || "" }}
              />
            </>
          ) : (
            <div className="empty">발송 대상이 없습니다.</div>
          )}
        </div>
      </section>
    </>
  );
}


function MailLogsPage({ setActive }) {
  const [filter, setFilter] = useState("all");
  const [logs, setLogs] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [checkedIds, setCheckedIds] = useState([]);
  const [logKeyword, setLogKeyword] = useState("");
  const [loading, setLoading] = useState(false);
  const logListRef = useRef(null);

  async function loadLogs(nextFilter = filter) {
    try {
      setLoading(true);

      let testMode = null;

      if (nextFilter === "test") {
        testMode = true;
      }

      if (nextFilter === "real") {
        testMode = false;
      }

      const data = await getMailLogs({
        limit: 200,
        testMode,
      });

      let rows = data.rows || [];

      if (nextFilter === "fail") {
        rows = rows.filter((row) => Number(row.success) !== 1);
      }

      setLogs(rows);

      if (rows.length > 0) {
        setSelectedId(rows[0].id);
      } else {
        setSelectedId(null);
      }

      setCheckedIds([]);
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadLogs(filter);
  }, []);

  function changeFilter(nextFilter) {
    setFilter(nextFilter);
    loadLogs(nextFilter);
  }

  function toggleChecked(id) {
    setCheckedIds((prev) => {
      if (prev.includes(id)) {
        return prev.filter((x) => x !== id);
      }

      return [...prev, id];
    });
  }

  async function handleHideSelected() {
    if (checkedIds.length === 0) {
      alert("숨김 처리할 로그를 선택하세요.");
      return;
    }

    const ok = window.confirm(
      "선택한 테스트 로그를 숨김 처리합니다. 실발송 로그는 기본적으로 숨김 처리되지 않습니다. 계속할까요?"
    );

    if (!ok) return;

    try {
      await hideMailLogs({
        ids: checkedIds,
        includeReal: false,
      });

      alert("숨김 처리 완료");
      await loadLogs(filter);
    } catch (err) {
      alert(err.message);
    }
  }

  const filteredLogs = useMemo(() => {
    const q = logKeyword.trim().toLowerCase();

    if (!q) return logs;

    return logs.filter((row) => {
      const text = [
        row.supplier,
        row.request_id,
        row.receiver,
        row.cc,
        row.mail_type,
        row.subject,
        row.sent_at,
        row.body_html,
        row.error_message,
      ]
        .join(" ")
        .toLowerCase();

      return text.includes(q);
    });
  }, [logs, logKeyword]);

  const selected = filteredLogs.find((row) => row.id === selectedId) || filteredLogs[0] || logs[0];

  function handleLogListKeyDown(e) {
    if (!filteredLogs.length) return;

    const currentIndex = Math.max(
      filteredLogs.findIndex((row) => row.id === selected?.id),
      0
    );

    if (e.key === "ArrowDown") {
      e.preventDefault();
      const nextIndex = Math.min(currentIndex + 1, filteredLogs.length - 1);
      setSelectedId(filteredLogs[nextIndex].id);
      return;
    }

    if (e.key === "ArrowUp") {
      e.preventDefault();
      const nextIndex = Math.max(currentIndex - 1, 0);
      setSelectedId(filteredLogs[nextIndex].id);
      return;
    }

    if (e.key === " " || e.key === "Spacebar") {
      e.preventDefault();
      const current = filteredLogs[currentIndex];
      if (current?.id) toggleChecked(current.id);
    }
  }

  const successCount = filteredLogs.filter((row) => Number(row.success) === 1).length;
  const failCount = filteredLogs.length - successCount;
  const testCount = filteredLogs.filter((row) => Number(row.test_mode) === 1).length;
  const realCount = filteredLogs.filter((row) => Number(row.test_mode) !== 1).length;

  return (
    <>
      <PageHeader
        eyebrow="MAIL LOGS"
        title="발송로그"
        desc="테스트/실발송 이력, 발송 결과, 메일 본문을 확인합니다."
        onBack={() => setActive("home")}
      />

      <StatLine
        items={[
          { label: "현재 목록", value: logs.length },
          { label: "성공", value: successCount },
          { label: "실패/제외", value: failCount },
          { label: "테스트 로그", value: testCount },
        ]}
      />

      <div className="log-toolbar">
        <button
          className={filter === "all" ? "filter-button active" : "filter-button"}
          onClick={() => changeFilter("all")}
        >
          전체
        </button>

        <button
          className={filter === "test" ? "filter-button active" : "filter-button"}
          onClick={() => changeFilter("test")}
        >
          테스트
        </button>

        <button
          className={filter === "real" ? "filter-button active" : "filter-button"}
          onClick={() => changeFilter("real")}
        >
          실발송
        </button>

        <button
          className={filter === "fail" ? "filter-button active" : "filter-button"}
          onClick={() => changeFilter("fail")}
        >
          실패/제외
        </button>

        <input
          className="mail-log-search-input"
          value={logKeyword}
          onChange={(e) => setLogKeyword(e.target.value)}
          placeholder="제목 / 내용 / 업체명 / 관리번호 / 수신자 검색"
        />

        <button className="ghost-action" onClick={() => loadLogs(filter)} disabled={loading}>
          {loading ? "불러오는 중..." : "새로고침"}
        </button>

        <button
          className="danger-action"
          onClick={handleHideSelected}
          disabled={checkedIds.length === 0}
        >
          선택 테스트로그 숨김
        </button>
      </div>

      <section className="mail-log-stack">
        <div className="mail-log-list-surface">
          <div className="surface-title">로그 목록</div>

          <div className="mail-log-table-head">
            <div className="col-check"></div>
            <div className="col-type">구분</div>
            <div className="col-supplier">업체명</div>
            <div className="col-mailtype">메일유형</div>
            <div className="col-subject">제목</div>
            <div className="col-date">발송일시</div>
            <div className="col-result">결과</div>
          </div>

          <div
            className="mail-log-table-body compact"
            ref={logListRef}
            tabIndex={0}
            onKeyDown={handleLogListKeyDown}
          >
            {filteredLogs.length === 0 ? (
              <div className="mail-log-empty">
                표시할 로그가 없습니다.
              </div>
            ) : (
              filteredLogs.map((row) => {
                const checked = checkedIds.includes(row.id);
                const isSelected = selected?.id === row.id;
                const isSuccess = Number(row.success) === 1;
                const isTest = Number(row.test_mode) === 1;

                return (
                  <button
                    key={row.id}
                    className={
                      isSelected ? "mail-log-row active" : "mail-log-row"
                    }
                    onClick={() => {
                      logListRef.current?.focus();
                      setSelectedId(row.id);
                    }}
                  >
                    <div className="col-check">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => {
                          e.stopPropagation();
                          toggleChecked(row.id);
                        }}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </div>

                    <div className="col-type">
                      <span className={isTest ? "mini-badge test" : "mini-badge real"}>
                        {isTest ? "TEST" : "REAL"}
                      </span>
                    </div>

                    <div className="col-supplier">
                      <strong>{row.supplier || "-"}</strong>
                    </div>

                    <div className="col-mailtype">
                      {row.mail_type || "-"}
                    </div>

                    <div className="col-subject subject-cell">
                      {row.subject || "-"}
                    </div>

                    <div className="col-date">
                      {row.sent_at || "-"}
                    </div>

                    <div className="col-result">
                      <span className={isSuccess ? "mini-badge ok" : "mini-badge fail"}>
                        {isSuccess ? "SUCCESS" : "FAIL"}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        <div className="mail-log-preview-surface">
          {selected ? (
            <>
              <div className="mail-log-preview-head">
                <div>
                  <div className="surface-title">메일 상세</div>
                  <h2>{selected.subject || "(제목 없음)"}</h2>
                </div>

                <div className="preview-badges">
                  <span className={Number(selected.test_mode) === 1 ? "mini-badge test" : "mini-badge real"}>
                    {Number(selected.test_mode) === 1 ? "TEST" : "REAL"}
                  </span>
                  <span className={Number(selected.success) === 1 ? "mini-badge ok" : "mini-badge fail"}>
                    {Number(selected.success) === 1 ? "SUCCESS" : "FAIL"}
                  </span>
                </div>
              </div>

              <div className="mail-preview-meta-block">
                <div className="mail-preview-meta-row">
                  <span className="meta-label">업체명</span>
                  <span className="meta-value">{selected.supplier || "-"}</span>
                </div>

                <div className="mail-preview-meta-row">
                  <span className="meta-label">관리번호</span>
                  <span className="meta-value">{selected.request_id || "-"}</span>
                </div>

                <div className="mail-preview-meta-row">
                  <span className="meta-label">수신자</span>
                  <span className="meta-value">{selected.receiver || "-"}</span>
                </div>

                <div className="mail-preview-meta-row">
                  <span className="meta-label">참조</span>
                  <span className="meta-value">{selected.cc || "-"}</span>
                </div>

                <div className="mail-preview-meta-row">
                  <span className="meta-label">발송일시</span>
                  <span className="meta-value">{selected.sent_at || "-"}</span>
                </div>

                <div className="mail-preview-meta-row">
                  <span className="meta-label">첨부PDF</span>
                  <span className="meta-value">{selected.attach_pdf || "-"}</span>
                </div>
              </div>

              {selected.error_message && (
                <div className="error-box">
                  {selected.error_message}
                </div>
              )}

              <div
                className="mail-preview-body"
                dangerouslySetInnerHTML={{ __html: selected.body_html || "" }}
              />
            </>
          ) : (
            <div className="mail-log-empty">
              메일을 선택하면 아래에 상세 내용이 표시됩니다.
            </div>
          )}
        </div>
      </section>
    </>
  );
}

function LhlnPage({ setActive }) {
  const [status, setStatus] = useState(null);
  const [records, setRecords] = useState([]);
  const [countries, setCountries] = useState([]);
  const [country, setCountry] = useState("");
  const [keyword, setKeyword] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const lhlnListRef = useRef(null);

  async function loadLhln(nextCountry = country, nextKeyword = keyword) {
    try {
      setLoading(true);

      const [statusData, recordData] = await Promise.all([
        getLhlnStatus(),
        getLhlnRecords({
          country: nextCountry,
          keyword: nextKeyword,
          limit: 500,
        }),
      ]);

      setStatus(statusData);
      setRecords(recordData.rows || []);
      setCountries(recordData.countries || []);
      setSelectedIndex(0);
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadLhln();
  }, []);

  async function handleSync() {
    const ok = window.confirm(
      "BPJPH LHLN 교차인정기관 DB를 동기화합니다. 외부 API 호출이 필요합니다. 계속할까요?"
    );

    if (!ok) return;

    try {
      setLoading(true);
      await syncLhln();
      await loadLhln();
      alert("LHLN DB 동기화 완료");
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreatePdf() {
    try {
      setLoading(true);
      const result = await createLhlnPdf();
      await loadLhln();
      alert(`PDF 생성 완료: ${result.pdf_name}`);
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleSearch() {
    loadLhln(country, keyword);
  }

  function handleLhlnListKeyDown(e) {
    if (!records.length) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.min(prev + 1, records.length - 1));
    }

    if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.max(prev - 1, 0));
    }
  }

  const selected = records[selectedIndex] || records[0];

  return (
    <>
      <PageHeader
        eyebrow="BPJPH / LHLN"
        title="교차인정기관 자료관리"
        desc="BPJPH LHLN 교차인정기관 DB를 동기화하고 업체 안내용 PDF를 생성합니다."
        onBack={() => setActive("home")}
      />

      <StatLine
        items={[
          { label: "기관 수", value: status?.record_count ?? "-" },
          { label: "국가 수", value: status?.country_count ?? "-" },
          { label: "PDF 생성", value: status?.pdf_exists ? "Y" : "N" },
          { label: "마지막 동기화", value: status?.last_sync?.crawled_at ? "Y" : "N" },
        ]}
      />

      <div className="log-toolbar">
        <button className="primary-button" onClick={handleSync} disabled={loading}>
          {loading ? "처리 중..." : "LHLN DB 동기화"}
        </button>

        <button className="ghost-action" onClick={handleCreatePdf} disabled={loading}>
          교차인정기관 안내 PDF 생성
        </button>

        <button className="ghost-action" onClick={() => loadLhln()} disabled={loading}>
          새로고침
        </button>
      </div>

      <div className="lhln-filter-bar">
        <select
          value={country}
          onChange={(e) => setCountry(e.target.value)}
        >
          <option value="">전체 국가</option>
          {countries.map((c) => (
            <option value={c} key={c}>
              {c}
            </option>
          ))}
        </select>

        <input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="기관명, 약어, 도시, 등록번호 검색"
        />

        <button className="primary-button" onClick={handleSearch} disabled={loading}>
          검색
        </button>
      </div>

      <section className="lhln-simple-surface">
        <div className="surface-title">기관 목록</div>

        <div className="lhln-simple-head">
          <div>국가</div>
          <div>기관명</div>
          <div>약어</div>
          <div>도시</div>
          <div>유효/등록일</div>
        </div>

        <div
          className="lhln-simple-body"
          ref={lhlnListRef}
          tabIndex={0}
          onKeyDown={handleLhlnListKeyDown}
        >
          {records.length === 0 ? (
            <div className="mail-log-empty">
              표시할 기관 데이터가 없습니다. 먼저 LHLN DB 동기화를 실행하세요.
            </div>
          ) : (
            records.map((row, idx) => (
              <button
                key={`${row.negara}-${row.nama_lhln}-${idx}`}
                className={
                  selectedIndex === idx
                    ? "lhln-simple-row active"
                    : "lhln-simple-row"
                }
                onClick={() => {
                  lhlnListRef.current?.focus();
                  setSelectedIndex(idx);
                }}
              >
                <div>{row.negara || "-"}</div>
                <div className="lhln-simple-name">{row.nama_lhln || "-"}</div>
                <div>{row.abbreviation || "-"}</div>
                <div>{row.kota || "-"}</div>
                <div>{row.tgl_berlaku || "-"}</div>
              </button>
            ))
          )}
        </div>

        <div className="lhln-pdf-note">
          <span>PDF 경로</span>
          <strong>{status?.pdf_path || "-"}</strong>
        </div>
      </section>
    </>
  );
}

function getEffectiveOcrStatus(item) {
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


function OcrPage({ setActive }) {
  const [files, setFiles] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [ocrTargets, setOcrTargets] = useState([]);
  const [mailTargets, setMailTargets] = useState([]);
  const [mailLogs, setMailLogs] = useState([]);
  const [lhlnRecords, setLhlnRecords] = useState([]);
  const [selectedPath, setSelectedPath] = useState("");
  const [selectedJob, setSelectedJob] = useState(null);
  
  const [ocrLang, setOcrLang] = useState("eng");
  const [ocrScannedPages, setOcrScannedPages] = useState(true);
  const [ocrHistoryStatusFilter, setOcrHistoryStatusFilter] = useState("");
  const [ocrHistoryOrgFilter, setOcrHistoryOrgFilter] = useState("");
  const [ocrHistoryKeyword, setOcrHistoryKeyword] = useState("");
  const [loading, setLoading] = useState(false);
  const [fileKeyword, setFileKeyword] = useState("");
  const [checkedOcrFilePaths, setCheckedOcrFilePaths] = useState([]);
  const [checkedOcrJobIds, setCheckedOcrJobIds] = useState([]);
  const [manualUploadFiles, setManualUploadFiles] = useState([]);
  const [manualDragActive, setManualDragActive] = useState(false);
  const manualUploadInputRef = useRef(null);

  const candidateListRef = useRef(null);
  const jobListRef = useRef(null);
  const certificateRule =
    selectedJob?.certificate_rule ||
    selectedJob?.result?.certificate_rule ||
    selectedJob?.result?.field_guess?.certificate_rule ||
    null;

  function safeText(value) {
    const text = String(value ?? "").trim();

    if (!text) return "";
    if (text === "-") return "";
    if (text.toLowerCase() === "nan") return "";
    if (text.toLowerCase() === "none") return "";
    if (text.toLowerCase() === "null") return "";

    return text;
  }

  function parseJsonArray(value) {
    try {
      if (!value) return [];
      if (Array.isArray(value)) return value;

      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return [];
    }
  }

  function normalizePath(value) {
    return String(value || "")
      .replaceAll("\\", "/")
      .toLowerCase()
      .trim();
  }

  function formatBytes(value) {
    const n = Number(value || 0);

    if (!n) return "-";
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;

    return `${(n / 1024 / 1024).toFixed(1)} MB`;
  }

  function pickFirst(obj, keys) {
    if (!obj) return "";

    for (const key of keys) {
      const value = safeText(obj[key]);

      if (value) return value;
    }

    return "";
  }

  function extractExpectedInfoFromMailText(text) {
    const raw = String(text || "")
      .replace(/&nbsp;/gi, " ")
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/p>/gi, "\n")
      .replace(/<[^>]+>/g, " ")
      .replace(/\r/g, "\n")
      .replace(/[ \t]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();

    const info = {
      supplier: "",
      koreanName: "",
      englishName: "",
      maker: "",
      org: "",
      certNo: "",
      expiry: "",
      country: "",
    };

    function cleanValue(value) {
      return String(value || "")
        .replace(/^[\s:\-]+/, "")
        .replace(/[\s]+$/g, "")
        .replace(/^\[/, "")
        .replace(/\]$/, "")
        .trim();
    }

    const supplierMatch =
      raw.match(/귀사\s*\[([^\]]+)\]/) ||
      raw.match(/귀사\s+(.+?)에서/) ||
      raw.match(/업체명\s*[:：]\s*(.+?)(?:\n|$)/) ||
      raw.match(/공급사\s*[:：]\s*(.+?)(?:\n|$)/);

    if (supplierMatch) {
      info.supplier = cleanValue(supplierMatch[1]);
    }

    const itemBlockMatch = raw.match(/★★★\s*해당\s*품목\s*★★★([\s\S]*?)(?:={10,}|■■■|관리번호:|$)/);
    const itemBlock = itemBlockMatch ? itemBlockMatch[1] : raw;

    const numberedItemMatch = itemBlock.match(/(?:^|\n)\s*1\.\s*([^\n\r]+)/);
    if (numberedItemMatch) {
      info.koreanName = cleanValue(numberedItemMatch[1]);
    }

    const materialMatch =
      itemBlock.match(/원료명\s*[:：]\s*(.+?)(?:\n|$)/) ||
      itemBlock.match(/품목명\s*[:：]\s*(.+?)(?:\n|$)/) ||
      itemBlock.match(/제품명\s*[:：]\s*(.+?)(?:\n|$)/);

    if (!info.koreanName && materialMatch) {
      info.koreanName = cleanValue(materialMatch[1]);
    }

    const englishMatch =
      itemBlock.match(/영문명\s*[:：]\s*(.+?)(?:\n|$)/) ||
      itemBlock.match(/english\s*name\s*[:：]\s*(.+?)(?:\n|$)/i);

    if (englishMatch) {
      info.englishName = cleanValue(englishMatch[1]);
    }

    const makerMatch =
      itemBlock.match(/제조사\s*[:：]\s*(.+?)(?:\n|$)/) ||
      itemBlock.match(/manufacturer\s*[:：]\s*(.+?)(?:\n|$)/i);

    if (makerMatch) {
      info.maker = cleanValue(makerMatch[1]);
    }

    const countryMatch =
      itemBlock.match(/제조국\s*[:：]\s*(.+?)(?:\n|$)/) ||
      itemBlock.match(/country\s*[:：]\s*(.+?)(?:\n|$)/i);

    if (countryMatch) {
      info.country = cleanValue(countryMatch[1]);
    }

    const orgMatch =
      itemBlock.match(/인증기관\s*[:：]\s*(BPJPH|MUI|KMF|JAKIM|CICOT|IFANCA|HQC|HCA|ISA|LHLN)/i) ||
      raw.match(/\b(BPJPH|MUI|KMF|JAKIM|CICOT|IFANCA|HQC|HCA|ISA|LHLN)\b/i);

    if (orgMatch) {
      info.org = orgMatch[1].toUpperCase();
    }

    const certNoMatch =
      itemBlock.match(/인증번호\s*[:：]\s*([A-Z0-9\-_.\/]+)/i) ||
      raw.match(/certificate\s*(?:no|number)\s*[:：]?\s*([A-Z0-9\-_.\/]+)/i);

    if (certNoMatch) {
      info.certNo = cleanValue(certNoMatch[1]);
    }

    const expiryMatch =
      itemBlock.match(/유효기간\s*[:：]\s*(20\d{2}[.\-\/]\d{1,2}[.\-\/]\d{1,2})/) ||
      itemBlock.match(/만료\s*[:：]?\s*(20\d{2}[.\-\/]\d{1,2}[.\-\/]\d{1,2})/) ||
      raw.match(/valid\s*(?:until|through)?\s*[:：]?\s*(20\d{2}[.\-\/]\d{1,2}[.\-\/]\d{1,2})/i);

    if (expiryMatch) {
      info.expiry = cleanValue(expiryMatch[1]).replaceAll(".", "-").replaceAll("/", "-");
    }

    return info;
  }

  function inferOrgCandidates(...texts) {
    const joined = texts
      .map((x) => String(x || ""))
      .join(" ")
      .toUpperCase();

    const orgs = [
      "BPJPH",
      "MUI",
      "KMF",
      "JAKIM",
      "CICOT",
      "IFANCA",
      "HQC",
      "HCA",
      "ISA",
      "LHLN",
    ];

    const result = [];

    for (const org of orgs) {
      if (joined.includes(org) && !result.includes(org)) {
        result.push(org);
      }
    }

    return result;
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

  function extractDateCandidates(rawText, source = "ocr") {
    const text = String(rawText || "")
      .replace(/&nbsp;/gi, " ")
      .replace(/\r/g, "\n")
      .replace(/[ \t]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();

    const low = text.toLowerCase();

    const monthMap = {
      jan: 1,
      january: 1,
      feb: 2,
      february: 2,
      mar: 3,
      march: 3,
      apr: 4,
      april: 4,
      may: 5,
      jun: 6,
      june: 6,
      jul: 7,
      july: 7,
      aug: 8,
      august: 8,
      sep: 9,
      sept: 9,
      september: 9,
      oct: 10,
      october: 10,
      nov: 11,
      november: 11,
      dec: 12,
      december: 12,
    };

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

    const candidates = [];

    function addCandidate(dateText, index, raw, pattern) {
      if (!dateText) return;

      const start = Math.max(0, index - 100);
      const end = Math.min(low.length, index + 140);
      const around = low.slice(start, end);
      const hasAnchor = anchors.some((anchor) => around.includes(anchor));

      candidates.push({
        date: dateText,
        raw,
        source,
        pattern,
        score: hasAnchor ? 90 : 50,
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
      addCandidate(
        toIsoDate(m[3], monthMap[m[2].toLowerCase()], m[1]),
        m.index || 0,
        m[0],
        "DD Month YYYY"
      );
    }

    for (const m of text.matchAll(/\b(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+(0?[1-9]|[12]\d|3[01]),?\s+(20\d{2})\b/gi)) {
      addCandidate(
        toIsoDate(m[3], monthMap[m[1].toLowerCase()], m[2]),
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
      .sort((a, b) => Number(b.score || 0) - Number(a.score || 0))
      .slice(0, 8);
  }

  function mergeDateCandidates(...lists) {
    const unique = new Map();

    for (const list of lists) {
      for (const item of list || []) {
        if (!item?.date) continue;

        const prev = unique.get(item.date);

        if (!prev || Number(item.score || 0) > Number(prev.score || 0)) {
          unique.set(item.date, item);
        }
      }
    }

    return Array.from(unique.values())
      .sort((a, b) => Number(b.score || 0) - Number(a.score || 0))
      .slice(0, 8);
  }


  function normalizeCertText(value) {
    return String(value || "")
      .replace(/&nbsp;/gi, " ")
      .replace(/\r/g, "\n")
      .replace(/[ \t]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function normalizeLoose(value) {
    return String(value || "")
      .toUpperCase()
      .replace(/Ⓡ/g, "R")
      .replace(/[^A-Z0-9]+/g, "")
      .trim();
  }

  function compactCompanyName(value) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    if (!text) return "";

    const stopWords = [
      " 3000 ", " 15024 ", " 1900 ", " 103,", " POL.", " UNIT ",
      " 2 RUE", " 56 GRAND", " P.O.", " PO BOX", " LAAN "
    ];

    const upper = text.toUpperCase();
    let cut = text.length;

    for (const word of stopWords) {
      const idx = upper.indexOf(word);
      if (idx > 0) cut = Math.min(cut, idx);
    }

    return text.slice(0, cut).replace(/[,:\-\s]+$/g, "").trim() || text;
  }

  function countryFromText(value) {
    const upper = String(value || "").toUpperCase();

    const countries = [
      ["UNITED STATES", "USA"],
      [" U.S.A", "USA"],
      [" USA", "USA"],
      ["KOREA", "KOREA"],
      ["THAILAND", "THAILAND"],
      ["MALAYSIA", "MALAYSIA"],
      ["INDONESIA", "INDONESIA"],
      ["NETHERLANDS", "NETHERLANDS"],
      ["UNITED KINGDOM", "UNITED KINGDOM"],
      [" U.K", "UNITED KINGDOM"],
      ["SPAIN", "SPAIN"],
      ["FRANCE", "FRANCE"],
      ["CHINA", "CHINA"],
      ["BRAZIL", "BRAZIL"],
    ];

    for (const [needle, country] of countries) {
      if (upper.includes(needle)) return country;
    }

    return "";
  }

  function certCountryByOrg(org) {
    const key = String(org || "").toUpperCase();
    const map = {
      IFANCA: "USA",
      ISA: "USA",
      KMF: "KOREA",
      JAKIM: "MALAYSIA",
      CICOT: "THAILAND",
      BPJPH: "INDONESIA",
      MUI: "INDONESIA",
      HQC: "NETHERLANDS",
      HCE: "UNITED KINGDOM",
      HFCE: "BELGIUM",
      HFQ: "SPAIN",
      HCA: "AUSTRALIA",
    };

    return map[key] || "";
  }

  function monthToNumber(monthText) {
    const key = String(monthText || "").toLowerCase().slice(0, 3);
    const map = {
      jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6,
      jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
    };
    return map[key] || 0;
  }

  function extractFirstDateByRegex(text, regexes) {
    for (const regex of regexes) {
      const match = String(text || "").match(regex);
      if (!match) continue;

      if (match.groups?.y && match.groups?.m && match.groups?.d) {
        return toIsoDate(match.groups.y, match.groups.m, match.groups.d);
      }

      if (match.groups?.month && match.groups?.day && match.groups?.year) {
        return toIsoDate(match.groups.year, monthToNumber(match.groups.month), match.groups.day);
      }

      if (match.groups?.day && match.groups?.month && match.groups?.year) {
        return toIsoDate(match.groups.year, monthToNumber(match.groups.month), match.groups.day);
      }
    }

    return "";
  }

  function findLineAfterLabel(lines, labelRegex) {
    const idx = lines.findIndex((line) => labelRegex.test(line));
    if (idx < 0) return "";

    for (let i = idx + 1; i < Math.min(lines.length, idx + 4); i += 1) {
      const value = String(lines[i] || "").trim();
      if (value && !labelRegex.test(value)) return value;
    }

    return "";
  }

  function cleanCompanyNameFromAddress(value) {
    const text = String(value || "")
      .replace(/\s+/g, " ")
      .trim();

    if (!text || text === "-") return "";

    // comma 앞 회사명 우선: Kalizea, 2 rue... -> Kalizea
    if (text.includes(",")) {
      const first = text.split(",", 1)[0].trim();
      if (first) return first;
    }

    const markers = [
      /\b\d{1,6}\b/i,
      /\bSTREET\b/i,
      /\bDRIVE\b/i,
      /\bROAD\b/i,
      /\bRD\b/i,
      /\bAVENUE\b/i,
      /\bAVE\b/i,
      /\bCORPORATE\b/i,
      /\bCENTER\b/i,
      /\bBUILDING\b/i,
      /\bWESTCHESTER\b/i,
      /\bILLINOIS\b/i,
      /\bPENNSYLVANIA\b/i,
      /\bUSA\b/i,
      /\bFRANCE\b/i,
      /\bGERMANY\b/i,
      /\bKOREA\b/i,
      /\bTHAILAND\b/i,
      /\bMALAYSIA\b/i,
    ];

    const positions = markers
      .map((regex) => {
        const match = text.match(regex);
        return match?.index ?? -1;
      })
      .filter((pos) => pos > 2);

    if (positions.length > 0) {
      return text.slice(0, Math.min(...positions)).trim(" ,-");
    }

    return text;
  }

  function normalizeProductNameForMatch(value) {
    return String(value || "")
      .toUpperCase()
      .replace(/[®™]/g, "")
      .replace(/\{.*?FAMILY OF PRODUCTS.*?\}/gi, "")
      .replace(/FAMILY OF PRODUCTS/gi, "")
      .replace(/[^A-Z0-9]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function productMatchScore(expected, candidate) {
    const a = normalizeProductNameForMatch(expected);
    const b = normalizeProductNameForMatch(candidate);

    if (!a || !b) return 0;
    if (a === b) return 100;
    if (a.includes(b) || b.includes(a)) return 92;

    const as = new Set(a.split(" ").filter(Boolean));
    const bs = new Set(b.split(" ").filter(Boolean));

    let hit = 0;
    as.forEach((token) => {
      if (bs.has(token)) hit += 1;
    });

    return Math.round((hit / Math.max(as.size, bs.size, 1)) * 85);
  }

  function parseEnglishDateToIso(value) {
    const monthMap = {
      JANUARY: "01",
      FEBRUARY: "02",
      MARCH: "03",
      APRIL: "04",
      MAY: "05",
      JUNE: "06",
      JULY: "07",
      AUGUST: "08",
      SEPTEMBER: "09",
      OCTOBER: "10",
      NOVEMBER: "11",
      DECEMBER: "12",
    };

    const text = String(value || "").replace(/\s+/g, " ").trim();

    let match = text.match(
      /(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(20\d{2})/i
    );

    if (match) {
      return `${match[3]}-${monthMap[match[1].toUpperCase()]}-${String(match[2]).padStart(2, "0")}`;
    }

    match = text.match(
      /(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s*,?\s*(20\d{2})/i
    );

    if (match) {
      return `${match[3]}-${monthMap[match[2].toUpperCase()]}-${String(match[1]).padStart(2, "0")}`;
    }

    return "";
  }

  function parseMalayDateToIso(value) {
    const monthMap = {
      JAN: "01",
      JANUARI: "01",
      FEB: "02",
      FEBRUARI: "02",
      MAC: "03",
      MARCH: "03",
      APR: "04",
      APRIL: "04",
      MEI: "05",
      MAY: "05",
      JUN: "06",
      JUNE: "06",
      JUL: "07",
      JULAI: "07",
      AUG: "08",
      OGOS: "08",
      SEP: "09",
      SEPTEMBER: "09",
      OKT: "10",
      OKTOBER: "10",
      NOV: "11",
      NOVEMBER: "11",
      DIS: "12",
      DISEMBER: "12",
    };

    const text = String(value || "").replace(/\s+/g, " ").trim();

    const match = text.match(/(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})/i);
    if (!match) return "";

    const month = monthMap[match[2].toUpperCase()];
    if (!month) return "";

    return `${match[3]}-${month}-${String(match[1]).padStart(2, "0")}`;
  }

  function inferMalaysiaCountry(text) {
    const upper = String(text || "").toUpperCase();

    const malaysiaMarkers = [
      "MALAYSIA",
      "SELANGOR",
      "SHAH ALAM",
      "KUALA LUMPUR",
      "JOHOR",
      "PENANG",
      "PULAU PINANG",
      "KEDAH",
      "KELANTAN",
      "MELAKA",
      "NEGERI SEMBILAN",
      "PAHANG",
      "PERAK",
      "PERLIS",
      "SABAH",
      "SARAWAK",
      "TERENGGANU",
      "PUTRAJAYA",
      "LABUAN",
    ];

    return malaysiaMarkers.some((marker) => upper.includes(marker))
      ? "MALAYSIA"
      : "";
  }

  function isHalalControlNoiseLine(line) {
    const text = String(line || "").trim();
    const upper = text.toUpperCase();

    if (!text) return true;

    if (/^[\u0600-\u06FF\s\W_]+$/.test(text)) return true;

    return [
      "MANUFACTURED BY",
      "اﻟﻣﺻﻧﻌﺔ",
      "المصنعة",
      "ﻓﻲ",
      "في",
    ].some((word) => upper.includes(word));
  }

  function looksLikeHalalControlCompany(line) {
    const text = String(line || "").trim();
    const upper = text.toUpperCase();

    if (!text) return false;
    if (isHalalControlNoiseLine(text)) return false;

    if (/\b\d{4,6}\b/.test(text) && /\([A-Za-z ]+\)/.test(text)) {
      return false;
    }

    return [
      "GMBH",
      "KG",
      "CO.",
      "CO,",
      "LTD",
      "LIMITED",
      "AG",
      "INC",
      "CORPORATION",
      "LLC",
      "S.A.",
      "SAS",
    ].some((token) => upper.includes(token));
  }

  function countryFromParentheses(line) {
    const text = String(line || "");
    const match = text.match(/\((Germany|France|Netherlands|China|Korea|USA|Thailand|Vietnam|Spain|Denmark|Hungary)\)/i);

    if (!match) return "";

    return countryFromText(match[1]);
  }

  function extractIfancaFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const lines = raw
      .split(/\n/)
      .map((line) => line.trim())
      .filter(Boolean);

    const expected = expectedInfo || {};
    const expectedEnglish = expected.englishName || "";

    const companyBlock =
      raw.match(
        /Company\s+Name\s*&\s*Address\s*:?\s*([\s\S]*?)(?:Plant\s+Name\s*&\s*Address|Muhammad|President|This Certificate|Page)/i
      )?.[1] || "";

    const companyFirstLine =
      companyBlock
        .split(/\n/)
        .map((line) => line.trim())
        .filter(Boolean)[0] || "";

    const maker = cleanCompanyNameFromAddress(companyFirstLine);

    const plantBlock =
      raw.match(
        /Plant\s+Name\s*&\s*Address\s*:?\s*([\s\S]*?)(?:Muhammad|President|This Certificate|Page)/i
      )?.[1] || "";

    const country =
      countryFromText(plantBlock) ||
      countryFromText(companyBlock) ||
      "USA";

    const expiryRaw =
      raw.match(/This Certificate is valid until\s+(.+?)\s+and subject/i)?.[1] ||
      raw.match(/This certificate is valid until\s+(.+?)\s+and subject/i)?.[1] ||
      "";

    const expiry = parseEnglishDateToIso(expiryRaw);

    const products = [];

    for (let i = 0; i < lines.length; i += 1) {
      const match = lines[i].match(/^(\d+)\.\s*(.+)$/);

      if (!match) continue;

      const no = Number(match[1]);
      let name = match[2]
        .replace(/\{.*?Family of products.*?\}/gi, "")
        .replace(/\{.*?\}/g, "")
        .replace(/\s+/g, " ")
        .trim();

      if (!name || /^THIS IS TO|^DATE:|^DOCUMENT/i.test(name)) continue;

      const lookAhead = lines.slice(i + 1, i + 8).join("\n");

      const halalId =
        lookAhead.match(/\b[A-Z]\d{5}\b/)?.[0] || "";

      const productCertNo =
        lookAhead.match(/\bHC-[A-Z0-9]{4,}\b/i)?.[0]?.toUpperCase() || "";

      products.push({
        no,
        name,
        halalId,
        certNo: productCertNo,
      });
    }

    const bestProduct =
      products
        .map((product) => ({
          ...product,
          score: productMatchScore(expectedEnglish, product.name),
        }))
        .sort((a, b) => b.score - a.score)[0] || null;

    const selectedProduct =
      bestProduct && bestProduct.score >= 45
        ? bestProduct
        : products[0] || null;

    return {
      supplier: maker || "-",
      koreanName: expected.koreanName || "-",
      englishName:
        selectedProduct?.name ||
        expected.englishName ||
        "-",
      product_name: selectedProduct?.name || "",
      maker: maker || "-",
      org: "IFANCA",
      certNo: selectedProduct?.certNo || "-",
      expiry: expiry || "-",
      country: country || "-",
      certCountry: "USA",
      products,
      best_product_match: selectedProduct
        ? {
            product: {
              name: selectedProduct.name,
              cert_no: selectedProduct.certNo,
              halal_id: selectedProduct.halalId,
            },
            score: selectedProduct.score || 0,
          }
        : null,
    };
  }

  function extractIsaFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const company = raw.match(/Company:\s*([\s\S]*?)(?:\n\s*This certificate|\n\s*This certificate states)/i)?.[1] || "";
    const expiry = extractFirstDateByRegex(raw, [
      /Valid Until:\s*\n?\s*(?<day>\d{1,2})\s+(?<month>[A-Za-z]+)\s+(?<year>20\d{2})/i,
    ]);
    const certNo = raw.match(/Certificate No\.\s*([A-Z0-9\-]+)/i)?.[1] || "";

    return {
      englishName: expectedInfo?.englishName || "",
      maker: compactCompanyName(company),
      org: "ISA",
      certNo,
      expiry,
      country: countryFromText(company),
      certCountry: "USA",
    };
  }

  function extractHfceFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const certNo = raw.match(/Document No\.?:\s*\n?\s*([^\n]+)/i)?.[1]?.trim() || "";
    const maker = raw.match(/For:\s*([^\n]+)/i)?.[1]?.trim() || raw.match(/This is to certify that\s+([^,\n]+)/i)?.[1]?.trim() || "";
    const locationBlock = raw.match(/following location:\s*\n?-?\s*([^\n]+)/i)?.[1] || raw;
    const expiry = extractFirstDateByRegex(raw, [
      /Valid until:\s*(?<month>[A-Za-z]+)\s+(?<day>\d{1,2}),?\s+(?<year>20\d{2})/i,
    ]);

    return {
      englishName: expectedInfo?.englishName || "",
      maker: compactCompanyName(maker),
      org: "HFCE",
      certNo,
      expiry,
      country: countryFromText(locationBlock),
      certCountry: "BELGIUM",
    };
  }

  function extractHfqCertNo(raw) {
    const text = String(raw || "")
      .replace(/\r/g, "\n")
      .replace(/[：]/g, ":")
      .replace(/[–—]/g, "-");

    const patterns = [
      /With\s+certificate\s+number\s*:?\s*(HFQ\s*-\s*\d{1,6}\s*\/\s*\d{1,4}\s*\/\s*[A-Z]{2,10})\b/i,
      /Con\s+n[ºo]\s+de\s+certificado\s*:?\s*(HFQ\s*-\s*\d{1,6}\s*\/\s*\d{1,4}\s*\/\s*[A-Z]{2,10})\b/i,
      /\b(HFQ\s*-\s*\d{1,6}\s*\/\s*\d{1,4}\s*\/\s*[A-Z]{2,10})\b/i,
    ];

    for (const pattern of patterns) {
      const match = text.match(pattern);

      if (match?.[1]) {
        return match[1].replace(/\s+/g, "").toUpperCase();
      }
    }

    return "";
  }

  function extractHfqFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const maker = raw.match(/CERTIFY THAT THE COMPANY:\s*CERTIFICA QUE LA EMPRESA:\s*\n?\s*([^\n]+)/i)?.[1] || "";
    const certNo = extractHfqCertNo(raw);
    
    const expiry = extractFirstDateByRegex(raw, [
      /Certificate valid until\s*\n?\s*(?<month>[A-Za-z]+)\s+(?<day>\d{1,2}),?\s+(?<year>20\d{2})/i,
      /Certificado válido hasta\s*\n?\s*(?<day>\d{1,2})\s+de\s+(?<month>[A-Za-z]+),?\s+(?<year>20\d{2})/i,
    ]);
    const plantBlock = raw.match(/Planta auditada[\s\S]*?Spain/i)?.[0] || raw;

    return {
      englishName: expectedInfo?.englishName || "",
      maker: compactCompanyName(maker),
      org: "HFQ",
      certNo: certNo || "-",
      expiry,
      country: countryFromText(plantBlock),
      certCountry: "SPAIN",
    };
  }

  function extractMuiFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const certNo = raw.match(/No\s*:\s*\n?\s*(LPPOM-[A-Z0-9]+)/i)?.[1] || raw.match(/\bLPPOM-[A-Z0-9]+\b/i)?.[0] || "";
    const maker = raw.match(/Name of Company\s*:?\s*\n?\s*([^\n:]+)/i)?.[1] || "";
    const expiry = extractFirstDateByRegex(raw, [
      /Valid until\s*:?\s*(?<month>[A-Za-z]+)\s+(?<day>\d{1,2})(?:st|nd|rd|th)?,?\s+(?<year>20\d{2})/i,
    ]);

    return {
      englishName: expectedInfo?.englishName || "",
      maker: compactCompanyName(maker),
      org: "MUI",
      certNo,
      expiry,
      country: countryFromText(maker),
      certCountry: "INDONESIA",
    };
  }

  function extractCicotFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const lines = raw
      .split(/\n/)
      .map((line) => line.trim())
      .filter(Boolean);

    const expected = expectedInfo || {};

    function normalizeName(value) {
      return String(value || "")
        .toUpperCase()
        .replace(/[®™]/g, "")
        .replace(/[^A-Z0-9]+/g, " ")
        .replace(/\s+/g, " ")
        .trim();
    }

    function productScore(a, b) {
      const x = normalizeName(a);
      const y = normalizeName(b);

      if (!x || !y) return 0;
      if (x === y) return 100;
      if (x.includes(y) || y.includes(x)) return 90;

      const xs = new Set(x.split(" ").filter(Boolean));
      const ys = new Set(y.split(" ").filter(Boolean));

      let hit = 0;
      xs.forEach((token) => {
        if (ys.has(token)) hit += 1;
      });

      return Math.round((hit / Math.max(xs.size, ys.size, 1)) * 80);
    }

    function parseCicotDate(value) {
      const monthMap = {
        JANUARY: "01",
        FEBRUARY: "02",
        MARCH: "03",
        APRIL: "04",
        MAY: "05",
        JUNE: "06",
        JULY: "07",
        AUGUST: "08",
        SEPTEMBER: "09",
        OCTOBER: "10",
        NOVEMBER: "11",
        DECEMBER: "12",
      };

      const match = String(value || "").match(
        /(January|February|March|April|May|June|July|August|September|October|November|December)\s*(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(20\d{2})/i
      );

      if (!match) return "";

      const month = monthMap[match[1].toUpperCase()];
      const day = String(match[2]).padStart(2, "0");
      const year = match[3];

      return `${year}-${month}-${day}`;
    }

    // 1) 제조사: CERTIFIES THAI / CERTIFIES THAT 바로 아래 회사명
    let maker = "";

    for (let i = 0; i < lines.length; i += 1) {
      const upperLine = lines[i].toUpperCase();

      if (upperLine.includes("CERTIFIES THAI") || upperLine.includes("CERTIFIES THAT")) {
        for (let j = i + 1; j < Math.min(lines.length, i + 6); j += 1) {
          const candidate = lines[j];

          if (
            /CO\.?,?\s*LTD\.?/i.test(candidate) ||
            /LIMITED/i.test(candidate) ||
            /COMPANY/i.test(candidate)
          ) {
            maker = candidate.trim();
            break;
          }
        }
      }

      if (maker) break;
    }

    // fallback: THAI EDIBLE OIL CO.,LTD. 같은 회사명 라인 직접 탐색
    if (!maker) {
      const companyLine = lines.find((line) =>
        /CO\.?,?\s*LTD\.?/i.test(line)
      );

      maker = companyLine || "";
    }

    // 2) 제품명: ProductType: 아래 comma-separated 목록
    const productBlockMatch = raw.match(
      /Product\s*Type\s*:?\s*([\s\S]*?)(?:Factory\s+Address|Undertakes|The\s+Central\s+Islamic|Effective\s+from|Regrsuation|Registration|Issued\s+on)/i
    );

    let productNames = [];

    if (productBlockMatch?.[1]) {
      productNames = productBlockMatch[1]
        .split(/\s*,\s*/)
        .map((name) => name.trim())
        .filter((name) => name.length >= 3)
        .filter((name) => !/^[^A-Za-z0-9]+$/.test(name));
    }

    const expectedEnglish = expected.englishName || "";
    let bestProduct = productNames[0] || "";

    if (expectedEnglish && productNames.length > 0) {
      bestProduct = productNames
        .map((name) => ({
          name,
          score: productScore(expectedEnglish, name),
        }))
        .sort((a, b) => b.score - a.score)[0]?.name || bestProduct;
    }

    // 3) 인증번호: Regrsuation/Registration No. CICOT HL: 다음 값
    const certNo =
      raw.match(/(?:Regrsuation|Registration)\s+No\.?\s+CICOT\s+HL\s*:?\s*\n?\s*([0-9/.-]+)/i)?.[1] ||
      "";

    // 4) 유효기간: Effective from 아래 날짜 2개 중 두 번째
    let expiry = "";

    const effectiveIndex = raw.toUpperCase().indexOf("EFFECTIVE FROM");

    if (effectiveIndex >= 0) {
      const chunk = raw.slice(effectiveIndex, effectiveIndex + 360);
      const dateMatches = Array.from(
        chunk.matchAll(
          /(January|February|March|April|May|June|July|August|September|October|November|December)\s*\d{1,2}(?:st|nd|rd|th)?\s*,?\s*20\d{2}/gi
        )
      ).map((m) => parseCicotDate(m[0]));

      expiry = dateMatches[1] || dateMatches[0] || "";
    }

    // 5) 제조국: Factory Address 블록에서 Thailand
    let country = "";

    const factoryMatch = raw.match(
      /Factory\s+Address\s*:?\s*([\s\S]*?)(?:Undertakes|The\s+Central\s+Islamic|Effective\s+from|Regrsuation|Registration)/i
    );

    if (factoryMatch?.[1]) {
      country = countryFromText(factoryMatch[1]) || "";
    }

    if (!country && raw.toUpperCase().includes("THAILAND")) {
      country = "THAILAND";
    }

    return {
      supplier: maker || "-",
      koreanName: expected.koreanName || "-",
      englishName: bestProduct || expected.englishName || "-",
      product_name: bestProduct || "",
      product_names: productNames,
      maker: maker || "-",
      org: "CICOT",
      certNo: certNo || "-",
      expiry: expiry || "-",
      country: country || "-",
      certCountry: "THAILAND",
    };
  }


  function extractHceFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const maker = raw.match(/Company Name:\s*([^\n]+)/i)?.[1] || "";
    const plant = raw.match(/Manufacture Site:\s*([^\n]+)/i)?.[1] || maker;
    const certNo = raw.match(/Certificate No:\s*([^\n]+)/i)?.[1]?.trim() || "";
    const expiry = extractFirstDateByRegex(raw, [
      /Expiry Date:\s*(?<day>\d{1,2})(?:st|nd|rd|th)?\s+(?<month>[A-Za-z]+)\s+(?<year>20\d{2})/i,
    ]);

    return {
      englishName: expectedInfo?.englishName || "",
      maker: compactCompanyName(maker),
      org: "HCE",
      certNo,
      expiry,
      country: countryFromText(plant),
      certCountry: "UNITED KINGDOM",
    };
  }

  function extractHqcFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const maker = findLineAfterLabel(raw.split(/\n/).map((line) => line.trim()).filter(Boolean), /Awarded to:/i);
    const certNo = raw.match(/Cert\. No:\s*\n?\s*([A-Z0-9]+)/i)?.[1] || "";
    const expiry = extractFirstDateByRegex(raw, [
      /Expiry Date:\s*\n?\s*(?<day>\d{1,2})[\/\-.](?<m>\d{1,2})[\/\-.](?<y>20\d{2})/i,
    ]);
    const companyBlock = raw.match(/Awarded to:[\s\S]*?Halal Quality Control BV/i)?.[0] || raw;

    return {
      englishName: expectedInfo?.englishName || "",
      maker: compactCompanyName(maker),
      org: "HQC",
      certNo,
      expiry,
      country: countryFromText(companyBlock),
      certCountry: "NETHERLANDS",
    };
  }

  function extractHalalControlFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const lines = raw
      .split(/\n/)
      .map((line) => line.trim())
      .filter(Boolean);

    let maker = "";
    let country = "";

    const idx = lines.findIndex((line) =>
      line.toUpperCase().includes("MANUFACTURED BY")
    );

    if (idx >= 0) {
      for (let i = idx + 1; i < Math.min(lines.length, idx + 10); i += 1) {
        const candidate = lines[i];

        if (looksLikeHalalControlCompany(candidate)) {
          maker = candidate.trim();
          break;
        }
      }

      for (let i = idx + 1; i < Math.min(lines.length, idx + 10); i += 1) {
        const candidateCountry = countryFromParentheses(lines[i]);

        if (candidateCountry) {
          country = candidateCountry;
          break;
        }
      }
    }

    const certNo =
      raw.match(/Cert\.-No\.:\s*([A-Z0-9\-\/]+)/i)?.[1] ||
      raw.match(/Certificate Registration No\.:\s*\n?\s*([A-Z0-9\-\/]+)/i)?.[1] ||
      "";

    const expiry = extractFirstDateByRegex(raw, [
      /Valid until:\s*\n?\s*(?<y>20\d{2})[-./](?<m>\d{1,2})[-./](?<d>\d{1,2})/i,
      /This certificate is valid until:\s*\n?\s*(?<y>20\d{2})[-./](?<m>\d{1,2})[-./](?<d>\d{1,2})/i,
      /This certificate is valid until\s+(?<y>20\d{2})[-./](?<m>\d{1,2})[-./](?<d>\d{1,2})/i,
    ]);

    return {
      englishName: expectedInfo?.englishName || "",
      maker,
      org: "HALAL CONTROL",
      certNo,
      expiry,
      country,
      certCountry: "GERMANY",
    };
  }

  function extractJakimFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const lines = raw
      .split(/\n/)
      .map((line) => line.trim())
      .filter(Boolean);

    const expected = expectedInfo || {};
    const expectedEnglish = expected.englishName || "";

    let maker = "";

    const makerIndex = lines.findIndex((line) =>
      /Manufactured\s*\/\s*distributed\s*\/\s*managed\s+by/i.test(line)
    );

    if (makerIndex >= 0) {
      maker = lines[makerIndex + 1] || "";
    }

    const addressBlock =
      makerIndex >= 0
        ? lines.slice(makerIndex + 2, makerIndex + 7).join("\n")
        : "";

    const country =
      countryFromText(addressBlock) ||
      inferMalaysiaCountry(addressBlock) ||
      "MALAYSIA";

    const certNo =
      raw.match(/No\.\s*Ruj\s*:\s*\/\s*Ref\s*No\.?\s*:?\s*\n?\s*([A-Z0-9.\-/ ]+)/i)?.[1]?.trim() ||
      raw.match(/\bJAKIM\.[A-Z0-9.\-/ ]+/i)?.[0]?.trim() ||
      raw.match(/Reference\s*:?\s*[\s\S]{0,80}?\b(E\d{4,})\b/i)?.[1]?.trim() ||
      "";

    const expiryRaw =
      raw.match(/Sah\s+Sehingga\s*\/\s*Valid\s+until\s*:?\s*\n?\s*([^\n]+)/i)?.[1] ||
      "";

    const expiry = parseMalayDateToIso(expiryRaw);

    const productBlock =
      raw.match(
        /It is hereby certified that\s*:?\s*([\s\S]*?)(?:yang dikeluarkan|Manufactured\s*\/\s*distributed\s*\/\s*managed\s+by)/i
      )?.[1] ||
      raw.match(
        /Adalah dengan ini diperakukan\s*:?\s*([\s\S]*?)(?:yang dikeluarkan|Manufactured\s*\/\s*distributed\s*\/\s*managed\s+by)/i
      )?.[1] ||
      "";

    const products = [];

    productBlock
      .split(/\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .forEach((line) => {
        const match = line.match(/^(\d+)\.\s*(.+)$/);

        if (!match) return;

        products.push({
          no: Number(match[1]),
          name: match[2].replace(/\s+/g, " ").trim(),
        });
      });

    const bestProduct =
      products
        .map((product) => ({
          ...product,
          score: productMatchScore(expectedEnglish, product.name),
        }))
        .sort((a, b) => b.score - a.score)[0] || null;

    const selectedProduct =
      bestProduct && bestProduct.score >= 45
        ? bestProduct
        : products[0] || null;

    return {
      supplier: maker || "-",
      koreanName: expected.koreanName || "-",
      englishName:
        selectedProduct?.name ||
        expected.englishName ||
        "-",
      product_name: selectedProduct?.name || "",
      maker: maker || "-",
      org: "JAKIM",
      certNo: certNo || "-",
      expiry: expiry || "-",
      country: country || "-",
      certCountry: "MALAYSIA",
      products,
      best_product_match: selectedProduct
        ? {
            product: {
              name: selectedProduct.name,
            },
            score: selectedProduct.score || 0,
          }
        : null,
    };
  }

  function extractOcrCertificateFields(rawText, expectedInfo, orgCandidates) {
    const text = normalizeCertText(rawText);
    const upper = text.toUpperCase();
    const expected = expectedInfo || {};

    let result = {
      supplier: "-",
      koreanName: expected.koreanName || "-",
      englishName: expected.englishName || "-",
      maker: "-",
      org: (orgCandidates || []).join(", ") || "-",
      certNo: "-",
      expiry: "-",
      country: "-",       // 제조국
      certCountry: "-",   // 인증국가
      countryOrgMatch: "-",
    };

    const primaryOrg =
      upper.includes("THE CENTRAL ISLAMIC COUNCIL OF THAILAND") ? "CICOT" :
      upper.includes("HALAL CONTROL") ? "HALAL CONTROL" :
      (upper.includes("JABATAN KEMAJUAN ISLAM MALAYSIA") || upper.includes("HALAL MALAYSIA") || upper.includes("JAKIM")) ? "JAKIM" :
      (upper.includes("ISLAMIC FOOD AND NUTRITION COUNCIL OF AMERICA") || upper.includes("IFANCA")) ? "IFANCA" :
      (upper.includes("ISLAMIC SERVICES OF AMERICA") || /\bISA\b/.test(upper)) ? "ISA" :
      upper.includes("HALAL FOOD COUNCIL OF EUROPE") ? "HFCE" :
      upper.includes("HALAL FOOD & QUALITY") ? "HFQ" :
      upper.includes("HALAL CERTIFICATION EUROPE") ? "HCE" :
      upper.includes("HALAL QUALITY CONTROL") ? "HQC" :
      upper.includes("MAJELIS ULAMA INDONESIA") || upper.includes("LPPOM MUI") ? "MUI" :
      upper.includes("REPUBLIK INDONESIA") || upper.includes("SERTIFIKAT HALAL") || /\bID00\d{8,}/.test(upper) ? "BPJPH" :
      (orgCandidates || [])[0] || "";

    const ruleMap = {
      IFANCA: extractIfancaFields,
      ISA: extractIsaFields,
      HFCE: extractHfceFields,
      HFQ: extractHfqFields,
      HCE: extractHceFields,
      HQC: extractHqcFields,
      MUI: extractMuiFields,
      CICOT: extractCicotFields,
      JAKIM: extractJakimFields,
    };

    if (typeof extractHalalControlFields === "function") {
      ruleMap["HALAL CONTROL"] = extractHalalControlFields;
    }

    if (typeof extractBpjphFields === "function") {
      ruleMap.BPJPH = extractBpjphFields;
    }

    const extracted = ruleMap[primaryOrg]
      ? ruleMap[primaryOrg](text, expected)
      : {};

    result = {
      ...result,
      ...extracted,
      org: extracted.org || primaryOrg || result.org,
      expiry:
        extracted.expiry ||
        mergeDateCandidates(extractDateCandidates(text, "ocr"))[0]?.date ||
        "-",
    };

    if (result.org === "HFQ") {
      const hfqCertNo = extractHfqCertNo(text);

      result.certNo = hfqCertNo || "-";
    }
    
    if (!result.certCountry || result.certCountry === "-") {
      result.certCountry = certCountryByOrg(result.org) || "-";
    }

    const makerCountry = normalizeLoose(result.country);
    const certCountry = normalizeLoose(result.certCountry);

    if (
      makerCountry &&
      certCountry &&
      result.country !== "-" &&
      result.certCountry !== "-"
    ) {
      result.countryOrgMatch = makerCountry === certCountry ? "일치" : "불일치";
    }

    return result;
  }

  function normalizeMatchText(value) {
    return String(value || "")
      .toUpperCase()
      .replace(/[^A-Z0-9가-힣]/g, "");
  }

  function getOrgAliases(org) {
    const key = String(org || "").toUpperCase();

    const aliasMap = {
      KMF: ["KMF", "KOREA MUSLIM FEDERATION"],
      CICOT: ["CICOT", "CENTRAL ISLAMIC COUNCIL OF THAILAND", "THE CENTRAL ISLAMIC COUNCIL OF THAILAND"],
      IFANCA: ["IFANCA", "ISLAMIC FOOD AND NUTRITION COUNCIL OF AMERICA"],
      HQC: ["HQC", "HALAL QUALITY CONTROL"],
      HCA: ["HCA", "HALAL CERTIFICATION AUTHORITY"],
      ISA: ["ISA", "ISLAMIC SERVICES OF AMERICA"],
      JAKIM: ["JAKIM", "JABATAN KEMAJUAN ISLAM MALAYSIA"],
      BPJPH: ["BPJPH", "BADAN PENYELENGGARA JAMINAN PRODUK HALAL"],
      MUI: ["MUI", "MAJELIS ULAMA INDONESIA"],
    };

    return aliasMap[key] || [key];
  }

  function scoreLhlnRecord(record, orgCandidates) {
    const orgs = orgCandidates || [];
    const aliases = orgs.flatMap((org) => getOrgAliases(org));

    const recordText = normalizeMatchText([
      record.country,
      record.negara,
      record.org_name,
      record.nama_lhln,
      record.name,
      record.agency,
      record.agency_name,
      record.short_name,
      record.abbr,
      record.abbreviation,
      record.city,
      record.kota,
      record.registration_no,
      record.no_reg,
    ].join(" "));

    let bestScore = 0;
    let matchedAlias = "";

    aliases.forEach((alias) => {
      const aliasText = normalizeMatchText(alias);

      if (!aliasText) return;

      let score = 0;

      if (recordText === aliasText) {
        score = 100;
      } else if (recordText.includes(aliasText)) {
        score = 85;
      } else if (aliasText.includes(recordText) && recordText.length >= 4) {
        score = 70;
      }

      if (score > bestScore) {
        bestScore = score;
        matchedAlias = alias;
      }
    });

    return {
      score: bestScore,
      matchedAlias,
    };
  }

  function findBestLhlnMatch(orgCandidates) {
    const orgs = orgCandidates || [];

    if (orgs.includes("BPJPH") || orgs.includes("MUI")) {
      return null;
    }

    const scored = (lhlnRecords || [])
      .map((record) => {
        const result = scoreLhlnRecord(record, orgs);

        return {
          ...record,
          _score: result.score,
          _matchedAlias: result.matchedAlias,
        };
      })
      .filter((record) => record._score > 0)
      .sort((a, b) => b._score - a._score);

    return scored[0] || null;
  }

  function buildLhlnDecision(orgCandidates) {
    const orgs = orgCandidates || [];
    const bestMatch = findBestLhlnMatch(orgs);

    if (orgs.includes("BPJPH") || orgs.includes("MUI")) {
      return {
        label: "LHLN 매칭 생략",
        status: "skip",
        match: null,
        desc: "BPJPH/MUI는 인도네시아 기관으로 관리하며, 현재 로직에서는 LHLN 교차인정 확인 대상에서 제외합니다.",
      };
    }

    if (bestMatch) {
      return {
        label: "LHLN 매칭 후보",
        status: "ok",
        match: bestMatch,
        desc: `${bestMatch._matchedAlias || "기관 후보"} 기준으로 LHLN 후보가 확인되었습니다.`,
      };
    }

    if (orgs.length === 0) {
      return {
        label: "기관 후보 없음",
        status: "unknown",
        match: null,
        desc: "OCR 원문/파일명/메일 제목에서 인증기관 후보를 찾지 못했습니다.",
      };
    }

    return {
      label: "LHLN 확인 필요",
      status: "check",
      match: null,
      desc: "기관 후보는 있으나 LHLN DB에서 직접 매칭되는 항목을 찾지 못했습니다.",
    };
  }

  async function loadOcrData(next = {}) {
    try {
      setLoading(true);

      const status = next.status ?? ocrHistoryStatusFilter;
      const org = next.org ?? ocrHistoryOrgFilter;
      const keyword = next.keyword ?? ocrHistoryKeyword;

      const [targetData, jobData, mailTargetData, logData, lhlnData] = await Promise.all([
        getInboxOcrTargets({ limit: 500, only_pending: false }),
        getOcrJobs({
          limit: 300,
          status,
          org,
          keyword,
          include_test: false,
        }),
        getMailTargets({ testMode: false }),
        getMailLogs({ limit: 500, testMode: false }),
        getLhlnRecords({ limit: 500 }),
      ]);

      setOcrTargets(targetData.rows || []);
      setJobs(jobData.rows || []);
      setMailTargets(mailTargetData.rows || mailTargetData.targets || []);
      setMailLogs(logData.rows || []);
      setLhlnRecords(lhlnData.rows || []);

      setCheckedOcrJobIds((prev) => {
        const valid = new Set((jobData.rows || []).map((job) => Number(job.id)));
        return prev.filter((id) => valid.has(Number(id)));
      });
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }
  

  useEffect(() => {
    loadOcrData();
  }, []);

  const targetByPath = useMemo(() => {
    const map = new Map();

    for (const row of ocrTargets) {
      if (row.saved_path) {
        map.set(normalizePath(row.saved_path), row);
      }
    }

    return map;
  }, [ocrTargets]);

  function findTargetByAnyPath(pathText) {
    const normalized = normalizePath(pathText);

    if (!normalized) return null;

    for (const row of ocrTargets) {
      const saved = normalizePath(row.saved_path);

      if (!saved) continue;

      if (normalized === saved) return row;
      if (normalized.endsWith(saved)) return row;
      if (saved.endsWith(normalized)) return row;
    }

    return null;
  }

  function getJobMeta(job) {
    const target = findTargetByAnyPath(job?.source_path);
    const mailTarget = target?.request_id
      ? mailTargetByRequestId.get(target.request_id)
      : null;
    const mailLog = target?.request_id
      ? mailLogByRequestId.get(target.request_id)
      : null;
    const logInfo = extractExpectedInfoFromMailText([
      mailLog?.subject,
      mailLog?.body_html,
      mailTarget?.subject,
      mailTarget?.body_html,
      target?.subject,
      target?.body_text,
      target?.body_preview,
    ].join("\n"));

    const orgs = inferOrgCandidates(
      job?.filename,
      job?.source_path,
      target?.subject,
      target?.saved_filename,
      target?.original_filename
    );

    const filenameCandidates = parseJsonArray(target?.filename_date_candidates_json);
    const mailCandidates = parseJsonArray(target?.mail_date_candidates_json);
    const jobFilenameCandidates = extractDateCandidates(job?.filename, "filename");

    const dateCandidates = mergeDateCandidates(
      filenameCandidates,
      mailCandidates,
      jobFilenameCandidates
    );

    return {
      target,
      mailTarget,
      supplier:
        logInfo.supplier ||
        pickFirst(mailTarget, ["supplier", "supplier_name", "vendor"]) ||
        pickFirst(target, ["sender"]) ||
        "-",
      material:
        logInfo.koreanName ||
        pickFirst(mailTarget, [
          "material_name",
          "main_material",
          "korean_name",
          "product_name",
          "item_name",
        ]) ||
        "-",
      org: orgs.join(", ") || "-",
      expiry: dateCandidates[0]?.date || "-",
      requestId: target?.request_id || "-",
    };
  }

  function getJobImageClassification(job) {
    return (
      job?.image_classification ||
      job?.result?.image_classification ||
      job?.result?.field_guess?.image_classification ||
      {}
    );
  }

  function getTemplateDecisionLabel(value) {
    const text = String(value || "").toUpperCase();

    if (text === "AUTO_IMAGE") return "자동";
    if (text === "REVIEW") return "검토";
    if (text === "MANUAL_REVIEW") return "수동";
    if (text === "EXCLUDED") return "제외";
    if (text === "ERROR") return "오류";
    if (text === "AUTO_CONFIRMED") return "확정";
    if (text === "MANUAL_CONFIRMED") return "확정";
    if (text === "MANUAL_CORRECTED") return "정정";
    if (text === "RESTORED") return "복구";

    return text || "-";
  }

  function getTemplateClassificationSummary(job) {
    const info = getJobImageClassification(job);

    if (!info) {
      return {
        predictedOrg: "-",
        finalOrg: "-",
        imageDecision: "-",
        adminDecision: "-",
        scoreText: "-",
        label: "-",
        isExcluded: false,
        title: "양식 DB 분류 정보 없음",
      };
    }

    const predictedOrg = info.predicted_org || "-";
    const finalOrg = info.is_excluded ? "-" : (info.final_org || predictedOrg || "-");
    const imageDecision = info.image_decision || info.decision || "-";
    const adminDecision = info.admin_decision || info.manual_decision?.decision_type || "";
    const score = Number(info.score);
    const scoreText = Number.isFinite(score) ? score.toFixed(4) : "-";
    const margin = Number(info.margin);
    const marginText = Number.isFinite(margin) ? margin.toFixed(4) : "-";

    const labelParts = [getTemplateDecisionLabel(imageDecision)];

    if (adminDecision) {
      labelParts.push(getTemplateDecisionLabel(adminDecision));
    }

    if (info.is_excluded) {
      labelParts.push("OCR제외");
    }

    return {
      predictedOrg,
      finalOrg,
      imageDecision,
      adminDecision,
      scoreText,
      marginText,
      label: labelParts.filter(Boolean).join(" / "),
      isExcluded: Boolean(info.is_excluded),
      title: [
        `이미지기관: ${predictedOrg}`,
        `최종기관: ${finalOrg}`,
        `이미지판정: ${getTemplateDecisionLabel(imageDecision)}`,
        adminDecision ? `관리자판정: ${getTemplateDecisionLabel(adminDecision)}` : "",
        `score: ${scoreText}`,
        `margin: ${marginText}`,
        info.second_org ? `2순위: ${info.second_org}` : "",
      ]
        .filter(Boolean)
        .join("\n"),
    };
  }

  const mailTargetByRequestId = useMemo(() => {
    const map = new Map();

    for (const row of mailTargets) {
      if (row.request_id) {
        map.set(row.request_id, row);
      }
    }

    return map;
  }, [mailTargets]);

  const mailLogByRequestId = useMemo(() => {
    const map = new Map();

    for (const row of mailLogs) {
      if (!row.request_id) continue;
      if (!map.has(row.request_id)) {
        map.set(row.request_id, row);
      }
    }

    return map;
  }, [mailLogs]);

  const candidateFiles = useMemo(() => {
    const targetRows = ocrTargets.map((row) => ({
      kind: "inbox_target",
      id: `target-${row.id}`,
      filepath: row.saved_path,
      filename: row.saved_filename || row.original_filename || "-",
      file_ext: row.ext || "",
      size_bytes: row.file_size || 0,
      modified_at: row.received_at || row.created_at || "-",
      request_id: row.request_id || "",
      ocr_status: row.ocr_status || "pending",
      ocr_selected: Number(row.ocr_selected || 0),
      source_row: row,
    }));

    const targetPaths = new Set(
      targetRows.map((row) => normalizePath(row.filepath))
    );

    const normalRows = files
      .filter((file) => !targetPaths.has(normalizePath(file.filepath)))
      .map((file) => ({
        kind: "file",
        id: `file-${file.filepath}`,
        filepath: file.filepath,
        filename: file.filename,
        file_ext: file.file_ext,
        size_bytes: file.size_bytes,
        modified_at: file.modified_at,
        request_id: "",
        ocr_status: "",
        ocr_selected: 0,
        source_row: file,
      }));

    return [...targetRows, ...normalRows];
  }, [ocrTargets, files]);

  const filteredFiles = useMemo(() => {
    const q = fileKeyword.trim().toLowerCase();

    if (!q) return candidateFiles;

    return candidateFiles.filter((file) => {
      const text = [
        file.filename,
        file.filepath,
        file.file_ext,
        file.modified_at,
        file.request_id,
        file.ocr_status,
      ]
        .join(" ")
        .toLowerCase();

      return text.includes(q);
    });
  }, [candidateFiles, fileKeyword]);

  const selectedFile =
    candidateFiles.find((file) => normalizePath(file.filepath) === normalizePath(selectedPath)) ||
    filteredFiles[0];

  const selectedTarget =
    findTargetByAnyPath(selectedJob?.source_path) ||
    findTargetByAnyPath(selectedFile?.filepath) ||
    null;

  const selectedMailTarget = selectedTarget?.request_id
    ? mailTargetByRequestId.get(selectedTarget.request_id)
    : null;

  const selectedMailLog = selectedTarget?.request_id
    ? mailLogByRequestId.get(selectedTarget.request_id)
    : null;

  const selectedJobRawText = selectedJob?.raw_text || selectedJob?.raw_text_preview || "";
  const jobOrgCandidates = selectedJob?.result?.field_guess?.org_candidates || [];

  const inferredOrgCandidates = inferOrgCandidates(
    selectedJob?.filename,
    selectedJob?.source_path,
    selectedTarget?.subject,
    selectedTarget?.saved_filename,
    selectedTarget?.original_filename,
    selectedMailTarget?.subject,
    selectedJobRawText
  );

  const orgCandidates = Array.from(
    new Set([...jobOrgCandidates, ...inferredOrgCandidates])
  );

  const filenameDateCandidates = parseJsonArray(
    selectedTarget?.filename_date_candidates_json
  );

  const mailDateCandidates = parseJsonArray(
    selectedTarget?.mail_date_candidates_json
  );

  const ocrDateCandidates = extractDateCandidates(selectedJobRawText, "ocr");

  const mergedDateCandidates = mergeDateCandidates(
    ocrDateCandidates,
    filenameDateCandidates,
    mailDateCandidates
  );

  const bestExpiry = mergedDateCandidates[0]?.date || "-";
  const lhlnDecision = buildLhlnDecision(orgCandidates);

  const mailTextInfo = extractExpectedInfoFromMailText([
    selectedMailLog?.subject,
    selectedMailLog?.body_html,
    selectedMailLog?.body_text,
    selectedTarget?.subject,
    selectedTarget?.body_text,
    selectedTarget?.body_preview,
    selectedMailTarget?.subject,
    selectedMailTarget?.body,
    selectedMailTarget?.body_html,
    selectedMailTarget?.content,
  ].join("\n"));

  const expectedInfo = {
    supplier:
      mailTextInfo.supplier ||
      pickFirst(selectedMailTarget, ["supplier", "supplier_name", "vendor", "company_name"]) ||
      pickFirst(selectedTarget, ["sender"]) ||
      "-",

    koreanName:
      mailTextInfo.koreanName ||
      pickFirst(selectedMailTarget, [
        "material_name",
        "main_material",
        "korean_name",
        "product_name",
        "item_name",
        "raw_material",
        "display_material",
      ]) ||
      "-",

    englishName:
      mailTextInfo.englishName ||
      pickFirst(selectedMailTarget, [
        "english_name",
        "main_english",
        "product_english",
        "material_english",
        "display_english",
      ]) ||
      "-",

    maker:
      mailTextInfo.maker ||
      pickFirst(selectedMailTarget, [
        "maker",
        "manufacturer",
        "display_maker",
      ]) ||
      "-",

    org:
      mailTextInfo.org ||
      pickFirst(selectedMailTarget, [
        "org",
        "main_org",
        "cert_org",
        "certification_body",
        "display_org",
      ]) ||
      orgCandidates[0] ||
      "-",

    certNo:
      mailTextInfo.certNo ||
      pickFirst(selectedMailTarget, [
        "cert_no",
        "certificate_no",
        "cert_number",
        "display_cert_no",
      ]) ||
      "-",

    expiry:
      mailTextInfo.expiry ||
      pickFirst(selectedMailTarget, [
        "exp",
        "expiry",
        "valid_until",
        "valid_date",
        "display_exp",
      ]) ||
      "-",

    country:
      mailTextInfo.country ||
      pickFirst(selectedMailTarget, [
        "maker_country",
        "country",
        "manufacture_country",
        "display_country",
      ]) ||
      "-",
  };

  const ocrReadInfo = extractOcrCertificateFields(
    selectedJobRawText,
    expectedInfo,
    orgCandidates
  );

  function buildOcrHighlightTerms(rule, expected, readInfo) {
    const terms = [];

    function add(label, value, className) {
      const text = String(value || "").trim();
      if (!text || text === "-" || text.length < 3) return;

      terms.push({
        label,
        value: text,
        className,
      });
    }

    add("제품명", rule?.best_product_match?.product?.name, "hl-product");
    add("제품명", rule?.product_name, "hl-product");
    add("제품명", expected?.englishName, "hl-product");
    add("제품명", readInfo?.englishName, "hl-product");
    add("제품명", expected?.koreanName, "hl-product");

    add("제조사", rule?.manufacturer, "hl-maker");
    add("제조사", expected?.maker, "hl-maker");
    add("제조사", readInfo?.maker, "hl-maker");

    add("인증기관", rule?.cert_org, "hl-org");
    add("인증기관", expected?.org, "hl-org");
    add("인증기관", readInfo?.org, "hl-org");

    add("인증번호", rule?.cert_no, "hl-cert");
    add("인증번호", expected?.certNo, "hl-cert");
    add("인증번호", readInfo?.certNo, "hl-cert");

    add("유효기간", rule?.expiry_date, "hl-expiry");
    add("유효기간", expected?.expiry, "hl-expiry");
    add("유효기간", readInfo?.expiry, "hl-expiry");
    add("유효기간", bestExpiry, "hl-expiry");

    add("제조국", rule?.manufacturing_country, "hl-mfg-country");
    add("제조국", expected?.country, "hl-mfg-country");
    add("제조국", readInfo?.country, "hl-mfg-country");
    add("인증국가", rule?.cert_country, "hl-cert-country");
    add("인증국가", readInfo?.certCountry, "hl-cert-country");

    const seen = new Set();

    return terms
      .filter((item) => {
        const key = item.value.toUpperCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .sort((a, b) => b.value.length - a.value.length);
  }

  function escapeRegExp(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function HighlightedOcrText({ text, rule, expected, readInfo }) {
    const source = String(text || "");
    const terms = buildOcrHighlightTerms(rule, expected, readInfo);

    if (!source.trim()) {
      return <>추출된 텍스트가 없습니다.</>;
    }

    if (terms.length === 0) {
      return <>{source}</>;
    }

    const pattern = new RegExp(
      `(${terms.map((item) => escapeRegExp(item.value)).join("|")})`,
      "gi"
    );

    return (
      <>
        {source.split(pattern).map((part, idx) => {
          const found = terms.find(
            (item) => item.value.toUpperCase() === String(part).toUpperCase()
          );

          if (!found) {
            return <span key={`ocr-text-${idx}`}>{part}</span>;
          }

          return (
            <mark
              key={`ocr-mark-${idx}`}
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

  async function handleRunOcr() {
    if (!selectedFile?.filepath) {
      alert("OCR 처리할 파일을 선택하세요.");
      return;
    }

    try {
      setLoading(true);

      const result = await createOcrJob({
        source_path: selectedFile.filepath,
        ocr_scanned_pages: ocrScannedPages,
        lang: ocrLang,
      });

      const detail = await getOcrJob(result.id);
      setSelectedJob(detail);

      await loadOcrData();

      alert(`OCR 처리 완료: ${detail.status}`);
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  function toggleOcrFileChecked(filepath) {
    if (!filepath) return;

    setCheckedOcrFilePaths((prev) => {
      if (prev.includes(filepath)) {
        return prev.filter((x) => x !== filepath);
      }

      return [...prev, filepath];
    });
  }

  function handleSelectAllOcrFiles() {
    setCheckedOcrFilePaths(
      filteredFiles
        .map((file) => file.filepath)
        .filter(Boolean)
    );
  }

  function handleClearOcrFiles() {
    setCheckedOcrFilePaths([]);
  }

  async function handleRunCheckedOcr() {
    const targets = filteredFiles.filter((file) =>
      checkedOcrFilePaths.includes(file.filepath)
    );

    if (targets.length === 0) {
      alert("OCR 실행할 후보 파일을 체크하세요.");
      return;
    }

    const ok = window.confirm(`체크한 파일 ${targets.length}건을 OCR 실행합니다. 계속할까요?`);
    if (!ok) return;

    try {
      setLoading(true);

      let lastDetail = null;

      for (const file of targets) {
        const result = await createOcrJob({
          source_path: file.filepath,
          ocr_scanned_pages: ocrScannedPages,
          lang: ocrLang,
        });

        lastDetail = await getOcrJob(result.id);
      }

      if (lastDetail) {
        setSelectedJob(lastDetail);
        if (lastDetail.source_path) {
          setSelectedPath(lastDetail.source_path);
        }
      }

      setCheckedOcrFilePaths([]);
      await loadOcrData();

      alert(`OCR 처리 완료: ${targets.length}건`);
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleSelectJob(jobId) {
    try {
      setLoading(true);
      const detail = await getOcrJob(jobId);
      setSelectedJob(detail);

      if (detail.source_path) {
        setSelectedPath(detail.source_path);
      }
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }
  
  function toggleOcrJobChecked(jobId) {
    const id = Number(jobId);

    if (!id) return;

    setCheckedOcrJobIds((prev) => {
      if (prev.includes(id)) {
        return prev.filter((x) => x !== id);
      }

      return [...prev, id];
    });
  }

  function handleSelectAllOcrJobs() {
    setCheckedOcrJobIds(jobsForView.map((job) => Number(job.id)).filter(Boolean));
  }

  function handleClearOcrJobChecks() {
    setCheckedOcrJobIds([]);
  }

  async function handleDeleteSelectedOcrJobs() {
    if (checkedOcrJobIds.length === 0) {
      alert("삭제할 OCR 작업을 선택하세요.");
      return;
    }

    const ok = window.confirm(`선택한 OCR 작업 ${checkedOcrJobIds.length}건을 삭제합니다. 계속할까요?`);
    if (!ok) return;

    try {
      setLoading(true);

      await deleteOcrJobs(checkedOcrJobIds);

      if (selectedJob?.id && checkedOcrJobIds.includes(Number(selectedJob.id))) {
        setSelectedJob(null);
      }

      setCheckedOcrJobIds([]);
      await loadOcrData();

      alert("선택 OCR 작업 삭제 완료");
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleRerunSelectedOcrJobs() {
    const targets = jobsForView.filter((job) =>
      checkedOcrJobIds.includes(Number(job.id))
    );

    if (targets.length === 0) {
      alert("재판독할 OCR 작업을 선택하세요.");
      return;
    }

    const ok = window.confirm(`선택한 OCR 작업 ${targets.length}건을 재판독합니다. 계속할까요?`);
    if (!ok) return;

    try {
      setLoading(true);

      let lastDetail = null;

      for (const job of targets) {
        if (!job.source_path) continue;

        const result = await createOcrJob({
          source_path: job.source_path,
          ocr_scanned_pages: ocrScannedPages,
          lang: ocrLang,
        });

        lastDetail = await getOcrJob(result.id);
      }

      if (lastDetail) {
        setSelectedJob(lastDetail);
      }

      setCheckedOcrJobIds([]);
      await loadOcrData();

      alert("선택 OCR 작업 재판독 완료");
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleManualFilePick(fileList) {
    const picked = Array.from(fileList || []);

    if (picked.length === 0) return;

    setManualUploadFiles((prev) => {
      const map = new Map();

      [...prev, ...picked].forEach((file) => {
        const key = `${file.name}_${file.size}_${file.lastModified}`;
        map.set(key, file);
      });

      return Array.from(map.values());
    });
  }

  function handleRemoveManualFile(index) {
    setManualUploadFiles((prev) => prev.filter((_, idx) => idx !== index));
  }

  async function handleUploadManualOcrFiles() {
    if (manualUploadFiles.length === 0) {
      alert("추가할 인증서 파일을 선택하세요.");
      return;
    }

    try {
      setLoading(true);

      const uploadResult = await uploadOcrManualFiles(manualUploadFiles);
      const uploadedRows = (uploadResult.rows || []).filter((row) => row.ok && row.saved_path);

      if (uploadedRows.length === 0) {
        alert("업로드된 OCR 대상 파일이 없습니다.");
        return;
      }

      let lastDetail = null;

      for (const row of uploadedRows) {
        const result = await createOcrJob({
          source_path: row.saved_path,
          ocr_scanned_pages: ocrScannedPages,
          lang: ocrLang,
        });

        lastDetail = await getOcrJob(result.id);
      }

      if (lastDetail) {
        setSelectedJob(lastDetail);
      }

      setManualUploadFiles([]);
      await loadOcrData();

      alert(`수동 파일 ${uploadedRows.length}건 OCR 등록 완료`);
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleCandidateKeyDown(e) {
    if (!filteredFiles.length) return;

    const currentIndex = Math.max(
      filteredFiles.findIndex(
        (file) => normalizePath(file.filepath) === normalizePath(selectedFile?.filepath)
      ),
      0
    );

    if (e.key === "ArrowDown") {
      e.preventDefault();
      const nextIndex = Math.min(currentIndex + 1, filteredFiles.length - 1);
      setSelectedPath(filteredFiles[nextIndex].filepath);
    }

    if (e.key === "ArrowUp") {
      e.preventDefault();
      const nextIndex = Math.max(currentIndex - 1, 0);
      setSelectedPath(filteredFiles[nextIndex].filepath);
    }
  }

  const jobsForView = useMemo(() => {
    const sorted = [...jobs].sort((a, b) => Number(b.id || 0) - Number(a.id || 0));
    const map = new Map();

    for (const job of sorted) {
      const meta = getJobMeta(job);

      const key = meta.requestId && meta.requestId !== "-"
        ? `${meta.requestId}__${job.filename || ""}`
        : normalizePath(job.source_path || job.filename || job.id);

      if (!map.has(key)) {
        map.set(key, job);
      }
    }

    return Array.from(map.values());
  }, [jobs, ocrTargets, mailTargets, mailLogs]);

  function handleJobKeyDown(e) {
    if (!jobsForView.length) return;

    const currentIndex = Math.max(
      jobsForView.findIndex((job) => job.id === selectedJob?.id),
      0
    );

    if (e.key === "ArrowDown") {
      e.preventDefault();
      const nextIndex = Math.min(currentIndex + 1, jobsForView.length - 1);
      handleSelectJob(jobsForView[nextIndex].id);
    }

    if (e.key === "ArrowUp") {
      e.preventDefault();
      const nextIndex = Math.max(currentIndex - 1, 0);
      handleSelectJob(jobsForView[nextIndex].id);
    }
  }

  const doneCount = jobsForView.filter((job) => job.status === "DONE").length;
  const noTextCount = jobsForView.filter((job) => job.status === "NO_TEXT").length;
  const errorCount = jobsForView.filter((job) => job.status === "ERROR").length;
  const selectedTemplateInfo = getTemplateClassificationSummary(selectedJob);
  const pendingTargetCount = ocrTargets.filter((row) =>
    ["pending", "error", "not_run", ""].includes(String(row.ocr_status || "pending"))
  ).length;

  return (
    <>
      <PageHeader
        eyebrow="OCR / AI"
        title="인증서 판독"
        desc="수신메일 OCR 대상과 OCR 작업 이력을 연결해 인증기관, 유효기간 후보, LHLN 확인 필요 여부를 검토합니다."
        onBack={() => setActive("home")}
      />

      <StatLine
        items={[
          { label: "OCR 대상", value: ocrTargets.length },
          { label: "대기/오류", value: pendingTargetCount },
          { label: "OCR 완료", value: doneCount },
          { label: "오류", value: errorCount },
        ]}
      />
      <section className="ocr-manual-upload-mini">
        <div className="ocr-manual-upload-head">
          <div>
            <span>MANUAL ADD</span>
            <strong>수동 파일 추가</strong>
          </div>

          <div className="ocr-manual-upload-actions">
            <select value={ocrLang} onChange={(e) => setOcrLang(e.target.value)}>
              <option value="eng">eng</option>
              <option value="kor+eng">kor+eng</option>
            </select>

            <label className="check-pill">
              <input
                type="checkbox"
                checked={ocrScannedPages}
                onChange={(e) => setOcrScannedPages(e.target.checked)}
              />
              <span>스캔 PDF OCR 시도</span>
            </label>
          </div>
        </div>

        <div
          className={manualDragActive ? "ocr-manual-dropzone active" : "ocr-manual-dropzone"}
          onDragOver={(e) => {
            e.preventDefault();
            setManualDragActive(true);
          }}
          onDragLeave={() => setManualDragActive(false)}
          onDrop={(e) => {
            e.preventDefault();
            setManualDragActive(false);
            handleManualFilePick(e.dataTransfer.files);
          }}
          onClick={() => manualUploadInputRef.current?.click()}
        >
          <input
            ref={manualUploadInputRef}
            type="file"
            multiple
            accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp"
            onChange={(e) => handleManualFilePick(e.target.files)}
            hidden
          />

          <strong>파일 드래그 또는 클릭</strong>
          <span>PDF / 이미지 인증서를 수동으로 추가합니다.</span>
        </div>

        {manualUploadFiles.length > 0 ? (
          <div className="ocr-manual-file-strip">
            {manualUploadFiles.map((file, idx) => (
              <button
                key={`${file.name}_${file.size}_${file.lastModified}`}
                type="button"
                onClick={() => handleRemoveManualFile(idx)}
                title="클릭하면 목록에서 제거"
              >
                <strong>{file.name}</strong>
                <span>{formatBytes(file.size)}</span>
              </button>
            ))}
          </div>
        ) : null}

        <div className="ocr-manual-bottom">
          <span>선택 {manualUploadFiles.length}건</span>

          <button
            type="button"
            className="primary-button"
            onClick={handleUploadManualOcrFiles}
            disabled={loading || manualUploadFiles.length === 0}
          >
            {loading ? "처리 중..." : "수동 파일 OCR 등록"}
          </button>
        </div>
      </section>
      

      <section className="ocr-history-wide-surface ocr-history-main-panel">
        <div className="ocr-history-head compact single-line">
          <div className="ocr-history-title-inline">
            <div className="surface-title">OCR 작업 이력</div>
            <p>수신메일 첨부파일 및 수동 등록 파일의 OCR 결과를 확인합니다.</p>
          </div>
        </div>

        <div className="ocr-history-toolbar one-line">
          <input
            value={ocrHistoryKeyword}
            onChange={(e) => setOcrHistoryKeyword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                loadOcrData({ keyword: ocrHistoryKeyword });
              }
            }}
            placeholder="업체명 / 원료명 / 파일명 / 인증번호 검색"
          />

          <select
            value={ocrHistoryOrgFilter}
            onChange={(e) => {
              const value = e.target.value;
              setOcrHistoryOrgFilter(value);
              loadOcrData({ org: value });
            }}
          >
            <option value="">전체 기관</option>
            <option value="BPJPH">BPJPH</option>
            <option value="MUI">MUI</option>
            <option value="IFANCA">IFANCA</option>
            <option value="HQC">HQC</option>
            <option value="ISA">ISA</option>
            <option value="LLS-ISA">LLS-ISA</option>
            <option value="JAKIM">JAKIM</option>
            <option value="MUIS">MUIS</option>
            <option value="HCE">HCE</option>
            <option value="HFCE">HFCE</option>
            <option value="HFQ">HFQ</option>
            <option value="CICOT">CICOT</option>
            <option value="HALAL CONTROL">HALAL CONTROL</option>
          </select>

          <select
            value={ocrHistoryStatusFilter}
            onChange={(e) => {
              const value = e.target.value;
              setOcrHistoryStatusFilter(value);
              loadOcrData({ status: value });
            }}
          >
            <option value="">전체 상태</option>
            <option value="DONE">DONE</option>
            <option value="NO_TEXT">NO_TEXT</option>
            <option value="ERROR">ERROR</option>
            <option value="SCANNED_NEED_OCR">스캔본</option>
            <option value="TESSERACT_ERROR">Tesseract 오류</option>
          </select>

          <button
            type="button"
            className="ghost-action"
            onClick={() => loadOcrData({ keyword: ocrHistoryKeyword })}
            disabled={loading}
          >
            검색
          </button>

          <button
            type="button"
            className="ghost-action"
            onClick={() => loadOcrData()}
            disabled={loading}
          >
            새로고침
          </button>

          <button
            type="button"
            className="ghost-action"
            onClick={handleSelectAllOcrJobs}
            disabled={loading || jobsForView.length === 0}
          >
            전체선택
          </button>

          <button
            type="button"
            className="ghost-action"
            onClick={handleClearOcrJobChecks}
            disabled={loading || checkedOcrJobIds.length === 0}
          >
            전체해제
          </button>

          <button
            type="button"
            className="ghost-action danger"
            onClick={handleDeleteSelectedOcrJobs}
            disabled={loading || checkedOcrJobIds.length === 0}
          >
            선택삭제
          </button>

          <button
            type="button"
            className="primary-button"
            onClick={handleRerunSelectedOcrJobs}
            disabled={loading || checkedOcrJobIds.length === 0}
          >
            선택 재판독
          </button>
        </div>

        <div className="ocr-history-table-scroll">
          <div className="ocr-history-table-head with-check compact">
            <div>선택</div>
            <div>업체명</div>
            <div>제품/원료명</div>
            <div>이미지기관</div>
            <div>최종기관</div>
            <div>분류상태</div>
            <div>유효기간후보</div>
            <div>OCR상태</div>
            <div>파일명</div>
            <div>처리일</div>
          </div>

          <div
            className="ocr-history-table-body compact"
            ref={jobListRef}
            tabIndex={0}
            onKeyDown={handleJobKeyDown}
          >
            {jobsForView.length === 0 ? (
              <div className="mail-log-empty">
                OCR 작업 이력이 없습니다.
              </div>
            ) : (
              jobsForView.map((job) => {
                const meta = getJobMeta(job);
                const rule =
                  job.certificate_rule ||
                  job.result?.certificate_rule ||
                  job.result?.field_guess?.certificate_rule ||
                  {};

                const historyOrg = rule.cert_org || meta.org || "-";

                const historyExpiry =
                  rule.cert_org === "BPJPH"
                    ? "유지확인"
                    : rule.expiry_date || meta.expiry || "-";

                const historyMaterial =
                  rule.best_product_match?.product?.name ||
                  meta.material ||
                  "-";

                const templateSummary = getTemplateClassificationSummary(job);

                const effectiveStatus = getEffectiveOcrStatus(job);

                const statusClass =
                  effectiveStatus === "DONE"
                    ? "mini-badge ok"
                    : effectiveStatus === "NO_TEXT" ||
                        effectiveStatus === "SCANNED_NEED_OCR" ||
                        effectiveStatus === "EXCLUDED"
                      ? "mini-badge warn"
                      : "mini-badge fail";

                return (
                  <button
                    key={job.id}
                    type="button"
                    className={
                      selectedJob?.id === job.id
                        ? "ocr-history-row with-check compact active"
                        : "ocr-history-row with-check compact"
                    }
                    onClick={() => handleSelectJob(job.id)}
                  >
                    <div
                      className="ocr-row-check"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        checked={checkedOcrJobIds.includes(Number(job.id))}
                        onChange={() => toggleOcrJobChecked(job.id)}
                      />
                    </div>

                    <EllipsisText
                      value={meta.supplier || "-"}
                      className="ocr-history-cell-center"
                    />

                    <EllipsisText
                      value={historyMaterial}
                      className="is-left history-material-name"
                    />

                    <EllipsisText
                      value={templateSummary.predictedOrg || historyOrg}
                      className="ocr-history-cell-center"
                    />

                    <EllipsisText
                      value={templateSummary.finalOrg || historyOrg}
                      className="ocr-history-cell-center"
                    />

                    <div title={templateSummary.title || ""}>
                      <span className={templateSummary.isExcluded ? "mini-badge warn" : "mini-badge ok"}>
                        {templateSummary.label}
                      </span>
                    </div>

                    <EllipsisText
                      value={historyExpiry}
                      className="ocr-history-cell-center"
                    />

                    <div title={effectiveStatus || ""}>
                      <span className={statusClass}>
                        {effectiveStatus}
                      </span>
                    </div>

                    <EllipsisText
                      value={job.filename || "-"}
                      className="is-left history-file-name"
                    />

                    <div title={job.updated_at || ""}>
                      {formatOcrTableDate(job.updated_at)}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>
      </section>

      <section className="mail-log-preview-surface ocr-preview ocr-preview-refined">
        {selectedJob ? (
          <>
            <div className="mail-log-preview-head">
              <div>
                <div className="surface-title fixed-panel-label">OCR 결과</div>
                <div className="ocr-file-title-soft" title={selectedJob.filename}>{selectedJob.filename}</div>
              </div>

              <div className="preview-badges">
                <span className={selectedJob.status === "DONE" ? "mini-badge ok" : "mini-badge fail"}>
                  {selectedJob.status}
                </span>
              </div>
            </div>

            <div className="ocr-meta-grid-refined">
              <div className="ocr-meta-card path">
                <span>파일 경로</span>
                <strong>{selectedJob.source_path}</strong>
              </div>

              <div className="ocr-meta-card small">
                <span>확장자</span>
                <strong>{selectedJob.file_ext}</strong>
              </div>

              <div className="ocr-meta-card small">
                <span>상태</span>
                <strong>{selectedJob.status}</strong>
              </div>

              <div className="ocr-meta-card small">
                <span>오류</span>
                <strong>{selectedJob.error_message || "-"}</strong>
              </div>
            </div>

            <div className="ocr-template-classification-strip">
              <div>
                <span>이미지기관</span>
                <strong title={selectedTemplateInfo.predictedOrg || "-"}>
                  {selectedTemplateInfo.predictedOrg || "-"}
                </strong>
              </div>
              <div>
                <span>최종기관</span>
                <strong title={selectedTemplateInfo.finalOrg || "-"}>
                  {selectedTemplateInfo.finalOrg || "-"}
                </strong>
              </div>
              <div>
                <span>분류상태</span>
                <strong title={selectedTemplateInfo.title || "-"}>
                  {selectedTemplateInfo.label || "-"}
                </strong>
              </div>
              <div>
                <span>점수 / Margin</span>
                <strong>
                  {selectedTemplateInfo.scoreText || "-"} / {selectedTemplateInfo.marginText || "-"}
                </strong>
              </div>
            </div>

            <div className="ocr-compare-section">
              <div className="ocr-compare-head">
                <span>PMF / 메일 기준 정보</span>
                <strong>기존 정보</strong>
              </div>

              <div className="ocr-compare-table">
                <div className="ocr-compare-table-head">
                  <div>구분</div>
                  <div>원료/제품명</div>
                  <div>영문명</div>
                  <div>제조사</div>
                  <div>인증기관</div>
                  <div>인증번호</div>
                  <div>유효기간</div>
                  <div>제조국</div>
                  <div>인증국가</div>
                  <div>제조국/인증국</div>
                </div>

                <div className="ocr-compare-row">
                  <div>기존</div>
                  <EllipsisText value={expectedInfo.koreanName} />
                  <EllipsisText value={expectedInfo.englishName} />
                  <EllipsisText value={expectedInfo.maker} />
                  <EllipsisText value={expectedInfo.org} />
                  <EllipsisText value={expectedInfo.certNo} />
                  <EllipsisText value={expectedInfo.expiry} />
                  <EllipsisText value={expectedInfo.country} />
                  <div>-</div>
                  <div>-</div>
                </div>

                <div className="ocr-compare-row read">
                  <div>OCR</div>
                  <EllipsisText value={ocrReadInfo.koreanName} />
                  <EllipsisText value={ocrReadInfo.englishName} />
                  <EllipsisText value={ocrReadInfo.maker} />
                  <EllipsisText value={ocrReadInfo.org} />
                  <EllipsisText value={ocrReadInfo.certNo} />
                  <EllipsisText value={ocrReadInfo.expiry} />
                  <EllipsisText value={ocrReadInfo.country} />
                  <EllipsisText value={ocrReadInfo.certCountry} />
                  <EllipsisText value={ocrReadInfo.countryOrgMatch} />
                </div>
              </div>
            </div>

            <div className="ocr-decision-grid compact-ratio">
              <div className="ocr-decision-card compact">
                <span>기관 후보</span>
                <strong title={orgCandidates.join(", ") || "-"}>
                  {orgCandidates.join(", ") || "-"}
                </strong>
              </div>

              <div className="ocr-decision-card compact">
                <span>유효기간 후보</span>
                <strong title={bestExpiry || "-"}>
                  {bestExpiry || "-"}
                </strong>
              </div>

              <div className={`ocr-decision-card ocr-lhln-mini-card wide ${lhlnDecision.status}`}>
                <div>
                  <span>인증국가</span>
                  <strong
                    title={
                      lhlnDecision.match?.negara ||
                      lhlnDecision.match?.country ||
                      certificateRule?.cert_country ||
                      ocrReadInfo.certCountry ||
                      "-"
                    }
                  >
                    {lhlnDecision.match?.negara ||
                      lhlnDecision.match?.country ||
                      certificateRule?.cert_country ||
                      ocrReadInfo.certCountry ||
                      "-"}
                  </strong>
                </div>

                <div>
                  <span>기관명</span>
                  <strong
                    title={
                      lhlnDecision.match?.nama_lhln ||
                      lhlnDecision.match?.org_name ||
                      lhlnDecision.match?.name ||
                      lhlnDecision.match?.agency ||
                      certificateRule?.cert_org ||
                      orgCandidates[0] ||
                      "-"
                    }
                  >
                    {lhlnDecision.match?.nama_lhln ||
                      lhlnDecision.match?.org_name ||
                      lhlnDecision.match?.name ||
                      lhlnDecision.match?.agency ||
                      certificateRule?.cert_org ||
                      orgCandidates[0] ||
                      "-"}
                  </strong>
                </div>
              </div>
            </div>
            
            {certificateRule ? (
              <div className="ocr-rule-card">
                <div className="ocr-rule-head">
                  <div>
                    <span>CERTIFICATE RULE</span>
                    <strong>규칙 기반 판독결과</strong>
                  </div>

                  <em className={`ocr-rule-status ${certificateRule.parse_status || "UNKNOWN"}`}>
                    {certificateRule.parse_status || "UNKNOWN"}
                  </em>
                </div>

                <div className="ocr-rule-compact">
                  <div className="ocr-rule-line">
                    <span className="rule-field-label hl-org">인증기관</span>
                    <strong>{certificateRule.cert_org || "-"}</strong>
                  </div>

                  <div className="ocr-rule-line">
                    <span className="rule-field-label hl-cert-country">인증국가</span>
                    <strong>{certificateRule.cert_country || "-"}</strong>
                  </div>

                  <div className="ocr-rule-line">
                    <span className="rule-field-label hl-mfg-country">제조국</span>
                    <strong>{certificateRule.manufacturing_country || "-"}</strong>
                  </div>

                  <div className="ocr-rule-line">
                    <span className="rule-field-label hl-cert">인증번호</span>
                    <strong>{certificateRule.cert_no || "-"}</strong>
                  </div>

                  <div className="ocr-rule-line">
                    <span className="rule-field-label hl-expiry">유효기간</span>
                    <strong>
                      {certificateRule.cert_org === "BPJPH"
                        ? "유지확인 대상"
                        : certificateRule.expiry_date || "-"}
                    </strong>
                  </div>

                  <div className="ocr-rule-line wide">
                    <span className="rule-field-label hl-maker">제조사</span>
                    <strong>{certificateRule.manufacturer || "-"}</strong>
                  </div>

                  <div className="ocr-rule-line wide">
                    <span className="rule-field-label hl-product">제품명</span>
                    <strong>
                      {certificateRule.best_product_match?.product?.name ||
                        certificateRule.product_name ||
                        ocrReadInfo.englishName ||
                        "-"}
                    </strong>
                  </div>
                </div>
              </div>
            ) : null}      


            <div className="ocr-highlight-legend">
              <span className="hl-product">제품명</span>
              <span className="hl-maker">제조사</span>
              <span className="hl-org">인증기관</span>
              <span className="hl-cert">인증번호</span>
              <span className="hl-expiry">유효기간</span>
              <span className="hl-mfg-country">제조국</span>
              <span className="hl-cert-country">인증국가</span>
            </div>

            <div className="ocr-text-box refined highlighted">
              <HighlightedOcrText
                text={selectedJob.raw_text || selectedJob.raw_text_preview || ""}
                rule={certificateRule}
                expected={expectedInfo}
                readInfo={ocrReadInfo}
              />
            </div>
          </>
        ) : (
          <div className="mail-log-empty">
            OCR 작업을 실행하거나 이력을 선택하면 결과가 표시됩니다.
          </div>
        )}
      </section>
    </>
  );
}

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

function buildRuleValidationRow(item) {
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

function filterRuleValidationRows(rows, filterValue) {
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
  const API_BASE = "http://127.0.0.1:8000";

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

  function OcrTestRuleSummary({ item }) {
    const rule = getOcrTestRule(item);

    if (!rule) return null;

    return (
      <div className="ocr-test-rule-summary">
        <div className="ocr-test-rule-row">
          <span>업체명</span>
          <strong>{rule.manufacturer || "-"}</strong>
        </div>

        <div className="ocr-test-rule-row">
          <span>영문명</span>
          <strong>
            {rule.best_product_match?.product?.name ||
              rule.product_name ||
              "-"}
          </strong>
        </div>

        <div className="ocr-test-rule-row">
          <span>제조사</span>
          <strong>{rule.manufacturer || "-"}</strong>
        </div>

        <div className="ocr-test-rule-row">
          <span>인증기관</span>
          <strong>{rule.cert_org || "-"}</strong>
        </div>

        <div className="ocr-test-rule-row">
          <span>인증번호</span>
          <strong>{rule.cert_no || "-"}</strong>
        </div>

        <div className="ocr-test-rule-row">
          <span>유효기간</span>
          <strong>
            {rule.cert_org === "BPJPH"
              ? "유지확인 대상"
              : rule.expiry_date || "-"}
          </strong>
        </div>

        <div className="ocr-test-rule-row">
          <span>제조국</span>
          <strong>{rule.manufacturing_country || "-"}</strong>
        </div>

        <div className="ocr-test-rule-row">
          <span>인증국가</span>
          <strong>{rule.cert_country || "-"}</strong>
        </div>
      </div>
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

function formatOcrTableDate(value) {
  const text = String(value || "").trim();

  if (!text) return "-";

  return text
    .replace("T", " ")
    .replace(/\.\d+$/, "")
    .slice(0, 16);
}

function EllipsisText({ value, className = "" }) {
  const text = String(value || "-");

  return (
    <div className={className} title={text}>
      {text}
    </div>
  );
}

function formatFileSize(value) {
  const n = Number(value || 0);
  if (!n) return "-";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function PlaceholderPage({ setActive, eyebrow, title, desc }) {
  return (
    <>
      <PageHeader
        eyebrow={eyebrow}
        title={title}
        desc={desc}
        onBack={() => setActive("home")}
      />

      <section className="surface">
        <p className="placeholder-text">
          이 화면은 다음 단계에서 API와 연결합니다.
        </p>
      </section>
    </>
  );
}

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

function getNearestScrollableParent(element) {
  let parent = element?.parentElement;

  while (parent) {
    const style = window.getComputedStyle(parent);
    const canScrollY =
      ["auto", "scroll"].includes(style.overflowY) &&
      parent.scrollHeight > parent.clientHeight;

    if (canScrollY) return parent;

    parent = parent.parentElement;
  }

  return null;
}

function useAutoScrollActiveRows() {
  useEffect(() => {
    let rafId = null;

    function scrollActiveIntoView() {
      if (rafId) cancelAnimationFrame(rafId);

      rafId = requestAnimationFrame(() => {
        const activeElements = document.querySelectorAll(
          [
            ".active",
            ".is-selected",
            "[aria-selected='true']",
          ].join(",")
        );

        activeElements.forEach((element) => {
          const scroller = getNearestScrollableParent(element);

          if (!scroller) return;

          const elementRect = element.getBoundingClientRect();
          const scrollerRect = scroller.getBoundingClientRect();

          const isAbove = elementRect.top < scrollerRect.top;
          const isBelow = elementRect.bottom > scrollerRect.bottom;

          if (isAbove || isBelow) {
            element.scrollIntoView({
              block: "nearest",
              inline: "nearest",
            });
          }
        });
      });
    }

    const observer = new MutationObserver(scrollActiveIntoView);

    observer.observe(document.body, {
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "aria-selected"],
    });

    window.addEventListener("keydown", scrollActiveIntoView, true);

    return () => {
      observer.disconnect();
      window.removeEventListener("keydown", scrollActiveIntoView, true);

      if (rafId) cancelAnimationFrame(rafId);
    };
  }, []);
}

function CertTemplateTrainingPanel({ setActive }) {
  const API_BASE = "http://127.0.0.1:8000";
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


function OcrDataExportPage({ setActive }) {
  const [limit, setLimit] = useState(10000);
  const [includeOcrJobs, setIncludeOcrJobs] = useState(true);
  const [includeOcrTests, setIncludeOcrTests] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [lastResult, setLastResult] = useState(null);
  const [exportConfirmOpen, setExportConfirmOpen] = useState(false);

  const [failureKeyword, setFailureKeyword] = useState("");
  const [failureSummary, setFailureSummary] = useState(null);
  const [failureLoading, setFailureLoading] = useState(false);
  const [selectedFailureId, setSelectedFailureId] = useState(null);
  const [hideStaleTesseract, setHideStaleTesseract] = useState(true);
  const [latestOnlyFailureJobs, setLatestOnlyFailureJobs] = useState(true);
  const [deletingStaleTesseract, setDeletingStaleTesseract] = useState(false);

    function handleRequestDownloadExport() {
    if (!includeOcrJobs && !includeOcrTests) {
      alert("OCR 작업이력 또는 OCR 테스트 결과 중 하나는 선택해야 합니다.");
      return;
    }

    setExportConfirmOpen(true);
  }

  async function handleDownloadExport(saveLatestForAi = false) {
    if (!includeOcrJobs && !includeOcrTests) {
      alert("OCR 작업이력 또는 OCR 테스트 결과 중 하나는 선택해야 합니다.");
      return;
    }

    try {
      setExportConfirmOpen(false);
      setExporting(true);

      const result = await downloadOcrDataExport({
        limit: Number(limit) || 10000,
        includeOcrJobs,
        includeOcrTests,
        saveLatestForAi,
      });

      setLastResult(result);

      if (result.savedLatestForAi) {
        alert(
          [
            "OCR 데이터 ZIP 생성 완료",
            "",
            "AI 규칙 리뷰용 export.jsonl도 최신 파일로 저장했습니다.",
            result.latestExportPath || "backend\\data\\ocr_exports\\export.jsonl",
          ].join("\n")
        );
      }
    } catch (err) {
      alert(err.message || "OCR 데이터 Export 생성 중 오류가 발생했습니다.");
    } finally {
      setExporting(false);
    }
  } 

  async function loadFailureSummary(next = {}) {
    const keyword = next.keyword ?? failureKeyword ?? "";
    const hideStale = next.hideStaleTesseract ?? hideStaleTesseract;
    const latestOnly = next.latestOnlyFailureJobs ?? latestOnlyFailureJobs;

    try {
      setFailureLoading(true);

      const data = await getOcrFailureSummary({
        limit: 500,
        keyword,
        include_test: true,
        includeTest: true,
        hide_stale_tesseract: hideStale,
        hideStaleTesseract: hideStale,
        latest_only: latestOnly,
        latestOnly,
      });

      const rows = data.rows || [];
      setFailureSummary(data);

      setSelectedFailureId((prev) => {
        if (prev && rows.some((row) => Number(row.id) === Number(prev))) {
          return prev;
        }

        return rows[0]?.id || null;
      });
    } catch (err) {
      alert(err.message || "OCR 오류 현황을 불러오지 못했습니다.");
    } finally {
      setFailureLoading(false);
    }
  }

  async function handleDeleteStaleTesseractHistory() {
    const staleCount = Number(failureSummary?.stale_tesseract_count || 0);

    if (staleCount <= 0) {
      alert("삭제할 과거 Tesseract 오류 이력이 없습니다.");
      return;
    }

    const ok = window.confirm(
      `과거 Tesseract 오류 이력 ${staleCount}건을 삭제합니다.\n` +
      "같은 파일에 더 최신 정상 DONE job이 있는 이력만 삭제됩니다. 계속할까요?"
    );

    if (!ok) return;

    try {
      setDeletingStaleTesseract(true);

      const result = await deleteStaleTesseractHistory({
        include_test: true,
        includeTest: true,
      });

      const deletedCount =
        result?.deleted ??
        result?.deleted_count ??
        result?.count ??
        0;

      alert(`삭제 완료: ${deletedCount}건`);

      await loadFailureSummary();
    } catch (err) {
      alert(err.message || "과거 Tesseract 오류 이력 삭제 실패");
    } finally {
      setDeletingStaleTesseract(false);
    }
  }

  useEffect(() => {
    loadFailureSummary({ keyword: "" }).catch((err) => {
      console.error("OCR 실패 현황 로드 실패:", err);
    });
  }, [hideStaleTesseract, latestOnlyFailureJobs]);

  const failureRows = failureSummary?.rows || [];

  const selectedFailure =
    failureRows.find((row) => Number(row.id) === Number(selectedFailureId)) ||
    failureRows[0] ||
    null;

  const errorEtcCount =
    (failureSummary?.counts?.ERROR ?? 0) +
    (failureSummary?.counts?.PDF_RENDER_ERROR ?? 0) +
    (failureSummary?.counts?.IMAGE_READ_ERROR ?? 0);

  return (
    <>
      {exportConfirmOpen ? (
        <div className="modal-backdrop">
          <div className="confirm-dialog">
            <div className="confirm-dialog-head">
              <span>OCR DATA EXPORT</span>
              <strong>AI 규칙 리뷰용 최신 export 저장 여부</strong>
            </div>

            <p>
              ZIP 파일을 생성하면서{" "}
              <b>backend\data\ocr_exports\export.jsonl</b> 위치에도 최신
              export.jsonl을 저장할까요?
            </p>

            <div className="confirm-dialog-actions">
              <button
                type="button"
                className="primary-button"
                onClick={() => handleDownloadExport(true)}
                disabled={exporting}
              >
                예, 저장하고 ZIP 생성
              </button>

              <button
                type="button"
                className="ghost-action"
                onClick={() => handleDownloadExport(false)}
                disabled={exporting}
              >
                아니오, ZIP만 생성
              </button>

              <button
                type="button"
                className="danger-action"
                onClick={() => setExportConfirmOpen(false)}
                disabled={exporting}
              >
                취소
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <PageHeader
        eyebrow="ADMIN / DATA EXPORT"
        title="OCR 데이터 추출"
        desc="OCR 작업이력과 OCR 테스트 결과를 규칙 검토용 export.jsonl, summary.csv, combined_ocr_text.md로 묶어 ZIP 파일로 생성합니다."
        onBack={() => setActive("home")}
      />

      <StatLine
        items={[
          { label: "출력 형식", value: "ZIP" },
          { label: "JSONL", value: "1" },
          { label: "CSV", value: "1" },
          { label: "TEXT", value: "1" },
        ]}
      />

      <section className="ocr-export-layout">
        <div className="detail-surface ocr-export-card">
          <div className="detail-top">
            <div>
              <div className="surface-title">OCR Rule Review Export</div>
              <h2>ocr_data_export ZIP 생성</h2>
            </div>

            <span className="badge ok">
              {lastResult?.recordCount ? `${lastResult.recordCount}건` : "READY"}
            </span>
          </div>

          <div className="ocr-export-desc">
            <strong>생성 파일</strong>
            <p>
              ZIP 내부에는 export.jsonl, summary.csv, combined_ocr_text.md가 포함됩니다.
              이 파일을 기준으로 OCR 원문, 인증기관 판정, 규칙 기반 추출값,
              이미지 양식 판정 결과를 다시 검토할 수 있습니다.
            </p>
          </div>

          <div className="form-grid ocr-export-form">
            <label>
              <span>최대 추출 건수</span>
              <input
                type="number"
                min="1"
                max="50000"
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
              />
            </label>

            <label className="cert-template-check-row">
              <input
                type="checkbox"
                checked={includeOcrJobs}
                onChange={(e) => setIncludeOcrJobs(e.target.checked)}
              />
              <span>OCR 작업이력 포함</span>
            </label>

            <label className="cert-template-check-row">
              <input
                type="checkbox"
                checked={includeOcrTests}
                onChange={(e) => setIncludeOcrTests(e.target.checked)}
              />
              <span>OCR 테스트 결과 포함</span>
            </label>
          </div>

          <div className="ocr-export-file-list">
            <div>
              <span>export.jsonl</span>
              <strong>OCR 1건 = JSON 1줄. raw_text, certificate_rule, image_classification 포함</strong>
            </div>
            <div>
              <span>summary.csv</span>
              <strong>엑셀 검토용 요약. 기관, 인증번호, 유효기간, 제조사, 오류 상태 포함</strong>
            </div>
            <div>
              <span>combined_ocr_text.md</span>
              <strong>OCR 원문 통합 문서. 규칙 개선 검토용 본문 확인 파일</strong>
            </div>
          </div>

          <div className="toolbar right">
            <button
              className="primary-button"
              onClick={handleRequestDownloadExport}
              disabled={exporting}
            >
              {exporting ? "ZIP 생성 중..." : "OCR 데이터 ZIP 생성"}
            </button>
          </div>

          {lastResult ? (
            <div className="ocr-export-result">
              <span>마지막 생성 결과</span>
              <strong>{lastResult.filename}</strong>
              <p>
                export_version: {lastResult.exportVersion || "-"} / record_count:{" "}
                {lastResult.recordCount || "-"}
              </p>

              {lastResult.savedLatestForAi ? (
                <p>
                  AI 규칙 리뷰용 저장:{" "}
                  {lastResult.latestExportPath || "backend\\data\\ocr_exports\\export.jsonl"}
                </p>
              ) : (
                <p>AI 규칙 리뷰용 최신 export.jsonl 저장 안 함</p>
              )}
            </div>
          ) : null}
        </div>

        <div className="detail-surface ocr-export-card">
          <div className="detail-top">
            <div>
              <div className="surface-title">Export 범위</div>
              <h2>포함되는 OCR 데이터</h2>
            </div>
          </div>

          <div className="ocr-export-scope-list">
            <div>
              <span>OCR 작업이력</span>
              <strong>인증서 판독 메뉴에서 실행한 OCR job 전체</strong>
            </div>
            <div>
              <span>OCR 테스트 결과</span>
              <strong>OCR 테스트 메뉴의 업로드 파일, 상태, OCR job 연결값</strong>
            </div>
            <div>
              <span>수신메일 파일</span>
              <strong>mail_downloads / received_certs 경로 기반 파일은 MAIL_RECEIVED_FILE로 분류</strong>
            </div>
            <div>
              <span>수동 업로드 파일</span>
              <strong>ocr_manual_uploads 경로 기반 파일은 MANUAL_UPLOAD_FILE로 분류</strong>
            </div>
            <div>
              <span>Tesseract / NO_TEXT</span>
              <strong>status와 error_message 그대로 포함</strong>
            </div>
            <div>
              <span>양식학습 판정</span>
              <strong>image_classification의 predicted_org, final_org, score, top_candidates 포함</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="ocr-failure-monitor">
        <div className="detail-surface ocr-failure-card">
          <div className="detail-top">
            <div>
              <div className="surface-title">OCR Failure Monitor</div>
              <h2>OCR 오류 모니터링</h2>
            </div>

            <span className="badge warn">
              현재 {failureSummary?.active_failure_count ?? failureSummary?.failure_count ?? "-"}건
            </span>
          </div>

          <div className="ocr-failure-stat-grid">
            <div>
              <span>TESSERACT</span>
              <strong>{failureSummary?.counts?.TESSERACT_ERROR ?? 0}</strong>
            </div>
            <div>
              <span>SCANNED</span>
              <strong>{failureSummary?.counts?.SCANNED_NEED_OCR ?? 0}</strong>
            </div>
            <div>
              <span>NO_TEXT</span>
              <strong>{failureSummary?.counts?.NO_TEXT ?? 0}</strong>
            </div>
            <div>
              <span>ERROR</span>
              <strong>{errorEtcCount}</strong>
            </div>
            <div>
              <span>STALE TESSERACT</span>
              <strong>{failureSummary?.stale_tesseract_count ?? 0}</strong>
            </div>
          </div>

          <div className="ocr-failure-toolbar">
            <input
              value={failureKeyword}
              onChange={(e) => setFailureKeyword(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  loadFailureSummary({ keyword: failureKeyword });
                }
              }}
              placeholder="파일명 / 경로 / 오류 메시지 검색"
            />

            <button
              type="button"
              className="ghost-action"
              onClick={() => loadFailureSummary({ keyword: failureKeyword })}
              disabled={failureLoading}
            >
              {failureLoading ? "조회 중..." : "새로고침"}
            </button>

            <button
              type="button"
              className={hideStaleTesseract ? "ghost-action active" : "ghost-action"}
              onClick={() => setHideStaleTesseract((prev) => !prev)}
              disabled={failureLoading}
              title="같은 파일에 더 최신 정상 DONE job이 있으면 과거 Tesseract 오류 이력을 목록에서 제외합니다."
            >
              {hideStaleTesseract ? "과거 오류이력 숨김" : "과거 오류이력 표시"}
            </button>

            <button
              type="button"
              className={latestOnlyFailureJobs ? "ghost-action active" : "ghost-action"}
              onClick={() => setLatestOnlyFailureJobs((prev) => !prev)}
              disabled={failureLoading}
              title="source_path 또는 filename 기준으로 최신 OCR job만 목록에 표시합니다."
            >
              {latestOnlyFailureJobs ? "최신 Job만 보기" : "전체 Job이력 보기"}
            </button>

            <button
              type="button"
              className="ghost-action danger"
              onClick={handleDeleteStaleTesseractHistory}
              disabled={
                failureLoading ||
                deletingStaleTesseract ||
                Number(failureSummary?.stale_tesseract_count || 0) <= 0
              }
              title="같은 파일에 더 최신 정상 DONE job이 있는 과거 Tesseract 오류 이력만 삭제합니다."
            >
              {deletingStaleTesseract
                ? "삭제 중..."
                : `과거 오류이력 삭제 ${failureSummary?.stale_tesseract_count || 0}건`}
            </button>
          </div>

          <div className="ocr-failure-option-note">
            <span>
              {hideStaleTesseract
                ? "과거 Tesseract 오류 이력은 목록에서 숨겨져 있습니다."
                : "과거 Tesseract 오류 이력까지 목록에 표시합니다."}
            </span>
            <span>
              {latestOnlyFailureJobs
                ? "동일 파일은 최신 Job 기준으로만 표시합니다."
                : "동일 파일의 과거 Job 이력까지 표시합니다."}
            </span>
          </div>

          <div className="ocr-failure-layout">
            <div className="ocr-failure-list">
              {failureRows.length === 0 ? (
                <div className="mail-log-empty">
                  OCR 오류 대상이 없습니다.
                </div>
              ) : (
                failureRows.map((row) => (
                  <button
                    type="button"
                    key={row.id}
                    className={
                      Number(selectedFailureId) === Number(row.id)
                        ? "ocr-failure-row active"
                        : "ocr-failure-row"
                    }
                    onClick={() => setSelectedFailureId(row.id)}
                  >
                    <span className={`ocr-failure-status ${row.failure_status}`}>
                      {row.failure_status}
                    </span>

                    <strong>{row.filename || "-"}</strong>

                    <em>
                      Job {row.id} · {row.text_length || 0} chars
                      {row.is_stale_tesseract ? " · stale" : ""}
                    </em>
                  </button>
                ))
              )}
            </div>

            <div className="ocr-failure-detail">
              {!selectedFailure ? (
                <div className="mail-log-empty">
                  선택된 오류 파일이 없습니다.
                </div>
              ) : (
                <>
                  <div className="info-grid">
                    <div>
                      <span>상태</span>
                      <strong>{selectedFailure.failure_status}</strong>
                    </div>
                    <div>
                      <span>파일명</span>
                      <strong>{selectedFailure.filename || "-"}</strong>
                    </div>
                    <div>
                      <span>경로</span>
                      <strong>{selectedFailure.source_path || "-"}</strong>
                    </div>
                    <div>
                      <span>이미지 판정</span>
                      <strong>
                        {selectedFailure.image_final_org || "-"} / {selectedFailure.image_decision || "-"}
                      </strong>
                    </div>
                    <div>
                      <span>규칙 판정</span>
                      <strong>
                        {selectedFailure.cert_org || "-"} / {selectedFailure.parse_status || "-"}
                      </strong>
                    </div>
                    <div>
                      <span>과거 오류 이력</span>
                      <strong>{selectedFailure.is_stale_tesseract ? "YES" : "NO"}</strong>
                    </div>
                    <div>
                      <span>Job 당시 Tesseract</span>
                      <strong>{selectedFailure.tesseract_available ? "YES" : "NO"}</strong>
                    </div>
                    <div>
                      <span>현재 Tesseract</span>
                      <strong>{selectedFailure.current_tesseract_available ? "YES" : "NO"}</strong>
                    </div>
                  </div>

                  {selectedFailure.current_tesseract_info ? (
                    <div className="ocr-export-result">
                      <span>현재 Tesseract Runtime</span>
                      <strong>{selectedFailure.current_tesseract_info.cmd || "-"}</strong>
                      <p>
                        version: {selectedFailure.current_tesseract_info.version || "-"} /
                        tessdata: {selectedFailure.current_tesseract_info.tessdata_prefix || "-"}
                      </p>
                    </div>
                  ) : null}

                  {selectedFailure.error_message ? (
                    <div className="error-box">
                      {selectedFailure.error_message}
                    </div>
                  ) : null}

                  <div className="ocr-text-box refined">
                    {selectedFailure.raw_text_preview || "OCR 원문 preview가 없습니다."}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </section>

    </>
  );
}

function formatAiRate(value) {
  const num = Number(value || 0);

  if (!Number.isFinite(num)) {
    return "0.0%";
  }

  return `${num.toFixed(1)}%`;
}

function getDeltaClass(value) {
  const num = Number(value || 0);

  if (num > 0) return "positive";
  if (num < 0) return "negative";
  return "neutral";
}

function getReportSummary(report, candidate) {
  return report?.summary || candidate?.validation_summary || {};
}

function AiRuleRecognitionChart({ report }) {
  const summary = report?.summary || {};
  const orgStatsRaw = report?.org_stats || [];

  if (!report) {
    return null;
  }

  const orgStats = orgStatsRaw.length > 0
    ? orgStatsRaw.slice(0, 10)
    : [
        {
          cert_org: "전체",
          total_records: summary.total_records || 0,
          before_rate: summary.before_recognition_rate || 0,
          after_rate: summary.after_recognition_rate || 0,
          delta_rate: summary.delta_recognition_rate || 0,
          improved_count: summary.improved_count || 0,
          regression_count: summary.regression_count || 0,
        },
      ];

  return (
    <section className="ai-rule-recognition-panel vertical">
      <div className="ai-rule-section-head compact">
        <div>
          <span>RECOGNITION</span>
          <strong>기관별 Before / After</strong>
          <p>정답률이 아니라 필수 필드 충족률 기준입니다. 막대는 Before와 After를 나란히 표시합니다.</p>
        </div>
      </div>

      <div className="ai-rule-vertical-chart">
        <div className="ai-rule-vertical-axis">
          <span>100%</span>
          <span>50%</span>
          <span>0%</span>
        </div>

        <div className="ai-rule-vertical-bars">
          {orgStats.map((row) => {
            const before = Math.max(0, Math.min(100, Number(row.before_rate || 0)));
            const after = Math.max(0, Math.min(100, Number(row.after_rate || 0)));

            return (
              <div className="ai-rule-vertical-item" key={`vertical-${row.cert_org}`}>
                <div className="ai-rule-vertical-barbox">
                  <div
                    className="bar before"
                    style={{ height: `${Math.max(2, before)}%` }}
                    title={`Before ${formatAiRate(before)}`}
                  />
                  <div
                    className="bar after"
                    style={{ height: `${Math.max(2, after)}%` }}
                    title={`After ${formatAiRate(after)}`}
                  />
                </div>

                <strong title={row.cert_org || "UNKNOWN"}>{row.cert_org || "UNKNOWN"}</strong>
                <span className={getDeltaClass(row.delta_rate)}>
                  {Number(row.delta_rate || 0) > 0 ? "+" : ""}
                  {formatAiRate(row.delta_rate)}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="ai-rule-chart-legend">
        <span><i className="before" />Before</span>
        <span><i className="after" />After</span>
      </div>
    </section>
  );
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

export default function App() {
  useAutoScrollActiveRows();
  const [active, setActive] = useState("home");
  const [health, setHealth] = useState(null);
  const [pmfSummary, setPmfSummary] = useState(null);
  const [emailReview, setEmailReview] = useState(null);
  const [loading, setLoading] = useState(true);

  async function reloadAll() {
    const [healthData, pmfData, emailData] = await Promise.all([
      getHealth(),
      getPmfSummary(),
      getSupplierEmailReview(),
    ]);

    setHealth(healthData);
    setPmfSummary(pmfData);
    setEmailReview(emailData);
  }

  useEffect(() => {
    async function init() {
      try {
        setLoading(true);
        await reloadAll();
      } catch (err) {
        alert(err.message);
      } finally {
        setLoading(false);
      }
    }

    init();
  }, []);

  return (
    <AppErrorBoundary>
      <Shell active={active} setActive={setActive} health={health}>
        {loading ? (
          <div className="loading">데이터를 불러오는 중...</div>
        ) : (
          <>
            {active === "home" && (
              <HomePage
                setActive={setActive}
                health={health}
                pmfSummary={pmfSummary}
                emailReview={emailReview}
              />
            )}

            {active === "pmf" && (
              <PmfPage
                setActive={setActive}
                pmfSummary={pmfSummary}
                reloadAll={reloadAll}
              />
            )}

            {active === "mail" && (
              <MailAddressPage
                setActive={setActive}
                emailReview={emailReview}
                reloadAll={reloadAll}
              />
            )}

            {active === "send" && (
              <SendPage setActive={setActive} />
            )}

            {active === "logs" && (
              <MailLogsPage setActive={setActive} />
            )}

            {active === "lhln" && (
              <LhlnPage setActive={setActive} />
            )}

            {active === "ocr" && (
              <OcrPage setActive={setActive} />
            )}

            {active === "ocr_test" && (
              <OcrTestPage setActive={setActive} />
            )}

            {active === "admin" && (
              <CertTemplateTrainingPanel setActive={setActive} />
            )}

            {active === "ocr_data_export" && (
              <OcrDataExportPage setActive={setActive} />
            )}

            {active === "ai_rule_review" && (
              <AiRuleReviewPage setActive={setActive} />
            )}

            {active === "receive" && (
              <ReceiveMailPage setActive={setActive} />
            )}
          </>
        )}
      </Shell>
    </AppErrorBoundary>
  );
}


