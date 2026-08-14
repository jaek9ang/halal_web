import { useEffect, useMemo, useRef, useState } from "react";
import {
  getMailLogs,
  hideMailLogs,
} from "../api";
import PageHeader from "../components/PageHeader";
import StatLine from "../components/StatLine";

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

export default MailLogsPage;
