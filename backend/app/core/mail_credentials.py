"""메일 계정 자격증명을 한 곳에서 읽는다.

같은 Daum 계정 하나를 위해 환경변수 이름이 24종까지 늘어나 있었고, 같은 값을
`routers/mail.py`, `services/mail_service.py`, `services/mail_receive_service.py`가
각각 다른 우선순위로 읽었다. 이름 목록과 우선순위를 여기로 모은다.

기존 이름은 전부 계속 지원한다 — 이미 설정된 개발 PC를 깨뜨리지 않기 위해서다.
새로 설정한다면 `DAUM_EMAIL` / `DAUM_APP_PASSWORD`만 쓰면 된다.
"""

from __future__ import annotations

import os

EMAIL_ENV_NAMES = (
    "DAUM_IMAP_EMAIL",
    "DAUM_MAIL_EMAIL",
    "DAUM_EMAIL",
    "DAUM_SMTP_EMAIL",
    "MAIL_SENDER",
    "MAIL_EMAIL",
    "SMTP_USER",
    "SENDER_EMAIL",
)

PASSWORD_ENV_NAMES = (
    "DAUM_IMAP_PASSWORD",
    "DAUM_IMAP_PW",
    "DAUM_MAIL_PASSWORD",
    "DAUM_MAIL_PW",
    "DAUM_APP_PASSWORD",
    "DAUM_APP_PW",
    "DAUM_SMTP_PASSWORD",
    "DAUM_SMTP_PW",
    "DAUM_PASSWORD",
    "MAIL_PASSWORD",
    "MAIL_PW",
    "MAIL_APP_PASSWORD",
    "SMTP_PASSWORD",
    "SMTP_PW",
    "SENDER_PASSWORD",
)


def _first_usable(values) -> str:
    for value in values:
        text = str(value or "").strip()

        # Swagger UI가 문자열 필드 기본값으로 넣는 "string"은 값이 아니다.
        if text and text.lower() != "string":
            return text

    return ""


def resolve_mail_credential(
    req_email: str = "",
    req_password: str = "",
) -> tuple[str, str]:
    """요청에 실려온 값이 우선, 없으면 환경변수를 순서대로 본다."""
    email = _first_usable(
        [req_email, *(os.getenv(name, "") for name in EMAIL_ENV_NAMES)]
    )
    password = _first_usable(
        [req_password, *(os.getenv(name, "") for name in PASSWORD_ENV_NAMES)]
    )

    return email, password
