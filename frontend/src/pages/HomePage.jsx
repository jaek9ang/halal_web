function HomePage({ setActive, health, pmfSummary, emailReview }) {
  const cards = [
    { key: "pmf", title: "PMF / 원료", desc: "최신 PMF 원본과 원료 데이터를 확인합니다.", icon: "◧" },
    { key: "mail", title: "메일주소 정리", desc: "업체별 발송 주소를 확정합니다.", icon: "✉" },
    { key: "send", title: "발송관리", desc: "만료 통보와 유지확인 메일을 검토합니다.", icon: "↗" },
    { key: "logs", title: "발송로그", desc: "발송 이력과 본문을 확인합니다.", icon: "☰" },
    { key: "receive", title: "수신메일", desc: "회신 메일과 첨부파일을 수집합니다.", icon: "↓" },
    { key: "lhln", title: "BPJPH / LHLN", desc: "교차인정기관 자료를 관리합니다.", icon: "◎" },
    { key: "ocr", title: "인증서 판독", desc: "인증서를 OCR로 판독합니다.", icon: "◌" },
    { key: "filing", title: "인증서 자동분류", desc: "OCR 결과를 PMF와 연결해 저장 경로와 갱신값을 검토합니다.", icon: "⇢" },
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

export default HomePage;
