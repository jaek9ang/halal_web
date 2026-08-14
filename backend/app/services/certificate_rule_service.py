"""인증서 판독 규칙 — `app.services.rules` 패키지로 옮겼다.

한 파일 2,749줄이던 것을 계층별로 나눴다. 새 코드는 `app.services.rules`에서
직접 가져오고, 이 모듈은 기존 import 경로를 깨지 않기 위해 남겨둔다.

기관별 규칙을 고칠 때 보통 필요한 파일:
    rules/dates.py          유효기간·발급일 인식
    rules/organizations.py  발급기관 판별, 기관 별칭
    rules/core.py           인증번호 추출, 판독 진입점
    rules/context.py        메일·PMF 교차검증, 자동확정 안전 원칙
"""

from __future__ import annotations

from app.services.rules import *  # noqa: F401,F403
from app.services.rules import __all__  # noqa: F401
