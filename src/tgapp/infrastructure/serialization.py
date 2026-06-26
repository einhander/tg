from __future__ import annotations

import json
import math
import shutil
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


def pack_session_directory(session_dir: Path, archive_path: Path) -> Path:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in session_dir.rglob("*"):
            if path.is_file():
                archive.write(path, arcname=path.relative_to(session_dir))
    return archive_path


def unpack_session_archive(archive_path: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, mode="r") as archive:
        archive.extractall(destination_dir)
    return destination_dir


def clone_session_directory(source_dir: Path, destination_dir: Path) -> Path:
    if destination_dir.exists():
        shutil.rmtree(destination_dir)
    shutil.copytree(source_dir, destination_dir)
    return destination_dir
