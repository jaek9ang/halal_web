import { useEffect, useMemo, useState } from "react";
import {
  saveSupplierEmailOverride,
} from "../api";
import PageHeader from "../components/PageHeader";
import StatLine from "../components/StatLine";

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

export default MailAddressPage;
