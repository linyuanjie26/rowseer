"""Supabase REST helpers for RowSeer auth and practice persistence."""

from __future__ import annotations

import uuid
from typing import Any

import bcrypt
import pandas as pd
import requests
import streamlit as st

# App-facing data columns (CSV export). `id` is loaded separately for edit/delete.
PRACTICE_COLUMNS = [
    "date",
    "type",
    "distance_m",
    "time_sec",
    "notes",
    "stroke_rate",
    "boat_class",
    "splits",
]
APP_COLUMNS = ["id", *PRACTICE_COLUMNS]

VALID_TYPES = ("water", "erg", "race")


class SecretsError(RuntimeError):
    """Raised when Streamlit secrets for Supabase are missing or incomplete."""


def get_config() -> tuple[str, str]:
    """Return (url, anon_key) from st.secrets['supabase']."""
    try:
        supabase = st.secrets["supabase"]
        url = str(supabase["url"]).rstrip("/")
        anon_key = str(supabase["anon_key"])
    except (KeyError, TypeError, AttributeError) as exc:
        raise SecretsError(
            "Missing Supabase secrets. Create `.streamlit/secrets.toml` with:\n\n"
            "[supabase]\n"
            'url = "https://YOUR_PROJECT.supabase.co"\n'
            'anon_key = "YOUR_ANON_KEY"\n'
        ) from exc
    if not url or not anon_key:
        raise SecretsError(
            "Supabase secrets are empty. Set both `url` and `anon_key` in "
            "`.streamlit/secrets.toml` (or Streamlit Cloud secrets)."
        )
    return url, anon_key


def _headers(anon_key: str, *, prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _check_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _normalize_date(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text if text else None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _practice_payload(user_id: str, row: dict[str, Any], *, practice_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "user_id": user_id,
        "practice_date": _normalize_date(row["date"]),
        "type": str(row["type"]).lower().strip(),
        "distance_m": int(row["distance_m"]),
        "time_sec": int(row["time_sec"]),
        "notes": str(row.get("notes") or ""),
        "stroke_rate": _optional_int(row.get("stroke_rate")),
        "boat_class": _optional_text(row.get("boat_class")),
        "splits": _optional_text(row.get("splits")),
    }
    if practice_id is not None:
        payload["id"] = practice_id
    return payload


def signup(email: str, password: str) -> dict[str, Any]:
    """Create a profiles row. Returns {id, email} on success. Raises ValueError on failure."""
    email = email.strip().lower()
    if not email or "@" not in email:
        raise ValueError("Enter a valid email address.")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")

    url, anon_key = get_config()
    user_id = str(uuid.uuid4())
    payload = {
        "id": user_id,
        "email": email,
        "password_hash": _hash_password(password),
    }
    response = requests.post(
        f"{url}/rest/v1/profiles",
        headers=_headers(anon_key, prefer="return=representation"),
        json=payload,
        timeout=30,
    )
    if response.status_code in (200, 201):
        rows = response.json()
        if isinstance(rows, list) and rows:
            return {"id": rows[0]["id"], "email": rows[0]["email"]}
        return {"id": user_id, "email": email}

    body = response.text.lower()
    if response.status_code in (409, 23505) or "duplicate" in body or "unique" in body:
        raise ValueError("An account with that email already exists. Try logging in.")
    raise ValueError(f"Signup failed ({response.status_code}): {response.text[:300]}")


def login(email: str, password: str) -> dict[str, Any]:
    """Verify email/password against profiles. Returns {id, email}. Raises ValueError."""
    email = email.strip().lower()
    if not email or not password:
        raise ValueError("Email and password are required.")

    url, anon_key = get_config()
    response = requests.get(
        f"{url}/rest/v1/profiles",
        headers=_headers(anon_key),
        params={"email": f"eq.{email}", "select": "id,email,password_hash"},
        timeout=30,
    )
    if response.status_code != 200:
        raise ValueError(f"Login failed ({response.status_code}): {response.text[:300]}")

    rows = response.json()
    if not rows:
        raise ValueError("No account found for that email. Sign up first.")
    profile = rows[0]
    if not _check_password(password, profile.get("password_hash", "")):
        raise ValueError("Incorrect password.")
    return {"id": profile["id"], "email": profile["email"]}


def load_practices(user_id: str) -> pd.DataFrame:
    """Fetch practices for a user as a DataFrame including selectable `id`."""
    url, anon_key = get_config()
    response = requests.get(
        f"{url}/rest/v1/practices",
        headers=_headers(anon_key),
        params={
            "user_id": f"eq.{user_id}",
            "select": (
                "id,practice_date,type,distance_m,time_sec,notes,"
                "stroke_rate,boat_class,splits"
            ),
            "order": "practice_date.desc",
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise ValueError(
            f"Could not load practices ({response.status_code}): {response.text[:300]}"
        )

    rows = response.json() or []
    if not rows:
        return pd.DataFrame(columns=APP_COLUMNS)

    frame = pd.DataFrame(rows)
    frame = frame.rename(columns={"practice_date": "date"})
    if "id" not in frame.columns:
        frame["id"] = ""
    for column in PRACTICE_COLUMNS:
        if column not in frame.columns:
            if column in ("notes", "boat_class", "splits"):
                frame[column] = ""
            else:
                frame[column] = None
    frame = frame[APP_COLUMNS].copy()
    frame["id"] = frame["id"].astype(str)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["distance_m"] = pd.to_numeric(frame["distance_m"], errors="coerce").fillna(0).astype(int)
    frame["time_sec"] = pd.to_numeric(frame["time_sec"], errors="coerce").fillna(0).astype(int)
    frame["type"] = frame["type"].astype(str).str.lower().str.strip()
    frame["notes"] = frame["notes"].fillna("").astype(str)
    frame["stroke_rate"] = pd.to_numeric(frame["stroke_rate"], errors="coerce")
    frame["boat_class"] = frame["boat_class"].fillna("").astype(str)
    frame["splits"] = frame["splits"].fillna("").astype(str)
    return frame.sort_values("date", ascending=False).reset_index(drop=True)


def save_practice(user_id: str, row: dict[str, Any]) -> str:
    """Insert one practice row. Returns the new practice id."""
    url, anon_key = get_config()
    practice_id = str(uuid.uuid4())
    payload = _practice_payload(user_id, row, practice_id=practice_id)
    response = requests.post(
        f"{url}/rest/v1/practices",
        headers=_headers(anon_key, prefer="return=minimal"),
        json=payload,
        timeout=30,
    )
    if response.status_code not in (200, 201):
        raise ValueError(
            f"Could not save practice ({response.status_code}): {response.text[:300]}"
        )
    return practice_id


def update_practice(user_id: str, practice_id: str, row: dict[str, Any]) -> None:
    """Update one practice owned by user_id."""
    if not practice_id:
        raise ValueError("Missing practice id.")
    url, anon_key = get_config()
    payload = _practice_payload(user_id, row)
    # Do not send id/user_id in the PATCH body; filter by both in the query.
    response = requests.patch(
        f"{url}/rest/v1/practices",
        headers=_headers(anon_key, prefer="return=minimal"),
        params={
            "id": f"eq.{practice_id}",
            "user_id": f"eq.{user_id}",
        },
        json=payload,
        timeout=30,
    )
    if response.status_code not in (200, 204):
        raise ValueError(
            f"Could not update practice ({response.status_code}): {response.text[:300]}"
        )


def delete_practice(user_id: str, practice_id: str) -> None:
    """Delete one practice owned by user_id."""
    if not practice_id:
        raise ValueError("Missing practice id.")
    url, anon_key = get_config()
    response = requests.delete(
        f"{url}/rest/v1/practices",
        headers=_headers(anon_key, prefer="return=minimal"),
        params={
            "id": f"eq.{practice_id}",
            "user_id": f"eq.{user_id}",
        },
        timeout=30,
    )
    if response.status_code not in (200, 204):
        raise ValueError(
            f"Could not delete practice ({response.status_code}): {response.text[:300]}"
        )


def clear_practices(user_id: str) -> None:
    """Delete all practices for user_id."""
    url, anon_key = get_config()
    response = requests.delete(
        f"{url}/rest/v1/practices",
        headers=_headers(anon_key, prefer="return=minimal"),
        params={"user_id": f"eq.{user_id}"},
        timeout=30,
    )
    if response.status_code not in (200, 204):
        raise ValueError(
            f"Could not clear practices ({response.status_code}): {response.text[:300]}"
        )

def load_user_goal(user_id: str) -> dict[str, Any] | None:
    """Return {user_id, season_meter_goal, updated_at} or None if no row."""
    url, anon_key = get_config()
    response = requests.get(
        f"{url}/rest/v1/user_goals",
        headers=_headers(anon_key),
        params={
            "user_id": f"eq.{user_id}",
            "select": "user_id,season_meter_goal,updated_at",
            "limit": "1",
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise ValueError(
            f"Could not load goal ({response.status_code}): {response.text[:300]}"
        )
    rows = response.json() or []
    if not rows:
        return None
    row = rows[0]
    goal = row.get("season_meter_goal")
    return {
        "user_id": row.get("user_id"),
        "season_meter_goal": int(goal) if goal is not None else None,
        "updated_at": row.get("updated_at"),
    }


def upsert_user_goal(user_id: str, season_meter_goal: int | None) -> None:
    """Insert or update the season meter goal for user_id."""
    from datetime import datetime, timezone

    url, anon_key = get_config()
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "user_id": user_id,
        "season_meter_goal": season_meter_goal,
        "updated_at": now,
    }
    existing = load_user_goal(user_id)
    if existing is None:
        response = requests.post(
            f"{url}/rest/v1/user_goals",
            headers=_headers(anon_key, prefer="return=minimal"),
            json=payload,
            timeout=30,
        )
        if response.status_code not in (200, 201):
            raise ValueError(
                f"Could not save goal ({response.status_code}): {response.text[:300]}"
            )
        return

    response = requests.patch(
        f"{url}/rest/v1/user_goals",
        headers=_headers(anon_key, prefer="return=minimal"),
        params={"user_id": f"eq.{user_id}"},
        json={
            "season_meter_goal": season_meter_goal,
            "updated_at": now,
        },
        timeout=30,
    )
    if response.status_code not in (200, 204):
        raise ValueError(
            f"Could not update goal ({response.status_code}): {response.text[:300]}"
        )
