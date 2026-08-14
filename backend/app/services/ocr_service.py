"""OCR 실행 — `app.services.ocr` 패키지로 옮겼다.

기존 import 경로를 깨지 않기 위해 남겨둔 re-export shim이다."""

from __future__ import annotations

from app.services.ocr import *  # noqa: F401,F403
from app.services.ocr import __all__  # noqa: F401
