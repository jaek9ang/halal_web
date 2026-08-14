"""API가 기동하고 GET 엔드포인트가 죽지 않는지 확인한다.

외부 의존(공유폴더, IMAP, OpenAI)이 없는 환경에서도 5xx로 터지지 않아야 한다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_health(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_openapi_schema_builds(client: TestClient):
    """라우터 시그니처가 깨지면 스키마 생성부터 실패한다."""
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["paths"]


# 외부 자원이 있어야만 응답하는 엔드포인트.
# PMF 공유폴더 / OCR export 파일이 없는 환경에서는 500을 던진다 — 알려진 동작이고,
# 이 목록은 "무엇이 환경에 묶여 있는가"의 기록이다. 늘리지 말 것.
EXTERNAL_DEPENDENT_PATHS = {
    "/pmf/summary",
    "/pmf/materials/search",
    "/suppliers/email-review",
    "/mail/targets",
    "/ai-rule-review/problem-cases",
}


def _parameterless_get_paths() -> list[str]:
    paths = set()

    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()

        if "GET" not in methods or "{" in path:
            continue

        if path.startswith(("/docs", "/redoc", "/openapi")):
            continue

        paths.add(path)

    return sorted(paths)


@pytest.mark.parametrize("path", _parameterless_get_paths())
def test_get_endpoint_does_not_crash(client: TestClient, path: str):
    """500은 허용하지 않는다.

    외부 자원이 없어 실패하는 것은 정상이지만, 이 프로젝트의 라우터는 그런 실패를
    `{"ok": false, "message": ...}`로 감싸도록 되어 있다. 500이 나오면 감싸지 못한
    예외가 새어나온 것이다.
    """
    response = client.get(path)

    if path in EXTERNAL_DEPENDENT_PATHS:
        # 응답 자체는 와야 한다. 라우팅이나 시그니처가 깨진 것과는 구분된다.
        assert response.status_code in (200, 500)
        return

    assert response.status_code < 500, f"{path} -> {response.status_code} {response.text[:300]}"


def test_no_duplicate_route_registrations():
    """같은 (method, path)가 두 번 등록되면 뒤엣것은 영원히 죽은 코드다.

    패치 스크립트가 핸들러를 반복 삽입해 실제로 이런 중복이 생긴 적이 있다.
    """
    seen: dict[tuple[str, str], int] = {}

    for route in app.routes:
        path = getattr(route, "path", "")
        for method in getattr(route, "methods", set()) or set():
            seen[(method, path)] = seen.get((method, path), 0) + 1

    duplicates = {key: count for key, count in seen.items() if count > 1}

    assert not duplicates, f"중복 등록된 라우트: {duplicates}"
