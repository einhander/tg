"""Storage reliability tests — PLAN_AUDIT §17."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import pandas as pd
import pytest

from tgapp.infrastructure.storage import (
    SessionLock,
    SessionStorage,
    validate_session_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(storage: SessionStorage, session_id: str) -> Path:
    """Create a session directory and return its path."""
    d = storage.session_dir(session_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _touch_old(session_dir: Path, seconds_ago: int) -> None:
    """Set mtime of *session_dir* to *seconds_ago* seconds in the past."""
    old_time = time.time() - seconds_ago
    os.utime(session_dir, (old_time, old_time))


def _write_file(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 17.3  TTL cleanup
# ---------------------------------------------------------------------------

class TestCleanupExpired:
    """Tests for SessionStorage.cleanup_expired()."""

    def test_cleanup_removes_old_sessions(self, tmp_path: Path) -> None:
        storage = SessionStorage(tmp_path)
        old_id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        _make_session(storage, old_id)
        _touch_old(storage.session_dir(old_id), 100_000)  # ~27 hours

        removed = storage.cleanup_expired(ttl_seconds=86_400)
        assert removed == 1
        assert not storage.session_dir(old_id).exists()

    def test_cleanup_keeps_recent_sessions(self, tmp_path: Path) -> None:
        storage = SessionStorage(tmp_path)
        recent_id = "abababababababababababababababab"
        _make_session(storage, recent_id)
        # mtime is now (default), well within 24h TTL

        removed = storage.cleanup_expired(ttl_seconds=86_400)
        assert removed == 0
        assert storage.session_dir(recent_id).exists()

    def test_cleanup_handles_empty_root(self, tmp_path: Path) -> None:
        storage = SessionStorage(tmp_path)
        removed = storage.cleanup_expired(ttl_seconds=86_400)
        assert removed == 0

    def test_cleanup_handles_nonexistent_root(self) -> None:
        storage = SessionStorage("/tmp/does_not_exist_xyz123")
        removed = storage.cleanup_expired(ttl_seconds=86_400)
        assert removed == 0

    def test_cleanup_skips_files_in_root(self, tmp_path: Path) -> None:
        storage = SessionStorage(tmp_path)
        # Drop a plain file in root — should not crash
        (tmp_path / "random_file.txt").write_text("ignore")
        _make_session(storage, "cacacacacacacacacacacacacacacaca")
        _touch_old(storage.session_dir("cacacacacacacacacacacacacacacaca"), 100_000)

        removed = storage.cleanup_expired(ttl_seconds=86_400)
        assert removed == 1
        assert (tmp_path / "random_file.txt").exists()


# ---------------------------------------------------------------------------
# 17.4  Session size limits
# ---------------------------------------------------------------------------

class TestSessionSize:
    """Tests for SessionStorage.session_size() and check_session_size()."""

    def test_session_size_calculated_correctly(self, tmp_path: Path) -> None:
        storage = SessionStorage(tmp_path)
        sid = "d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0"
        d = _make_session(storage, sid)
        # Write a known 100-byte file
        _write_file(d / "data.bin", "x" * 100)
        # Write a known 50-byte file
        _write_file(d / "small.bin", "y" * 50)

        size = storage.session_size(sid)
        assert size == 150

    def test_session_size_empty_session(self, tmp_path: Path) -> None:
        storage = SessionStorage(tmp_path)
        sid = "e1e1e1e1e1e1e1e1e1e1e1e1e1e1e1e1"
        _make_session(storage, sid)
        assert storage.session_size(sid) == 0

    def test_session_size_nonexistent(self, tmp_path: Path) -> None:
        storage = SessionStorage(tmp_path)
        assert storage.session_size("f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2") == 0

    def test_check_session_size_raises_on_exceed(self, tmp_path: Path) -> None:
        storage = SessionStorage(tmp_path)
        sid = "a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0"
        d = _make_session(storage, sid)
        _write_file(d / "big.bin", "z" * 1_000)

        with pytest.raises(ValueError, match="exceeds max size"):
            storage.check_session_size(sid, max_size=500)

    def test_check_session_size_passes_within_limit(self, tmp_path: Path) -> None:
        storage = SessionStorage(tmp_path)
        sid = "b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1"
        d = _make_session(storage, sid)
        _write_file(d / "small.bin", "a" * 10)

        # Should not raise
        storage.check_session_size(sid, max_size=1_000)


# ---------------------------------------------------------------------------
# 17.2  Session locking
# ---------------------------------------------------------------------------

class TestSessionLock:
    """Tests for SessionLock."""

    def test_acquire_release(self, tmp_path: Path) -> None:
        storage = SessionStorage(tmp_path)
        sid = "a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1"
        _make_session(storage, sid)
        lock = SessionLock(storage, sid)
        lock.acquire()
        assert lock._lock_file is not None
        lock.release()
        assert lock._lock_file is None

    def test_lock_context_manager(self, tmp_path: Path) -> None:
        storage = SessionStorage(tmp_path)
        sid = "b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2"
        _make_session(storage, sid)
        lock = SessionLock(storage, sid)
        with lock:
            assert lock._lock_file is not None
        assert lock._lock_file is None

    def test_lock_blocks_concurrent(self, tmp_path: Path) -> None:
        storage = SessionStorage(tmp_path)
        sid = "c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3"
        _make_session(storage, sid)
        lock1 = SessionLock(storage, sid)
        lock1.acquire()

        lock2 = SessionLock(storage, sid)
        with pytest.raises(RuntimeError, match="locked"):
            lock2.acquire()

        lock1.release()

    def test_lock_file_cleaned_up_on_release(self, tmp_path: Path) -> None:
        storage = SessionStorage(tmp_path)
        sid = "d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4d4"
        d = _make_session(storage, sid)
        lock = SessionLock(storage, sid)
        lock.acquire()
        assert (d / ".lock").exists()
        lock.release()
        assert not (d / ".lock").exists()


# ---------------------------------------------------------------------------
# 17.1  Atomic writes (verify existing behavior still works)
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    """Tests confirming atomic write semantics."""

    def test_atomic_write_json(self, tmp_path: Path) -> None:
        storage = SessionStorage(tmp_path)
        sid = "a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5"
        d = _make_session(storage, sid)
        path = d / "data.json"
        result = storage.save_json(path, {"key": "value", "num": 42})
        assert result == path
        assert json.loads(path.read_text()) == {"key": "value", "num": 42}

    def test_atomic_write_csv(self, tmp_path: Path) -> None:
        storage = SessionStorage(tmp_path)
        sid = "b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6b6"
        d = _make_session(storage, sid)
        path = d / "data.csv"
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        result = storage.save_frame(path, df)
        assert result == path
        loaded = pd.read_csv(result)
        pd.testing.assert_frame_equal(loaded, df, check_dtype=False)

    def test_atomic_write_no_tmp_left_on_failure(self, tmp_path: Path) -> None:
        """If writing fails, no leftover .tmp file should remain."""
        storage = SessionStorage(tmp_path)
        sid = "c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7"
        d = _make_session(storage, sid)
        # Create a file that will fail to write (read-only parent)
        ro_dir = d / "readonly"
        ro_dir.mkdir()
        target = ro_dir / "out.json"
        # Make directory read-only so writing fails
        os.chmod(ro_dir, 0o444)
        try:
            with pytest.raises((OSError, PermissionError)):
                storage.save_json(target, {"x": 1})
            # No .tmp file should be left behind
            tmp_files = list(ro_dir.glob("*.tmp"))
            assert len(tmp_files) == 0, f"Leftover tmp files: {tmp_files}"
        finally:
            os.chmod(ro_dir, 0o755)

    def test_atomic_write_survives_partial_content(self, tmp_path: Path) -> None:
        """After a successful atomic write, the file contains complete valid JSON."""
        storage = SessionStorage(tmp_path)
        sid = "d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8d8"
        d = _make_session(storage, sid)
        path = d / "complete.json"
        data = {"nested": {"a": [1, 2, 3], "b": "hello"}, "count": 100}
        storage.save_json(path, data)
        loaded = json.loads(path.read_text())
        assert loaded == data