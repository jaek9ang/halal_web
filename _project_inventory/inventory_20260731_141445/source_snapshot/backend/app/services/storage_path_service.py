from __future__ import annotations

import os
import uuid
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path


DEFAULT_SHARED_RAW_MATERIAL_ROOT = (
    r"\\홍진우\공유\1) 인증심사관련\4. MUI HALAL"
    r"\2) HALAL 하부원료 서류\1)원재료"
)
DEFAULT_LOCAL_RAW_MATERIAL_ROOT = r"D:\halal_web_runtime\원재료"


@dataclass(frozen=True)
class StorageRootStatus:
    root: str
    mode: str
    shared_root: str
    fallback_root: str
    writable: bool
    warning: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _is_unc(path: Path) -> bool:
    return str(path).startswith("\\\\")


def _probe_writable(path: Path, *, create: bool) -> tuple[bool, str]:
    try:
        if create:
            path.mkdir(parents=True, exist_ok=True)

        if not path.exists():
            return False, "경로가 존재하지 않습니다."

        if not path.is_dir():
            return False, "경로가 폴더가 아닙니다."

        test_file = path / f".__storage_write_test_{uuid.uuid4().hex}.tmp"
        with test_file.open("x", encoding="utf-8") as file:
            file.write("storage write test")
        test_file.unlink(missing_ok=True)

        return True, ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


@lru_cache(maxsize=1)
def get_storage_root_status() -> StorageRootStatus:
    explicit_value = os.getenv("HALAL_RAW_MATERIAL_ROOT", "").strip()
    shared_value = os.getenv(
        "HALAL_SHARED_RAW_MATERIAL_ROOT",
        DEFAULT_SHARED_RAW_MATERIAL_ROOT,
    ).strip()
    fallback_value = os.getenv(
        "HALAL_LOCAL_RAW_MATERIAL_ROOT",
        DEFAULT_LOCAL_RAW_MATERIAL_ROOT,
    ).strip()

    shared_root = Path(shared_value)
    fallback_root = Path(fallback_value)

    candidates: list[tuple[str, Path, bool]] = []

    if explicit_value:
        explicit_root = Path(explicit_value)
        candidates.append(
            (
                "EXPLICIT",
                explicit_root,
                not _is_unc(explicit_root),
            )
        )

    if not explicit_value or str(Path(explicit_value)) != str(shared_root):
        candidates.append(("SHARED", shared_root, False))

    for mode, root, create in candidates:
        writable, _warning = _probe_writable(root, create=create)
        if writable:
            os.environ["HALAL_ACTIVE_RAW_MATERIAL_ROOT"] = str(root)
            os.environ["HALAL_STORAGE_MODE"] = mode
            return StorageRootStatus(
                root=str(root),
                mode=mode,
                shared_root=str(shared_root),
                fallback_root=str(fallback_root),
                writable=True,
            )

    writable, warning = _probe_writable(fallback_root, create=True)
    if not writable:
        raise RuntimeError(
            "공유폴더와 D드라이브 대체폴더를 모두 사용할 수 없습니다. "
            f"fallback={fallback_root}, error={warning}"
        )

    os.environ["HALAL_ACTIVE_RAW_MATERIAL_ROOT"] = str(fallback_root)
    os.environ["HALAL_STORAGE_MODE"] = "LOCAL_FALLBACK"

    return StorageRootStatus(
        root=str(fallback_root),
        mode="LOCAL_FALLBACK",
        shared_root=str(shared_root),
        fallback_root=str(fallback_root),
        writable=True,
        warning="공유폴더를 사용할 수 없어 D드라이브 대체폴더를 사용합니다.",
    )


def resolve_raw_material_root() -> Path:
    return Path(get_storage_root_status().root)


def reset_storage_root_cache() -> None:
    get_storage_root_status.cache_clear()
