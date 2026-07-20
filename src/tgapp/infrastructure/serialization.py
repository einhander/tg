from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
import zipfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import numpy as np


def to_json(data: Any) -> str:
    serializable = asdict(data) if is_dataclass(data) and not isinstance(data, type) else data
    sanitized = _json_safe(serializable)
    return json.dumps(sanitized, indent=2, default=str, allow_nan=False)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


# Plan-AUDIT §16.2: safe ZIP extraction constants
_MAX_ZIP_FILES = 500
_MAX_ZIP_UNPACKED = 200 * 1024 * 1024  # 200 MB


def _validate_zip_member(member_name: str) -> None:
    """Validate a single ZIP member name for path traversal attacks."""
    # Absolute path check
    if os.path.isabs(member_name):
        raise ValueError(f"Absolute path in archive: {member_name!r}")
    # Parent directory traversal check
    parts = member_name.replace("\\", "/").split("/")
    for part in parts:
        if part == "..":
            raise ValueError(f"Parent directory traversal in archive: {member_name!r}")
    # Empty path or "." component
    if not parts or parts == [""]:
        raise ValueError(f"Empty or root path in archive: {member_name!r}")


def pack_session_directory(session_dir: Path, archive_path: Path) -> Path:
    """Pack session directory into ZIP with file count and size limits (PLAN_AUDIT §16.3)."""
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    file_count = 0
    total_size = 0
    with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(session_dir.rglob("*")):
            if path.is_file():
                file_count += 1
                total_size += path.stat().st_size
                if file_count > _MAX_ZIP_FILES:
                    raise ValueError(
                        f"Session directory contains too many files ({file_count} > {_MAX_ZIP_FILES})"
                    )
                if total_size > _MAX_ZIP_UNPACKED:
                    raise ValueError(
                        f"Session directory total size exceeds limit ({total_size} > {_MAX_ZIP_UNPACKED})"
                    )
                archive.write(path, arcname=path.relative_to(session_dir))
    return archive_path


def unpack_session_archive(archive_path: Path, destination_dir: Path) -> Path:
    """Safely unpack a session archive (PLAN_AUDIT §16.2).

    - Validates all member names (no absolute paths, no ``..``, no symlinks)
    - Limits total file count and uncompressed size
    - Extracts to a temporary directory first
    - Validates expected structure
    - Atomically moves to destination
    """
    destination_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, mode="r") as archive:
        # 1. Validate all member names before extracting anything
        namelist = archive.namelist()
        file_count = 0
        total_size = 0
        for member in namelist:
            _validate_zip_member(member)
            member_info = archive.getinfo(member)
            # Symlink check via external_attr (Unix symlink = 0o120000 << 16)
            if member_info.external_attr >> 16 == 0o120000:
                raise ValueError(f"Symlink in archive: {member!r}")
            if member_info.is_dir():
                continue
            file_count += 1
            total_size += member_info.file_size
            if file_count > _MAX_ZIP_FILES:
                raise ValueError(
                    f"Archive contains too many files ({file_count} > {_MAX_ZIP_FILES})"
                )
            if total_size > _MAX_ZIP_UNPACKED:
                raise ValueError(
                    f"Archive uncompressed size exceeds limit ({total_size} > {_MAX_ZIP_UNPACKED})"
                )

        # 2. Extract to temporary directory first
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            archive.extractall(tmp_path)

            # 3. Validate expected structure — at least one thermogram or correction file
            extracted = list(tmp_path.rglob("*.csv"))
            if not extracted:
                raise ValueError(
                    "Invalid session archive: no CSV files found after extraction"
                )

            # 4. Atomically move to destination
            if destination_dir.exists():
                shutil.rmtree(destination_dir)
            shutil.move(str(tmp_path), str(destination_dir))

    return destination_dir


def clone_session_directory(source_dir: Path, destination_dir: Path) -> Path:
    if destination_dir.exists():
        shutil.rmtree(destination_dir)
    shutil.copytree(source_dir, destination_dir)
    return destination_dir
