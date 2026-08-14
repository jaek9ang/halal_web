import { useEffect, useState } from "react";
import {
  deleteStaleTesseractHistory,
  downloadOcrDataExport,
  getOcrFailureSummary,
} from "../api";
import PageHeader from "../components/PageHeader";
import StatLine from "../components/StatLine";

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

export default OcrDataExportPage;
