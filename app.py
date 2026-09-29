from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from db import (  # noqa: E402
    PRACTICE_COLUMNS,
    SecretsError,
    get_config,
    load_practices,
    login,
    save_practice,
    signup,
)
from metrics import meters_per_week, pace_per_500m  # noqa: E402

VALID_TYPES = ["water", "erg", "race"]

st.set_page_config(page_title="RowSeer", page_icon="🚣", layout="wide")


def csv_bytes(frame: pd.DataFrame) -> bytes:
    """Serialize the editable practice columns for download."""
    output = frame[PRACTICE_COLUMNS].copy()
    output["date"] = pd.to_datetime(output["date"]).dt.strftime("%Y-%m-%d")
    return output.to_csv(index=False).encode("utf-8")


def ensure_secrets() -> bool:
    """Return True if Supabase secrets are configured; otherwise show setup help."""
    try:
        get_config()
        return True
    except SecretsError as exc:
        st.error("Supabase is not configured.")
        st.code(str(exc), language="toml")
        st.markdown(
            "For **Streamlit Community Cloud**, open your app → **Settings → Secrets** "
            "and paste the same `[supabase]` block."
        )
        return False


def render_auth() -> None:
    """Signup / login tabs when the user is not authenticated."""
    st.title("🚣 RowSeer")
    st.caption("Sign in to log practices and track volume and pace.")

    if not ensure_secrets():
        return

    login_tab, signup_tab = st.tabs(["Log in", "Sign up"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log in", type="primary")
        if submitted:
            try:
                user = login(email, password)
                st.session_state.user_id = user["id"]
                st.session_state.email = user["email"]
                st.session_state.pop("practices", None)
                st.rerun()
            except (ValueError, SecretsError) as exc:
                st.error(str(exc))

    with signup_tab:
        with st.form("signup_form"):
            email = st.text_input("Email", key="signup_email")
            password = st.text_input("Password", type="password", key="signup_password")
            confirm = st.text_input("Confirm password", type="password", key="signup_confirm")
            submitted = st.form_submit_button("Create account", type="primary")
        if submitted:
            if password != confirm:
                st.error("Passwords do not match.")
            else:
                try:
                    user = signup(email, password)
                    st.session_state.user_id = user["id"]
                    st.session_state.email = user["email"]
                    st.session_state.pop("practices", None)
                    st.success("Account created. Loading your log…")
                    st.rerun()
                except (ValueError, SecretsError) as exc:
                    st.error(str(exc))


def render_app() -> None:
    """Logged-in dashboard: sidebar form, metrics, table, charts."""
    st.title("🚣 RowSeer")
    st.caption("A simple training log for college rowing: volume, pace, and season trends.")

    with st.sidebar:
        st.write(f"Signed in as **{st.session_state.email}**")
        if st.button("Log out"):
            for key in ("user_id", "email", "practices"):
                st.session_state.pop(key, None)
            st.rerun()

        st.divider()
        st.subheader("Add a practice")
        with st.form("add_practice", clear_on_submit=True):
            practice_date = st.date_input("Date")
            practice_type = st.selectbox("Type", VALID_TYPES)
            distance = st.number_input("Distance (m)", min_value=0, step=500, value=2000)
            time_seconds = st.number_input("Time (seconds)", min_value=0, step=1, value=480)
            notes = st.text_input("Notes", placeholder="e.g. 4 x 500m controlled")
            submitted = st.form_submit_button("Add practice", type="primary")
        if submitted:
            row = {
                "date": practice_date,
                "type": practice_type,
                "distance_m": int(distance),
                "time_sec": int(time_seconds),
                "notes": notes,
            }
            try:
                save_practice(st.session_state.user_id, row)
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
                st.success("Practice saved.")
                st.rerun()
            except (ValueError, SecretsError) as exc:
                st.error(str(exc))

    if "practices" not in st.session_state:
        try:
            st.session_state.practices = load_practices(st.session_state.user_id)
        except (ValueError, SecretsError) as exc:
            st.error(str(exc))
            st.session_state.practices = pd.DataFrame(columns=PRACTICE_COLUMNS)

    frame = st.session_state.practices.copy()
    if not frame.empty:
        frame["pace /500m"] = [
            pace_per_500m(distance, seconds)
            for distance, seconds in zip(frame["distance_m"], frame["time_sec"])
        ]
    else:
        frame["pace /500m"] = []

    if frame.empty:
        st.info("No practices yet. Add one from the sidebar.")
        return

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
    display["date"] = pd.to_datetime(display["date"]).dt.strftime("%Y-%m-%d")
    st.dataframe(
        display[["date", "type", "distance_m", "time_sec", "pace /500m", "notes"]],
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download CSV",
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
                weekly,
                x="week_start",
                y="total_meters",
                title="Meters per week",
                labels={"week_start": "Week", "total_meters": "Meters"},
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
                pace_frame,
                x="date",
                y="pace_seconds",
                markers=True,
                color="type",
                hover_data=["distance_m", "notes"],
                title="Pace over time",
                labels={"date": "Date", "pace_seconds": "Seconds / 500m"},
            )
            pace_chart.update_yaxes(autorange="reversed")
            st.plotly_chart(pace_chart, use_container_width=True)


# --- entry ---
if "user_id" not in st.session_state:
    render_auth()
else:
    if not ensure_secrets():
        st.stop()
    render_app()
