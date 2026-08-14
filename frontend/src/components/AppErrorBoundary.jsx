import React from "react";

class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
    };
  }

  static getDerivedStateFromError(error) {
    return {
      hasError: true,
      error,
    };
  }

  componentDidCatch(error, info) {
    console.error("[APP_RENDER_ERROR]", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="app-crash-panel">
          <strong>화면 렌더링 오류</strong>
          <p>
            OCR 실행 후 화면 구성 중 오류가 발생했습니다. 브라우저 Console의
            빨간 오류 메시지를 확인하세요.
          </p>
          <pre>{String(this.state.error?.message || this.state.error || "")}</pre>
          <button
            type="button"
            onClick={() => window.location.reload()}
          >
            새로고침
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default AppErrorBoundary;
