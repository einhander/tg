from __future__ import annotations

import pandas as pd

from tgapp.domain.models import ValidatedThermogram


def validated_to_df(v: ValidatedThermogram) -> pd.DataFrame:
    """Convert ValidatedThermogram back to DataFrame for storage."""
    data: dict[str, list[float]] = {
        "temp": v.temp.tolist(),
        "time": v.time.tolist(),
        "mass": v.mass.tolist(),
    }
    if v.deltatemp is not None:
        data["deltatemp"] = v.deltatemp.tolist()
    return pd.DataFrame(data)