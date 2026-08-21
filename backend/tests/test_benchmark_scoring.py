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

import json
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


# ==========================================
# 에이전트 판독기
# ==========================================
# 에이전트는 OpenAI 없이도 배선을 검증할 수 있어야 한다. 아래 스텁은 도구 호출을
# 각본대로 돌려주고, 루프가 도구를 실제로 실행해 결과를 대화에 되먹이는지 본다.

import agent_reader as ar  # noqa: E402


class _StubFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _StubToolCall:
    def __init__(self, call_id: str, name: str, arguments: str) -> None:
        self.id = call_id
        self.function = _StubFunction(name, arguments)


class _StubMessage:
    def __init__(self, content=None, tool_calls=None) -> None:
        self.content = content
        self.tool_calls = tool_calls


class _StubResponse:
    def __init__(self, message) -> None:
        self.choices = [type("Choice", (), {"message": message})()]


class _StubCompletions:
    """각본대로 도구를 부르다가 소진되면 최종 답을 낸다."""

    def __init__(self, script, final_payload) -> None:
        self.script = list(script)
        self.final_payload = final_payload
        self.create_calls = 0
        self.parse_calls = 0
        self.last_messages = None
        self.saw_tools = None

    def create(self, *, model, messages, tools=None, **kwargs):
        self.create_calls += 1
        self.last_messages = messages
        self.saw_tools = tools
        if not self.script:
            return _StubResponse(_StubMessage(content="확인 끝"))
        round_calls = self.script.pop(0)
        return _StubResponse(_StubMessage(tool_calls=[
            _StubToolCall(f"call_{i}", name, json.dumps(arguments))
            for i, (name, arguments) in enumerate(round_calls)
        ]))

    def parse(self, *, model, messages, response_format=None, **kwargs):
        self.parse_calls += 1
        self.last_messages = messages
        return _StubResponse(_StubMessage(content=json.dumps(self.final_payload)))


class _StubClient:
    def __init__(self, script, final_payload) -> None:
        self.chat = type("Chat", (), {"completions": _StubCompletions(script, final_payload)})()



FINAL_PAYLOAD = {
    "cert_org": "JAKIM",
    "cert_country": "MALAYSIA",
    "cert_no": "JAKIM/S/14-12345",
    "expiry_date": "2027-02-28",
    "manufacturer": "Acme Foods Sdn Bhd",
    "manufacturing_country": "MALAYSIA",
}


@pytest.fixture()
def sample_pdf(tmp_path):
    fitz = pytest.importorskip("fitz")
    path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "HALAL CERTIFICATE - JAKIM", fontsize=14)
    doc.save(path)
    doc.close()
    return path


def test_agent_executes_tools_and_feeds_results_back(sample_pdf):
    script = [
        [("get_document_overview", {})],
        [("read_page_text", {"page": 1}), ("list_certification_organizations", {})],
    ]
    client = _StubClient(script, FINAL_PAYLOAD)

    result, trace = ar.run_agent(
        client, "stub-model", sample_pdf, rb.resolve_schema("enum"), max_iterations=6
    )

    assert result == FINAL_PAYLOAD
    assert trace["tool_calls"] == 3
    assert trace["call_sequence"] == [
        "get_document_overview", "read_page_text", "list_certification_organizations"
    ]
    assert trace["budget_exhausted"] is False

    # 도구 결과가 실제로 대화에 들어갔는지 — 껍데기만 도는 루프가 아님을 확인한다.
    tool_messages = [m for m in client.chat.completions.last_messages if m.get("role") == "tool"]
    assert len(tool_messages) == 3
    assert "HALAL CERTIFICATE - JAKIM" in " ".join(m["content"] for m in tool_messages)


def test_agent_stops_when_model_returns_no_tool_calls(sample_pdf):
    client = _StubClient([], FINAL_PAYLOAD)

    _result, trace = ar.run_agent(client, "stub-model", sample_pdf, rb.resolve_schema("enum"))

    assert trace["tool_calls"] == 0
    assert trace["iterations"] == 1
    assert client.chat.completions.parse_calls == 1


def test_agent_respects_tool_call_budget(sample_pdf):
    script = [[("get_document_overview", {})] * 5 for _ in range(4)]
    client = _StubClient(script, FINAL_PAYLOAD)

    _result, trace = ar.run_agent(
        client, "stub-model", sample_pdf, rb.resolve_schema("enum"),
        max_iterations=6, max_tool_calls=3,
    )

    assert trace["tool_calls"] == 3
    assert trace["budget_exhausted"] is True


def test_agent_respects_iteration_budget(sample_pdf):
    script = [[("get_document_overview", {})] for _ in range(20)]
    client = _StubClient(script, FINAL_PAYLOAD)

    _result, trace = ar.run_agent(
        client, "stub-model", sample_pdf, rb.resolve_schema("enum"),
        max_iterations=2, max_tool_calls=99,
    )

    assert trace["iterations"] == 2
    assert client.chat.completions.create_calls == 2


def test_agent_attaches_requested_page_images(sample_pdf):
    client = _StubClient([[("view_page_image", {"page": 1})]], FINAL_PAYLOAD)

    ar.run_agent(client, "stub-model", sample_pdf, rb.resolve_schema("enum"))

    user_messages = [
        m for m in client.chat.completions.last_messages
        if m.get("role") == "user" and isinstance(m.get("content"), list)
    ]
    image_parts = [
        part for m in user_messages for part in m["content"] if part.get("type") == "image_url"
    ]
    # 첫 페이지 사전 제공 1장 + 모델이 요청한 1장
    assert len(image_parts) == 2


def test_agent_survives_failing_tools(sample_pdf):
    client = _StubClient([[("read_page_text", {"page": 999})]], FINAL_PAYLOAD)

    result, trace = ar.run_agent(client, "stub-model", sample_pdf, rb.resolve_schema("enum"))

    assert result == FINAL_PAYLOAD
    assert trace["tool_calls"] == 1
    tool_messages = [m for m in client.chat.completions.last_messages if m.get("role") == "tool"]
    assert "범위 밖" in tool_messages[0]["content"]


def test_agent_has_no_tool_exposing_existing_pmf_values():
    """PMF 기존값을 보여주면 모델이 베껴 써서 미갱신 인증서를 놓친다.

    이 성질은 도구 목록이 늘어날 때 조용히 깨지기 쉬워서 테스트로 박아둔다.
    """
    names = {spec["function"]["name"] for spec in ar.TOOL_SPECS}
    forbidden = {"get_pmf_row", "get_existing_certificate", "get_current_values", "lookup_pmf"}
    assert names & forbidden == set()

    blob = " ".join(
        spec["function"]["name"] + spec["function"]["description"] for spec in ar.TOOL_SPECS
    )
    assert "PMF" not in blob


def test_agent_tools_are_all_read_only():
    names = {spec["function"]["name"] for spec in ar.TOOL_SPECS}
    write_prefixes = ("save_", "write_", "update_", "delete_", "confirm_", "apply_", "send_")
    assert not any(name.startswith(write_prefixes) for name in names)
