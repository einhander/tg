from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_base_path(value: str | None) -> str:
    raw = (value or "/").strip()
    if not raw or raw == "/":
        return ""
    return "/" + raw.strip("/")


@dataclass(frozen=True)
class AppConfig:
    host: str = "127.0.0.1"
    port: int = 8050
    debug: bool = False
    base_path: str = ""
    session_dir: Path = Path(".session-data")

    # Security limits (PLAN_AUDIT §16.4)
    max_upload_size: int = 50 * 1024 * 1024       # 50 MB
    max_upload_files: int = 10
    max_archive_size: int = 100 * 1024 * 1024     # 100 MB
    max_unpacked_size: int = 200 * 1024 * 1024    # 200 MB
    max_data_rows: int = 1_000_000

    @property
    def public_base_path(self) -> str:
        return self.base_path or "/"

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            host=os.getenv("APP_HOST", "127.0.0.1"),
            port=int(os.getenv("APP_PORT", "8050")),
            debug=_as_bool(os.getenv("APP_DEBUG"), default=False),
            base_path=normalize_base_path(os.getenv("APP_BASE_PATH", "/")),
            session_dir=Path(os.getenv("APP_SESSION_DIR", ".session-data")).expanduser(),
            max_upload_size=int(os.getenv("APP_MAX_UPLOAD_SIZE", "52428800")),
            max_upload_files=int(os.getenv("APP_MAX_UPLOAD_FILES", "10")),
            max_archive_size=int(os.getenv("APP_MAX_ARCHIVE_SIZE", "104857600")),
            max_unpacked_size=int(os.getenv("APP_MAX_UNPACKED_SIZE", "209715200")),
            max_data_rows=int(os.getenv("APP_MAX_DATA_ROWS", "1000000")),
        )
