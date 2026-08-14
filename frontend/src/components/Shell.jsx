import { useEffect, useState } from "react";

const MAIL_MENU_ITEMS = [
  { key: "mail", label: "메일주소 정리", icon: "✉" },
  { key: "send", label: "발송관리", icon: "↗" },
  { key: "logs", label: "발송로그", icon: "☰" },
  { key: "receive", label: "수신메일", icon: "↓" },
];

const REF_MENU_ITEMS = [
  { key: "lhln", label: "BPJPH / LHLN", icon: "◎" },
  { key: "ocr", label: "인증서 판독", icon: "◌" },
  { key: "filing", label: "인증서 자동분류", icon: "⇢" },
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
    ref: ["lhln", "ocr", "filing", "ocr_test"].includes(active),
    admin: ["admin", "ocr_data_export", "ai_rule_review"].includes(active),
  });

  useEffect(() => {
    if (["mail", "send", "logs", "receive"].includes(active)) {
      setOpenGroups((prev) => ({ ...prev, mail: true }));
    }

    if (["lhln", "ocr", "filing", "ocr_test"].includes(active)) {
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
  const refActive = ["lhln", "ocr", "filing", "ocr_test"].includes(active);
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

export default Shell;
