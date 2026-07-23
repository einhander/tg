"""Serialization helpers for kinetics data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


def numpy_default(obj: Any) -> Any:
    """JSON serializer for numpy types."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    raise TypeError(
        f"Object of type {type(obj).__name__} is not JSON serializable"
    )


def save_npz_with_meta(
    path: Path,
    arrays: dict[str, np.ndarray],
    metadata: dict[str, Any] | None = None,
) -> None:
    """Save numpy arrays with metadata JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(str(path), **arrays)
    if metadata:
        (path.parent / "meta.json").write_text(
            json.dumps(metadata, default=numpy_default, indent=2)
        )


def load_npz_with_meta(
    path: Path,
) -> tuple[dict[str, np.ndarray], dict[str, Any] | None]:
    """Load numpy arrays and optional metadata."""
    npz = np.load(str(path))
    arrays = {key: npz[key] for key in npz.files}
    meta_path = path.parent / "meta.json"
    metadata = None
    if meta_path.exists():
        metadata = json.loads(meta_path.read_text())
    return arrays, metadata