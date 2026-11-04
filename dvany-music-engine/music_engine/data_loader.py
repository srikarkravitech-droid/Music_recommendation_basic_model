"""Load, validate and normalise the CSV files.

Every ``prepare_*`` function takes a raw all-string DataFrame and returns a
cleaned one, so tests can build tiny in-memory datasets without touching disk.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DELIMITER = "|"
TRUE_VALUES = {"true", "1", "yes", "y"}

REQUIRED = {
    "songs": ["song_id", "title", "artist_id", "artist_name", "genres", "release_date", "available"],
    "users": ["user_id", "region_code"],
    "interactions": ["user_id", "song_id", "action", "event_date"],
    "activity": ["region_code", "song_id", "activity_date", "plays", "unique_listeners", "likes"],
    "follows": ["user_id", "artist_id", "event_date"],
}
OPTIONAL = {
    "songs": ["language"],
    "users": ["city", "preferred_languages"],
    "interactions": ["duration_seconds"],
    "activity": [],
    "follows": ["action"],
}


class DataError(Exception):
    """Raised when an input file is missing or lacks required columns."""


def _parse_date(value) -> Optional[date]:
    """ISO date (YYYY-MM-DD) -> date, anything else -> None."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _split_list(value) -> List[str]:
    return [part.strip().lower() for part in str(value).split(DELIMITER) if part.strip()]


def _check_columns(df: pd.DataFrame, name: str) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in REQUIRED[name] if c not in df.columns]
    if missing:
        raise DataError(f"{name}: missing required column(s): {', '.join(missing)}")
    for col in OPTIONAL[name]:
        if col not in df.columns:
            df[col] = ""
    return df


def _strip(df: pd.DataFrame, cols: List[str]) -> None:
    for col in cols:
        df[col] = df[col].fillna("").astype(str).str.strip()


# ---------------------------------------------------------------- prepare_*
def prepare_songs(raw: pd.DataFrame) -> pd.DataFrame:
    df = _check_columns(raw, "songs")
    _strip(df, ["song_id", "title", "artist_id", "artist_name", "genres", "language", "available"])
    n = len(df)
    df = df[df["song_id"] != ""]
    df = df.drop_duplicates("song_id", keep="first")
    if len(df) != n:
        log.warning("songs: dropped %d row(s) with blank or duplicate song_id", n - len(df))
    df["release_date"] = df["release_date"].map(_parse_date)
    df["genres_list"] = df["genres"].map(_split_list)
    df["available_bool"] = df["available"].str.lower().isin(TRUE_VALUES)
    return df.reset_index(drop=True)


def prepare_users(raw: pd.DataFrame) -> pd.DataFrame:
    df = _check_columns(raw, "users")
    _strip(df, ["user_id", "region_code", "city", "preferred_languages"])
    df = df[df["user_id"] != ""].drop_duplicates("user_id", keep="first")
    df["preferred_languages_list"] = df["preferred_languages"].map(_split_list)
    return df.reset_index(drop=True)


def prepare_interactions(raw: pd.DataFrame) -> pd.DataFrame:
    df = _check_columns(raw, "interactions")
    _strip(df, ["user_id", "song_id", "action"])
    df["action"] = df["action"].str.lower()
    df["event_date"] = df["event_date"].map(_parse_date)
    bad = df["event_date"].isna()
    if bad.any():
        log.warning("interactions: dropped %d row(s) with an invalid event_date", int(bad.sum()))
        df = df[~bad]
    df["duration_seconds"] = pd.to_numeric(df["duration_seconds"], errors="coerce")
    return df.reset_index(drop=True)


def prepare_activity(raw: pd.DataFrame) -> pd.DataFrame:
    df = _check_columns(raw, "activity")
    _strip(df, ["region_code", "song_id"])
    df["activity_date"] = df["activity_date"].map(_parse_date)
    bad = df["activity_date"].isna()
    if bad.any():
        log.warning("regional_activity: dropped %d row(s) with an invalid activity_date", int(bad.sum()))
        df = df[~bad]
    for col in ("plays", "unique_listeners", "likes"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).clip(lower=0)
    return df.reset_index(drop=True)


def prepare_follows(raw: pd.DataFrame) -> pd.DataFrame:
    df = _check_columns(raw, "follows")
    _strip(df, ["user_id", "artist_id", "action"])
    df["action"] = df["action"].str.lower().replace("", "follow")
    df["event_date"] = df["event_date"].map(_parse_date)
    df = df[df["event_date"].notna()]
    return df.reset_index(drop=True)


# --------------------------------------------------------------------- I/O
def _read_csv(data_dir: Path, filename: str) -> pd.DataFrame:
    path = data_dir / filename
    if not path.exists():
        raise DataError(f"Missing data file: {path}")
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception as exc:  # malformed CSV
        raise DataError(f"Could not read {path}: {exc}") from exc


def load_data(data_dir=None) -> Tuple[pd.DataFrame, ...]:
    """Return (songs, users, interactions, activity, follows)."""
    data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    songs = prepare_songs(_read_csv(data_dir, "songs.csv"))
    users = prepare_users(_read_csv(data_dir, "users.csv"))
    interactions = prepare_interactions(_read_csv(data_dir, "interactions.csv"))
    activity = prepare_activity(_read_csv(data_dir, "regional_activity.csv"))
    follows_path = data_dir / "artist_follows.csv"
    if follows_path.exists():
        follows = prepare_follows(_read_csv(data_dir, "artist_follows.csv"))
    else:
        log.info("artist_follows.csv not found; continuing without follows")
        follows = prepare_follows(pd.DataFrame(columns=REQUIRED["follows"]))
    return songs, users, interactions, activity, follows
