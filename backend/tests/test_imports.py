"""모든 백엔드 모듈이 import되는지 확인한다.

모듈을 쪼개거나 옮기는 리팩토링에서 가장 먼저 깨지는 것이 import이고,
가장 싸게 잡히는 것도 import다. 이 테스트가 그 그물이다.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import app


def _module_names(package_name: str) -> list[str]:
    package = importlib.import_module(package_name)
    return sorted(
        name
        for _, name, _ in pkgutil.walk_packages(
            package.__path__,
            prefix=f"{package_name}.",
        )
    )


ROUTER_MODULES = _module_names("app.routers")
SERVICE_MODULES = _module_names("app.services")
ML_MODULES = _module_names("app.ml")


def test_package_layout_is_not_empty():
    assert ROUTER_MODULES, "app.routers에 모듈이 없다"
    assert SERVICE_MODULES, "app.services에 모듈이 없다"


@pytest.mark.parametrize("module_name", ROUTER_MODULES + SERVICE_MODULES + ML_MODULES)
def test_module_imports(module_name: str):
    importlib.import_module(module_name)


def test_app_main_imports_and_mounts_routes():
    from app.main import app as fastapi_app

    paths = {getattr(route, "path", "") for route in fastapi_app.routes}

    assert "/health" in paths

    for prefix in (
        "/pmf",
        "/suppliers",
        "/mail",
        "/lhln",
        "/ocr",
        "/ai-rule-review",
        "/certificate-filing",
        "/cert-template",
    ):
        assert any(path.startswith(prefix) for path in paths), f"{prefix} 라우트가 없다"


def test_no_backup_modules_in_source_tree():
    """백업 사본이 소스 트리로 다시 기어들어오는 것을 막는다.

    한때 app/services에 백업 사본 32개가 import 가능한 모듈명으로 놓여 있었다.
    """
    offenders = [
        name
        for name in ROUTER_MODULES + SERVICE_MODULES + ML_MODULES
        if any(token in name for token in ("_backup", "_broken", "_bak", "_old", "_copy"))
    ]

    assert not offenders, f"백업 사본이 소스 트리에 있다: {offenders}"
