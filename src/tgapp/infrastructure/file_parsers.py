from __future__ import annotations

import base64
import io

import numpy as np
import pandas as pd

from tgapp.application.dto import UploadPayload
from tgapp.application.ports import DecodedUpload
from tgapp.domain.models import CorrectionFile, ParsedThermogram, ThermogramFile
from tgapp.domain.thermogram import normalize_thermogram_frame


def decode_upload(upload: UploadPayload) -> DecodedUpload:
    if not upload.content:
        return DecodedUpload(filename=upload.filename or "upload", content_type=upload.content_type or "", raw_bytes=b"")
    _, _, encoded = upload.content.partition(",")
    payload = base64.b64decode(encoded) if encoded else b""
    return DecodedUpload(
        filename=upload.filename or "upload",
        content_type=upload.content_type or "",
        raw_bytes=payload,
    )


def _read_frame(raw_bytes: bytes) -> pd.DataFrame:
    if not raw_bytes:
        return pd.DataFrame(columns=["temp", "deltatemp", "time", "mass"])

    for separator in (",", ";", "\t", r"\s+"):
        try:
            frame = pd.read_csv(io.StringIO(raw_bytes.decode("utf-8", errors="ignore")), sep=separator, header=None if separator == r"\s+" else "infer")
            if len(frame.columns) > 1:
                return frame
        except Exception:
            continue
    return pd.DataFrame(columns=["temp", "deltatemp", "time", "mass"])


def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    renamed = frame.copy()
    mapping = {
        "temperature": "temp",
        "t": "temp",
        "dt": "deltatemp",
        "delta_temp": "deltatemp",
        "minutes": "time",
        "timestamp": "time",
        "weight": "mass",
        # Numeric column indices (no header files)
        "0": "temp",
        "1": "deltatemp",
        "2": "time",
        "3": "mass",
    }
    renamed.columns = [mapping.get(str(column).strip().lower(), str(column).strip().lower()) for column in renamed.columns]
    normalized = normalize_thermogram_frame(renamed)
    for column in ["temp", "deltatemp", "time", "mass"]:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    return normalized


def parse_thermogram_uploads(uploads: list[UploadPayload]) -> list[ThermogramFile]:
    parsed: list[ThermogramFile] = []
    for upload in uploads:
        decoded = decode_upload(upload)
        frame = _normalize_columns(_read_frame(decoded.raw_bytes))
        parsed.append(ThermogramFile(name=decoded.filename, frame=frame, metadata={"content_type": decoded.content_type}))
    return parsed


def parse_correction_upload(upload: UploadPayload) -> CorrectionFile:
    decoded = decode_upload(upload)
    frame = _normalize_columns(_read_frame(decoded.raw_bytes))
    return CorrectionFile(name=decoded.filename, frame=frame, metadata={"content_type": decoded.content_type})


def frame_to_parsed(name: str, frame: pd.DataFrame, content_type: str = "") -> ParsedThermogram:
    """Convert a normalized DataFrame to ParsedThermogram (numpy arrays)."""
    if frame.empty:
        return ParsedThermogram(
            name=name,
            temp=np.array([], dtype=float),
            deltatemp=None,
            time=np.array([], dtype=float),
            mass=np.array([], dtype=float),
            metadata={"content_type": content_type, "rows_parsed": 0, "rows_with_nan": 0},
        )
    temp = frame["temp"].to_numpy(dtype=float)
    deltatemp = frame["deltatemp"].to_numpy(dtype=float) if "deltatemp" in frame.columns else None
    time = frame["time"].to_numpy(dtype=float)
    mass = frame["mass"].to_numpy(dtype=float)
    n_nan = int(np.isnan(temp).sum() + np.isnan(time).sum() + np.isnan(mass).sum())
    if deltatemp is not None:
        n_nan += int(np.isnan(deltatemp).sum())
    return ParsedThermogram(
        name=name,
        temp=temp,
        deltatemp=deltatemp,
        time=time,
        mass=mass,
        metadata={
            "content_type": content_type,
            "rows_parsed": len(frame),
            "rows_with_nan": n_nan,
        },
    )