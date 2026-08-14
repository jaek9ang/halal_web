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

export default AiRuleRecognitionChart;
