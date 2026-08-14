import { useEffect, useMemo, useRef, useState } from "react";
import {
  getMailTargets,
  sendMailRequests,
} from "../api";
import PageHeader from "../components/PageHeader";
import StatLine from "../components/StatLine";

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

export default SendPage;
