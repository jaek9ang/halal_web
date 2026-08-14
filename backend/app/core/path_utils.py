from __future__ import annotations

from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]


def to_backend_storage_path(path: str | Path) -> str:
    """절대경로를 backend 폴더 기준 상대경로 문자열로 바꾼다.

    운영 PC에서는 `backend/data`, `output`, `cache`, `db`가 D 드라이브를 가리키는
    junction이다. 그래서 같은 파일이 실행 시점에 따라 다른 절대경로로 나타난다.
    DB에는 항상 `data/...` 형태의 상대경로로 저장해 경로가 흔들리지 않게 한다.

    backend 아래로 정규화할 수 없으면 절대경로를 그대로 돌려준다.
    """
    candidate = Path(path)

    if not candidate.is_absolute():
        candidate = BACKEND_DIR / candidate

    resolved = candidate.resolve()
    backend_resolved = BACKEND_DIR.resolve()

    try:
        return resolved.relative_to(backend_resolved).as_posix()
    except ValueError:
        pass

    for folder_name in ("data", "output", "cache", "db"):
        physical_root = (BACKEND_DIR / folder_name).resolve()

        try:
            relative = resolved.relative_to(physical_root)
            return (Path(folder_name) / relative).as_posix()
        except ValueError:
            continue

    return resolved.as_posix()
