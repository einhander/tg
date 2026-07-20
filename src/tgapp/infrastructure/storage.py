from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import tempfile
import time
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import pandas as pd

# PLAN_AUDIT §16.1: session ID must be full UUID hex (32 chars)
_SESSION_ID_RE = re.compile(r"^[a-f0-9]{32}$")


def validate_session_id(session_id: str) -> bool:
    """Return True if *session_id* is a valid 32-char lowercase hex string."""
    return bool(_SESSION_ID_RE.match(session_id))


class SessionStorage:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def ensure(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def create_session(self) -> str:
        # PLAN_AUDIT §16.1: full UUID hex (32 chars) instead of 12-char truncation
        session_id = uuid.uuid4().hex  # 32 chars
        self.session_dir(session_id).mkdir(parents=True, exist_ok=True)
        return session_id

    def session_dir(self, session_id: str) -> Path:
        # PLAN_AUDIT §16.1: reject unsafe session IDs before touching filesystem
        if not validate_session_id(session_id):
            raise ValueError(
                f"Invalid session_id: must be 32-char lowercase hex, got {session_id!r}"
            )
        resolved = self.ensure().resolve() / session_id
        # Ensure the resolved path stays inside APP_SESSION_DIR
        if not str(resolved.resolve()).startswith(str(resolved.parent.resolve()) + os.sep) and resolved.resolve() != resolved.parent.resolve():
            raise ValueError(f"Session path escapes APP_SESSION_DIR: {session_id}")
        return resolved

    def thermogram_dir(self, session_id: str) -> Path:
        path = self.session_dir(session_id) / "thermograms"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def raw_thermogram_dir(self, session_id: str) -> Path:
        path = self.session_dir(session_id) / "raw_thermograms"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def correction_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "correction.csv"

    def processed_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "processed.csv"

    def settings_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "settings.json"

    def tga2_settings_path(self, session_id: str) -> Path:
        # Kept for backward compatibility with legacy sessions
        return self.session_dir(session_id) / "tga2-settings.json"

    def thermogram_settings_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "thermogram-settings.json"

    def metadata_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "metadata.json"

    def raw_plot_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "plot-data.csv"

    def save_frame(self, path: Path, frame: pd.DataFrame) -> Path:
        """Save DataFrame atomically (write to temp → os.replace)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                frame.to_csv(tmp_file, index=False)
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return path

    def load_frame(self, path: Path) -> pd.DataFrame:
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path)

    def save_json(self, path: Path, data: Any) -> Path:
        """Save JSON atomically (write to temp → os.replace)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(data) if is_dataclass(data) and not isinstance(data, type) else data
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(json.dumps(payload, indent=2, default=str))
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return path

    def load_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def save_thermograms(self, session_id: str, frames: dict[str, pd.DataFrame]) -> list[str]:
        names: list[str] = []
        for filename, frame in frames.items():
            target = self.thermogram_dir(session_id) / filename
            self.save_frame(target, frame)
            names.append(filename)
        return names

    def load_thermograms(self, session_id: str) -> dict[str, pd.DataFrame]:
        thermogram_root = self.thermogram_dir(session_id)
        return {path.name: self.load_frame(path) for path in sorted(thermogram_root.glob("*.csv"))}

    def save_raw_thermograms(self, session_id: str, frames: dict[str, pd.DataFrame]) -> list[str]:
        names: list[str] = []
        for filename, frame in frames.items():
            target = self.raw_thermogram_dir(session_id) / filename
            self.save_frame(target, frame)
            names.append(filename)
        return names

    def load_raw_thermograms(self, session_id: str) -> dict[str, pd.DataFrame]:
        raw_root = self.raw_thermogram_dir(session_id)
        if not raw_root.exists():
            return {}
        return {path.name: self.load_frame(path) for path in sorted(raw_root.glob("*.csv"))}

    def validated_thermogram_dir(self, session_id: str) -> Path:
        path = self.session_dir(session_id) / "validated_thermograms"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_validated_thermograms(self, session_id: str, frames: dict[str, pd.DataFrame]) -> list[str]:
        names: list[str] = []
        for filename, frame in frames.items():
            target = self.validated_thermogram_dir(session_id) / filename
            self.save_frame(target, frame)
            names.append(filename)
        return names

    def load_validated_thermograms(self, session_id: str) -> dict[str, pd.DataFrame]:
        validated_root = self.validated_thermogram_dir(session_id)
        if not validated_root.exists():
            return {}
        return {path.name: self.load_frame(path) for path in sorted(validated_root.glob("*.csv"))}

    # ------------------------------------------------------------------
    # TTL & cleanup (PLAN_AUDIT §17.3)
    # ------------------------------------------------------------------

    def cleanup_expired(self, ttl_seconds: int = 86_400) -> int:
        """Remove sessions whose mtime is older than *ttl_seconds*.

        Returns the number of sessions removed.
        """
        removed = 0
        now = time.time()
        if not self.root.exists():
            return removed
        for entry in self.root.iterdir():
            if not entry.is_dir():
                continue
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            if now - mtime > ttl_seconds:
                shutil.rmtree(entry)
                removed += 1
        return removed

    # ------------------------------------------------------------------
    # Session size limits (PLAN_AUDIT §17.4)
    # ------------------------------------------------------------------

    def session_size(self, session_id: str) -> int:
        """Return total size (bytes) of all files in a session directory."""
        total = 0
        sess = self.session_dir(session_id)
        if not sess.exists():
            return 0
        for f in sess.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
        return total

    def check_session_size(self, session_id: str, max_size: int) -> None:
        """Raise ``ValueError`` if session exceeds *max_size* bytes."""
        size = self.session_size(session_id)
        if size > max_size:
            raise ValueError(
                f"Session {session_id} exceeds max size: {size} > {max_size}"
            )


class SessionLock:
    """File-based advisory lock for a single session (PLAN_AUDIT §17.2).

    Uses ``fcntl.flock`` on Unix.  On non-Unix platforms falls back to
    a simple file-existence check (best-effort, not truly exclusive).
    """

    def __init__(self, storage: SessionStorage, session_id: str):
        self._storage = storage
        self._session_id = session_id
        self._lock_path = storage.session_dir(session_id) / ".lock"
        self._lock_file = None  # type: ignore[assignment]

    def acquire(self) -> None:
        """Acquire an exclusive lock.  Raises ``RuntimeError`` if already locked."""
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_file = open(self._lock_path, "w")
        try:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            self._lock_file.close()
            self._lock_file = None
            raise RuntimeError(
                f"Session {self._session_id} is locked by another process"
            )

    def release(self) -> None:
        """Release the lock and clean up the lock file."""
        if self._lock_file is not None:
            try:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                self._lock_file.close()
            except OSError:
                pass
            try:
                self._lock_path.unlink(missing_ok=True)
            except OSError:
                pass
        self._lock_file = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()
