from __future__ import annotations

import json
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import pandas as pd


class SessionStorage:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def ensure(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def create_session(self) -> str:
        session_id = uuid.uuid4().hex[:12]
        self.session_dir(session_id).mkdir(parents=True, exist_ok=True)
        return session_id

    def session_dir(self, session_id: str) -> Path:
        safe = session_id.replace("/", "_")
        return self.ensure() / safe

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
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        return path

    def load_frame(self, path: Path) -> pd.DataFrame:
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path)

    def save_json(self, path: Path, data: Any) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(data) if is_dataclass(data) and not isinstance(data, type) else data
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
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
