"""벤치마크 채점 정규화 테스트.

`scripts/benchmark/run_benchmark.py`의 채점은 두 축으로 낸다.

  strict     — 원본 방식. `.strip().lower()` 후 완전일치.
  normalized — 표기 차이(기관 별칭·국가 표기·날짜 형식·구두점)를 흡수한 뒤 비교.

normalized 축의 존재 이유는 Rule이 이미 정규화된 값을 뱉고 LLM은 원문 표기를 그대로
뱉기 때문이다. 그 차이를 실력 차이로 오독하지 않으려고 나눴다.

여기서 지켜야 할 성질은 하나다: **표기 차이만 접고 의미 차이는 남긴다.**
정규화가 조금씩 똑똑해지면 실제 오답까지 정답으로 접어버리는데, 그러면 채점기가
개선을 측정하는 게 아니라 개선을 만들어낸다. 아래 REAL_MISMATCHES가 그 방어선이다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "scripts" / "benchmark"

if str(BENCHMARK_DIR) not in sys.path:
    sys.path.insert(0, str(BENCHMARK_DIR))

# 벤치마크 스크립트는 백엔드 런타임이 아니라 실험 도구다. 의존성이 없는 개발 환경도
# 있으므로 여기서 걸러 전체 스위트를 깨뜨리지 않는다.
pytest.importorskip("fitz", reason="PyMuPDF 없음 — 벤치마크 스크립트 테스트 건너뜀")
pytest.importorskip("openai", reason="openai 없음 — 벤치마크 스크립트 테스트 건너뜀")

import run_benchmark as rb  # noqa: E402


FIELD_TO_SCHEMA_KEY = {label: key for label, key, _normalizer in rb.FIELD_SPECS}


def score_one(field: str, ground_truth: str, predicted: str) -> dict[str, bool]:
    """한 필드만 채점해 strict/normalized 결과를 돌려준다."""
    gt_row = {f"정답_{field}": ground_truth}
    llm_result = {FIELD_TO_SCHEMA_KEY[field]: predicted}
    fields = rb.score_document(gt_row, llm_result, low_conf=False)
    return {
        "strict": fields[field]["strict"]["llm"],
        "normalized": fields[field]["normalized"]["llm"],
    }


# 표기만 다르고 의미는 같다. strict는 틀리고 normalized는 맞아야 한다.
NOTATION_ONLY = [
    ("인증기관", "MUI", "Majelis Ulama Indonesia"),
    ("인증기관", "BPJPH", "Badan Penyelenggara Jaminan Produk Halal"),
    ("인증국가", "USA", "United States"),
    ("인증국가", "UK", "United Kingdom"),
    ("유효기간", "2027-02-28", "28 February 2027"),
    ("유효기간", "2027-02-28", "28/02/2027"),
    ("인증번호", "ID-123/456", "ID123456"),
    ("제조사", "Nongshim Co., Ltd", "Nongshim Co.,Ltd"),
]


# 의미가 다르다. 두 축 모두 틀려야 한다. 이 테스트가 채점기의 방어선이다.
REAL_MISMATCHES = [
    ("인증기관", "JAKIM", "MUIS"),
    ("인증기관", "MUI", "BPJPH"),
    ("인증기관", "ISA", "LLS-ISA"),
    ("인증국가", "USA", "MALAYSIA"),
    ("유효기간", "2027-02-28", "2026-02-28"),
    ("인증번호", "ID-123/456", "ID-123/457"),
    ("인증번호", "ID-123/456", "ID999999"),
    ("제조사", "Acme Foods", "Beta Trading"),
    ("제조사", "Acme Foods", ""),
]


@pytest.mark.parametrize(("field", "ground_truth", "predicted"), NOTATION_ONLY)
def test_notation_difference_is_absorbed_only_by_normalized(field, ground_truth, predicted):
    marks = score_one(field, ground_truth, predicted)
    assert marks["strict"] is False, "표기 차이는 strict 축에서는 오답으로 남아야 한다"
    assert marks["normalized"] is True


@pytest.mark.parametrize(("field", "ground_truth", "predicted"), REAL_MISMATCHES)
def test_real_mismatch_stays_wrong_on_both_axes(field, ground_truth, predicted):
    marks = score_one(field, ground_truth, predicted)
    assert marks["strict"] is False
    assert marks["normalized"] is False, "정규화가 실제 오답까지 접으면 채점기를 믿을 수 없다"


def test_identical_values_pass_both_axes():
    marks = score_one("제조사", "Acme Foods", "Acme Foods")
    assert marks["strict"] is True
    assert marks["normalized"] is True


def test_unknown_sentinel_counts_as_empty():
    """enum 스키마의 UNKNOWN은 '모름'이다. 빈 값과 다르게 채점하면 enum 쪽만 손해를 본다."""
    marks = score_one("인증기관", "", "UNKNOWN")
    assert marks["normalized"] is True


def test_enum_schema_rejects_values_outside_the_closed_set():
    model = rb.resolve_schema("enum")
    payload = {
        "cert_org": "Majelis Ulama Indonesia",  # 정규형은 MUI다
        "cert_country": "INDONESIA",
        "cert_no": "ID-1",
        "expiry_date": "",
        "manufacturer": "Acme",
        "manufacturing_country": "INDONESIA",
    }
    with pytest.raises(Exception):
        model(**payload)

    payload["cert_org"] = "MUI"
    assert model(**payload).cert_org == "MUI"


def test_enum_choices_come_from_the_rules_package():
    """보기 목록이 organizations.py와 갈라지면 LLM이 시스템에 없는 값을 고르게 된다."""
    from app.services.rules.organizations import ORG_ALIASES

    canonical = {org for org, _country, _aliases in ORG_ALIASES}
    assert canonical <= set(rb.ORG_CHOICES)
    assert rb.UNKNOWN in rb.ORG_CHOICES


def test_template_hint_is_skipped_unless_classification_is_trusted(tmp_path, monkeypatch):
    """틀린 힌트는 힌트 없음보다 나쁘다. AUTO_IMAGE가 아니면 힌트를 만들지 않는다."""
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    def fake_classify(path, **kwargs):
        return {"decision": "NO_REFERENCE", "predicted_org": "NO_REFERENCE", "score": 0.0}

    import app.services.cert_template_service as cert_template_service

    monkeypatch.setattr(cert_template_service, "classify_file_path", fake_classify)

    hint, diagnostic = rb.build_template_hint(pdf, "image")
    assert hint == ""
    assert diagnostic.startswith("LOW_CONFIDENCE")


def test_template_hint_is_built_for_trusted_classification(tmp_path, monkeypatch):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    def fake_classify(path, **kwargs):
        return {"decision": "AUTO_IMAGE", "predicted_org": "JAKIM", "score": 0.91}

    import app.services.cert_template_service as cert_template_service

    monkeypatch.setattr(cert_template_service, "classify_file_path", fake_classify)

    hint, diagnostic = rb.build_template_hint(pdf, "image")
    assert "JAKIM" in hint
    assert diagnostic.startswith("HINT:JAKIM")


def test_template_hint_skips_human_confirmed_decisions(tmp_path, monkeypatch):
    """사람이 확정한 판정을 힌트로 주면 정답을 알려주는 셈이다."""
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    def fake_classify(path, **kwargs):
        return {
            "decision": "AUTO_IMAGE",
            "predicted_org": "JAKIM",
            "score": 1.0,
            "feature_kind": "manual",
        }

    import app.services.cert_template_service as cert_template_service

    monkeypatch.setattr(cert_template_service, "classify_file_path", fake_classify)

    hint, diagnostic = rb.build_template_hint(pdf, "image")
    assert hint == ""
    assert diagnostic == "SKIPPED_MANUAL_DECISION"
