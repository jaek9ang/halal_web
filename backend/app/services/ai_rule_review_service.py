from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.services.rule_candidate_service import create_rule_candidates, get_rule_storage_status
from app.services.rule_validation_service import get_certificate_rule, read_export_jsonl

DEFAULT_RULE_REVIEW_MODEL = os.getenv("OPENAI_RULE_REVIEW_MODEL", "gpt-4.1")
MAX_TEXT_CHARS_PER_CASE = 700
MAX_CASES_FOR_PROMPT = 20

OCR_FAILURE_PARSE_STATUSES = {
    "SCANNED_NEED_OCR",
    "NO_TEXT",
    "TESSERACT_ERROR",
}

MIN_RULE_REVIEW_TEXT_LENGTH = 120

AI_RULE_REVIEW_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "review_version": {"type": "string"},
        "summary": {"type": "string"},
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "rule_candidate_id": {"type": "string"},
                    "target_org": {"type": "string"},
                    "target_field": {"type": "string"},
                    "rule_kind": {
                        "type": "string",
                        "enum": [
                            "date_anchor_rule",
                            "manufacturer_cleanup_rule",
                            "cert_no_pattern_rule",
                            "non_certificate_doc_rule",
                        ],
                    },
                    "problem_summary": {"type": "string"},
                    "proposed_rule": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "anchors": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "stop_before": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "date_normalizers": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "allow_filename_fallback": {"type": "boolean"},
                            "window": {"type": "integer"},
                            "source_field": {"type": "string"},
                            "cleanup_steps": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "patterns": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "markers": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "anchors",
                            "stop_before",
                            "date_normalizers",
                            "allow_filename_fallback",
                            "window",
                            "source_field",
                            "cleanup_steps",
                            "patterns",
                            "markers",
                        ],
                    },
                    "expected_cases": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "filename_keyword": {"type": "string"},
                                "field": {"type": "string"},
                                "expected_value": {"type": "string"},
                            },
                            "required": [
                                "filename_keyword",
                                "field",
                                "expected_value",
                            ],
                        },
                    },
                    "risk_level": {
                        "type": "string",
                        "enum": ["LOW", "MEDIUM", "HIGH"],
                    },
                    "safe_to_auto_apply": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": [
                    "rule_candidate_id",
                    "target_org",
                    "target_field",
                    "rule_kind",
                    "problem_summary",
                    "proposed_rule",
                    "expected_cases",
                    "risk_level",
                    "safe_to_auto_apply",
                    "reason",
                ],
            },
        },
    },
    "required": ["review_version", "summary", "candidates"],
}

SYSTEM_PROMPT = """
너는 할랄 인증서 OCR 규칙 리뷰어다.
SCANNED_NEED_OCR, NO_TEXT, TESSERACT_ERROR는 규칙 후보 생성 대상이 아니다.
이들은 OCR 오류 모니터링 또는 스캔본 처리 대상으로 분류한다.

target_org = ALL 규칙은 원칙적으로 제안하지 않는다.
cert_no_pattern_rule, date_anchor_rule, manufacturer_cleanup_rule은 반드시 기관별 target_org를 가져야 한다.
ALL 범위는 non_certificate_doc_rule에서만 제한적으로 허용한다.

역할:
- export.jsonl OCR 결과를 보고 규칙 후보 JSON만 생성한다.
- Python 코드를 직접 수정하지 않는다.
- 특정 파일명/제품명 하드코딩을 하지 않는다.
- 기관별 라벨, anchor, stop marker, OCR 날짜 정규화 등 일반화 가능한 규칙만 제안한다.

금지:
- 특정 업체명 하나만 맞추는 규칙 금지
- 특정 제품명 하나만 맞추는 규칙 금지
- 발급일을 유효기간으로 쓰는 fallback 금지
- cert_country와 manufacturing_country 혼동 금지
- 인정기관 목록에 등장하는 기관명을 cert_org로 오인하는 규칙 금지
- global date fallback 규칙 제안 금지

출력:
- 반드시 JSON Schema에 맞는 JSON만 반환한다.
- markdown, 코드블록, 설명 문장 금지.
"""


def get_openai_status() -> dict[str, Any]:
    return {"openai_api_key_configured": bool(os.getenv("OPENAI_API_KEY")), "model": DEFAULT_RULE_REVIEW_MODEL}


def get_ai_rule_review_status() -> dict[str, Any]:
    status = get_rule_storage_status()
    status.update(get_openai_status())
    return status

def get_problem_reasons(record: dict[str, Any]) -> list[str]:
    rule = get_certificate_rule(record)

    cert_org = str(rule.get("cert_org") or "")
    parse_status = str(rule.get("parse_status") or "")
    expiry_date = str(rule.get("expiry_date") or "")
    cert_no = str(rule.get("cert_no") or "")
    manufacturer = str(rule.get("manufacturer") or "")
    manufacturing_country = str(rule.get("manufacturing_country") or "")
    cert_country = str(rule.get("cert_country") or "")
    raw_text = str(record.get("raw_text") or "")
    raw_upper = raw_text.upper()

    reasons: list[str] = []

    if parse_status in {"MANUAL_REVIEW", "LOW_CONFIDENCE"}:
        reasons.append(f"규칙 판정 신뢰도 낮음: {parse_status}")

    if parse_status in {"TESSERACT_ERROR", "SCANNED_NEED_OCR", "NO_TEXT"}:
        reasons.append(f"OCR 원문 확인 필요: {parse_status}")

    if cert_org and cert_org != "UNKNOWN":
        if not cert_no or cert_no == "-":
            reasons.append("인증번호 누락")

        if cert_org != "BPJPH" and (not expiry_date or expiry_date == "-"):
            if any(x in raw_upper for x in ["VALID UNTIL", "EXPIRY DATE", "EXPIRED DATE", "VALID THROUGH"]):
                reasons.append("유효기간 라벨은 있으나 expiry_date 미추출")
            else:
                reasons.append("유효기간 누락")

        if not manufacturer or manufacturer == "-":
            reasons.append("제조사 누락")

        if not manufacturing_country or manufacturing_country == "-":
            reasons.append("제조국 누락")

        if not cert_country or cert_country == "-":
            reasons.append("인증국가 누락")

    if any(x in manufacturer.upper() for x in ["COMPANY NAME:", "ADDRESS:", "  "]) and len(manufacturer) > 40:
        reasons.append("제조사 값에 라벨/주소 꼬리 포함 가능")

    if cert_org == "UNKNOWN" and raw_text.strip():
        reasons.append("OCR 원문은 있으나 인증기관 UNKNOWN")

    return reasons

def is_rule_reviewable_problem_case(record: dict[str, Any]) -> bool:
    """
    AI 규칙 리뷰 대상 여부.
    OCR 자체가 실패한 건은 제외하고,
    raw_text가 있는 상태에서 기존 규칙이 일부 필드를 못 잡은 케이스만 대상으로 한다.
    """
    rule = get_certificate_rule(record)

    parse_status = str(rule.get("parse_status") or "").upper().strip()
    raw_text = str(record.get("raw_text") or "").strip()

    if parse_status in OCR_FAILURE_PARSE_STATUSES:
        return False

    if len(raw_text) < MIN_RULE_REVIEW_TEXT_LENGTH:
        return False

    reasons = get_problem_reasons(record)

    if not reasons:
        return False

    # OCR 실패성 사유만 있는 케이스는 제외
    joined = " / ".join(reasons)

    if "OCR 원문 확인 필요" in joined:
        return False

    return True

def compact_raw_text_for_ai(raw_text: str, max_chars: int = MAX_TEXT_CHARS_PER_CASE) -> str:
    """
    AI 규칙 후보 생성용 OCR 본문 축약.
    전체 raw_text 앞부분을 무작정 보내지 않고,
    규칙 판단에 필요한 라벨 주변만 잘라 토큰을 줄인다.
    """
    text = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)

    if len(text) <= max_chars:
        return text.strip()

    upper = text.upper()

    markers = [
        "VALID UNTIL",
        "EXPIRY DATE",
        "EXPIRED DATE",
        "VALID THROUGH",
        "CERTIFICATE NO",
        "CERTIFICATE NUMBER",
        "CERT. NO",
        "REGISTRATION NO",
        "COMPANY NAME",
        "NAME OF COMPANY",
        "MANUFACTURER",
        "MANUFACTURED BY",
        "FACTORY",
        "FACTORY ADDRESS",
        "PLANT NAME",
        "ADDRESS",
        "PRODUCT NAME",
        "NAME OF PRODUCTS",
        "PRODUCTTYPE",
        "EFFECTIVE FROM",
        "ISSUED ON",
        "ISSUED IN JAKARTA",
        "F.8.2",
    ]

    chunks: list[str] = []
    seen_ranges: list[tuple[int, int]] = []

    for marker in markers:
        start = 0

        while True:
            idx = upper.find(marker, start)

            if idx < 0:
                break

            left = max(0, idx - 180)
            right = min(len(text), idx + 520)

            # 중복 범위 방지
            overlap = any(not (right < a or left > b) for a, b in seen_ranges)

            if not overlap:
                seen_ranges.append((left, right))
                chunks.append(text[left:right].strip())

            start = idx + len(marker)

            if len("\n...\n".join(chunks)) >= max_chars:
                break

        if len("\n...\n".join(chunks)) >= max_chars:
            break

    if not chunks:
        return text[:max_chars].strip()

    compacted = "\n...\n".join(chunks)
    return compacted[:max_chars].strip()

def compact_case(record: dict[str, Any]) -> dict[str, Any]:
    rule = get_certificate_rule(record)
    raw_text = str(record.get("raw_text") or "")
    problem_reasons = get_problem_reasons(record)

    return {
        "filename": record.get("filename") or "",
        "source_type": record.get("source_type") or "",
        "source_id": record.get("source_id") or "",
        "status": record.get("status") or "",
        "cert_org": rule.get("cert_org") or "",
        "parse_status": rule.get("parse_status") or "",
        "cert_no": rule.get("cert_no") or "",
        "expiry_date": rule.get("expiry_date") or "",
        "manufacturer": rule.get("manufacturer") or "",
        "manufacturing_country": rule.get("manufacturing_country") or "",
        "cert_country": rule.get("cert_country") or "",
        "confidence": rule.get("confidence") or "",
        "problem_reasons": problem_reasons,
        "problem_summary": " / ".join(problem_reasons) if problem_reasons else "검토 필요",
        "raw_text_preview": compact_raw_text_for_ai(raw_text),
    }

def is_problem_case(record: dict[str, Any]) -> bool:
    return is_rule_reviewable_problem_case(record)

def problem_case_priority(case: dict[str, Any]) -> int:
    """
    AI에 먼저 보낼 문제 케이스 우선순위.
    BPJPH 유지확인 반복 같은 저위험 케이스보다
    실제 규칙 개선 가능성이 큰 케이스를 먼저 보낸다.
    """
    reasons = " / ".join(case.get("problem_reasons") or [])
    cert_org = str(case.get("cert_org") or "").upper()
    parse_status = str(case.get("parse_status") or "").upper()

    score = 0

    if "유효기간 라벨은 있으나 expiry_date 미추출" in reasons:
        score += 50

    if "인증번호 누락" in reasons:
        score += 35

    if "제조사 값에 라벨/주소 꼬리 포함 가능" in reasons:
        score += 30

    if "제조사 누락" in reasons:
        score += 25

    if "제조국 누락" in reasons:
        score += 20

    if cert_org == "UNKNOWN":
        score += 18

    if parse_status == "LOW_CONFIDENCE":
        score += 10

    if cert_org == "BPJPH" and parse_status == "BPJPH_MAINTENANCE_ONLY":
        score -= 20

    return score

def extract_problem_cases(
    export_path: str | Path | None = None,
    limit: int = 10000,
    max_cases: int = MAX_CASES_FOR_PROMPT,
) -> list[dict[str, Any]]:
    records = read_export_jsonl(export_path, limit=limit)

    cases: list[dict[str, Any]] = []
    seen_filenames: set[str] = set()

    for record in records:
        if not is_rule_reviewable_problem_case(record):
            continue

        filename = str(record.get("filename") or "").strip().lower()

        # 같은 파일의 과거/중복 job이 반복으로 들어가는 것 방지
        if filename and filename in seen_filenames:
            continue

        if filename:
            seen_filenames.add(filename)

        cases.append(compact_case(record))

    cases = sorted(cases, key=problem_case_priority, reverse=True)

    return cases[:max(1, int(max_cases or MAX_CASES_FOR_PROMPT))]

def build_user_prompt(cases: list[dict[str, Any]]) -> str:
    return json.dumps({
        "task": "다음 OCR 결과의 문제 케이스를 보고 일반화 가능한 규칙 후보를 생성하라.",
        "rule_candidate_constraints": {
            "allowed_rule_kind": [
                "date_anchor_rule",
                "manufacturer_cleanup_rule",
                "cert_no_pattern_rule",
                "non_certificate_doc_rule",
            ],
            "target_field_examples": [
                "expiry_date",
                "manufacturer",
                "cert_no",
                "parse_status",
            ],
            "proposed_rule_required_keys": [
                "anchors",
                "stop_before",
                "date_normalizers",
                "allow_filename_fallback",
                "window",
                "source_field",
                "cleanup_steps",
                "patterns",
                "markers",
            ],
            "proposed_rule_default_values": {
                "anchors": [],
                "stop_before": [],
                "date_normalizers": [],
                "allow_filename_fallback": False,
                "window": 650,
                "source_field": "",
                "cleanup_steps": [],
                "patterns": [],
                "markers": [],
            },
            "date_anchor_rule_schema": {
                "anchors": ["VALID UNTIL"],
                "stop_before": ["ISSUED IN JAKARTA", "F.8.2"],
                "date_normalizers": ["MONTH_DAY_SUFFIX_MULTILINE"],
                "allow_filename_fallback": False,
                "window": 650,
                "source_field": "",
                "cleanup_steps": [],
                "patterns": [],
                "markers": [],
            },
            "manufacturer_cleanup_rule_schema": {
                "anchors": [],
                "stop_before": [],
                "date_normalizers": [],
                "allow_filename_fallback": False,
                "window": 650,
                "source_field": "manufacturer",
                "cleanup_steps": ["REMOVE_LABEL_PREFIX", "STRIP_INLINE_ADDRESS_TAIL"],
                "patterns": [],
                "markers": [],
            },
            "cert_no_pattern_rule_schema": {
                "anchors": [],
                "stop_before": [],
                "date_normalizers": [],
                "allow_filename_fallback": False,
                "window": 650,
                "source_field": "",
                "cleanup_steps": [],
                "patterns": ["regex patterns with capture group"],
                "markers": [],
            },
            "non_certificate_doc_rule_schema": {
                "anchors": [],
                "stop_before": [],
                "date_normalizers": [],
                "allow_filename_fallback": False,
                "window": 650,
                "source_field": "",
                "cleanup_steps": [],
                "patterns": [],
                "markers": ["MSDS", "CERTIFICATION PROCESS IS CURRENTLY UNDERWAY"],
            },
        },
        "problem_cases": cases,
    }, ensure_ascii=False)


def call_openai_for_rule_candidates(
    cases: list[dict[str, Any]],
    model: str | None = None,
) -> dict[str, Any]:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY 환경변수가 설정되어 있지 않습니다.")

    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError(
            "openai 패키지가 설치되어 있지 않습니다. "
            "`conda install -c conda-forge openai` 또는 "
            "`python -m pip install openai` 후 다시 실행하세요."
        ) from e

    selected_model = model or DEFAULT_RULE_REVIEW_MODEL
    user_prompt = build_user_prompt(cases)

    selected_model = model or DEFAULT_RULE_REVIEW_MODEL
    user_prompt = build_user_prompt(cases)

    client = OpenAI()
    try:
        response = client.responses.create(
            model=selected_model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "ai_rule_review_output",
                    "schema": AI_RULE_REVIEW_JSON_SCHEMA,
                    "strict": True,
                }
            },
        )
    except Exception as e:
        msg = str(e)

        if (
            "rate_limit_exceeded" in msg
            or "Request too large" in msg
            or "tokens per min" in msg
        ):
            raise RuntimeError(
                "OpenAI 요청 크기가 현재 TPM 한도를 초과했습니다. "
                "AI 규칙 후보 생성의 max_cases를 10~20으로 낮추거나, "
                "MAX_TEXT_CHARS_PER_CASE를 500~700으로 줄인 뒤 다시 실행하세요."
            ) from e

        raise

    output_text = getattr(response, "output_text", "") or ""

    if not output_text:
        raise RuntimeError("OpenAI 응답에서 output_text를 찾지 못했습니다.")

    try:
        data = json.loads(output_text)
    except Exception as e:
        raise RuntimeError(
            f"OpenAI 응답 JSON 파싱 실패: {output_text[:1000]}"
        ) from e

    if not isinstance(data, dict):
        raise RuntimeError("OpenAI 응답이 JSON object가 아닙니다.")

    data.setdefault("review_version", "ai_rule_review_v1")
    data.setdefault("candidates", [])

    return data
def is_wildcard_org(value: str) -> bool:
    org = str(value or "").upper().strip()
    return org in {"", "ALL", "ANY", "*"}


def is_invalid_ai_rule_candidate(candidate: dict[str, Any]) -> bool:
    """
    AI가 생성한 후보 중 운영상 금지해야 할 광범위 후보를 차단한다.
    cert_no / expiry / manufacturer 계열은 기관별 규칙이어야 한다.
    """
    target_org = str(candidate.get("target_org") or "").upper().strip()
    target_field = str(candidate.get("target_field") or "").strip()
    rule_kind = str(candidate.get("rule_kind") or "").strip()

    if not is_wildcard_org(target_org):
        return False

    # ALL 허용은 비인증문서 분류 정도로 제한
    if rule_kind == "non_certificate_doc_rule" and target_field == "parse_status":
        return False

    return True


def sanitize_ai_rule_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []

    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue

        if is_invalid_ai_rule_candidate(candidate):
            continue

        cleaned.append(candidate)

    return cleaned


def is_wildcard_org(value: str) -> bool:
    org = str(value or "").upper().strip()
    return org in {"", "ALL", "ANY", "*"}


def sanitize_ai_rule_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    운영 원칙:
    - AI 규칙 후보는 기관별 규칙만 허용한다.
    - ALL / ANY / * 후보는 저장하지 않는다.
    """
    cleaned: list[dict[str, Any]] = []

    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue

        if is_wildcard_org(candidate.get("target_org")):
            continue

        cleaned.append(candidate)

    return cleaned

def analyze_export_with_ai(export_path: str | Path | None = None, limit: int = 10000, max_cases: int = MAX_CASES_FOR_PROMPT, model: str | None = None, save_candidates: bool = True) -> dict[str, Any]:
    cases = extract_problem_cases(export_path=export_path, limit=limit, max_cases=max_cases)
    if not cases:
        return {"ok": True, "message": "AI 규칙 후보 생성 대상 문제 케이스가 없습니다.", "problem_case_count": 0, "created_count": 0, "candidates": []}
    ai_result = call_openai_for_rule_candidates(cases=cases, model=model)
    raw_candidates = ai_result.get("candidates") or []
    candidates = sanitize_ai_rule_candidates(raw_candidates)
    
    created = []

    if save_candidates:
        created = create_rule_candidates(candidates, source="AI")
    else:
        created = candidates