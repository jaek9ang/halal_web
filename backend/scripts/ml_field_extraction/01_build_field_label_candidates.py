from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


SCHEMA_VERSION = "field_label_candidates_v1"
FIELD_NAMES = (
    "cert_no",
    "manufacturer",
    "manufacturing_country",
    "expiry_date",
    "products",
)
ORG_ALIASES = {
    "LLS-ISA": "ISA",
    "LLS ISA": "ISA",
    "HALALCONTROL": "HALAL CONTROL",
}
EMPTY_WORDS = {"", "-", "NONE", "NULL", "NAN", "NAT", "UNKNOWN"}
COMPANY_SUFFIX_RE = re.compile(
    r"\b(?:CO\.?|COMPANY|CORP\.?|CORPORATION|INC\.?|LTD\.?|LIMITED|LLC|"
    r"PTE\.?\s*LTD\.?|SDN\.?\s*BHD\.?|GMBH|B\.?V\.?|S\.?A\.?|PLC|AG)\b",
    re.I,
)
PAGE_MARKER_RE = re.compile(
    r"---\s*PAGE\s+(\d+)\s*\[[^\]]*\]\s*---",
    re.I,
)
WHITESPACE_RE = re.compile(r"\s+")
DATE_ISO_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")


@dataclass
class Evidence:
    found: bool
    page: int
    line_no: int
    line: str
    score: float
    method: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "page": self.page,
            "line_no": self.line_no,
            "line": self.line,
            "score": round(float(self.score), 4),
            "method": self.method,
        }


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, value: str) -> None:
        if value and value not in self.parent:
            self.parent[value] = value

    def find(self, value: str) -> str:
        self.add(value)
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        if not left or not right:
            return
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left != root_right:
            if root_left < root_right:
                self.parent[root_right] = root_left
            else:
                self.parent[root_left] = root_right


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean(value: Any) -> str:
    text = str(value or "").replace("\u00a0", " ").replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if text.upper() in EMPTY_WORDS:
        return ""
    return text


def normalize_org(value: Any) -> str:
    text = clean(value).upper().replace("_", " ")
    text = WHITESPACE_RE.sub(" ", text).strip()
    return ORG_ALIASES.get(text, text)


def norm_key(value: Any) -> str:
    text = clean(value).upper().replace("®", "").replace("™", "")
    text = re.sub(r"[^A-Z0-9가-힣]+", "", text)
    return text


def norm_words(value: Any) -> str:
    text = clean(value).upper().replace("®", "").replace("™", "")
    text = re.sub(r"[^A-Z0-9가-힣]+", " ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def similarity(left: Any, right: Any) -> float:
    left_key = norm_key(left)
    right_key = norm_key(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    if left_key in right_key or right_key in left_key:
        ratio = min(len(left_key), len(right_key)) / max(len(left_key), len(right_key))
        return 0.78 + 0.20 * ratio
    return SequenceMatcher(None, left_key, right_key).ratio()


def normalize_date(value: Any) -> str:
    text = clean(value)
    if not text:
        return ""
    match = re.search(r"\b(20\d{2})[-./](\d{1,2})[-./](\d{1,2})\b", text)
    if match:
        year, month, day = map(int, match.groups())
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return ""
    try:
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.isna(parsed):
            return ""
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return ""


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def read_pointer(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"포인터 파일이 없습니다: {path}")
    value = path.read_text(encoding="utf-8-sig").strip()
    if not value:
        raise ValueError(f"포인터 파일이 비어 있습니다: {path}")
    target = Path(value)
    if not target.exists():
        raise FileNotFoundError(f"포인터 대상이 없습니다: {target}")
    return target


def split_pages_and_lines(raw_text: str) -> list[tuple[int, int, str]]:
    text = clean(raw_text)
    if not text:
        return []

    matches = list(PAGE_MARKER_RE.finditer(text))
    page_chunks: list[tuple[int, str]] = []

    if matches:
        for index, match in enumerate(matches):
            page_no = int(match.group(1))
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            page_chunks.append((page_no, text[start:end].strip()))
    else:
        page_chunks.append((1, text))

    rows: list[tuple[int, int, str]] = []
    for page_no, chunk in page_chunks:
        for line_no, line in enumerate(chunk.splitlines(), start=1):
            cleaned = clean(line)
            if cleaned:
                rows.append((page_no, line_no, cleaned))
    return rows


def find_value_evidence(
    lines: list[tuple[int, int, str]],
    value: str,
    *,
    field: str,
    date_finder: Any = None,
) -> Evidence:
    value = clean(value)
    if not value:
        return Evidence(False, 0, 0, "", 0.0, "EMPTY")

    target_key = norm_key(value)
    best = Evidence(False, 0, 0, "", 0.0, "NOT_FOUND")

    for page_no, line_no, line in lines:
        line_key = norm_key(line)
        score = 0.0
        method = ""

        if field == "expiry_date" and date_finder is not None:
            try:
                dates = date_finder(line)
            except Exception:
                dates = []
            if any(clean(item.get("date")) == value for item in dates if isinstance(item, dict)):
                score = 1.0
                method = "PARSED_DATE_MATCH"

        if not score and target_key and target_key in line_key:
            score = 1.0 if target_key == line_key else 0.96
            method = "NORMALIZED_SUBSTRING"

        if not score and field == "manufacturer":
            score = similarity(value, line)
            method = "LINE_SIMILARITY"

        if not score and field == "products":
            score = similarity(value, line)
            method = "PRODUCT_LINE_SIMILARITY"

        if score > best.score:
            best = Evidence(score >= 0.72, page_no, line_no, line[:500], score, method)

    return best


def value_key(field: str, value: Any) -> str:
    if field == "expiry_date":
        return normalize_date(value)
    if field == "manufacturing_country":
        return norm_words(value)
    if field == "products":
        if isinstance(value, list):
            return "|".join(sorted(norm_key(item) for item in value if norm_key(item)))
        return norm_key(value)
    return norm_key(value)


def safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in [None, "", {}]:
        return []
    return [value]


def load_near_duplicate_groups(model_report_root: Path | None) -> tuple[UnionFind, dict[str, str]]:
    union_find = UnionFind()
    if model_report_root is None:
        return union_find, {}

    path = model_report_root / "14_near_duplicate_candidates.csv"
    if not path.exists():
        return union_find, {}

    try:
        frame = pd.read_csv(path, dtype=str).fillna("")
    except Exception:
        return union_find, {}

    for row in frame.itertuples(index=False):
        left = clean(getattr(row, "sha256_a", ""))
        right = clean(getattr(row, "sha256_b", ""))
        if left and right:
            union_find.union(left, right)

    roots: dict[str, str] = {}
    for value in list(union_find.parent):
        roots[value] = union_find.find(value)
    return union_find, roots


def load_pmf_entries(rule_module: Any) -> tuple[list[dict[str, Any]], str]:
    try:
        from app.services.pmf_service import read_pmf_bundle
        from app.services.supplier_service import clean as pmf_clean
        from app.services.supplier_service import get_full_row_data

        bundle = read_pmf_bundle()
        frame = bundle["df_raw"]
        entries: list[dict[str, Any]] = []

        for row_pos in range(len(frame)):
            row = frame.iloc[row_pos]
            supplier = pmf_clean(row.iloc[6]) if len(row) > 6 else ""
            main = get_full_row_data(row, 0) or {}
            material_no = pmf_clean(main.get("id"))

            for depth in range(5):
                selected = get_full_row_data(row, depth) or {}
                material_name = pmf_clean(selected.get("n"))
                if not material_name or material_name == "-":
                    continue

                entry = {
                    "row_pos": int(row_pos),
                    "depth": int(depth),
                    "material_no": clean(material_no),
                    "supplier": clean(supplier),
                    "material_name": clean(material_name),
                    "english_name": clean(selected.get("e")),
                    "maker": clean(selected.get("m")),
                    "maker_country": clean(selected.get("o")).upper(),
                    "org": normalize_org(selected.get("h")),
                    "cert_no": clean(selected.get("i")),
                    "expiry_date": normalize_date(selected.get("v")),
                }
                entry["cert_no_key"] = norm_key(entry["cert_no"])
                entry["maker_key"] = norm_key(entry["maker"])
                entry["material_key"] = norm_key(entry["material_name"])
                entry["english_key"] = norm_key(entry["english_name"])
                entries.append(entry)

        return entries, ""
    except Exception as exc:
        return [], f"PMF를 읽지 못해 PMF 교차검증 없이 진행했습니다: {exc}"


def score_pmf_entry(
    entry: dict[str, Any],
    *,
    institution: str,
    raw_text_key: str,
    file_name_key: str,
    extracted: dict[str, Any],
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    entry_org = normalize_org(entry.get("org"))
    if entry_org:
        if entry_org != institution:
            return -999, ["org:mismatch"]
        score += 12
        reasons.append("org:match")

    cert_key = norm_key(entry.get("cert_no"))
    extracted_cert_key = norm_key(extracted.get("cert_no"))
    if cert_key:
        if cert_key == extracted_cert_key:
            score += 150
            reasons.append("cert_no:exact_extracted")
        elif cert_key in raw_text_key:
            score += 130
            reasons.append("cert_no:exact_text")

    maker_key = norm_key(entry.get("maker"))
    extracted_maker = clean(extracted.get("manufacturer"))
    if maker_key:
        if maker_key in raw_text_key:
            score += 55
            reasons.append("maker:exact_text")
        maker_score = similarity(entry.get("maker"), extracted_maker)
        if maker_score >= 0.88:
            score += 45
            reasons.append("maker:similar_extracted")
        elif maker_score >= 0.72:
            score += 25
            reasons.append("maker:weak_similar")

    english_key = norm_key(entry.get("english_name"))
    material_key = norm_key(entry.get("material_name"))
    if english_key and english_key in raw_text_key:
        score += 65
        reasons.append("english_name:exact_text")
    if material_key and material_key in raw_text_key:
        score += 50
        reasons.append("material_name:exact_text")
    if english_key and english_key in file_name_key:
        score += 25
        reasons.append("english_name:filename")
    if material_key and material_key in file_name_key:
        score += 20
        reasons.append("material_name:filename")

    expiry = normalize_date(entry.get("expiry_date"))
    extracted_expiry = normalize_date(extracted.get("expiry_date"))
    if expiry and extracted_expiry and expiry == extracted_expiry:
        score += 25
        reasons.append("expiry:exact")

    return score, reasons


def rank_pmf_entries(
    entries: list[dict[str, Any]],
    *,
    institution: str,
    raw_text: str,
    file_name: str,
    extracted: dict[str, Any],
    limit: int = 5,
) -> list[dict[str, Any]]:
    raw_text_key = norm_key(raw_text)
    file_name_key = norm_key(file_name)
    ranked: list[dict[str, Any]] = []

    for entry in entries:
        score, reasons = score_pmf_entry(
            entry,
            institution=institution,
            raw_text_key=raw_text_key,
            file_name_key=file_name_key,
            extracted=extracted,
        )
        if score <= 12:
            continue
        row = {key: value for key, value in entry.items() if not key.endswith("_key")}
        row["score"] = int(score)
        row["reasons"] = reasons
        ranked.append(row)

    ranked.sort(key=lambda item: (-int(item["score"]), int(item["row_pos"]), int(item["depth"])))
    return ranked[:limit]


def pmf_match_is_strong(ranked: list[dict[str, Any]]) -> bool:
    if not ranked:
        return False
    top = ranked[0]
    top_score = int(top.get("score") or 0)
    second_score = int(ranked[1].get("score") or 0) if len(ranked) > 1 else 0
    reasons = set(top.get("reasons") or [])
    exact_identity = bool(
        {
            "cert_no:exact_extracted",
            "cert_no:exact_text",
            "english_name:exact_text",
        }
        & reasons
    )
    return bool(top_score >= 130 and (top_score - second_score >= 25 or exact_identity))


def choose_consensus(
    *,
    field: str,
    institution: str,
    source_values: dict[str, Any],
    evidence: Evidence,
    full_rule: dict[str, Any],
    pmf_strong: bool,
) -> dict[str, Any]:
    if field == "products":
        pmf_products = [clean(item) for item in safe_list(source_values.get("pmf")) if clean(item)]
        rule_products = []
        for source in ("full_rule", "conditional_rule"):
            rule_products.extend(
                clean(item)
                for item in safe_list(source_values.get(source))
                if clean(item)
            )
        rule_products = list(dict.fromkeys(rule_products))

        if pmf_strong and pmf_products:
            pmf_product = pmf_products[0]
            best_rule_score = max(
                [similarity(pmf_product, candidate) for candidate in rule_products] or [0.0]
            )
            if evidence.found and best_rule_score >= 0.82:
                return {
                    "value": [pmf_product],
                    "status": "AUTO_READY",
                    "reason": "강한 PMF 연결, 제품 후보와 본문 근거가 일치합니다.",
                    "agreeing_sources": ["pmf", "conditional_rule"],
                    "conflicting_values": [],
                }

        if rule_products:
            return {
                "value": rule_products,
                "status": "CANDIDATE_ONLY",
                "reason": "제품목록 후보가 생성되었으나 다품목·부속목록 가능성 때문에 검토가 필요합니다.",
                "agreeing_sources": ["full_rule", "conditional_rule"],
                "conflicting_values": [],
            }

        if pmf_products:
            return {
                "value": pmf_products,
                "status": "CANDIDATE_ONLY",
                "reason": "PMF 연결 제품은 있으나 인증서 제품목록 근거가 부족합니다.",
                "agreeing_sources": ["pmf"],
                "conflicting_values": [],
            }

        filename_products = [clean(item) for item in safe_list(source_values.get("filename")) if clean(item)]
        if filename_products:
            return {
                "value": filename_products,
                "status": "CANDIDATE_ONLY",
                "reason": "파일명 제품 후보만 존재합니다.",
                "agreeing_sources": ["filename"],
                "conflicting_values": [],
            }

        return {
            "value": [],
            "status": "MISSING_REQUIRED",
            "reason": "제품 후보가 없습니다.",
            "agreeing_sources": [],
            "conflicting_values": [],
        }

    grouped: dict[str, list[tuple[str, Any]]] = defaultdict(list)
    for source, raw_value in source_values.items():
        if field == "products":
            value = [clean(item) for item in safe_list(raw_value) if clean(item)]
            if not value:
                continue
        else:
            value = clean(raw_value)
            if not value:
                continue
        key = value_key(field, value)
        if key:
            grouped[key].append((source, value))

    if not grouped:
        if field == "expiry_date" and institution == "BPJPH":
            return {
                "value": [],
                "status": "MISSING_ALLOWED",
                "reason": "BPJPH는 운영상 만료일이 필수 항목이 아닙니다.",
                "agreeing_sources": [],
                "conflicting_values": [],
            }
        return {
            "value": [] if field == "products" else "",
            "status": "MISSING_REQUIRED",
            "reason": "추출 후보가 없습니다.",
            "agreeing_sources": [],
            "conflicting_values": [],
        }

    source_weights = {
        "pmf": 5,
        "full_rule": 4,
        "conditional_rule": 3,
        "filename": 2,
    }

    def group_score(item: tuple[str, list[tuple[str, Any]]]) -> tuple[int, int, str]:
        key, pairs = item
        weight = sum(source_weights.get(source, 1) for source, _ in pairs)
        return weight, len(pairs), key

    selected_key, selected_pairs = max(grouped.items(), key=group_score)
    selected_value = selected_pairs[0][1]
    agreeing_sources = [source for source, _ in selected_pairs]
    conflicting_values = []
    for key, pairs in grouped.items():
        if key == selected_key:
            continue
        conflicting_values.extend(
            {"source": source, "value": value}
            for source, value in pairs
        )

    blocking_flags = set(full_rule.get("blocking_quality_flags") or [])
    field_sources = full_rule.get("field_sources") or {}
    field_source = clean(field_sources.get(field))
    conflict = bool(conflicting_values)

    if conflict:
        status = "REVIEW_REQUIRED"
        reason = "출처 간 값이 서로 다릅니다."
    elif field == "cert_no":
        if evidence.score >= 0.95 and {"full_rule", "conditional_rule"}.issubset(set(agreeing_sources)) and "CERT_NO_MISSING" not in blocking_flags and "CERT_NO_OCR_UNCERTAIN" not in blocking_flags:
            status = "AUTO_READY"
            reason = "두 추출 경로와 본문 근거가 일치합니다."
        elif pmf_strong and "pmf" in agreeing_sources and evidence.found:
            status = "AUTO_READY"
            reason = "PMF, 추출값, 본문 근거가 일치합니다."
        else:
            status = "CANDIDATE_ONLY"
            reason = "인증번호 후보는 있으나 자동 학습 기준을 충족하지 못했습니다."
    elif field == "manufacturer":
        company_like = bool(COMPANY_SUFFIX_RE.search(clean(selected_value)))
        if pmf_strong and "pmf" in agreeing_sources and evidence.score >= 0.72:
            status = "AUTO_READY"
            reason = "강한 PMF 연결과 본문 제조사 근거가 일치합니다."
        elif evidence.score >= 0.90 and company_like and {"full_rule", "conditional_rule"}.issubset(set(agreeing_sources)) and "MANUFACTURER_UNRELIABLE" not in blocking_flags:
            status = "AUTO_READY"
            reason = "두 추출 경로와 회사명 형태, 본문 근거가 일치합니다."
        else:
            status = "CANDIDATE_ONLY"
            reason = "제조사 후보는 있으나 추가 교차검증이 필요합니다."
    elif field == "manufacturing_country":
        if pmf_strong and "pmf" in agreeing_sources:
            status = "AUTO_READY"
            reason = "PMF 제조국과 추출값이 일치합니다."
        elif evidence.score >= 0.95 and {"full_rule", "conditional_rule"}.issubset(set(agreeing_sources)):
            status = "AUTO_READY"
            reason = "두 추출 경로와 본문 국가명이 일치합니다."
        else:
            status = "CANDIDATE_ONLY"
            reason = "제조국 후보는 있으나 본문 또는 PMF 교차검증이 부족합니다."
    elif field == "expiry_date":
        filename_only = field_source.upper() == "FILENAME" or "EXPIRY_FROM_FILENAME" in set(full_rule.get("quality_flags") or [])
        if institution == "BPJPH" and not clean(selected_value):
            status = "MISSING_ALLOWED"
            reason = "BPJPH는 운영상 만료일이 필수 항목이 아닙니다."
        elif evidence.score >= 0.95 and {"full_rule", "conditional_rule"}.issubset(set(agreeing_sources)) and not filename_only and "EXPIRY_MISSING" not in blocking_flags:
            status = "AUTO_READY"
            reason = "두 추출 경로와 본문 날짜 근거가 일치합니다."
        elif pmf_strong and "pmf" in agreeing_sources and evidence.found:
            status = "AUTO_READY"
            reason = "PMF, 추출값, 본문 날짜 근거가 일치합니다."
        else:
            status = "CANDIDATE_ONLY"
            reason = "만료일 후보는 있으나 파일명 의존 또는 근거 부족으로 검토가 필요합니다."
    else:
        status = "CANDIDATE_ONLY"
        reason = "후보가 생성되었습니다."

    return {
        "value": selected_value,
        "status": status,
        "reason": reason,
        "agreeing_sources": agreeing_sources,
        "conflicting_values": conflicting_values,
    }


def conditional_extract(rule_module: Any, profile_module: Any, text: str, filename: str, institution: str) -> dict[str, Any]:
    cert_no, cert_no_candidates = rule_module.extract_cert_no(text, institution)
    expiry_date, expiry_candidates = rule_module.extract_expiry(text, filename, institution)
    manufacturer = rule_module.normalize_manufacturer_output(
        rule_module.extract_manufacturer(text, institution),
        institution,
    )
    manufacturing_country = rule_module.extract_manufacturing_country(text, institution)
    products = rule_module.finalize_product_candidates(
        rule_module.extract_products(text, institution)
    )

    try:
        cert_no, cert_source = profile_module.repair_cert_no(
            institution,
            text,
            cert_no,
            {},
        )
    except Exception:
        cert_source = "CONDITIONAL_RULE"

    try:
        manufacturer, manufacturer_source = profile_module.repair_manufacturer(
            institution,
            text,
            manufacturer,
        )
    except Exception:
        manufacturer_source = "CONDITIONAL_RULE"

    return {
        "cert_org": institution,
        "cert_no": clean(cert_no),
        "cert_no_candidates": safe_list(cert_no_candidates),
        "expiry_date": normalize_date(expiry_date),
        "expiry_candidates": safe_list(expiry_candidates),
        "manufacturer": clean(manufacturer),
        "manufacturing_country": clean(manufacturing_country).upper(),
        "products": [clean(item.get("name")) for item in products if clean(item.get("name"))],
        "cert_no_source": clean(cert_source),
        "manufacturer_source": clean(manufacturer_source),
    }


def filename_expiry(filename: str) -> str:
    return normalize_date(filename)


def filename_product_hint(filename: str, institution: str) -> str:
    base = Path(filename).stem
    base = re.sub(r"^[A-F0-9]{12}__", "", base, flags=re.I)
    base = re.sub(r"^\d+[_ .-]*", "", base)
    base = re.split(r"\[(?:" + re.escape(institution) + r")[^\]]*\]", base, flags=re.I)[0]
    base = re.split(r"-(?:" + re.escape(institution) + r")\b", base, flags=re.I)[0]
    base = re.sub(r"\([^)]*\)\s*$", "", base).strip(" _.-")
    return clean(base)


def create_html_report(summary: dict[str, Any], coverage: pd.DataFrame, review: pd.DataFrame, output_path: Path) -> None:
    cards = [
        ("문서", summary.get("total_documents", 0)),
        ("기관", summary.get("institution_count", 0)),
        ("AUTO_READY 필드", summary.get("auto_ready_field_count", 0)),
        ("검토 필드", summary.get("review_field_count", 0)),
        ("PMF 강한 연결", summary.get("strong_pmf_match_count", 0)),
        ("학습 예제", summary.get("training_ready_example_count", 0)),
    ]

    card_html = "".join(
        f"<div class='card'><div>{html.escape(str(label))}</div><div class='value'>{html.escape(str(value))}</div></div>"
        for label, value in cards
    )

    coverage_html = coverage.to_html(index=False, escape=True) if not coverage.empty else "<p>자료 없음</p>"
    review_preview = review.head(100).copy()
    review_html = review_preview.to_html(index=False, escape=True) if not review_preview.empty else "<p>검토 대상 없음</p>"

    html_text = f"""<!doctype html>
<html lang='ko'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>필드 학습 라벨 후보 보고서</title>
<style>
body {{ font-family: Arial, 'Malgun Gothic', sans-serif; margin: 28px; color: #1f2937; background: #f8fafc; }}
h1, h2 {{ margin-top: 0; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin:18px 0 26px; }}
.card, .section {{ background:white; border:1px solid #dbe3ec; border-radius:10px; padding:16px; }}
.section {{ margin:16px 0; overflow:auto; }}
.value {{ font-size:26px; font-weight:700; margin-top:6px; }}
table {{ border-collapse:collapse; width:100%; font-size:13px; }}
th, td {{ border-bottom:1px solid #e5e7eb; padding:7px; text-align:left; vertical-align:top; }}
.note {{ color:#64748b; font-size:14px; }}
</style>
</head>
<body>
<h1>필드 학습 라벨 후보 보고서</h1>
<p class='note'>기존 규칙, 기관 조건부 추출, OCR 본문 근거와 PMF를 교차검증한 약지도 데이터입니다. AUTO_READY도 운영 확정값이 아니라 학습 후보입니다.</p>
<div class='grid'>{card_html}</div>
<div class='section'><h2>기관별 필드 커버리지</h2>{coverage_html}</div>
<div class='section'><h2>검토 대상 미리보기</h2>{review_html}</div>
<div class='section'><h2>다음 단계</h2><p>검토 큐에서 라벨 오류와 누락을 정리한 뒤, 동일 제조사·갱신본을 같은 그룹으로 묶어 기관 조건부 필드 후보 순위 모델을 학습합니다.</p></div>
</body>
</html>"""
    output_path.write_text(html_text, encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="할랄 인증서 필드 학습 라벨 후보 생성")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--runtime-root", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    runtime_root = Path(args.runtime_root)
    backend_root = project_root / "backend"
    if not backend_root.exists():
        raise FileNotFoundError(f"backend 폴더가 없습니다: {backend_root}")
    sys.path.insert(0, str(backend_root))

    from app.services import certificate_rule_profile_service as profile_module
    from app.services import certificate_rule_service as rule_module

    ocr_report_root = read_pointer(runtime_root / "reports" / "latest_ocr_run.txt")
    manifest_path = ocr_report_root / "04_training_text_manifest.csv"
    if not manifest_path.exists():
        raise FileNotFoundError(f"OCR 학습 매니페스트가 없습니다: {manifest_path}")

    model_report_root: Path | None = None
    model_pointer = runtime_root / "reports" / "latest_model_training.txt"
    if model_pointer.exists():
        try:
            model_report_root = read_pointer(model_pointer)
        except Exception:
            model_report_root = None

    manifest = pd.read_csv(manifest_path, dtype=str).fillna("")
    required_columns = {"institution", "file_name", "pdf_path", "sha256", "final_status"}
    missing_columns = required_columns.difference(manifest.columns)
    if missing_columns:
        raise ValueError(f"OCR 매니페스트 필수 열 누락: {sorted(missing_columns)}")
    manifest = manifest[manifest["final_status"].str.upper() == "READY"].copy()
    if manifest.empty:
        raise ValueError("READY 상태 인증서가 없습니다.")

    duplicate_hashes = manifest[manifest.duplicated("sha256", keep=False)]
    if not duplicate_hashes.empty:
        raise ValueError("동일 SHA256 문서가 매니페스트에 중복되어 있습니다.")

    pmf_entries, pmf_warning = load_pmf_entries(rule_module)
    _, duplicate_roots = load_near_duplicate_groups(model_report_root)

    stamp = now_stamp()
    report_root = runtime_root / "reports" / f"field_label_candidates_{stamp}"
    report_root.mkdir(parents=True, exist_ok=False)

    document_rows: list[dict[str, Any]] = []
    field_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    pmf_rows: list[dict[str, Any]] = []
    group_rows: list[dict[str, Any]] = []
    auto_ready_documents: list[dict[str, Any]] = []
    training_examples: list[dict[str, Any]] = []
    conflict_rows: list[dict[str, Any]] = []

    cache_root = runtime_root / "text_cache" / "combined"

    for index, row in enumerate(manifest.itertuples(index=False), start=1):
        institution = normalize_org(row.institution)
        sha256 = clean(row.sha256).upper()
        file_name = clean(row.file_name)
        pdf_path = clean(row.pdf_path)
        cache_path = cache_root / f"{sha256}.json"
        if not cache_path.exists():
            raise FileNotFoundError(f"결합 텍스트 캐시가 없습니다: {cache_path}")

        payload = json.loads(cache_path.read_text(encoding="utf-8-sig"))
        raw_text = clean(payload.get("combined_text"))
        if not raw_text:
            raise ValueError(f"결합 텍스트가 비어 있습니다: {file_name}")

        full_rule = rule_module.parse_certificate_rule(
            raw_text=raw_text,
            filename=file_name,
            expected_org=institution,
        )
        conditional = conditional_extract(
            rule_module,
            profile_module,
            raw_text,
            file_name,
            institution,
        )

        full_products = [
            clean(item.get("name"))
            for item in safe_list(full_rule.get("product_candidates"))
            if isinstance(item, dict) and clean(item.get("name"))
        ]

        extracted_for_pmf = {
            "cert_no": conditional.get("cert_no") or full_rule.get("cert_no"),
            "manufacturer": conditional.get("manufacturer") or full_rule.get("manufacturer"),
            "expiry_date": conditional.get("expiry_date") or full_rule.get("expiry_date"),
        }
        pmf_ranked = rank_pmf_entries(
            pmf_entries,
            institution=institution,
            raw_text=raw_text,
            file_name=file_name,
            extracted=extracted_for_pmf,
            limit=5,
        )
        pmf_strong = pmf_match_is_strong(pmf_ranked)
        pmf_top = pmf_ranked[0] if pmf_ranked else {}

        for rank, candidate in enumerate(pmf_ranked, start=1):
            pmf_rows.append({
                "sha256": sha256,
                "institution": institution,
                "file_name": file_name,
                "rank": rank,
                **{key: value for key, value in candidate.items() if key != "reasons"},
                "reasons": " | ".join(candidate.get("reasons") or []),
                "is_strong": pmf_strong and rank == 1,
            })

        lines = split_pages_and_lines(raw_text)
        sources_by_field: dict[str, dict[str, Any]] = {
            "cert_no": {
                "full_rule": clean(full_rule.get("cert_no")),
                "conditional_rule": clean(conditional.get("cert_no")),
                "pmf": clean(pmf_top.get("cert_no")) if pmf_strong else "",
            },
            "manufacturer": {
                "full_rule": clean(full_rule.get("manufacturer")),
                "conditional_rule": clean(conditional.get("manufacturer")),
                "pmf": clean(pmf_top.get("maker")) if pmf_strong else "",
            },
            "manufacturing_country": {
                "full_rule": clean(full_rule.get("manufacturing_country")).upper(),
                "conditional_rule": clean(conditional.get("manufacturing_country")).upper(),
                "pmf": clean(pmf_top.get("maker_country")).upper() if pmf_strong else "",
            },
            "expiry_date": {
                "full_rule": normalize_date(full_rule.get("expiry_date")),
                "conditional_rule": normalize_date(conditional.get("expiry_date")),
                "pmf": normalize_date(pmf_top.get("expiry_date")) if pmf_strong else "",
                "filename": filename_expiry(file_name),
            },
            "products": {
                "full_rule": full_products,
                "conditional_rule": conditional.get("products") or [],
                "pmf": [clean(pmf_top.get("english_name") or pmf_top.get("material_name"))]
                if pmf_strong and clean(pmf_top.get("english_name") or pmf_top.get("material_name"))
                else [],
                "filename": [filename_product_hint(file_name, institution)],
            },
        }

        field_results: dict[str, dict[str, Any]] = {}
        for field in FIELD_NAMES:
            provisional_values = sources_by_field[field]
            provisional_nonempty = []
            source_order = ("pmf", "conditional_rule", "full_rule", "filename") if field == "products" else tuple(provisional_values)
            for source_name in source_order:
                value = provisional_values.get(source_name)
                if field == "products":
                    provisional_nonempty.extend(clean(item) for item in safe_list(value) if clean(item))
                elif clean(value):
                    provisional_nonempty.append(clean(value))
            provisional = provisional_nonempty[0] if provisional_nonempty else ""
            evidence = find_value_evidence(
                lines,
                provisional,
                field=field,
                date_finder=rule_module.find_dates,
            )
            selected = choose_consensus(
                field=field,
                institution=institution,
                source_values=provisional_values,
                evidence=evidence,
                full_rule=full_rule,
                pmf_strong=pmf_strong,
            )
            selected_value = selected["value"]
            if field == "products" and isinstance(selected_value, list):
                evidence_target = selected_value[0] if selected_value else ""
                evidence = find_value_evidence(
                    lines,
                    evidence_target,
                    field=field,
                    date_finder=rule_module.find_dates,
                )
            elif clean(selected_value) != provisional:
                evidence = find_value_evidence(
                    lines,
                    clean(selected_value),
                    field=field,
                    date_finder=rule_module.find_dates,
                )

            selected["evidence"] = evidence.to_dict()
            selected["sources"] = provisional_values
            field_results[field] = selected

            field_row = {
                "sha256": sha256,
                "institution": institution,
                "file_name": file_name,
                "pdf_path": pdf_path,
                "field": field,
                "candidate_value": json_text(selected_value) if field == "products" else clean(selected_value),
                "status": selected["status"],
                "reason": selected["reason"],
                "agreeing_sources": " | ".join(selected["agreeing_sources"]),
                "source_full_rule": json_text(provisional_values.get("full_rule")) if field == "products" else clean(provisional_values.get("full_rule")),
                "source_conditional_rule": json_text(provisional_values.get("conditional_rule")) if field == "products" else clean(provisional_values.get("conditional_rule")),
                "source_pmf": json_text(provisional_values.get("pmf")) if field == "products" else clean(provisional_values.get("pmf")),
                "source_filename": json_text(provisional_values.get("filename")) if field == "products" else clean(provisional_values.get("filename")),
                "conflicting_values": json_text(selected["conflicting_values"]),
                "evidence_found": evidence.found,
                "evidence_page": evidence.page,
                "evidence_line_no": evidence.line_no,
                "evidence_score": round(evidence.score, 4),
                "evidence_method": evidence.method,
                "evidence_line": evidence.line,
                "review_decision": "",
                "reviewed_value": "",
                "review_note": "",
            }
            field_rows.append(field_row)

            if selected["status"] not in {"AUTO_READY", "MISSING_ALLOWED"}:
                review_rows.append(field_row.copy())
            if selected["conflicting_values"]:
                conflict_rows.append(field_row.copy())

            if selected["status"] == "AUTO_READY":
                if field == "products":
                    for product in safe_list(selected_value):
                        product_evidence = find_value_evidence(
                            lines,
                            clean(product),
                            field="products",
                            date_finder=rule_module.find_dates,
                        )
                        training_examples.append({
                            "schema_version": SCHEMA_VERSION,
                            "sha256": sha256,
                            "institution": institution,
                            "validation_group": "",
                            "field": "product",
                            "label_value": clean(product),
                            "positive_page": product_evidence.page,
                            "positive_line_no": product_evidence.line_no,
                            "positive_line": product_evidence.line,
                            "evidence_score": round(product_evidence.score, 4),
                            "source": selected["agreeing_sources"],
                        })
                else:
                    training_examples.append({
                        "schema_version": SCHEMA_VERSION,
                        "sha256": sha256,
                        "institution": institution,
                        "validation_group": "",
                        "field": field,
                        "label_value": clean(selected_value),
                        "positive_page": evidence.page,
                        "positive_line_no": evidence.line_no,
                        "positive_line": evidence.line,
                        "evidence_score": round(evidence.score, 4),
                        "source": selected["agreeing_sources"],
                    })

        chosen_manufacturer = clean(field_results["manufacturer"].get("value"))
        manufacturer_group_key = norm_words(chosen_manufacturer)[:100]
        near_root = duplicate_roots.get(sha256, "")
        if near_root:
            validation_group = f"{institution}::NEAR::{near_root[:16]}"
        elif manufacturer_group_key:
            validation_group = f"{institution}::MAKER::{manufacturer_group_key}"
        else:
            validation_group = f"{institution}::DOC::{sha256[:16]}"

        for example in training_examples:
            if example["sha256"] == sha256 and not example["validation_group"]:
                example["validation_group"] = validation_group

        group_rows.append({
            "sha256": sha256,
            "institution": institution,
            "file_name": file_name,
            "manufacturer": chosen_manufacturer,
            "manufacturer_group_key": manufacturer_group_key,
            "near_duplicate_root": near_root,
            "validation_group": validation_group,
        })

        ready_labels = {
            field: result["value"]
            for field, result in field_results.items()
            if result["status"] == "AUTO_READY"
        }
        if ready_labels:
            auto_ready_documents.append({
                "schema_version": SCHEMA_VERSION,
                "sha256": sha256,
                "institution": institution,
                "file_name": file_name,
                "pdf_path": pdf_path,
                "validation_group": validation_group,
                "labels": ready_labels,
                "field_results": field_results,
                "pmf_match": pmf_top if pmf_strong else {},
            })

        statuses = {field: result["status"] for field, result in field_results.items()}
        document_rows.append({
            "sha256": sha256,
            "institution": institution,
            "file_name": file_name,
            "pdf_path": pdf_path,
            "text_length": len(raw_text),
            "page_count": int(payload.get("page_count") or 0),
            "ocr_page_count": int(payload.get("ocr_page_count") or 0),
            "mean_ocr_confidence": float(payload.get("mean_ocr_confidence") or 0.0),
            "full_rule_org": normalize_org(full_rule.get("cert_org")),
            "full_rule_parse_status": clean(full_rule.get("parse_status")),
            "full_rule_confidence": clean(full_rule.get("confidence")),
            "full_rule_quality_flags": " | ".join(full_rule.get("quality_flags") or []),
            "pmf_top_score": int(pmf_top.get("score") or 0),
            "pmf_top_margin": int(pmf_top.get("score") or 0) - int(pmf_ranked[1].get("score") or 0) if len(pmf_ranked) > 1 else int(pmf_top.get("score") or 0),
            "pmf_strong": pmf_strong,
            "pmf_row_pos": pmf_top.get("row_pos", ""),
            "pmf_depth": pmf_top.get("depth", ""),
            "pmf_material_no": pmf_top.get("material_no", ""),
            "pmf_material_name": pmf_top.get("material_name", ""),
            "pmf_english_name": pmf_top.get("english_name", ""),
            "pmf_maker": pmf_top.get("maker", ""),
            "validation_group": validation_group,
            **{f"{field}_status": statuses[field] for field in FIELD_NAMES},
            **{
                f"{field}_value": json_text(field_results[field]["value"])
                if field == "products"
                else clean(field_results[field]["value"])
                for field in FIELD_NAMES
            },
            "auto_ready_count": sum(status == "AUTO_READY" for status in statuses.values()),
            "review_required_count": sum(status not in {"AUTO_READY", "MISSING_ALLOWED"} for status in statuses.values()),
        })

        if index % 25 == 0 or index == len(manifest):
            print(f"[{index}/{len(manifest)}] 필드 후보 생성 완료")

    document_frame = pd.DataFrame(document_rows)
    field_frame = pd.DataFrame(field_rows)
    review_frame = pd.DataFrame(review_rows)
    pmf_frame = pd.DataFrame(pmf_rows)
    group_frame = pd.DataFrame(group_rows)
    conflict_frame = pd.DataFrame(conflict_rows)

    coverage_rows: list[dict[str, Any]] = []
    for (institution, field), group in field_frame.groupby(["institution", "field"], dropna=False):
        counts = Counter(group["status"].astype(str))
        total = len(group)
        coverage_rows.append({
            "institution": institution,
            "field": field,
            "documents": total,
            "auto_ready": counts.get("AUTO_READY", 0),
            "candidate_only": counts.get("CANDIDATE_ONLY", 0),
            "review_required": counts.get("REVIEW_REQUIRED", 0),
            "missing_required": counts.get("MISSING_REQUIRED", 0),
            "missing_allowed": counts.get("MISSING_ALLOWED", 0),
            "auto_ready_rate": round(counts.get("AUTO_READY", 0) / total, 4) if total else 0.0,
        })
    coverage_frame = pd.DataFrame(coverage_rows).sort_values(["institution", "field"])

    auto_ready_count = int((field_frame["status"] == "AUTO_READY").sum())
    review_count = int((~field_frame["status"].isin(["AUTO_READY", "MISSING_ALLOWED"])).sum())
    summary = {
        "schema_version": SCHEMA_VERSION,
        "run_id": stamp,
        "created_at": now_iso(),
        "project_root": str(project_root),
        "runtime_root": str(runtime_root),
        "ocr_report_root": str(ocr_report_root),
        "model_report_root": str(model_report_root or ""),
        "report_root": str(report_root),
        "total_documents": int(len(document_frame)),
        "institution_count": int(document_frame["institution"].nunique()),
        "field_count": int(len(field_frame)),
        "auto_ready_field_count": auto_ready_count,
        "review_field_count": review_count,
        "conflict_field_count": int(len(conflict_frame)),
        "strong_pmf_match_count": int(document_frame["pmf_strong"].astype(bool).sum()),
        "training_ready_example_count": int(len(training_examples)),
        "pmf_entry_count": int(len(pmf_entries)),
        "pmf_warning": pmf_warning,
        "status_counts": dict(Counter(field_frame["status"].astype(str))),
        "important_note": "AUTO_READY는 여러 출처와 본문 근거가 일치한 약지도 학습 후보이며 운영 확정값이 아닙니다.",
        "next_validation": "동일 제조사, 갱신본, 유사 문서는 validation_group 기준으로 같은 Fold에 배치해야 합니다.",
    }

    document_frame.to_csv(report_root / "01_document_candidates.csv", index=False, encoding="utf-8-sig")
    field_frame.to_csv(report_root / "02_field_candidates.csv", index=False, encoding="utf-8-sig")
    write_jsonl(report_root / "03_auto_ready_labels.jsonl", auto_ready_documents)
    review_frame.to_csv(report_root / "04_review_required.csv", index=False, encoding="utf-8-sig")
    coverage_frame.to_csv(report_root / "05_field_coverage_by_institution.csv", index=False, encoding="utf-8-sig")
    pmf_frame.to_csv(report_root / "06_pmf_match_candidates.csv", index=False, encoding="utf-8-sig")
    group_frame.to_csv(report_root / "07_group_assignments.csv", index=False, encoding="utf-8-sig")
    (report_root / "08_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    create_html_report(summary, coverage_frame, review_frame, report_root / "09_annotation_report.html")
    (report_root / "10_label_schema.json").write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "condition_field": "institution",
                "learning_targets": list(FIELD_NAMES),
                "derived_or_validation_fields": ["cert_country", "material_name", "english_name", "material_no"],
                "statuses": {
                    "AUTO_READY": "복수 출처와 본문 근거가 일치한 학습 후보",
                    "CANDIDATE_ONLY": "단일 또는 약한 근거 후보",
                    "REVIEW_REQUIRED": "출처 간 충돌",
                    "MISSING_REQUIRED": "필수 후보 없음",
                    "MISSING_ALLOWED": "기관 정책상 공란 허용",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_jsonl(report_root / "11_training_ready_field_examples.jsonl", training_examples)
    conflict_frame.to_csv(report_root / "12_source_conflicts.csv", index=False, encoding="utf-8-sig")

    latest_pointer = runtime_root / "reports" / "latest_field_label_candidates.txt"
    latest_pointer.write_text(str(report_root), encoding="utf-8")

    print("")
    print("필드 라벨 후보 생성 완료")
    print(f"문서 수          : {summary['total_documents']}")
    print(f"AUTO_READY 필드  : {summary['auto_ready_field_count']}")
    print(f"검토 필드        : {summary['review_field_count']}")
    print(f"충돌 필드        : {summary['conflict_field_count']}")
    print(f"강한 PMF 연결    : {summary['strong_pmf_match_count']}")
    print(f"학습 예제        : {summary['training_ready_example_count']}")
    if pmf_warning:
        print(f"주의              : {pmf_warning}")
    print(f"보고서            : {report_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
