"""테스트 공통 설정.

이 프로젝트의 런타임 경로는 기본값이 사내 공유폴더(UNC)와 D: 드라이브다.
테스트는 그것들에 붙지 않고 tmp 폴더만 쓴다. import 시점에 경로가 굳는 모듈이
있으므로 환경변수는 app을 import하기 전에 세팅해야 한다 — 그래서 autouse
픽스처가 아니라 모듈 로드 시점에 처리한다.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# app.core.config는 import 시점에 경로를 읽고 디렉토리를 만든다.
# 공유폴더를 건드리지 않도록 여기서 먼저 tmp 경로로 덮어쓴다.
_TEST_ROOT = Path(tempfile.mkdtemp(prefix="halal_web_test_"))

os.environ.setdefault("PMF_SOURCE_DIR", str(_TEST_ROOT / "pmf_source"))
os.environ.setdefault("HALAL_DOC_ROOT", str(_TEST_ROOT / "halal_docs"))
os.environ.setdefault("HALAL_RAW_MATERIAL_ROOT", str(_TEST_ROOT / "raw_material"))
os.environ.setdefault("HALAL_LOCAL_RAW_MATERIAL_ROOT", str(_TEST_ROOT / "raw_material"))

for _name in ("pmf_source", "halal_docs", "raw_material"):
    (_TEST_ROOT / _name).mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope="session")
def test_root() -> Path:
    """테스트 전용 임시 루트."""
    return _TEST_ROOT


@pytest.fixture(scope="session")
def pmf_fixture_path() -> Path | None:
    """실제 PMF 테스트 워크북. 없으면 None (해당 테스트는 skip)."""
    path = BACKEND_DIR / "tests" / "fixtures" / "active_pmf_test_copy.xlsm"
    return path if path.exists() else None
