from __future__ import annotations

from io import StringIO
from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from metrics import meters_per_week, pace_per_500m  # noqa: E402

DATA_PATH = Path(__file__).resolve().parent / "data" / "sample_practices.csv"
REQUIRED_COLUMNS = ["date", "type", "distance_m", "time_sec", "notes"]
VALID_TYPES = ["water", "erg", "race"]

st.set_page_config(page_title="RowSeer", page_icon="🚣", layout="wide")


def load_csv(file_or_path) -> pd.DataFrame:
    """Read and normalize a practice CSV."""
    try:
        frame = pd.read_csv(file_or_path)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        st.error(f"Could not read that CSV: {exc}")
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        st.error(f"CSV is missing required columns: {', '.join(missing)}")
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    frame = frame[REQUIRED_COLUMNS].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["distance_m"] = pd.to_numeric(frame["distance_m"], errors="coerce")
    frame["time_sec"] = pd.to_numeric(frame["time_sec"], errors="coerce")
    frame["type"] = frame["type"].astype(str).str.lower().str.strip()
    frame["notes"] = frame["notes"].fillna("").astype(str)
    frame = frame.dropna(subset=["date", "distance_m", "time_sec"])
    frame = frame[(frame["distance_m"] >= 0) & (frame["time_sec"] >= 0)]
    frame = frame[frame["type"].isin(VALID_TYPES)]
    frame["distance_m"] = frame["distance_m"].round().astype(int)
    frame["time_sec"] = frame["time_sec"].round().astype(int)
    return frame.sort_values("date", ascending=False).reset_index(drop=True)


def practices_to_csv_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize practice columns for disk or download."""
    output = frame[REQUIRED_COLUMNS].copy()
    output["date"] = pd.to_datetime(output["date"]).dt.strftime("%Y-%m-%d")
    return output


def save_practices(frame: pd.DataFrame) -> None:
    """Write the practice log to the on-disk CSV."""
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    practices_to_csv_frame(frame).to_csv(DATA_PATH, index=False)


def csv_bytes(frame: pd.DataFrame) -> bytes:
    """Serialize the editable practice columns for download."""
    return practices_to_csv_frame(frame).to_csv(index=False).encode("utf-8")


st.title("🚣 RowSeer")
st.caption("A simple training log for rowing: volume, pace, and season trends.")

if "practices" not in st.session_state:
    st.session_state.practices = load_csv(DATA_PATH)

with st.sidebar:
    st.header("Practice log")
    st.subheader("Add a practice")
    with st.form("add_practice", clear_on_submit=True):
        practice_date = st.date_input("Date")
        practice_type = st.selectbox("Type", VALID_TYPES)
        distance = st.number_input("Distance (m)", min_value=0, step=500, value=2000)
        time_seconds = st.number_input("Time (seconds)", min_value=0, step=1, value=480)
        notes = st.text_input("Notes", placeholder="e.g. 4 x 500m controlled")
        submitted = st.form_submit_button("Add practice", type="primary")
    if submitted:
        new_row = pd.DataFrame([{
            "date": pd.Timestamp(practice_date),
            "type": practice_type,
            "distance_m": int(distance),
            "time_sec": int(time_seconds),
            "notes": notes,
        }])
        st.session_state.practices = pd.concat(
            [st.session_state.practices, new_row], ignore_index=True
        )
        try:
            save_practices(st.session_state.practices)
            st.success("Practice saved.")
        except OSError as exc:
            st.error(f"Added for this session, but could not save to disk: {exc}")

frame = st.session_state.practices.copy()
frame["pace /500m"] = [
    pace_per_500m(distance, seconds)
    for distance, seconds in zip(frame["distance_m"], frame["time_sec"])
]

if frame.empty:
    st.warning("No valid practices yet. Add one from the sidebar.")
else:
    total_meters = int(frame["distance_m"].sum())
    practice_count = len(frame)
    qualifying = frame[frame["distance_m"] >= 1000].copy()
    qualifying["pace_seconds"] = qualifying["time_sec"] * 500 / qualifying["distance_m"]
    best_pace = None
    if not qualifying.empty:
        best_seconds = qualifying["pace_seconds"].min()
        best_pace = pace_per_500m(500, best_seconds)

    metric_cols = st.columns(3)
    metric_cols[0].metric("Total meters", f"{total_meters:,}")
    metric_cols[1].metric("Practices", practice_count)
    metric_cols[2].metric("Best pace (≥1,000m)", best_pace or "—")

    st.subheader("Practice log")
    display = frame.copy()
    display["date"] = display["date"].dt.strftime("%Y-%m-%d")
    st.dataframe(
        display[["date", "type", "distance_m", "time_sec", "pace /500m", "notes"]],
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Save pray",
        data=csv_bytes(frame),
        file_name="rowseer_practices.csv",
        mime="text/csv",
    )

    st.subheader("Training trends")
    weekly = meters_per_week(frame)
    chart_cols = st.columns(2)
    with chart_cols[0]:
        if weekly.empty:
            st.info("Add a valid distance to see weekly meters.")
        else:
            weekly_chart = px.bar(
                weekly, x="week_start", y="total_meters",
                title="Meters per week", labels={"week_start": "Week", "total_meters": "Meters"},
            )
            weekly_chart.update_layout(showlegend=False)
            st.plotly_chart(weekly_chart, use_container_width=True)
    with chart_cols[1]:
        pace_frame = frame[frame["distance_m"] > 0].copy()
        pace_frame["pace_seconds"] = pace_frame["time_sec"] * 500 / pace_frame["distance_m"]
        pace_frame = pace_frame.sort_values("date")
        if pace_frame.empty:
            st.info("Add a valid distance to see pace over time.")
        else:
            pace_chart = px.line(
                pace_frame, x="date", y="pace_seconds", markers=True,
                color="type", hover_data=["distance_m", "notes"],
                title="Pace over time", labels={"date": "Date", "pace_seconds": "Seconds / 500m"},
            )
            pace_chart.update_yaxes(autorange="reversed")
            st.plotly_chart(pace_chart, use_container_width=True)
