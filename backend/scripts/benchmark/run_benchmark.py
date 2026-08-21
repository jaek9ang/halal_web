#!/usr/bin/env python
"""Rule vs OpenAI vs Hybrid 할랄 인증서 판독 벤치마크.

2026-08-21 최초 측정(Rule 83.0 / Hybrid 69.8 / LLM 61.5) 이후 아래 넷을 고쳤다.

1. **채점을 strict / normalized 두 축으로 낸다.**
   기존 채점은 `.strip().lower()` 후 완전일치였다. Rule은 값을 뱉기 전에 이미
   정규화 단계를 거치고 LLM은 원문 표기를 그대로 뱉으므로, `Co., Ltd` vs
   `Co.,Ltd` 같은 표기 차이가 전부 LLM 오답으로 잡혔다. 두 축을 나란히 내서
   "실력 차이"와 "표기 차이"를 분리한다.

2. **기관·국가를 폐쇄집합(enum)으로 강제한다.**
   기존 스키마는 `cert_org: str`이라 모델이 `Majelis Ulama Indonesia`처럼
   서류 원문을 그대로 뱉었다. 우리 시스템의 정규 기관명은 `MUI`다. 보기를 주면
   구조적으로 딴 값이 나올 수 없다. 보기는 `rules/organizations.py`에서 만든다.

3. **양식 분류(pHash/ORB) 결과를 프롬프트 힌트로 넣을 수 있다.**
   `cert_template_service`가 OCR 전에 이미 기관 후보를 뽑는데 LLM에게는 알려주지
   않고 있었다. 정답 누출 위험이 있어 기본값은 off다 (아래 주의 참고).

4. **경로 하드코딩을 CLI 인자로 뺐다.** 기존엔 `D:\\`, `C:\\Users\\user\\Downloads`가
   소스에 박혀 있어 다른 PC에서 재현이 불가능했다.

주의 — `--template-hint image`의 정답 누출:
    양식 분류는 `cert_template_features.db`의 참조 특징과 대조한다. 벤치마크
    대상 PDF가 그 참조 집합에 들어 있으면 힌트가 사실상 정답이 되어 점수가
    부풀려진다. 사람이 확정한 판정(`feature_kind == "manual"`)은 코드에서
    자동으로 건너뛰지만, 참조 집합 자체의 중복까지는 막지 못한다.
    이 옵션으로 낸 수치는 참조 집합과 대상이 분리되어 있음을 확인한 뒤에만 쓴다.

PMF 기존값(기존 인증번호·제조사)은 의도적으로 주입하지 않는다. 답을 미리 보여주면
모델이 그대로 베껴 써서 "갱신되지 않은 인증서"를 잡지 못한다. 이는
`rules/context.py`의 자동확정 안전 원칙과 같은 이유다.

실행:
    python run_benchmark.py --pdf-dir D:\\halal_baseline_review_100 \\
        --baseline C:\\path\\halal_ocr_baseline_google_dashboard.html \\
        --out report.html --schema enum
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Literal

import fitz  # PyMuPDF
from openai import OpenAI
from pydantic import BaseModel, Field, create_model

# 정규화 규칙은 판독기와 같은 것을 쓴다. 채점기가 자기만의 정규화를 따로
# 갖게 되면 판독기가 바뀔 때 채점이 조용히 어긋난다.
BACKEND_DIR = Path(__file__).resolve().parents[2]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.rules.dates import parse_date_text  # noqa: E402
from app.services.rules.organizations import (  # noqa: E402
    COUNTRY_WORDS,
    ORG_ALIASES,
    detect_org,
)
from app.services.rules.text import norm_key  # noqa: E402


UNKNOWN = "UNKNOWN"

METHODS = ("rule", "llm", "hybrid")

AXES = ("strict", "normalized")


# ==========================================
# 폐쇄집합 (기관 / 국가)
# ==========================================

def build_org_choices() -> tuple[str, ...]:
    """LLM에게 줄 기관 보기. rules/organizations.py가 단일 소스다."""
    orgs = [org for org, _country, _aliases in ORG_ALIASES]
    return tuple(dict.fromkeys(orgs)) + (UNKNOWN,)


def build_country_choices() -> tuple[str, ...]:
    """LLM에게 줄 국가 보기."""
    return tuple(sorted(set(COUNTRY_WORDS.values()))) + (UNKNOWN,)


ORG_CHOICES = build_org_choices()
COUNTRY_CHOICES = build_country_choices()


# ==========================================
# 응답 스키마 두 종류
# ==========================================

_CERT_NO_DESC = "할랄 인증번호. 서류에 적힌 그대로."
_EXPIRY_DESC = "유효기간 만료일 (YYYY-MM-DD). 없으면 빈 문자열."
_MAKER_DESC = "제조사명. 주소·전화번호 등 노이즈 제외한 회사명만."


class HalalCertFree(BaseModel):
    """원본 스키마 — 전 필드 자유 문자열. 비교용 baseline."""

    cert_org: str = Field(description="인증기관명 (예: MUI, JAKIM, BPJPH, HFFIA)")
    cert_country: str = Field(description="인증국가 영문명")
    cert_no: str = Field(description=_CERT_NO_DESC)
    expiry_date: str = Field(description=_EXPIRY_DESC)
    manufacturer: str = Field(description=_MAKER_DESC)
    manufacturing_country: str = Field(description="제조국 영문명 (공장 위치 기준)")


def build_enum_model() -> type[BaseModel]:
    """기관·국가를 보기에서 고르게 강제한 스키마."""
    return create_model(
        "HalalCertEnum",
        cert_org=(
            Literal[ORG_CHOICES],
            Field(description="인증기관. 보기에 없으면 UNKNOWN."),
        ),
        cert_country=(
            Literal[COUNTRY_CHOICES],
            Field(description="인증서를 발급한 기관의 국가. 보기에 없으면 UNKNOWN."),
        ),
        cert_no=(str, Field(description=_CERT_NO_DESC)),
        expiry_date=(str, Field(description=_EXPIRY_DESC)),
        manufacturer=(str, Field(description=_MAKER_DESC)),
        manufacturing_country=(
            Literal[COUNTRY_CHOICES],
            Field(description="공장·제조사가 있는 국가. 인증국가와 다를 수 있다. 보기에 없으면 UNKNOWN."),
        ),
    )


def resolve_schema(name: str) -> type[BaseModel]:
    return HalalCertFree if name == "free" else build_enum_model()


# ==========================================
# 채점 정규화
# ==========================================
# 원칙 하나만 지킨다: 표기 차이만 흡수하고 의미 차이는 남긴다.
# 기관·국가·날짜는 정규형이 존재하므로 그 정규형으로 접고, 제조사처럼 정규형이
# 없는 필드는 대소문자·구두점·공백만 지운다. 채점기가 필드별로 더 똑똑해지면
# 실제 오답까지 정답으로 접어버린다.

# 정규 기관 코드 자체는 detect_org로 못 찾는다. detect_org는 인증서 본문을 훑도록
# 만들어져 있고, 예를 들어 MUI의 별칭 목록에는 "MAJELIS ULAMA INDONESIA"는 있어도
# "MUI"는 없다. 그래서 정규 코드 직접 대조를 앞에 둔다.
CANONICAL_ORGS = {org.upper(): org for org, _country, _aliases in ORG_ALIASES}


def norm_org_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.upper() == UNKNOWN:
        # UNKNOWN은 enum 스키마의 "모름" 센티널이다. 빈 값과 같이 취급하지 않으면
        # enum 쪽만 "모름"을 오답으로 얻어맞아 free 스키마와 비교가 어긋난다.
        return ""

    if text.upper() in CANONICAL_ORGS:
        return CANONICAL_ORGS[text.upper()]

    key = norm_key(text)
    for canonical in CANONICAL_ORGS.values():
        if norm_key(canonical) == key:
            return canonical

    org, _country, _aliases = detect_org(text)
    if org and org != UNKNOWN:
        return org

    return key


def norm_country_value(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text or text == UNKNOWN:
        return ""
    if text in COUNTRY_WORDS:
        return COUNTRY_WORDS[text]
    key = norm_key(text)
    for word, canonical in COUNTRY_WORDS.items():
        if norm_key(word) == key:
            return canonical
    return key


def norm_date_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return parse_date_text(text) or norm_key(text)


def norm_cert_no_value(value: Any) -> str:
    """인증번호는 구분자 표기만 흡수한다. 영숫자는 그대로 둔다."""
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def norm_plain_value(value: Any) -> str:
    return norm_key(value)


# (표시명, 스키마 필드명, 정규화 함수)
FIELD_SPECS: tuple[tuple[str, str, Any], ...] = (
    ("인증기관", "cert_org", norm_org_value),
    ("인증국가", "cert_country", norm_country_value),
    ("인증번호", "cert_no", norm_cert_no_value),
    ("유효기간", "expiry_date", norm_date_value),
    ("제조사", "manufacturer", norm_plain_value),
    ("제조국", "manufacturing_country", norm_country_value),
)


def strict_key(value: Any) -> str:
    """원본 채점 방식. 비교 기준으로 남겨둔다."""
    return str(value or "").strip().lower()


# ==========================================
# 정답 데이터
# ==========================================

def load_ground_truth(html_path: Path) -> dict[str, dict[str, Any]]:
    content = html_path.read_text(encoding="utf-8")
    match = re.search(r"const DATA = ({.*?});\s*const FIELDS", content, re.DOTALL)
    if not match:
        return {}
    data = json.loads(match.group(1))
    return {row["파일명"].strip(): row for row in data["review_rows"]}


def find_gt_row(filename: str, gt_data: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if filename.strip() in gt_data:
        return gt_data[filename.strip()]
    for gt_file, row in gt_data.items():
        if filename in gt_file or gt_file in filename:
            return row
    return None


def is_low_confidence(gt_row: dict[str, Any]) -> bool:
    conf = str(gt_row.get("시스템CONFIDENCE", "") or "").upper()
    status = str(gt_row.get("PARSE_STATUS", "") or "").upper()
    return conf == "LOW" or status in {"LOW_CONFIDENCE", "FILENAME_ONLY"}


# ==========================================
# 입력 준비
# ==========================================

def pdf_to_base64_image(pdf_path: Path, zoom: float) -> str:
    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        return base64.b64encode(pix.tobytes("png")).decode("utf-8")
    finally:
        doc.close()


# classify_file_path는 판정 실패를 predicted_org 자리에 센티널 문자열로 돌려준다
# (참조 양식이 없으면 predicted_org = "NO_REFERENCE"). 이걸 기관명으로 착각하면
# "이 문서는 NO_REFERENCE 양식과 비슷하다" 같은 힌트를 프롬프트에 넣게 된다.
NON_ORG_SENTINELS = {"", "-", UNKNOWN, "NO_REFERENCE", "ERROR", "REVIEW", "MANUAL_REVIEW"}

# 이미지 판정을 신뢰하는 기준은 운영 코드와 같은 것을 쓴다 (AUTO_SCORE_THRESHOLD /
# AUTO_MARGIN_THRESHOLD를 통과한 결과에만 붙는 decision).
TRUSTED_TEMPLATE_DECISION = "AUTO_IMAGE"


def build_template_hint(pdf_path: Path, mode: str) -> tuple[str, str]:
    """양식 분류 결과를 프롬프트 힌트 문장으로 만든다.

    반환: (힌트 문장, 진단 코드). 힌트를 못 만들면 문장은 빈 문자열.
    틀린 힌트는 아무 힌트도 없는 것보다 나쁘므로, 운영 코드가 자동 판정으로
    인정하는 수준(AUTO_IMAGE)일 때만 힌트를 만든다.
    사람이 확정한 판정은 정답 누출이므로 건너뛴다.
    """
    if mode != "image":
        return "", "OFF"

    try:
        from app.services.cert_template_service import classify_file_path
    except Exception as exc:  # cv2 등 의존성이 없는 환경
        return "", f"UNAVAILABLE:{type(exc).__name__}"

    try:
        row = classify_file_path(str(pdf_path), enhanced_retry=True, max_pages=1)
    except Exception as exc:
        return "", f"ERROR:{type(exc).__name__}"

    if str(row.get("feature_kind") or "") == "manual":
        return "", "SKIPPED_MANUAL_DECISION"

    decision = str(row.get("decision") or "").strip().upper()
    if decision != TRUSTED_TEMPLATE_DECISION:
        return "", f"LOW_CONFIDENCE:{decision or 'NONE'}"

    org = str(row.get("predicted_org") or "").strip()
    if org.upper() in NON_ORG_SENTINELS:
        return "", f"NO_CANDIDATE:{org or 'EMPTY'}"

    score = float(row.get("score") or 0.0)
    hint = (
        f"참고: 이 문서의 레이아웃은 {org} 양식과 가장 비슷하다 (유사도 {score:.2f}). "
        "확정 정보가 아니므로 이미지에서 직접 확인하고, 다르면 본 것을 따르라."
    )
    return hint, f"HINT:{org}:{score:.2f}"


SYSTEM_PROMPT = (
    "당신은 할랄 인증서 판독 전문가입니다. 첨부된 이미지의 텍스트와 레이아웃을 "
    "종합적으로 분석하여 요청된 JSON 형식으로 데이터를 정확하게 추출하세요. "
    "이미지에서 확인되지 않는 값은 지어내지 말고 비워 두세요."
)


def call_llm(
    client: OpenAI,
    model: str,
    schema: type[BaseModel],
    base64_image: str,
    hint: str,
    max_retries: int,
) -> tuple[dict[str, Any], float]:
    user_content: list[dict[str, Any]] = [
        {"type": "text", "text": "이 인증서에서 정보를 추출해줘."},
    ]

    if hint:
        user_content.append({"type": "text", "text": hint})

    user_content.append(
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
    )

    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            started = time.time()
            response = client.chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                response_format=schema,
                temperature=0.0,
            )
            return json.loads(response.choices[0].message.content), time.time() - started
        except Exception as exc:
            last_error = exc
            if "429" in str(exc) or "rate_limit" in str(exc):
                print(f"   API 한도 초과. 20초 후 재시도 ({attempt + 1}/{max_retries})")
                time.sleep(20)
                continue
            raise

    # 재시도를 모두 소진했다. 원본 스크립트는 여기서 미정의 변수를 참조해 죽었다.
    raise RuntimeError(f"LLM 호출이 {max_retries}회 모두 실패했습니다: {last_error}")


# ==========================================
# 채점
# ==========================================

def blank_stats() -> dict[str, int]:
    stats = {"docs": 0, "total_fields": 0}
    for method in METHODS:
        stats[f"{method}_correct"] = 0
        stats[f"{method}_full_match"] = 0
    return stats


def score_document(
    gt_row: dict[str, Any],
    llm_result: dict[str, Any],
    low_conf: bool,
) -> dict[str, Any]:
    """한 문서를 strict/normalized 두 축으로 채점한다."""
    fields: dict[str, Any] = {}

    for label, schema_field, normalizer in FIELD_SPECS:
        gt_raw = str(gt_row.get(f"정답_{label}", "") or "").strip()
        rule_raw = str(gt_row.get(f"추출_{label}", "") or "").strip()
        llm_raw = str(llm_result.get(schema_field, "") or "").strip()
        hybrid_raw = llm_raw if low_conf else rule_raw

        values = {"rule": rule_raw, "llm": llm_raw, "hybrid": hybrid_raw}
        gt_norm = normalizer(gt_raw)

        fields[label] = {
            "gt": gt_raw,
            "gt_norm": gt_norm,
            "rule_val": rule_raw,
            "llm_val": llm_raw,
            "hybrid_val": hybrid_raw,
            "llm_norm": normalizer(llm_raw),
            "strict": {
                m: strict_key(gt_raw) == strict_key(v) for m, v in values.items()
            },
            "normalized": {
                m: gt_norm == normalizer(v) for m, v in values.items()
            },
        }

    return fields


def accumulate(stats: dict[str, int], fields: dict[str, Any], axis: str) -> None:
    errors = {method: 0 for method in METHODS}

    for label, _schema_field, _normalizer in FIELD_SPECS:
        marks = fields[label][axis]
        for method in METHODS:
            if marks[method]:
                stats[f"{method}_correct"] += 1
            else:
                errors[method] += 1

    stats["docs"] += 1
    stats["total_fields"] += len(FIELD_SPECS)

    for method, error_count in errors.items():
        if error_count == 0:
            stats[f"{method}_full_match"] += 1


def field_accuracy(results: list[dict[str, Any]], axis: str) -> list[dict[str, Any]]:
    table = []
    for label, _schema_field, _normalizer in FIELD_SPECS:
        row: dict[str, Any] = {"field": label}
        for method in METHODS:
            hits = sum(1 for r in results if r["fields"][label][axis][method])
            row[method] = round(hits / len(results) * 100, 1) if results else 0.0
        table.append(row)
    return table


def summarize(stats: dict[str, int]) -> dict[str, Any]:
    total = stats["total_fields"] or 1
    summary: dict[str, Any] = {"docs": stats["docs"]}
    for method in METHODS:
        summary[f"{method}_acc"] = round(stats[f"{method}_correct"] / total * 100, 1)
        summary[f"{method}_full"] = stats[f"{method}_full_match"]
    return summary


# ==========================================
# 리포트
# ==========================================

HTML_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>Halal OCR: Rule vs LLM</title>
<style>
  body { margin:0; background:#F8FAFC; color:#0F172A; font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  .topbar { background:#fff; padding:20px 32px; border-bottom:1px solid #E2E8F0; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; }
  .title { font-size:22px; font-weight:700; color:#1E293B; }
  .badge { background:#EEF2FF; color:#4F46E5; padding:6px 12px; border-radius:20px; font-size:13px; font-weight:700; }
  .content { padding:32px; max-width:1400px; margin:0 auto; }
  .runcfg { background:#fff; border:1px solid #E2E8F0; border-radius:12px; padding:16px 20px; margin-bottom:24px; font-size:13px; color:#475569; }
  .runcfg code { background:#F1F5F9; padding:2px 6px; border-radius:4px; }
  .warn { background:#FEF3C7; border:1px solid #FCD34D; color:#92400E; border-radius:12px; padding:14px 20px; margin-bottom:24px; font-size:13px; }
  h2.axis { font-size:16px; color:#334155; margin:28px 0 12px; padding-bottom:8px; border-bottom:2px solid #E2E8F0; }
  h2.axis small { font-weight:400; color:#64748B; margin-left:8px; }
  .grid-3 { display:grid; grid-template-columns:repeat(3, 1fr); gap:20px; margin-bottom:20px; }
  .card { background:#fff; padding:20px; border-radius:14px; box-shadow:0 1px 3px rgba(0,0,0,.06); border:1px solid #E2E8F0; }
  .card h3 { margin:0 0 4px; font-size:14px; color:#334155; }
  .kpi { font-size:38px; font-weight:800; margin:8px 0 4px; }
  .kpi.rule { color:#64748B; } .kpi.hybrid { color:#4F46E5; } .kpi.llm { color:#10B981; }
  .delta { font-size:13px; font-weight:700; }
  .delta.up { color:#059669; } .delta.flat { color:#94A3B8; }
  .sub-text { font-size:13px; color:#64748B; }
  table { width:100%; border-collapse:collapse; background:#fff; border-radius:12px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,.06); }
  th, td { padding:10px 14px; border-bottom:1px solid #E2E8F0; text-align:left; font-size:13px; }
  th { background:#F8FAFC; color:#64748B; font-weight:700; }
  .err { color:#EF4444; font-weight:700; }
  .ok { color:#10B981; font-weight:700; }
  .fixed { color:#F59E0B; font-weight:700; }
  .filters { margin:0 0 14px; display:flex; gap:10px; align-items:center; }
  select { padding:8px 12px; border-radius:8px; border:1px solid #E2E8F0; outline:none; }
  .scroll { overflow-x:auto; }
</style>
</head>
<body>
  <div class="topbar">
    <div class="title">Halal OCR Benchmark — Rule vs LLM</div>
    <div class="badge">검증 {DOCS}건</div>
  </div>
  <div class="content">
    <div class="runcfg">
      모델 <code>{MODEL}</code> ·
      스키마 <code>{SCHEMA}</code> ·
      양식힌트 <code>{HINT_MODE}</code> ·
      렌더배율 <code>{ZOOM}x</code>
      <br>양식힌트 진단: {HINT_DIAG}
    </div>
    {WARN_BLOCK}

    <h2 class="axis">STRICT <small>원본 채점 — 대소문자만 무시하고 글자 완전일치</small></h2>
    <div class="grid-3">{STRICT_CARDS}</div>
    <div class="scroll">{STRICT_FIELD_TABLE}</div>

    <h2 class="axis">NORMALIZED <small>표기 정규화 후 — 기관 별칭·국가 표기·날짜 형식·구두점 차이를 흡수</small></h2>
    <div class="grid-3">{NORM_CARDS}</div>
    <div class="scroll">{NORM_FIELD_TABLE}</div>

    <h2 class="axis">문서별 상세</h2>
    <div class="filters">
      <select id="fField" onchange="renderTable()">{FIELD_OPTIONS}</select>
      <select id="fAxis" onchange="renderTable()">
        <option value="normalized">NORMALIZED 기준</option>
        <option value="strict">STRICT 기준</option>
      </select>
      <span class="sub-text">주황 = STRICT에서는 오답이지만 정규화하면 정답 (표기 차이)</span>
    </div>
    <div class="scroll">
      <table>
        <thead><tr>
          <th>파일명</th><th>기관</th><th>Conf</th>
          <th>정답</th><th>Rule</th><th>LLM</th><th>Hybrid</th>
        </tr></thead>
        <tbody id="dataBody"></tbody>
      </table>
    </div>
  </div>

<script>
const results = {RESULTS_JSON};

function cell(value, data, method, axis) {
  const ok = data[axis][method];
  const strictOk = data.strict[method];
  const shown = value || '미추출';
  if (ok && !strictOk) return '<span class="fixed">' + shown + '</span>';
  return ok ? '<span class="ok">' + shown + '</span>'
            : '<span class="err">' + shown + '</span>';
}

function renderTable() {
  const field = document.getElementById('fField').value;
  const axis = document.getElementById('fAxis').value;
  const tbody = document.getElementById('dataBody');
  tbody.innerHTML = '';
  results.forEach(function (r) {
    const d = r.fields[field];
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td style="max-width:220px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="' + r.filename + '">' + r.filename + '</td>' +
      '<td><b>' + r.org + '</b></td>' +
      '<td>' + r.conf + '</td>' +
      '<td style="color:#10B981;font-weight:700">' + (d.gt || '-') + '</td>' +
      '<td>' + cell(d.rule_val, d, 'rule', axis) + '</td>' +
      '<td>' + cell(d.llm_val, d, 'llm', axis) + '</td>' +
      '<td style="background:#F8FAFF">' + cell(d.hybrid_val, d, 'hybrid', axis) + '</td>';
    tbody.appendChild(tr);
  });
}
renderTable();
</script>
</body>
</html>
"""

CARD_LABELS = {
    "rule": "1. Rule (기존 판독기)",
    "hybrid": "2. Hybrid (LOW conf만 LLM)",
    "llm": "3. Full LLM",
}


def render_cards(summary: dict[str, Any], baseline: dict[str, Any] | None) -> str:
    blocks = []
    for method in ("rule", "hybrid", "llm"):
        accuracy = summary[f"{method}_acc"]
        delta_html = ""
        if baseline is not None:
            delta = round(accuracy - baseline[f"{method}_acc"], 1)
            css = "up" if delta > 0 else "flat"
            sign = "+" if delta > 0 else ""
            delta_html = f'<div class="delta {css}">STRICT 대비 {sign}{delta}%p</div>'
        blocks.append(
            f'<div class="card"><h3>{CARD_LABELS[method]}</h3>'
            f'<div class="kpi {method}">{accuracy}%</div>{delta_html}'
            f'<div class="sub-text">완전일치 {summary[f"{method}_full"]} / {summary["docs"]}건</div></div>'
        )
    return "".join(blocks)


def render_field_table(rows: list[dict[str, Any]]) -> str:
    body = "".join(
        f'<tr><td><b>{r["field"]}</b></td><td>{r["rule"]}</td>'
        f'<td>{r["llm"]}</td><td>{r["hybrid"]}</td></tr>'
        for r in rows
    )
    return (
        "<table><thead><tr><th>필드</th><th>Rule</th><th>LLM</th><th>Hybrid</th></tr>"
        f"</thead><tbody>{body}</tbody></table>"
    )


def render_report(
    results: list[dict[str, Any]],
    stats_by_axis: dict[str, dict[str, int]],
    config: dict[str, Any],
    hint_diagnostics: dict[str, int],
) -> str:
    strict_summary = summarize(stats_by_axis["strict"])
    norm_summary = summarize(stats_by_axis["normalized"])

    diag = ", ".join(f"{k} {v}건" for k, v in sorted(hint_diagnostics.items())) or "없음"

    warn_block = ""
    leaked = hint_diagnostics.get("SKIPPED_MANUAL_DECISION", 0)
    if config["hint_mode"] == "image":
        warn_block = (
            '<div class="warn"><b>양식 힌트 사용 중 — 정답 누출 확인 필요.</b> '
            "벤치마크 대상 PDF가 양식 참조 DB에 들어 있으면 힌트가 사실상 정답이 되어 "
            "점수가 부풀려집니다. 사람이 확정한 판정 "
            f"{leaked}건은 자동으로 제외했으나, 참조 집합 중복은 코드가 막지 못합니다.</div>"
        )

    field_options = "".join(
        f'<option value="{label}">{label}</option>' for label, _f, _n in FIELD_SPECS
    )

    replacements = {
        "{DOCS}": str(strict_summary["docs"]),
        "{MODEL}": config["model"],
        "{SCHEMA}": config["schema"],
        "{HINT_MODE}": config["hint_mode"],
        "{ZOOM}": str(config["zoom"]),
        "{HINT_DIAG}": diag,
        "{WARN_BLOCK}": warn_block,
        "{STRICT_CARDS}": render_cards(strict_summary, None),
        "{NORM_CARDS}": render_cards(norm_summary, strict_summary),
        "{STRICT_FIELD_TABLE}": render_field_table(field_accuracy(results, "strict")),
        "{NORM_FIELD_TABLE}": render_field_table(field_accuracy(results, "normalized")),
        "{FIELD_OPTIONS}": field_options,
        "{RESULTS_JSON}": json.dumps(results, ensure_ascii=False),
    }

    html = HTML_TEMPLATE
    for placeholder, value in replacements.items():
        html = html.replace(placeholder, value)
    return html


# ==========================================
# CLI
# ==========================================

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rule vs OpenAI vs Hybrid 할랄 인증서 판독 벤치마크",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--pdf-dir",
        default=os.environ.get("HALAL_BENCHMARK_PDF_DIR", ""),
        help="인증서 PDF 폴더. 환경변수 HALAL_BENCHMARK_PDF_DIR로도 준다.",
    )
    parser.add_argument(
        "--baseline",
        default=os.environ.get("HALAL_BENCHMARK_BASELINE", ""),
        help="정답 데이터가 든 baseline 대시보드 HTML.",
    )
    parser.add_argument("--out", default="llm_comparison_report.html", help="리포트 출력 경로.")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI 모델.")
    parser.add_argument("--schema", choices=("free", "enum"), default="enum",
                        help="free=원본 자유 문자열, enum=기관·국가 폐쇄집합 강제.")
    parser.add_argument("--template-hint", choices=("off", "image"), default="off",
                        help="양식 분류 힌트 주입. image는 정답 누출 위험 — 독스트링 참고.")
    parser.add_argument("--limit", type=int, default=0, help="처리할 PDF 수 상한. 0이면 전부.")
    parser.add_argument("--zoom", type=float, default=2.0, help="PDF -> PNG 렌더 배율.")
    parser.add_argument("--sleep", type=float, default=2.0, help="문서 간 대기 초.")
    parser.add_argument("--max-retries", type=int, default=5, help="429 재시도 횟수.")
    parser.add_argument("--offline", action="store_true",
                        help="OpenAI를 호출하지 않는다. 배선 점검용이며 LLM 수치는 무의미하다.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.pdf_dir or not args.baseline:
        print("오류: --pdf-dir 와 --baseline 은 필수입니다. (-h 로 사용법 확인)")
        return 2

    pdf_dir = Path(args.pdf_dir)
    baseline_path = Path(args.baseline)

    if not pdf_dir.is_dir():
        print(f"오류: PDF 폴더가 없습니다: {pdf_dir}")
        return 2
    if not baseline_path.is_file():
        print(f"오류: baseline HTML이 없습니다: {baseline_path}")
        return 2

    client: OpenAI | None = None
    if not args.offline:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("오류: OPENAI_API_KEY가 없습니다. (--offline 은 배선 점검 전용)")
            return 2
        client = OpenAI(api_key=api_key)
    else:
        print("!! --offline: OpenAI를 호출하지 않습니다. LLM/Hybrid 수치는 의미 없습니다.")

    gt_data = load_ground_truth(baseline_path)
    if not gt_data:
        print(f"오류: baseline에서 정답 데이터를 찾지 못했습니다: {baseline_path}")
        return 2
    print(f"정답 데이터 {len(gt_data)}건 로드")

    schema = resolve_schema(args.schema)
    if args.schema == "enum":
        print(f"폐쇄집합: 기관 {len(ORG_CHOICES)}개, 국가 {len(COUNTRY_CHOICES)}개")

    pdf_files = sorted(f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf"))
    if args.limit > 0:
        pdf_files = pdf_files[: args.limit]

    results: list[dict[str, Any]] = []
    stats_by_axis = {axis: blank_stats() for axis in AXES}
    hint_diagnostics: dict[str, int] = {}

    for index, filename in enumerate(pdf_files, 1):
        gt_row = find_gt_row(filename, gt_data)
        if not gt_row:
            print(f"[{index}/{len(pdf_files)}] 정답 없음, 건너뜀: {filename}")
            continue

        pdf_path = pdf_dir / filename
        print(f"[{index}/{len(pdf_files)}] {filename}")

        try:
            hint, diagnostic = build_template_hint(pdf_path, args.template_hint)
            diagnostic_key = diagnostic.split(":", 1)[0]
            hint_diagnostics[diagnostic_key] = hint_diagnostics.get(diagnostic_key, 0) + 1

            if args.offline:
                llm_result: dict[str, Any] = {}
                elapsed = 0.0
            else:
                assert client is not None
                base64_image = pdf_to_base64_image(pdf_path, args.zoom)
                llm_result, elapsed = call_llm(
                    client, args.model, schema, base64_image, hint, args.max_retries
                )

            fields = score_document(gt_row, llm_result, is_low_confidence(gt_row))

            for axis in AXES:
                accumulate(stats_by_axis[axis], fields, axis)

            results.append({
                "filename": filename,
                "org": gt_row.get("기관", "Unknown"),
                "conf": gt_row.get("시스템CONFIDENCE", "UNKNOWN"),
                "time": round(elapsed, 2),
                "hint": diagnostic,
                "fields": fields,
            })

            if not args.offline and args.sleep > 0:
                time.sleep(args.sleep)

        except Exception as exc:
            print(f"  오류 ({filename}): {exc}")

    if not results:
        print("오류: 채점된 문서가 없습니다.")
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        render_report(
            results,
            stats_by_axis,
            {
                "model": args.model if not args.offline else f"{args.model} (offline)",
                "schema": args.schema,
                "hint_mode": args.template_hint,
                "zoom": args.zoom,
            },
            hint_diagnostics,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 58)
    for axis in AXES:
        summary = summarize(stats_by_axis[axis])
        print(
            f"{axis.upper():11} Rule {summary['rule_acc']:5.1f}%  "
            f"Hybrid {summary['hybrid_acc']:5.1f}%  LLM {summary['llm_acc']:5.1f}%   "
            f"(완전일치 {summary['rule_full']}/{summary['hybrid_full']}/{summary['llm_full']} "
            f"of {summary['docs']})"
        )
    print("=" * 58)
    print(f"리포트: {out_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
