"""Security hardening tests — PLAN_AUDIT §16."""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path

import pytest

from tgapp.config import AppConfig
from tgapp.infrastructure.serialization import (
    _MAX_ZIP_FILES,
    _MAX_ZIP_UNPACKED,
    _validate_zip_member,
    pack_session_directory,
    unpack_session_archive,
)
from tgapp.infrastructure.storage import (
    SessionStorage,
    validate_session_id,
)


# ====================================================================
# 16.1 — Session ID validation
# ====================================================================


class TestValidateSessionId:
    """validate_session_id per §16.1."""

    def test_valid_uuid_hex(self):
        """Full 32-char lowercase hex passes."""
        assert validate_session_id("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4") is True

    def test_valid_all_zeros(self):
        assert validate_session_id("0" * 32) is True

    def test_valid_all_nines(self):
        assert validate_session_id("f" * 32) is True

    def test_reject_short_string(self):
        """12-char truncation (old format) must be rejected."""
        assert validate_session_id("a1b2c3d4e5f6") is False

    def test_reject_uppercase(self):
        assert validate_session_id("A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4") is False

    def test_reject_slash(self):
        assert validate_session_id("a1b2c3d4/e5f6a1b2c3d4e5f6a1b2c3d4") is False

    def test_reject_backslash(self):
        assert validate_session_id("a1b2c3d4\\e5f6a1b2c3d4e5f6a1b2c3d4") is False

    def test_reject_parent_dir(self):
        assert validate_session_id("a1b2c3d4..e5f6a1b2c3d4e5f6a1b2c3d4") is False

    def test_reject_absolute_path(self):
        assert validate_session_id("/etc/passwd") is False

    def test_reject_empty(self):
        assert validate_session_id("") is False

    def test_reject_random_string(self):
        assert validate_session_id("not-a-uuid") is False


# ====================================================================
# 16.1 — Storage session_dir rejection
# ====================================================================


class TestSessionStorageValidation:
    """SessionStorage must reject invalid session IDs."""

    def test_session_dir_rejects_short_id(self, tmp_path: Path):
        storage = SessionStorage(tmp_path)
        with pytest.raises(ValueError, match="Invalid session_id"):
            storage.session_dir("short")

    def test_session_dir_rejects_slash(self, tmp_path: Path):
        storage = SessionStorage(tmp_path)
        with pytest.raises(ValueError, match="Invalid session_id"):
            storage.session_dir("a1b2c3d4/e5f6a1b2c3d4e5f6a1b2c3d4")

    def test_session_dir_rejects_parent_dir(self, tmp_path: Path):
        storage = SessionStorage(tmp_path)
        with pytest.raises(ValueError, match="Invalid session_id"):
            storage.session_dir("a1b2c3d4..e5f6a1b2c3d4e5f6a1b2c3d4")

    def test_session_dir_accepts_valid(self, tmp_path: Path):
        storage = SessionStorage(tmp_path)
        sid = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
        d = storage.session_dir(sid)
        d.mkdir(parents=True, exist_ok=True)  # session_dir returns path; caller creates it
        assert d.exists()
        assert d.name == sid

    def test_create_session_produces_32_char_hex(self, tmp_path: Path):
        storage = SessionStorage(tmp_path)
        sid = storage.create_session()
        assert len(sid) == 32
        assert validate_session_id(sid) is True


# ====================================================================
# 16.2 — Safe ZIP extraction
# ====================================================================


class TestValidateZipMember:
    """_validate_zip_member rejects dangerous paths."""

    def test_reject_absolute_path(self):
        with pytest.raises(ValueError, match="Absolute path"):
            _validate_zip_member("/etc/passwd")

    def test_reject_parent_dir(self):
        with pytest.raises(ValueError, match="Parent directory"):
            _validate_zip_member("../secret")

    def test_reject_parent_dir_middle(self):
        with pytest.raises(ValueError, match="Parent directory"):
            _validate_zip_member("foo/../../etc/passwd")

    def test_reject_backslash_parent(self):
        with pytest.raises(ValueError, match="Parent directory"):
            _validate_zip_member("foo\\..\\secret")

    def test_accept_normal_path(self):
        _validate_zip_member("thermograms/data.csv")

    def test_accept_nested_path(self):
        _validate_zip_member("sub/dir/file.csv")


class TestSafeUnpack:
    """unpack_session_archive rejects malicious archives."""

    def test_rejects_absolute_path_member(self, tmp_path: Path):
        archive = tmp_path / "bad.tg"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("data.csv", "temp;mass\n10;100")
            # Add a member with absolute path
            zf.writestr("/etc/passwd", "root:x:0:0")
        dest = tmp_path / "dest"
        with pytest.raises(ValueError, match="Absolute path"):
            unpack_session_archive(archive, dest)

    def test_rejects_symlink_member(self, tmp_path: Path):
        archive = tmp_path / "symlink.tg"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("data.csv", "temp;mass\n10;100")
            # Create a symlink entry (Unix symlink external_attr = 0o120000 << 16)
            info = zipfile.ZipInfo("link")
            info.external_attr = (0o120000 << 16) | (0o10 << 8)  # symlink, mode 10
            zf.writestr(info, "/etc/passwd")
        dest = tmp_path / "dest"
        with pytest.raises(ValueError, match="Symlink"):
            unpack_session_archive(archive, dest)

    def test_rejects_parent_dir_member(self, tmp_path: Path):
        archive = tmp_path / "traversal.tg"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("data.csv", "temp;mass\n10;100")
            zf.writestr("../etc/evil.csv", "malicious")
        dest = tmp_path / "dest"
        with pytest.raises(ValueError, match="Parent directory"):
            unpack_session_archive(archive, dest)

    def test_valid_archive_extracts(self, tmp_path: Path):
        archive = tmp_path / "good.tg"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("thermograms/data.csv", "temp;mass\n10;100\n20;90")
        dest = tmp_path / "dest"
        result = unpack_session_archive(archive, dest)
        assert result.exists()
        csv_files = list(result.rglob("*.csv"))
        assert len(csv_files) == 1

    def test_rejects_empty_archive(self, tmp_path: Path):
        archive = tmp_path / "empty.tg"
        with zipfile.ZipFile(archive, "w") as zf:
            pass  # no members
        dest = tmp_path / "dest"
        with pytest.raises(ValueError, match="no CSV files"):
            unpack_session_archive(archive, dest)


# ====================================================================
# 16.3 — Safe export
# ====================================================================


class TestPackSessionDirectory:
    """pack_session_directory respects limits."""

    def test_normal_pack(self, tmp_path: Path):
        session = tmp_path / "session"
        session.mkdir()
        (session / "data.csv").write_text("temp;mass\n10;100")
        archive = tmp_path / "out.tg"
        result = pack_session_directory(session, archive)
        assert result.exists()
        with zipfile.ZipFile(result) as zf:
            assert len(zf.namelist()) == 1

    def test_respects_file_count_limit(self, tmp_path: Path):
        session = tmp_path / "session"
        session.mkdir()
        # Create more than _MAX_ZIP_FILES files
        for i in range(_MAX_ZIP_FILES + 1):
            (session / f"file_{i}.csv").write_text(f"data_{i}")
        archive = tmp_path / "out.tg"
        with pytest.raises(ValueError, match="too many files"):
            pack_session_directory(session, archive)


# ====================================================================
# 16.4 — Upload size limit
# ====================================================================


class TestUploadSizeLimit:
    """Upload size enforcement."""

    def test_config_defaults(self):
        config = AppConfig()
        assert config.max_upload_size == 50 * 1024 * 1024
        assert config.max_upload_files == 10
        assert config.max_archive_size == 100 * 1024 * 1024
        assert config.max_unpacked_size == 200 * 1024 * 1024
        assert config.max_data_rows == 1_000_000

    def test_config_env_overrides(self):
        import os as _os
        old = {}
        for key in ("APP_MAX_UPLOAD_SIZE", "APP_MAX_UPLOAD_FILES",
                     "APP_MAX_ARCHIVE_SIZE", "APP_MAX_UNPACKED_SIZE",
                     "APP_MAX_DATA_ROWS"):
            old[key] = _os.environ.pop(key, None)
        try:
            _os.environ["APP_MAX_UPLOAD_SIZE"] = "1048576"
            _os.environ["APP_MAX_UPLOAD_FILES"] = "5"
            config = AppConfig.from_env()
            assert config.max_upload_size == 1048576
            assert config.max_upload_files == 5
        finally:
            for k, v in old.items():
                if v is not None:
                    _os.environ[k] = v
                else:
                    _os.environ.pop(k, None)


# ====================================================================
# Atomic write test
# ====================================================================


class TestAtomicSave:
    """Atomic writes produce complete files."""

    def test_save_frame_atomic(self, tmp_path: Path):
        import pandas as pd
        storage = SessionStorage(tmp_path)
        frame = pd.DataFrame({"temp": [10, 20], "mass": [100, 90]})
        path = tmp_path / "output.csv"
        storage.save_frame(path, frame)
        assert path.exists()
        loaded = pd.read_csv(path)
        assert len(loaded) == 2
        assert list(loaded.columns) == ["temp", "mass"]

    def test_save_json_atomic(self, tmp_path: Path):
        import json
        storage = SessionStorage(tmp_path)
        path = tmp_path / "meta.json"
        storage.save_json(path, {"key": "value", "num": 42})
        assert path.exists()
        data = json.loads(path.read_text())
        assert data == {"key": "value", "num": 42}