"""인증서 판독 규칙 특성화(characterization) 테스트.

`certificate_rule_service`는 2,700줄이 넘고 기관별 규칙이 한 파일에 뭉쳐 있다.
그 파일을 쪼개거나 정리할 때 판독 결과가 바뀌지 않았음을 증명할 수단이 필요하다.

여기서는 고정 입력에 대한 현재 출력을 골든 파일로 박아두고 매 실행마다 비교한다.
"판독이 옳은가"를 묻는 테스트가 아니라 "판독이 달라졌는가"를 묻는 테스트다.

골든을 다시 만들려면 (동작이 의도적으로 바뀐 경우에만):
    UPDATE_CERTIFICATE_RULE_GOLDEN=1 pytest tests/test_certificate_rules.py
그리고 골든 diff를 반드시 눈으로 확인한다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.services.certificate_rule_service import detect_org, parse_certificate_rule
from tests.fixtures.certificate_samples import SAMPLES

GOLDEN_PATH = Path(__file__).parent / "fixtures" / "certificate_rules_golden.json"

# 실행 환경에 따라 달라지는 필드는 비교에서 뺀다.
VOLATILE_KEYS = {"text_length", "has_text"}


def _parse(filename: str, text: str) -> dict:
    result = parse_certificate_rule(text, filename=filename)

    return {key: value for key, value in sorted(result.items()) if key not in VOLATILE_KEYS}


def _current_snapshot() -> dict[str, dict]:
    return {case_id: _parse(filename, text) for case_id, filename, text in SAMPLES}


def _load_golden() -> dict[str, dict]:
    if not GOLDEN_PATH.exists():
        pytest.fail(
            f"골든 파일이 없다: {GOLDEN_PATH}\n"
            "UPDATE_CERTIFICATE_RULE_GOLDEN=1 pytest 로 생성한 뒤 내용을 확인하고 커밋할 것."
        )

    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def test_golden_is_current():
    """골든과 현재 출력이 같아야 한다."""
    current = _current_snapshot()

    if os.getenv("UPDATE_CERTIFICATE_RULE_GOLDEN"):
        GOLDEN_PATH.write_text(
            json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        pytest.skip("골든을 다시 생성했다. diff를 확인하고 커밋할 것.")

    golden = _load_golden()

    assert set(current) == set(golden), "샘플 목록이 골든과 다르다"

    for case_id in sorted(current):
        assert current[case_id] == golden[case_id], (
            f"[{case_id}] 판독 결과가 골든과 다르다.\n"
            f"golden : {json.dumps(golden[case_id], ensure_ascii=False, sort_keys=True)}\n"
            f"current: {json.dumps(current[case_id], ensure_ascii=False, sort_keys=True)}"
        )


@pytest.mark.parametrize("case_id,filename,text", SAMPLES, ids=[s[0] for s in SAMPLES])
def test_parse_never_raises(case_id: str, filename: str, text: str):
    """어떤 입력에서도 예외 없이 결과 dict를 돌려줘야 한다."""
    result = parse_certificate_rule(text, filename=filename)

    assert isinstance(result, dict)
    assert "parse_status" in result
    assert "cert_org" in result


def test_tesseract_failure_is_reported_not_parsed():
    """OCR 엔진 오류 텍스트를 인증서로 오독하지 않는다."""
    result = parse_certificate_rule(
        "[TESSERACT_ERROR] tesseract is not installed",
        filename="whatever.pdf",
    )

    assert result["ok"] is False
    assert result["parse_status"] == "TESSERACT_ERROR"
    assert result["cert_org"] == "UNKNOWN"


def test_detect_org_uses_filename_when_body_is_silent():
    """본문에 기관 표기가 없어도 파일명 힌트로 기관을 잡는다."""
    org, _country, _hits = detect_org("", filename="[BPJPH] 어떤원료.pdf")

    assert org == "BPJPH"
