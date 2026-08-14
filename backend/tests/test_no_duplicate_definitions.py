"""같은 모듈에서 같은 이름을 두 번 정의하지 않는지 확인한다.

패치 스크립트로 소스를 고치던 시절, 같은 함수·클래스가 한 파일에 2~3번 붙여넣어진
채로 남았다. 파이썬은 마지막 정의만 남기므로 앞의 것은 조용히 죽은 코드가 되고,
Pydantic 모델에서는 필드가 사라져 실제 500 에러로 이어졌다.

한 번 청소했고, 다시 쌓이지 않게 이 테스트로 막는다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "app"

PYTHON_FILES = sorted(APP_DIR.rglob("*.py"))


def _duplicate_names(tree: ast.Module) -> list[tuple[str, int, int]]:
    """(이름, 앞선 정의 줄, 나중 정의 줄) 목록. 같은 스코프만 본다."""
    duplicates: list[tuple[str, int, int]] = []

    def scan(body: list[ast.stmt]) -> None:
        seen: dict[str, int] = {}

        for node in body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in seen:
                    duplicates.append((node.name, seen[node.name], node.lineno))

                seen[node.name] = node.lineno
                scan(node.body)

    scan(tree.body)

    return duplicates


@pytest.mark.parametrize("path", PYTHON_FILES, ids=[str(p.relative_to(APP_DIR)) for p in PYTHON_FILES])
def test_no_duplicate_definitions(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))

    duplicates = _duplicate_names(tree)

    assert not duplicates, "\n".join(
        f"{path.relative_to(APP_DIR)}: {name} 이 line {first} 과 line {second} 에 중복 정의됨"
        for name, first, second in duplicates
    )
