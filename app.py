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
    APP_COLUMNS,
    PRACTICE_COLUMNS,
    SecretsError,
    clear_practices,
    delete_practice,
    get_config,
    load_practices,
    load_user_goal,
    login,
    save_practice,
    signup,
    update_practice,
    upsert_user_goal,
)
from pdf_export import build_season_pdf  # noqa: E402
from metrics import best_pace, meters_per_week, pace_per_500m  # noqa: E402

VALID_TYPES = ["water", "erg", "race"]
TYPE_LABELS = {"water": "Water", "erg": "Erg", "race": "Race"}
TYPE_OPTIONS = [TYPE_LABELS[t] for t in VALID_TYPES]

# Predefined workouts — no DB. Selecting one pre-fills distance + notes via session_state.

def safe_int(value, default: int = 0) -> int:
    """Coerce to int; treat None/NaN/blank as default."""
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


REQUIRED_CSV_COLUMNS = ["date", "type", "distance_m", "time_sec", "notes"]
OPTIONAL_CSV_COLUMNS = ["stroke_rate", "boat_class", "splits"]


def _csv_cell(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def validate_csv_practice_row(raw: dict[str, object], row_num: int) -> dict[str, object] | None:
    """Return a save_practice-ready dict, or None if the row should be skipped."""
    date_raw = _csv_cell(raw.get("date"))
    if not date_raw:
        return None
    try:
        parsed_date = pd.to_datetime(date_raw, errors="raise").date()
    except (ValueError, TypeError, OverflowError):
        return None

    parsed_type = type_value(_csv_cell(raw.get("type")))
    if parsed_type is None:
        return None

    try:
        distance = int(float(_csv_cell(raw.get("distance_m"))))
        time_sec = int(float(_csv_cell(raw.get("time_sec"))))
    except (ValueError, TypeError):
        return None
    if distance < 0 or time_sec < 0:
        return None

    notes = _csv_cell(raw.get("notes"))
    _ = row_num  # keep signature clear for callers / future error messages
    row = {
        "date": parsed_date,
        "type": parsed_type,
        "distance_m": distance,
        "time_sec": time_sec,
        "notes": notes,
    }
    stroke_raw = _csv_cell(raw.get("stroke_rate"))
    if stroke_raw:
        try:
            row["stroke_rate"] = int(float(stroke_raw))
        except (ValueError, TypeError):
            pass
    boat = _csv_cell(raw.get("boat_class"))
    if boat:
        row["boat_class"] = boat
    splits = _csv_cell(raw.get("splits"))
    if splits:
        row["splits"] = splits
    return row


def import_practices_from_csv(user_id: str, uploaded_file) -> tuple[int, int]:
    """Validate CSV rows and save_practice each good one. Returns (saved, skipped)."""
    try:
        frame = pd.read_csv(uploaded_file)
    except Exception as exc:  # noqa: BLE001 — surface parse errors to the UI
        raise ValueError(f"Could not read CSV: {exc}") from exc

    frame.columns = [str(c).strip().lower() for c in frame.columns]
    missing = [c for c in REQUIRED_CSV_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(
            "CSV must include columns: "
            + ", ".join(REQUIRED_CSV_COLUMNS)
            + f". Missing: {', '.join(missing)}."
        )

    saved = 0
    skipped = 0
    for idx, series in frame.iterrows():
        row_num = int(idx) + 2  # header is row 1
        validated = validate_csv_practice_row(series.to_dict(), row_num)
        if validated is None:
            skipped += 1
            continue
        try:
            save_practice(user_id, validated)
            saved += 1
        except (ValueError, SecretsError):
            skipped += 1
    return saved, skipped


st.set_page_config(page_title="RowSeer", layout="wide")

WORKOUT_TEMPLATES: dict[str, dict[str, object] | None] = {
    "Custom (no template)": None,
    "Steady 10k": {"distance_m": 10000, "notes": "Steady 10k"},
    "4x2k": {"distance_m": 8000, "notes": "4 x 2k"},
    "8x500": {"distance_m": 4000, "notes": "8 x 500m"},
    "2k Test": {"distance_m": 2000, "notes": "2k test"},
    "6k Steady": {"distance_m": 6000, "notes": "6k steady state"},
    "3x1k": {"distance_m": 3000, "notes": "3 x 1k"},
}


def type_label(value: str) -> str:
    key = str(value or "").lower().strip()
    return TYPE_LABELS.get(key, str(value).title() if value else "")


def type_value(label: str | None) -> str | None:
    if label is None:
        return None
    lowered = str(label).lower().strip()
    for key, pretty in TYPE_LABELS.items():
        if lowered == key or lowered == pretty.lower():
            return key
    return None


def apply_workout_template() -> None:
    """on_change: copy template distance/notes into add-form session_state keys."""
    name = st.session_state.get("workout_template", "Custom (no template)")
    tmpl = WORKOUT_TEMPLATES.get(name)
    if not tmpl:
        return
    st.session_state["add_distance"] = int(tmpl["distance_m"])  # type: ignore[arg-type]
    st.session_state["add_notes"] = str(tmpl.get("notes") or "")


st.set_page_config(page_title="RowSeer", layout="wide")


def csv_bytes(frame: pd.DataFrame) -> bytes:
    """Serialize the editable practice columns for download."""
    output = frame[PRACTICE_COLUMNS].copy()
    output["date"] = pd.to_datetime(output["date"]).dt.strftime("%Y-%m-%d")
    output["type"] = output["type"].map(type_label)
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


def refresh_practices() -> None:
    """Drop cached practices so the next render reloads from Supabase."""
    st.session_state.pop("practices", None)


def refresh_goal() -> None:
    st.session_state.pop("user_goal", None)


def render_auth() -> None:
    """Signup / login tabs when the user is not authenticated."""
    st.title("RowSeer")
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
                refresh_practices()
                refresh_goal()
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
                    refresh_practices()
                    refresh_goal()
                    st.success("Account created. Loading your log…")
                    st.rerun()
                except (ValueError, SecretsError) as exc:
                    st.error(str(exc))


def render_manage_practices(frame: pd.DataFrame) -> None:
    """Expander list: edit form + delete button per practice row."""
    st.subheader("Manage practices")
    st.caption("Expand a row to edit fields or delete that practice.")

    for _, row in frame.iterrows():
        practice_id = str(row.get("id") or "")
        date_str = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")
        label = (
            f"{date_str} · {type_label(row['type'])} · "
            f"{safe_int(row['distance_m']):,} m · {safe_int(row['time_sec'])}s"
        )
        with st.expander(label):
            if not practice_id:
                st.warning("This row has no id and cannot be edited. Reload the log.")
            else:
                with st.form(f"edit_{practice_id}"):
                    # No explicit key= on form widgets — let the form own identity
                    # (keys inside forms/expanders can break submit-button rendering).
                    edit_date = st.date_input(
                        "Date",
                        value=pd.to_datetime(row["date"]).date(),
                    )
                    current_label = type_label(row["type"])
                    try:
                        type_index = TYPE_OPTIONS.index(current_label)
                    except ValueError:
                        type_index = 0
                    edit_type_label = st.selectbox(
                        "Type",
                        TYPE_OPTIONS,
                        index=type_index,
                    )
                    edit_distance = st.number_input(
                        "Distance (m)",
                        min_value=0,
                        step=500,
                        value=safe_int(row["distance_m"], 0),
                    )
                    edit_time = st.number_input(
                        "Time (seconds)",
                        min_value=0,
                        step=1,
                        value=safe_int(row["time_sec"], 0),
                    )
                    edit_notes = st.text_input(
                        "Notes",
                        value=str(row.get("notes") or ""),
                    )
                    edit_stroke = st.number_input(
                        "Stroke rate (optional)",
                        min_value=0,
                        max_value=60,
                        step=1,
                        value=safe_int(row.get("stroke_rate"), 0),
                    )
                    edit_boat = st.text_input(
                        "Boat class (optional)",
                        value=str(row.get("boat_class") or ""),
                    )
                    edit_splits = st.text_input(
                        "Splits (optional)",
                        value=str(row.get("splits") or ""),
                    )
                    save_clicked = st.form_submit_button(
                        "Save changes",
                        type="primary",
                        use_container_width=True,
                    )

                if save_clicked:
                    parsed_type = type_value(edit_type_label)
                    if parsed_type is None:
                        st.error("Choose a valid type.")
                    else:
                        try:
                            update_practice(
                                st.session_state.user_id,
                                practice_id,
                                {
                                    "date": edit_date,
                                    "type": parsed_type,
                                    "distance_m": safe_int(edit_distance),
                                    "time_sec": safe_int(edit_time),
                                    "notes": edit_notes,
                                    "stroke_rate": safe_int(edit_stroke) or None,
                                    "boat_class": (edit_boat or "").strip() or None,
                                    "splits": (edit_splits or "").strip() or None,
                                },
                            )
                            refresh_practices()
                            st.success("Practice updated.")
                            st.rerun()
                        except (ValueError, SecretsError) as exc:
                            st.error(str(exc))

                if st.button("Delete practice", key=f"del_{practice_id}", type="secondary"):
                    try:
                        delete_practice(st.session_state.user_id, practice_id)
                        refresh_practices()
                        st.success("Practice deleted.")
                        st.rerun()
                    except (ValueError, SecretsError) as exc:
                        st.error(str(exc))


def render_goals_and_prs(frame: pd.DataFrame) -> None:
    """Season meter goal (Supabase) + client-side PRs from practices."""
    st.subheader("Goals & PRs")

    if "user_goal" not in st.session_state:
        try:
            st.session_state.user_goal = load_user_goal(st.session_state.user_id)
        except (ValueError, SecretsError) as exc:
            st.warning(
                f"Could not load season goal (run `supabase_goals.sql` if the table is missing): {exc}"
            )
            st.session_state.user_goal = None

    goal_row = st.session_state.user_goal
    current_goal = None
    if goal_row and goal_row.get("season_meter_goal") is not None:
        current_goal = int(goal_row["season_meter_goal"])

    total_meters = int(frame["distance_m"].sum()) if not frame.empty else 0
    pace_1k = best_pace(frame, 1000) if not frame.empty else None
    pace_2k = best_pace(frame, 2000) if not frame.empty else None

    pr_cols = st.columns(3)
    pr_cols[0].metric("Total meters", f"{total_meters:,}")
    pr_cols[1].metric("Best /500m (≥1,000m)", pace_1k or "—")
    pr_cols[2].metric("Best /500m (≥2,000m)", pace_2k or "—")

    with st.form("season_goal_form"):
        goal_input = st.number_input(
            "Season meter goal",
            min_value=0,
            step=1000,
            value=int(current_goal) if current_goal is not None else 100000,
            help="Target total meters for the season. Stored in Supabase `user_goals`.",
        )
        save_goal = st.form_submit_button("Save season goal", type="primary")
    if save_goal:
        try:
            upsert_user_goal(st.session_state.user_id, int(goal_input))
            refresh_goal()
            st.success("Season goal saved.")
            st.rerun()
        except (ValueError, SecretsError) as exc:
            st.error(str(exc))

    if current_goal and current_goal > 0:
        progress = min(total_meters / current_goal, 1.0)
        st.progress(progress, text=f"{total_meters:,} / {current_goal:,} m ({progress * 100:.0f}%)")
    elif current_goal == 0:
        st.caption("Season goal is 0 — set a positive target above.")
    else:
        st.caption("Set a season meter goal to see progress.")


def render_app() -> None:
    """Logged-in dashboard: sidebar form, metrics, manage list, charts."""
    st.title("RowSeer")
    st.caption("A simple training log for rowing: volume, pace, and season trends.")

    # Defaults for template-driven add form widgets (must exist before widgets render).
    if "add_distance" not in st.session_state:
        st.session_state["add_distance"] = 2000
    if "add_notes" not in st.session_state:
        st.session_state["add_notes"] = ""

    with st.sidebar:
        st.write(f"Signed in as **{st.session_state.email}**")
        if st.button("Log out"):
            for key in ("user_id", "email", "practices", "user_goal"):
                st.session_state.pop(key, None)
            st.rerun()

        st.divider()
        st.subheader("Add a practice")
        st.selectbox(
            "Workout template",
            list(WORKOUT_TEMPLATES.keys()),
            key="workout_template",
            on_change=apply_workout_template,
            help="Pick a template to pre-fill distance and notes. No database required.",
        )
        with st.form("add_practice", clear_on_submit=True):
            practice_date = st.date_input("Date")
            practice_type_label = st.selectbox(
                "Type",
                TYPE_OPTIONS,
                index=None,
                placeholder="Choose type",
            )
            distance = st.number_input(
                "Distance (m)",
                min_value=0,
                step=500,
                key="add_distance",
            )
            time_seconds = st.number_input("Time (seconds)", min_value=0, step=1, value=480)
            notes = st.text_input(
                "Notes",
                placeholder="e.g. 4 x 500m controlled",
                key="add_notes",
            )
            stroke_rate = st.number_input(
                "Stroke rate (optional)",
                min_value=0,
                max_value=60,
                step=1,
                value=0,
            )
            boat_class = st.text_input(
                "Boat class (optional)",
                placeholder="e.g. 8+, 4-, 1x",
            )
            splits = st.text_input(
                "Splits (optional)",
                placeholder="e.g. 1:58, 1:59",
            )
            submitted = st.form_submit_button("Add practice", type="primary")
        if submitted:
            parsed_type = type_value(practice_type_label)
            if parsed_type is None:
                st.error("Choose a practice type.")
            else:
                row = {
                    "date": practice_date,
                    "type": parsed_type,
                    "distance_m": int(distance),
                    "time_sec": int(time_seconds),
                    "notes": notes,
                    "stroke_rate": int(stroke_rate) or None,
                    "boat_class": (boat_class or "").strip() or None,
                    "splits": (splits or "").strip() or None,
                }
                try:
                    save_practice(st.session_state.user_id, row)
                    refresh_practices()
                    st.success("Practice saved.")
                    st.rerun()
                except (ValueError, SecretsError) as exc:
                    st.error(str(exc))

        st.divider()
        st.subheader("Import CSV")
        st.caption(
            "Your file needs a header row with date, type, distance (meters), "
            "time (seconds), and notes. You can also include stroke rate, boat class, "
            "and splits if you have them."
        )
        uploaded_csv = st.file_uploader(
            "Upload practices CSV",
            type=["csv"],
            key="csv_import_uploader",
            help="One practice per row. Bad rows are skipped.",
        )
        if uploaded_csv is not None and st.button(
            "Import practices",
            type="primary",
            key="csv_import_btn",
        ):
            try:
                saved, skipped = import_practices_from_csv(
                    st.session_state.user_id, uploaded_csv
                )
                refresh_practices()
                if saved and skipped:
                    st.success(f"Imported {saved} practice(s); skipped {skipped} bad row(s).")
                elif saved:
                    st.success(f"Imported {saved} practice(s).")
                elif skipped:
                    st.warning(f"No practices imported; skipped {skipped} bad row(s).")
                else:
                    st.warning("CSV had no data rows.")
                if saved:
                    st.rerun()
            except (ValueError, SecretsError) as exc:
                st.error(str(exc))

        with st.expander("Team (coming soon)", expanded=False):
            st.caption("Coach / crew share views are on the roadmap. This section is disabled for now.")
            st.button("Invite teammates", disabled=True, key="team_stub_btn")

        st.divider()
        st.subheader("Danger zone")
        confirm_clear = st.checkbox(
            "I understand this permanently deletes all of my practices",
            key="confirm_clear_all",
        )
        if st.button(
            "Clear all practices",
            type="secondary",
            disabled=not confirm_clear,
            key="clear_all_btn",
        ):
            try:
                clear_practices(st.session_state.user_id)
                refresh_practices()
                st.success("All practices cleared.")
                st.rerun()
            except (ValueError, SecretsError) as exc:
                st.error(str(exc))

    if "practices" not in st.session_state:
        try:
            st.session_state.practices = load_practices(st.session_state.user_id)
        except (ValueError, SecretsError) as exc:
            st.error(str(exc))
            st.session_state.practices = pd.DataFrame(columns=APP_COLUMNS)

    frame = st.session_state.practices.copy()
    if not frame.empty:
        frame["pace /500m"] = [
            pace_per_500m(distance, seconds)
            for distance, seconds in zip(frame["distance_m"], frame["time_sec"])
        ]
        frame["type_display"] = frame["type"].map(type_label)
    else:
        frame["pace /500m"] = []
        frame["type_display"] = []

    render_goals_and_prs(frame)

    st.download_button(
        "Export season PDF",
        data=build_season_pdf(st.session_state.get("email", ""), frame),
        file_name="rowseer_season.pdf",
        mime="application/pdf",
        key="export_season_pdf",
        help="Download a season summary PDF (email, totals, best paces, recent practices).",
    )


    if frame.empty:
        st.info("No practices yet. Add one from the sidebar.")
        return

    total_meters = int(frame["distance_m"].sum())
    practice_count = len(frame)
    pace_1k = best_pace(frame, 1000)

    metric_cols = st.columns(3)
    metric_cols[0].metric("Total meters", f"{total_meters:,}")
    metric_cols[1].metric("Practices", practice_count)
    metric_cols[2].metric("Best pace (≥1,000m)", pace_1k or "—")

    st.subheader("Practice log")
    display = frame.copy()
    display["date"] = pd.to_datetime(display["date"]).dt.strftime("%Y-%m-%d")
    log_cols = ["date", "type_display", "distance_m", "time_sec", "pace /500m"]
    # Show piece-detail columns only when at least one row has a value.
    if "stroke_rate" in display.columns and display["stroke_rate"].notna().any():
        log_cols.append("stroke_rate")
    if "boat_class" in display.columns and display["boat_class"].fillna("").astype(str).str.strip().ne("").any():
        log_cols.append("boat_class")
    if "splits" in display.columns and display["splits"].fillna("").astype(str).str.strip().ne("").any():
        log_cols.append("splits")
    log_cols.append("notes")
    st.dataframe(
        display[log_cols].rename(
            columns={
                "date": "Date",
                "type_display": "Type",
                "distance_m": "Distance (m)",
                "time_sec": "Time (sec)",
                "pace /500m": "Pace /500m",
                "notes": "Notes",
                "stroke_rate": "Stroke Rate",
                "boat_class": "Boat Class",
                "splits": "Splits",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download CSV",
        data=csv_bytes(frame),
        file_name="rowseer_practices.csv",
        mime="text/csv",
    )

    render_manage_practices(frame)

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
        pace_frame["type"] = pace_frame["type"].map(type_label)
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
