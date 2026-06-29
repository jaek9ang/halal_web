from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator


RUNTIME_NAMES = ("data", "output", "cache", "db")
BACKUP_MARKER = ".__onedrive_backup_"


def to_long_path(path: str | os.PathLike[str]) -> str:
    """Return a Windows extended-length path without changing the real location."""
    value = os.path.abspath(os.fspath(path))

    if os.name != "nt":
        return value

    if value.startswith("\\\\?\\"):
        return value

    if value.startswith("\\\\"):
        return "\\\\?\\UNC\\" + value[2:]

    return "\\\\?\\" + value


def display_path(path: str | os.PathLike[str]) -> str:
    value = os.fspath(path)
    if value.startswith("\\\\?\\UNC\\"):
        return "\\\\" + value[8:]
    if value.startswith("\\\\?\\"):
        return value[4:]
    return value


def same_path(left: str | os.PathLike[str], right: str | os.PathLike[str]) -> bool:
    return os.path.normcase(os.path.abspath(os.fspath(left))) == os.path.normcase(
        os.path.abspath(os.fspath(right))
    )


def find_project_root(explicit: str | None) -> Path:
    if explicit:
        root = Path(explicit).resolve()
        if not (root / "backend" / "app" / "main.py").exists():
            raise RuntimeError(f"halal_web 프로젝트 루트가 아닙니다: {root}")
        return root

    current = Path.cwd().resolve()
    candidates = [current, *current.parents]

    for candidate in candidates:
        if (candidate / "backend" / "app" / "main.py").exists():
            return candidate

    raise RuntimeError("--project-root로 halal_web 프로젝트 경로를 지정하세요.")


def iter_files(root: str) -> Iterator[tuple[str, str]]:
    """
    Yield (absolute_path, relative_path).

    os.scandir is called with the extended-length path so PowerShell/.NET의
    260자 경로 제한에 걸리는 파일도 열 수 있다.
    """

    def walk(current: str, relative_parts: tuple[str, ...]) -> Iterator[tuple[str, str]]:
        with os.scandir(to_long_path(current)) as entries:
            for entry in entries:
                name = entry.name
                absolute = os.path.join(current, name)
                next_parts = (*relative_parts, name)

                if entry.is_dir(follow_symlinks=False):
                    yield from walk(absolute, next_parts)
                elif entry.is_file(follow_symlinks=False):
                    yield absolute, os.path.join(*next_parts)

    yield from walk(os.path.abspath(root), ())


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()

    with open(to_long_path(path), "rb", buffering=1024 * 1024) as file:
        while True:
            chunk = file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)

    return digest.hexdigest().upper()


def stat_file(path: str) -> os.stat_result:
    return os.stat(to_long_path(path), follow_symlinks=False)


def copy_atomically(source: str, destination: str, retries: int = 3) -> tuple[str, int]:
    destination_dir = os.path.dirname(destination)
    os.makedirs(to_long_path(destination_dir), exist_ok=True)

    for attempt in range(1, retries + 1):
        source_before = stat_file(source)
        source_hash_before = sha256_file(source)

        temp = destination + f".__copy_{uuid.uuid4().hex}.tmp"
        try:
            with open(to_long_path(source), "rb", buffering=1024 * 1024) as src:
                with open(to_long_path(temp), "wb", buffering=1024 * 1024) as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
                    dst.flush()
                    os.fsync(dst.fileno())

            source_after = stat_file(source)
            source_hash_after = sha256_file(source)
            temp_hash = sha256_file(temp)

            source_stable = (
                source_before.st_size == source_after.st_size
                and source_before.st_mtime_ns == source_after.st_mtime_ns
                and source_hash_before == source_hash_after
            )

            if source_stable and source_hash_before == temp_hash:
                os.replace(to_long_path(temp), to_long_path(destination))
                try:
                    shutil.copystat(
                        to_long_path(source),
                        to_long_path(destination),
                        follow_symlinks=False,
                    )
                except OSError:
                    pass

                final_hash = sha256_file(destination)
                if final_hash != source_hash_before:
                    raise RuntimeError("최종 파일 SHA-256 재검증 실패")

                return final_hash, attempt
        finally:
            if os.path.exists(to_long_path(temp)):
                os.remove(to_long_path(temp))

        time.sleep(1)

    raise RuntimeError("원본이 계속 변하거나 복사된 바이트가 일치하지 않습니다.")


def remove_tree(path: str) -> None:
    def handle_remove_error(function, target, exc_info):
        try:
            os.chmod(to_long_path(target), stat.S_IWRITE)
            function(to_long_path(target))
        except Exception:
            raise exc_info[1]

    shutil.rmtree(to_long_path(path), onerror=handle_remove_error)


@dataclass
class FileResult:
    backup_name: str
    relative_path: str
    source_size: int | None
    archive_size: int | None
    source_hash: str
    archive_hash: str
    status: str
    repaired: bool
    error: str = ""


def verify_runtime_junctions(project_root: Path, destination_root: Path) -> list[str]:
    backend = project_root / "backend"
    checked: list[str] = []

    for name in RUNTIME_NAMES:
        logical = backend / name
        physical = destination_root / name

        if not logical.exists():
            raise RuntimeError(f"논리 런타임 경로가 없습니다: {logical}")
        if not physical.exists():
            raise RuntimeError(f"D 드라이브 경로가 없습니다: {physical}")

        resolved = logical.resolve()
        if not same_path(resolved, physical.resolve()):
            raise RuntimeError(
                f"Junction 대상 불일치: {logical} -> {resolved}, 예상: {physical}"
            )

        test_name = f"_long_path_verify_{uuid.uuid4().hex}.txt"
        logical_test = logical / test_name
        physical_test = physical / test_name

        logical_test.write_text("long path runtime verification", encoding="utf-8")

        if not physical_test.exists():
            logical_test.unlink(missing_ok=True)
            raise RuntimeError(f"Junction 쓰기 검증 실패: {logical}")

        logical_test.unlink(missing_ok=True)
        checked.append(f"{logical} -> {physical}")
        print(f"[OK] {logical} -> {physical}")

    return checked


def backup_directories(backend_root: Path) -> list[Path]:
    found: list[Path] = []

    for entry in backend_root.iterdir():
        if not entry.is_dir():
            continue

        if BACKUP_MARKER not in entry.name:
            continue

        prefix = entry.name.split(BACKUP_MARKER, 1)[0]
        if prefix in RUNTIME_NAMES:
            found.append(entry)

    return sorted(found, key=lambda value: value.name)


def verify_backup(
    backup: Path,
    archive_root: Path,
    repair: bool,
) -> list[FileResult]:
    archive = archive_root / backup.name
    archive.mkdir(parents=True, exist_ok=True)

    results: list[FileResult] = []
    files = list(iter_files(str(backup)))

    print(f"\n[{backup.name}] 파일 {len(files)}개")

    for index, (source, relative) in enumerate(files, start=1):
        destination = str(archive / relative)
        result = FileResult(
            backup_name=backup.name,
            relative_path=relative,
            source_size=None,
            archive_size=None,
            source_hash="",
            archive_hash="",
            status="PENDING",
            repaired=False,
        )

        try:
            source_stat = stat_file(source)
            result.source_size = source_stat.st_size
            result.source_hash = sha256_file(source)

            if os.path.exists(to_long_path(destination)):
                archive_stat = stat_file(destination)
                result.archive_size = archive_stat.st_size
                result.archive_hash = sha256_file(destination)

            if (
                result.source_size == result.archive_size
                and result.source_hash
                and result.source_hash == result.archive_hash
            ):
                result.status = "OK"
            elif repair:
                repaired_hash, attempts = copy_atomically(source, destination)
                archive_stat = stat_file(destination)

                result.archive_size = archive_stat.st_size
                result.archive_hash = repaired_hash
                result.repaired = True
                result.status = f"REPAIRED_{attempts}"

                if (
                    result.source_size != result.archive_size
                    or result.source_hash != result.archive_hash
                ):
                    raise RuntimeError("복구 후에도 크기 또는 SHA-256이 다릅니다.")
            else:
                result.status = "MISMATCH"

        except Exception as exc:
            result.status = "ERROR"
            result.error = f"{type(exc).__name__}: {exc}"

        results.append(result)

        if index % 100 == 0 or result.status not in {"OK"}:
            print(
                f"  {index}/{len(files)} "
                f"{result.status}: {relative}"
            )

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "PowerShell 5.1의 긴 경로 제한을 우회하여 OneDrive 런타임 백업과 "
            "D 드라이브 보관본을 SHA-256으로 검증합니다."
        )
    )
    parser.add_argument("--project-root")
    parser.add_argument(
        "--destination-root",
        default=r"D:\halal_web_runtime",
    )
    parser.add_argument(
        "--no-repair",
        action="store_true",
        help="불일치 보관본을 자동 재복사하지 않고 검사만 합니다.",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="모든 검증이 통과한 경우 OneDrive 임시 백업을 삭제합니다.",
    )
    args = parser.parse_args()

    if os.name != "nt":
        raise RuntimeError("이 도구는 Windows에서 실행해야 합니다.")

    project_root = find_project_root(args.project_root)
    backend_root = project_root / "backend"
    destination_root = Path(args.destination_root)
    archive_root = destination_root / "_onedrive_backup_archive"

    print("=== HALAL 긴 경로 백업 검증 ===")
    print(f"프로젝트: {project_root}")
    print(f"D 저장소: {destination_root}")
    print("")

    junctions = verify_runtime_junctions(project_root, destination_root)
    backups = backup_directories(backend_root)

    if not backups:
        print("OK_NO_BACKUPS_FOUND")
        return 0

    archive_root.mkdir(parents=True, exist_ok=True)

    all_results: list[FileResult] = []
    for backup in backups:
        all_results.extend(
            verify_backup(
                backup=backup,
                archive_root=archive_root,
                repair=not args.no_repair,
            )
        )

    errors = [item for item in all_results if item.status == "ERROR"]
    mismatches = [item for item in all_results if item.status == "MISMATCH"]
    repaired = [item for item in all_results if item.repaired]

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(project_root),
        "destination_root": str(destination_root),
        "junctions": junctions,
        "backup_count": len(backups),
        "file_count": len(all_results),
        "repaired_count": len(repaired),
        "mismatch_count": len(mismatches),
        "error_count": len(errors),
        "results": [asdict(item) for item in all_results],
    }

    report_path = destination_root / (
        f"backup_long_path_verification_{datetime.now():%Y%m%d_%H%M%S}.json"
    )
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )

    print("")
    print("=== 결과 ===")
    print(f"전체 파일 : {len(all_results)}")
    print(f"자동 복구 : {len(repaired)}")
    print(f"불일치    : {len(mismatches)}")
    print(f"오류      : {len(errors)}")
    print(f"보고서    : {report_path}")

    if errors or mismatches:
        print("BACKUP_VERIFICATION_FAILED")
        for item in [*errors[:10], *mismatches[:10]]:
            print(f"- {item.status}: {item.relative_path} / {item.error}")
        return 1

    print("OK_TO_DELETE_BACKUPS")

    if not args.delete:
        print(
            '삭제 명령: .\\.venv\\Scripts\\python.exe '
            '.\\backend\\scripts\\verify_long_path_backups.py --delete'
        )
        return 0

    confirmation = input("OneDrive 임시 백업을 삭제하려면 DELETE 입력: ").strip()
    if confirmation != "DELETE":
        print("삭제를 취소했습니다.")
        return 2

    for backup in backups:
        remove_tree(str(backup))
        if os.path.exists(to_long_path(backup)):
            raise RuntimeError(f"백업 삭제 실패: {backup}")
        print(f"삭제 완료: {backup.name}")

    print("BACKUPS_DELETED_OK")
    print(f"D 보관본 유지: {archive_root}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n사용자가 중단했습니다.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
