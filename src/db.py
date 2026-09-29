"""Supabase REST helpers for RowSeer auth and practice persistence."""

from __future__ import annotations

import uuid
from typing import Any

import bcrypt
import pandas as pd
import requests
import streamlit as st

PRACTICE_COLUMNS = ["date", "type", "distance_m", "time_sec", "notes"]


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
    """Fetch practices for a user as a DataFrame with app columns."""
    url, anon_key = get_config()
    response = requests.get(
        f"{url}/rest/v1/practices",
        headers=_headers(anon_key),
        params={
            "user_id": f"eq.{user_id}",
            "select": "practice_date,type,distance_m,time_sec,notes",
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
        return pd.DataFrame(columns=PRACTICE_COLUMNS)

    frame = pd.DataFrame(rows)
    frame = frame.rename(columns={"practice_date": "date"})
    for column in PRACTICE_COLUMNS:
        if column not in frame.columns:
            frame[column] = "" if column == "notes" else None
    frame = frame[PRACTICE_COLUMNS].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["distance_m"] = pd.to_numeric(frame["distance_m"], errors="coerce").fillna(0).astype(int)
    frame["time_sec"] = pd.to_numeric(frame["time_sec"], errors="coerce").fillna(0).astype(int)
    frame["type"] = frame["type"].astype(str).str.lower().str.strip()
    frame["notes"] = frame["notes"].fillna("").astype(str)
    return frame.sort_values("date", ascending=False).reset_index(drop=True)


def save_practice(user_id: str, row: dict[str, Any]) -> None:
    """Insert one practice row for the given user."""
    url, anon_key = get_config()
    practice_date = row["date"]
    if hasattr(practice_date, "strftime"):
        practice_date = practice_date.strftime("%Y-%m-%d")
    else:
        practice_date = str(practice_date)[:10]

    payload = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "practice_date": practice_date,
        "type": str(row["type"]).lower().strip(),
        "distance_m": int(row["distance_m"]),
        "time_sec": int(row["time_sec"]),
        "notes": str(row.get("notes") or ""),
    }
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
