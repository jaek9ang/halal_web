from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.filing_name_service import FilingNameInput, build_target_path, get_halal_raw_material_root

@dataclass(frozen=True)
class FilingPreview:
    ok: bool
    source_path: str
    target_root: str
    target_folder: str
    target_filename: str
    target_path: str
    folder_reused: bool
    target_exists: bool
    warnings: list[str]
    naming: dict[str, Any]
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class FilingResult:
    ok: bool
    status: str
    source_path: str
    target_path: str
    source_sha256: str
    target_sha256: str
    folder_created: bool
    folder_reused: bool
    copied_at: str
    warnings: list[str]
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()

def preview_certificate_filing(source_path: str | Path, naming_input: FilingNameInput, root: Path | None = None) -> FilingPreview:
    source = Path(source_path)
    target_root = root or get_halal_raw_material_root()
    names, target_path, folder_reused = build_target_path(naming_input, root=target_root)
    warnings: list[str] = []
    if not source.exists(): warnings.append("원본 파일이 존재하지 않습니다.")
    elif not source.is_file(): warnings.append("원본 경로가 파일이 아닙니다.")
    if target_path.exists(): warnings.append("동일한 대상 파일명이 이미 존재합니다.")
    return FilingPreview(
        ok=not warnings,
        source_path=str(source),
        target_root=str(target_root),
        target_folder=str(target_path.parent),
        target_filename=target_path.name,
        target_path=str(target_path),
        folder_reused=folder_reused,
        target_exists=target_path.exists(),
        warnings=warnings,
        naming=names.to_dict(),
    )

def append_filing_history(payload: dict[str, Any], history_path: Path | None = None) -> None:
    history_path = history_path or (Path(__file__).resolve().parents[2] / "data" / "filing" / "certificate_filing_history.jsonl")
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

def copy_certificate_atomically(source_path: str | Path, naming_input: FilingNameInput, root: Path | None = None, overwrite: bool = False) -> FilingResult:
    source = Path(source_path)
    preview = preview_certificate_filing(source, naming_input, root=root)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"원본 파일을 찾을 수 없습니다: {source}")

    target_path = Path(preview.target_path)
    target_folder = target_path.parent
    folder_created = not target_folder.exists()
    target_folder.mkdir(parents=True, exist_ok=True)
    source_hash = sha256_file(source)

    if target_path.exists():
        target_hash = sha256_file(target_path)
        if target_hash == source_hash:
            result = FilingResult(True, "DUPLICATE_SKIPPED", str(source), str(target_path), source_hash, target_hash, False, preview.folder_reused, datetime.now().isoformat(timespec="seconds"), ["동일한 파일이 이미 저장되어 있어 복사를 생략했습니다."])
            append_filing_history(result.to_dict())
            return result
        if not overwrite:
            raise FileExistsError(f"같은 파일명으로 다른 내용의 파일이 이미 존재합니다: {target_path}")

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".filing_", suffix=target_path.suffix, dir=target_folder, delete=False) as tf:
            temp_path = Path(tf.name)
        shutil.copy2(source, temp_path)
        if sha256_file(temp_path) != source_hash:
            raise IOError("복사된 임시 파일의 SHA-256이 원본과 일치하지 않습니다.")
        if target_path.exists() and overwrite:
            target_path.unlink()
        os.replace(temp_path, target_path)
        temp_path = None
        target_hash = sha256_file(target_path)
        if target_hash != source_hash:
            raise IOError("최종 저장 파일의 SHA-256이 원본과 일치하지 않습니다.")
        result = FilingResult(True, "COPIED", str(source), str(target_path), source_hash, target_hash, folder_created, preview.folder_reused, datetime.now().isoformat(timespec="seconds"), [])
        append_filing_history(result.to_dict())
        return result
    except Exception as exc:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        append_filing_history({"ok": False, "status": "ERROR", "source_path": str(source), "target_path": str(target_path), "error": str(exc), "created_at": datetime.now().isoformat(timespec="seconds")})
        raise
