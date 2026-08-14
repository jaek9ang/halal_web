import { useEffect, useState } from "react";
import {
  getHealth,
  getPmfSummary,
  getSupplierEmailReview,
} from "./api";
import AppErrorBoundary from "./components/AppErrorBoundary";
import Shell from "./components/Shell";
import useAutoScrollActiveRows from "./hooks/useAutoScrollActiveRows";
import AiRuleReviewPage from "./pages/AiRuleReviewPage";
import CertTemplateTrainingPanel from "./pages/CertTemplateTrainingPage";
import HomePage from "./pages/HomePage";
import LhlnPage from "./pages/LhlnPage";
import MailAddressPage from "./pages/MailAddressPage";
import MailLogsPage from "./pages/MailLogsPage";
import OcrDataExportPage from "./pages/OcrDataExportPage";
import OcrPage from "./pages/OcrPage";
import OcrTestPage from "./pages/OcrTestPage";
import PmfPage from "./pages/PmfPage";
import ReceiveMailPage from "./pages/ReceiveMailPage";
import SendPage from "./pages/SendPage";
import FilingPage from "./pages/FilingPage";
import "./App.css";

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

            {active === "filing" && (
              <FilingPage setActive={setActive} />
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
