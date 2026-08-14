"""SQLite 연결을 한 곳에서 만든다.

이전에는 서비스 13개가 각자 `sqlite3.connect`를 호출했고, 부모 디렉토리 생성 여부와
`row_factory` 설정이 파일마다 달랐다. 스키마(테이블 정의)는 계속 각 서비스가 소유하고,
여기서는 연결만 책임진다.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# 인증서 양식 DB는 OCR 실행 중 여러 스레드에서 오래 잡고 쓰기 때문에
# 다른 DB보다 넉넉한 설정이 필요하다.
WAL_PRAGMAS = (
    "PRAGMA busy_timeout = 60000",
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA temp_store = MEMORY",
)


def connect(
    db_path: Path | str,
    *,
    timeout: float = 5.0,
    check_same_thread: bool = True,
    pragmas: tuple[str, ...] = (),
) -> sqlite3.Connection:
    """DB 파일을 열고 행을 `sqlite3.Row`로 돌려주는 연결을 만든다.

    부모 디렉토리가 없으면 만든다 — 런타임 DB는 gitignore 대상이라
    새로 받은 작업본에는 `backend/db/`가 아예 없다.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        path,
        timeout=timeout,
        check_same_thread=check_same_thread,
    )
    conn.row_factory = sqlite3.Row

    for pragma in pragmas:
        conn.execute(pragma)

    return conn
