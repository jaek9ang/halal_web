"""문자열 유사도 경로 회귀 테스트.

`rules/text.py`와 `rules/context.py`는 `difflib.SequenceMatcher`를 쓰면서
import를 빠뜨린 채로 있었다. 두 함수 모두 "완전일치" / "부분일치"일 때는 먼저
return하고 그 뒤에서야 SequenceMatcher로 떨어지기 때문에, 값이 일치하는 동안에는
아무 일도 일어나지 않고 **값이 어긋날 때만** NameError로 죽었다.
교차검증이 불일치를 잡아내야 하는 바로 그 순간에 죽는 모양이었다.

그래서 여기서는 "일치할 때"가 아니라 **"어긋날 때"**를 고정한다.
"""

from __future__ import annotations

from app.services.rules.context import _context_similarity, _context_text_match
from app.services.rules.products import best_product_match
from app.services.rules.text import similarity


def test_similarity_falls_through_to_sequence_matcher():
    """일치도 부분일치도 아닌 값 — SequenceMatcher까지 내려간다."""
    score = similarity("Nongshim Co., Ltd", "Acme Trading")
    assert 0.0 < score < 1.0


def test_context_similarity_falls_through_to_sequence_matcher():
    score = _context_similarity("NONGSHIM CO LTD", "XYZ TRADING")
    assert 0.0 < score < 1.0


def test_context_similarity_shortcuts_still_hold():
    assert _context_similarity("NONGSHIM", "NONGSHIM") == 1.0
    assert _context_similarity("", "NONGSHIM") == 0.0
    # 부분일치는 0.75 이상으로 가산된다.
    assert _context_similarity("NONGSHIM", "NONGSHIM CO LTD") >= 0.75


def test_context_text_match_scans_lines_when_expected_value_is_absent():
    """기대값이 원문에 없으면 줄 단위 비교로 내려간다 — 예전 크래시 경로."""
    raw_text = "CERTIFICATE OF HALAL\nISSUED TO ACME TRADING\nVALID UNTIL 2027-01-01"

    result = _context_text_match(raw_text, "NONGSHIM CO LTD")

    assert result["matched"] is False
    assert result["method"] == "LINE_SIMILARITY"


def test_context_text_match_finds_expected_value_in_raw_text():
    raw_text = "CERTIFICATE OF HALAL\nISSUED TO ACME TRADING\nVALID UNTIL 2027-01-01"

    result = _context_text_match(raw_text, "ACME TRADING")

    assert result["matched"] is True
    assert result["method"] == "NORMALIZED_SUBSTRING"


def test_best_product_match_scores_unrelated_product():
    """products.best_product_match도 같은 유사도 경로를 탄다."""
    result = best_product_match([{"name": "Acme Ramen Base"}], "ZZZ PRODUCT")

    assert result["score"] < 0.5
