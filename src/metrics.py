"""Small, defensive training metrics used by the Streamlit app."""

from __future__ import annotations

from numbers import Real

import pandas as pd


def pace_per_500m(distance_m, time_sec):
    """Return average pace per 500m as m:ss, or None for invalid inputs."""
    try:
        if not isinstance(distance_m, Real) or not isinstance(time_sec, Real):
            return None
        if distance_m <= 0 or time_sec < 0:
            return None
        total_seconds = time_sec * 500 / distance_m
        minutes, seconds = divmod(round(total_seconds), 60)
        return f"{int(minutes)}:{int(seconds):02d}"
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None


def split_list(distance_m, time_sec, split_m=500):
    """Return equal-split paces, or an empty list for invalid inputs."""
    try:
        if not all(isinstance(value, Real) for value in (distance_m, time_sec, split_m)):
            return []
        if distance_m <= 0 or time_sec < 0 or split_m <= 0:
            return []
        count = int(distance_m // split_m)
        if count <= 0:
            return []
        split_time = time_sec * split_m / distance_m
        return [pace_per_500m(split_m, split_time)] * count
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        return []


def meters_per_week(df):
    """Aggregate valid practice distances by Monday week start."""
    columns = ["week_start", "total_meters"]
    if df is None or not hasattr(df, "columns"):
        return pd.DataFrame(columns=columns)
    required = {"date", "distance_m"}
    if not required.issubset(df.columns):
        return pd.DataFrame(columns=columns)

    clean = df[["date", "distance_m"]].copy()
    clean["date"] = pd.to_datetime(clean["date"], errors="coerce")
    clean["distance_m"] = pd.to_numeric(clean["distance_m"], errors="coerce")
    clean = clean.dropna(subset=["date", "distance_m"])
    clean = clean[clean["distance_m"] > 0]
    if clean.empty:
        return pd.DataFrame(columns=columns)

    clean["week_start"] = clean["date"].dt.to_period("W-SUN").dt.start_time.dt.date
    result = (
        clean.groupby("week_start", as_index=False)["distance_m"]
        .sum()
        .rename(columns={"distance_m": "total_meters"})
    )
    result["total_meters"] = result["total_meters"].round().astype(int)
    return result[columns].sort_values("week_start").reset_index(drop=True)
