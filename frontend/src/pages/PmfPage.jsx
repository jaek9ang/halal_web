import { useEffect, useRef, useState } from "react";
import {
  getPmfMaterialDetail,
  getPmfMaterialHalalFolder,
  getPmfSummary,
  openHalalDocFolder,
  openInboxAttachmentFolder,
  searchPmfMaterials,
  syncPmf,
} from "../api";
import PageHeader from "../components/PageHeader";
import StatLine from "../components/StatLine";

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

export default PmfPage;
