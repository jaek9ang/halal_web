import { useEffect, useRef, useState } from "react";
import {
  createLhlnPdf,
  getLhlnRecords,
  getLhlnStatus,
  syncLhln,
} from "../api";
import PageHeader from "../components/PageHeader";
import StatLine from "../components/StatLine";

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

export default LhlnPage;
