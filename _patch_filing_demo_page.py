from __future__ import annotations

import ast
import shutil
from datetime import datetime
from pathlib import Path


TARGET = Path(
    "backend/app/routers/"
    "certificate_filing.py"
)

IMPORT_LINE = (
    "from fastapi.responses "
    "import HTMLResponse\n"
)

IMPORT_MARKER = (
    "from pydantic import "
    "BaseModel, Field\n"
)

ROUTE_MARKER = (
    '@router.get("/status")'
)

DEMO_MARKER = (
    "HALAL_FILING_DEMO_PAGE"
)


DEMO_BLOCK = r'''
# HALAL_FILING_DEMO_PAGE
DEMO_HTML = r"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >
    <title>할랄 인증서 자동 분류</title>

    <style>
        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            min-height: 100vh;
            font-family:
                Pretendard,
                "Noto Sans KR",
                "Malgun Gothic",
                Arial,
                sans-serif;
            background: #f3f6fb;
            color: #1f2937;
        }

        button {
            font-family: inherit;
        }

        .layout {
            min-height: 100vh;
            display: grid;
            grid-template-columns: 230px 1fr;
        }

        .sidebar {
            background:
                linear-gradient(
                    180deg,
                    #10233f 0%,
                    #162f53 100%
                );
            color: white;
            padding: 28px 20px;
        }

        .logo {
            font-size: 21px;
            font-weight: 800;
            letter-spacing: -0.5px;
            margin-bottom: 34px;
        }

        .logo small {
            display: block;
            margin-top: 7px;
            color: #a9bdd8;
            font-size: 12px;
            font-weight: 500;
        }

        .nav-item {
            padding: 13px 14px;
            border-radius: 10px;
            margin-bottom: 8px;
            color: #c9d7e9;
            font-size: 14px;
        }

        .nav-item.active {
            color: white;
            background: rgba(255, 255, 255, 0.12);
            font-weight: 700;
        }

        .main {
            padding: 28px 34px 40px;
            overflow: hidden;
        }

        .topbar {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 20px;
            margin-bottom: 22px;
        }

        .title h1 {
            margin: 0;
            font-size: 26px;
            letter-spacing: -1px;
        }

        .title p {
            margin: 8px 0 0;
            color: #667085;
            font-size: 14px;
        }

        .system-status {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            justify-content: flex-end;
        }

        .status-pill {
            padding: 8px 11px;
            border-radius: 999px;
            background: #e8f7ef;
            color: #19794d;
            font-size: 12px;
            font-weight: 700;
        }

        .stats {
            display: grid;
            grid-template-columns:
                repeat(4, minmax(0, 1fr));
            gap: 14px;
            margin-bottom: 18px;
        }

        .stat-card {
            background: white;
            border: 1px solid #e4e9f1;
            border-radius: 14px;
            padding: 17px 18px;
            box-shadow:
                0 5px 16px rgba(31, 42, 68, 0.04);
        }

        .stat-label {
            color: #78859a;
            font-size: 12px;
            margin-bottom: 10px;
        }

        .stat-value {
            font-size: 24px;
            font-weight: 800;
            color: #183153;
        }

        .stat-unit {
            margin-left: 4px;
            font-size: 12px;
            color: #8a96a8;
            font-weight: 500;
        }

        .content-grid {
            display: grid;
            grid-template-columns:
                minmax(390px, 0.9fr)
                minmax(520px, 1.25fr);
            gap: 18px;
            align-items: start;
        }

        .panel {
            background: white;
            border: 1px solid #e4e9f1;
            border-radius: 16px;
            box-shadow:
                0 8px 25px rgba(31, 42, 68, 0.05);
            overflow: hidden;
        }

        .panel-header {
            padding: 18px 20px;
            border-bottom: 1px solid #e8edf4;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
        }

        .panel-header h2 {
            margin: 0;
            font-size: 17px;
            letter-spacing: -0.4px;
        }

        .panel-header p {
            margin: 5px 0 0;
            color: #7b8798;
            font-size: 12px;
        }

        .button-row {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }

        .btn {
            border: 0;
            border-radius: 9px;
            padding: 10px 13px;
            font-size: 12px;
            font-weight: 700;
            cursor: pointer;
            transition: 0.15s ease;
        }

        .btn:hover {
            transform: translateY(-1px);
        }

        .btn-primary {
            background: #1f5fbf;
            color: white;
        }

        .btn-light {
            background: #edf2f8;
            color: #38506e;
        }

        .btn-success {
            width: 100%;
            background: #16865d;
            color: white;
            padding: 13px;
            font-size: 14px;
        }

        .btn-success:disabled {
            cursor: default;
            opacity: 1;
        }

        .candidate-list {
            max-height: 590px;
            overflow: auto;
        }

        .candidate {
            padding: 16px 19px;
            border-bottom: 1px solid #edf0f5;
            cursor: pointer;
            transition: 0.15s ease;
        }

        .candidate:hover {
            background: #f7f9fc;
        }

        .candidate.selected {
            background: #edf5ff;
            border-left: 4px solid #2473d4;
            padding-left: 15px;
        }

        .candidate-title {
            font-size: 14px;
            line-height: 1.5;
            font-weight: 700;
            color: #24364d;
            word-break: break-all;
        }

        .candidate-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 7px;
            margin-top: 10px;
        }

        .mini-tag {
            padding: 5px 7px;
            border-radius: 6px;
            background: #eef2f7;
            color: #5e6d80;
            font-size: 11px;
        }

        .preview-body {
            padding: 20px;
        }

        .decision-card {
            border-radius: 14px;
            padding: 17px;
            background:
                linear-gradient(
                    135deg,
                    #e9f8f1 0%,
                    #f2fbf7 100%
                );
            border: 1px solid #bce8d4;
            margin-bottom: 16px;
        }

        .decision-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 14px;
        }

        .decision-title {
            color: #146443;
            font-size: 18px;
            font-weight: 800;
        }

        .decision-code {
            margin-top: 6px;
            color: #4f7766;
            font-size: 12px;
        }

        .success-badge {
            padding: 8px 11px;
            border-radius: 999px;
            background: #16865d;
            color: white;
            font-size: 12px;
            font-weight: 800;
            white-space: nowrap;
        }

        .info-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 11px;
            margin-bottom: 14px;
        }

        .info-box {
            border: 1px solid #e3e8ef;
            border-radius: 11px;
            padding: 13px;
            min-width: 0;
        }

        .info-box.full {
            grid-column: 1 / -1;
        }

        .info-label {
            color: #7c8999;
            font-size: 11px;
            margin-bottom: 7px;
        }

        .info-value {
            color: #24364d;
            font-size: 13px;
            font-weight: 700;
            line-height: 1.45;
            word-break: break-all;
        }

        .change-card {
            border: 1px solid #dce4ef;
            border-radius: 12px;
            overflow: hidden;
            margin-bottom: 14px;
        }

        .change-title {
            padding: 11px 14px;
            background: #f5f7fa;
            font-size: 12px;
            font-weight: 800;
            color: #40546c;
        }

        .change-row {
            display: grid;
            grid-template-columns:
                110px 1fr 26px 1fr;
            gap: 8px;
            align-items: center;
            padding: 12px 14px;
            border-top: 1px solid #edf0f4;
            font-size: 12px;
        }

        .change-label {
            color: #6b7788;
            font-weight: 700;
        }

        .before {
            color: #8a4d4d;
            word-break: break-all;
        }

        .after {
            color: #176a4a;
            font-weight: 700;
            word-break: break-all;
        }

        .arrow {
            text-align: center;
            color: #8996a8;
        }

        .warning {
            border-radius: 10px;
            padding: 11px 13px;
            background: #fff8e7;
            border: 1px solid #f1d999;
            color: #765a18;
            font-size: 12px;
            line-height: 1.5;
            margin-bottom: 10px;
        }

        .empty {
            padding: 45px 20px;
            text-align: center;
            color: #8a96a8;
            font-size: 13px;
        }

        .loading {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid #c9d3df;
            border-top-color: #2a6ecb;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            vertical-align: middle;
            margin-right: 7px;
        }

        @keyframes spin {
            to {
                transform: rotate(360deg);
            }
        }

        @media (max-width: 1150px) {
            .layout {
                grid-template-columns: 1fr;
            }

            .sidebar {
                display: none;
            }

            .content-grid {
                grid-template-columns: 1fr;
            }
        }

        @media (max-width: 760px) {
            .main {
                padding: 20px;
            }

            .stats {
                grid-template-columns: 1fr 1fr;
            }

            .info-grid {
                grid-template-columns: 1fr;
            }

            .change-row {
                grid-template-columns: 1fr;
            }

            .arrow {
                display: none;
            }
        }
    </style>
</head>

<body>
    <div class="layout">
        <aside class="sidebar">
            <div class="logo">
                HALAL FLOW
                <small>인증서 통합 관리 시스템</small>
            </div>

            <div class="nav-item">
                관리대장 불러오기
            </div>

            <div class="nav-item">
                만료·도래 대상 분류
            </div>

            <div class="nav-item">
                메일 자동 발송
            </div>

            <div class="nav-item">
                인증서 OCR 판독
            </div>

            <div class="nav-item active">
                인증서 자동 분류
            </div>
        </aside>

        <main class="main">
            <div class="topbar">
                <div class="title">
                    <h1>할랄 인증서 자동 분류</h1>
                    <p>
                        OCR 판독 결과와 PMF 관리대장을 연결하여
                        저장 위치와 갱신 내용을 자동으로 검토합니다.
                    </p>
                </div>

                <div class="system-status">
                    <div class="status-pill">
                        OCR ENGINE 연결
                    </div>
                    <div class="status-pill">
                        PMF DATA 연결
                    </div>
                    <div class="status-pill">
                        DEMO MODE
                    </div>
                </div>
            </div>

            <section class="stats">
                <div class="stat-card">
                    <div class="stat-label">
                        조회 후보
                    </div>
                    <div class="stat-value">
                        <span id="candidateCount">-</span>
                        <span class="stat-unit">건</span>
                    </div>
                </div>

                <div class="stat-card">
                    <div class="stat-label">
                        선택 OCR Job
                    </div>
                    <div class="stat-value">
                        <span id="selectedJob">498</span>
                    </div>
                </div>

                <div class="stat-card">
                    <div class="stat-label">
                        PMF 변경 가능
                    </div>
                    <div class="stat-value">
                        <span id="pmfAvailable">확인 중</span>
                    </div>
                </div>

                <div class="stat-card">
                    <div class="stat-label">
                        차단 항목
                    </div>
                    <div class="stat-value">
                        <span id="blockerCount">-</span>
                        <span class="stat-unit">건</span>
                    </div>
                </div>
            </section>

            <section class="content-grid">
                <div class="panel">
                    <div class="panel-header">
                        <div>
                            <h2>OCR 완료 후보</h2>
                            <p>
                                인증서와 PMF 원료 매칭 결과
                            </p>
                        </div>

                        <div class="button-row">
                            <button
                                class="btn btn-light"
                                onclick="loadCandidates()"
                            >
                                새로고침
                            </button>

                            <button
                                class="btn btn-primary"
                                onclick="loadRepresentativePreview()"
                            >
                                대표 갱신 건
                            </button>
                        </div>
                    </div>

                    <div
                        id="candidateList"
                        class="candidate-list"
                    >
                        <div class="empty">
                            <span class="loading"></span>
                            후보 목록 조회 중
                        </div>
                    </div>
                </div>

                <div class="panel">
                    <div class="panel-header">
                        <div>
                            <h2>자동 분류 미리보기</h2>
                            <p>
                                실제 파일 및 PMF는 변경하지 않습니다.
                            </p>
                        </div>
                    </div>

                    <div
                        id="previewBody"
                        class="preview-body"
                    >
                        <div class="empty">
                            <span class="loading"></span>
                            대표 갱신 건 분석 중
                        </div>
                    </div>
                </div>
            </section>
        </main>
    </div>

    <script>
        const API_BASE = "/certificate-filing";

        const representativeCandidate = {
            ocr_job_id: 498,
            pmf_row_pos: 57,
            pmf_depth: 0
        };

        function escapeHtml(value) {
            return String(value ?? "")
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;")
                .replaceAll('"', "&quot;")
                .replaceAll("'", "&#039;");
        }

        function pickValue(
            object,
            keys,
            fallback = ""
        ) {
            for (const key of keys) {
                if (
                    object
                    && object[key] !== undefined
                    && object[key] !== null
                    && object[key] !== ""
                ) {
                    return object[key];
                }
            }

            return fallback;
        }

        function normalizeCandidate(row) {
            const job = row.job || {};
            const match =
                row.selected_pmf_match
                || row.top_match
                || row.pmf_match
                || row.pmf_material
                || {};

            return {
                raw: row,
                ocr_job_id: Number(
                    pickValue(
                        row,
                        ["ocr_job_id", "job_id", "id"],
                        pickValue(job, ["id"], 0)
                    )
                ),
                pmf_row_pos: Number(
                    pickValue(
                        match,
                        ["row_pos", "pmf_row_pos"],
                        pickValue(
                            row,
                            ["pmf_row_pos", "row_pos"],
                            0
                        )
                    )
                ),
                pmf_depth: Number(
                    pickValue(
                        match,
                        ["depth", "pmf_depth"],
                        pickValue(
                            row,
                            ["pmf_depth", "depth"],
                            0
                        )
                    )
                ),
                filename: pickValue(
                    row,
                    ["filename"],
                    pickValue(
                        job,
                        ["filename"],
                        "OCR 인증서"
                    )
                ),
                material_no: pickValue(
                    match,
                    ["material_no"],
                    pickValue(
                        row,
                        ["material_no"],
                        "-"
                    )
                ),
                english_name: pickValue(
                    match,
                    ["english_name"],
                    pickValue(
                        row,
                        ["english_name"],
                        "PMF 원료 매칭 대기"
                    )
                ),
                maker: pickValue(
                    match,
                    ["maker", "manufacturer"],
                    pickValue(
                        row,
                        ["maker", "manufacturer"],
                        "-"
                    )
                ),
                supplier: pickValue(
                    match,
                    ["supplier"],
                    pickValue(
                        row,
                        ["supplier"],
                        "-"
                    )
                )
            };
        }

        async function fetchJson(
            url,
            options = {}
        ) {
            const response = await fetch(
                url,
                options
            );

            const data = await response.json();

            if (!response.ok) {
                throw new Error(
                    data.detail
                    || data.message
                    || "API 요청 실패"
                );
            }

            return data;
        }

        async function loadCandidates() {
            const target = document.getElementById(
                "candidateList"
            );

            target.innerHTML = `
                <div class="empty">
                    <span class="loading"></span>
                    후보 목록 조회 중
                </div>
            `;

            try {
                const data = await fetchJson(
                    `${API_BASE}/candidates?limit=10`
                );

                const rows =
                    data.rows
                    || data.items
                    || data.candidates
                    || [];

                document.getElementById(
                    "candidateCount"
                ).textContent = rows.length;

                if (!rows.length) {
                    target.innerHTML = `
                        <div class="empty">
                            조회 가능한 후보가 없습니다.
                        </div>
                    `;
                    return;
                }

                const candidates = rows.map(
                    normalizeCandidate
                );

                target.innerHTML = candidates
                    .map(
                        (item, index) => `
                            <div
                                class="candidate ${
                                    item.ocr_job_id === 498
                                    ? "selected"
                                    : ""
                                }"
                                onclick='previewCandidate(
                                    ${JSON.stringify(item)}
                                )'
                            >
                                <div class="candidate-title">
                                    ${escapeHtml(item.filename)}
                                </div>

                                <div class="candidate-meta">
                                    <span class="mini-tag">
                                        Job ${escapeHtml(item.ocr_job_id)}
                                    </span>

                                    <span class="mini-tag">
                                        원료 ${escapeHtml(item.material_no)}
                                    </span>

                                    <span class="mini-tag">
                                        ${escapeHtml(item.supplier)}
                                    </span>
                                </div>

                                <div
                                    style="
                                        margin-top: 9px;
                                        color: #66778c;
                                        font-size: 12px;
                                        line-height: 1.45;
                                    "
                                >
                                    ${escapeHtml(item.english_name)}
                                </div>
                            </div>
                        `
                    )
                    .join("");

            } catch (error) {
                target.innerHTML = `
                    <div class="empty">
                        후보 조회 실패<br>
                        ${escapeHtml(error.message)}
                    </div>
                `;
            }
        }

        async function previewCandidate(item) {
            if (
                !item.ocr_job_id
                || !item.pmf_row_pos
            ) {
                alert(
                    "이 후보는 PMF 위치 정보가 없어 "
                    + "대표 갱신 건을 표시합니다."
                );

                await loadRepresentativePreview();
                return;
            }

            document.getElementById(
                "selectedJob"
            ).textContent = item.ocr_job_id;

            await loadPreview({
                ocr_job_id: item.ocr_job_id,
                pmf_row_pos: item.pmf_row_pos,
                pmf_depth: item.pmf_depth || 0
            });
        }

        async function loadRepresentativePreview() {
            document.getElementById(
                "selectedJob"
            ).textContent = 498;

            await loadPreview(
                representativeCandidate
            );
        }

        async function loadPreview(payload) {
            const target = document.getElementById(
                "previewBody"
            );

            target.innerHTML = `
                <div class="empty">
                    <span class="loading"></span>
                    OCR 결과와 PMF 관리대장 비교 중
                </div>
            `;

            try {
                const data = await fetchJson(
                    `${API_BASE}/preview`,
                    {
                        method: "POST",
                        headers: {
                            "Content-Type":
                                "application/json"
                        },
                        body: JSON.stringify(payload)
                    }
                );

                renderPreview(data);

            } catch (error) {
                document.getElementById(
                    "pmfAvailable"
                ).textContent = "오류";

                target.innerHTML = `
                    <div class="warning">
                        미리보기 실패:
                        ${escapeHtml(error.message)}
                    </div>
                `;
            }
        }

        function renderPreview(data) {
            const decision =
                data.change_decision || {};

            const changes =
                decision.changes || {};

            const expiry =
                changes.expiry_date || {};

            const manufacturer =
                changes.manufacturer || {};

            const filing =
                data.filing_preview || {};

            const pmfPreview =
                data.pmf_update_preview || {};

            const snapshot =
                pmfPreview.snapshot || {};

            const warnings =
                data.warnings || [];

            const blockers =
                data.blockers || [];

            const hardBlockers =
                data.hard_blockers || [];

            const canUpdate =
                decision.can_update_pmf === true;

            const decisionNameMap = {
                SAME_AUTHORITY_RENEWAL:
                    "동일 인증서 갱신 확인",
                DUPLICATE:
                    "기존 인증서와 동일",
                NEW_CERTIFICATE:
                    "신규 인증서 검토",
                MANUFACTURER_CHANGED:
                    "제조사 변경 검토",
                OCR_REVIEW_REQUIRED:
                    "OCR 수동 검토 필요"
            };

            const decisionTitle =
                decisionNameMap[
                    decision.decision_code
                ]
                || decision.decision_code
                || "판정 완료";

            document.getElementById(
                "pmfAvailable"
            ).textContent = canUpdate
                ? "가능"
                : "검토";

            document.getElementById(
                "blockerCount"
            ).textContent =
                blockers.length
                + hardBlockers.length;

            const equivalentText =
                manufacturer.equivalent
                ? "동일 업체로 판정"
                : (
                    manufacturer.changed
                    ? "변경 검토"
                    : "변경 없음"
                );

            const warningHtml = warnings.length
                ? warnings
                    .map(
                        item => `
                            <div class="warning">
                                ${escapeHtml(item)}
                            </div>
                        `
                    )
                    .join("")
                : "";

            document.getElementById(
                "previewBody"
            ).innerHTML = `
                <div class="decision-card">
                    <div class="decision-top">
                        <div>
                            <div class="decision-title">
                                ${escapeHtml(decisionTitle)}
                            </div>

                            <div class="decision-code">
                                ${escapeHtml(
                                    decision.decision_code
                                )}
                                · ${escapeHtml(
                                    decision.auto_action
                                )}
                            </div>
                        </div>

                        <div class="success-badge">
                            ${
                                data.ok
                                ? "확정 가능"
                                : "검토 필요"
                            }
                        </div>
                    </div>
                </div>

                <div class="info-grid">
                    <div class="info-box">
                        <div class="info-label">
                            원료번호
                        </div>
                        <div class="info-value">
                            ${escapeHtml(
                                snapshot.material_no
                                || "-"
                            )}
                        </div>
                    </div>

                    <div class="info-box">
                        <div class="info-label">
                            인증기관 / 인증번호
                        </div>
                        <div class="info-value">
                            ${escapeHtml(
                                snapshot.org
                                || data.certificate?.cert_org
                                || "-"
                            )}
                            <br>
                            ${escapeHtml(
                                snapshot.cert_no
                                || data.certificate?.cert_no
                                || "-"
                            )}
                        </div>
                    </div>

                    <div class="info-box full">
                        <div class="info-label">
                            대상 원료
                        </div>
                        <div class="info-value">
                            ${escapeHtml(
                                snapshot.english_name
                                || "-"
                            )}
                        </div>
                    </div>

                    <div class="info-box full">
                        <div class="info-label">
                            자동 분류 폴더
                        </div>
                        <div class="info-value">
                            ${escapeHtml(
                                filing.target_folder
                                || "-"
                            )}
                        </div>
                    </div>

                    <div class="info-box full">
                        <div class="info-label">
                            자동 생성 파일명
                        </div>
                        <div class="info-value">
                            ${escapeHtml(
                                filing.target_filename
                                || "-"
                            )}
                        </div>
                    </div>
                </div>

                <div class="change-card">
                    <div class="change-title">
                        PMF 관리대장 변경 예정
                    </div>

                    <div class="change-row">
                        <div class="change-label">
                            유효기간
                        </div>

                        <div class="before">
                            ${escapeHtml(
                                expiry.before
                                || "-"
                            )}
                        </div>

                        <div class="arrow">
                            →
                        </div>

                        <div class="after">
                            ${escapeHtml(
                                expiry.after
                                || "-"
                            )}
                        </div>
                    </div>

                    <div class="change-row">
                        <div class="change-label">
                            제조사
                        </div>

                        <div class="before">
                            ${escapeHtml(
                                manufacturer.before
                                || "-"
                            )}
                        </div>

                        <div class="arrow">
                            →
                        </div>

                        <div class="after">
                            ${escapeHtml(
                                manufacturer.after
                                || "-"
                            )}
                            <br>
                            <span
                                style="
                                    font-size: 11px;
                                    color: #16865d;
                                "
                            >
                                ${escapeHtml(equivalentText)}
                            </span>
                        </div>
                    </div>
                </div>

                ${warningHtml}

                <button
                    class="btn btn-success"
                    disabled
                >
                    ${
                        canUpdate
                        && !blockers.length
                        && !hardBlockers.length
                        ? "인증서 분류 및 PMF 갱신 가능"
                        : "수동 검토 필요"
                    }
                    · 데모 모드
                </button>
            `;
        }

        window.addEventListener(
            "DOMContentLoaded",
            async () => {
                loadCandidates();
                loadRepresentativePreview();
            }
        );
    </script>
</body>
</html>
"""


@router.get(
    "/demo",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def filing_demo():
    return HTMLResponse(
        content=DEMO_HTML
    )


'''


def main() -> None:
    if not TARGET.exists():
        raise FileNotFoundError(TARGET)

    source = TARGET.read_text(
        encoding="utf-8-sig",
    )

    if DEMO_MARKER in source:
        print(
            "DEMO_PAGE_ALREADY_EXISTS"
        )
        return

    if (
        "from fastapi.responses "
        "import HTMLResponse"
        not in source
    ):
        if IMPORT_MARKER not in source:
            raise RuntimeError(
                "Pydantic import 위치를 "
                "찾지 못했습니다."
            )

        source = source.replace(
            IMPORT_MARKER,
            IMPORT_MARKER
            + IMPORT_LINE,
            1,
        )

    marker_count = source.count(
        ROUTE_MARKER
    )

    if marker_count != 1:
        raise RuntimeError(
            "status route marker "
            f"검색 결과: {marker_count}"
        )

    source = source.replace(
        ROUTE_MARKER,
        DEMO_BLOCK
        + ROUTE_MARKER,
        1,
    )

    ast.parse(
        source,
        filename=str(TARGET),
    )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup = TARGET.with_name(
        TARGET.name
        + ".backup_"
        + stamp
    )

    shutil.copy2(
        TARGET,
        backup,
    )

    TARGET.write_text(
        source,
        encoding="utf-8",
    )

    print("UPDATED:", TARGET)
    print("BACKUP :", backup)
    print("FILING_DEMO_PAGE_PATCH_OK")


if __name__ == "__main__":
    main()
