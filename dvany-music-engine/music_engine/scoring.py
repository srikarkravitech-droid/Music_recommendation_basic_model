"""Pure scoring functions (no file or database access)."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

from .config import DEFAULT_CONFIG, EngineConfig


def normalize_map(values: Dict[str, float]) -> Dict[str, float]:
    """Scale positive values into (0, 1] by dividing by the max. Drops non-positive entries."""
    if not values:
        return {}
    max_value = max(values.values())
    if max_value <= 0:
        return {}
    return {key: value / max_value for key, value in values.items() if value > 0}


# ------------------------------------------------------------------ For You
def score_for_you(song: dict, profile: dict, config: EngineConfig = DEFAULT_CONFIG) -> Tuple[float, List[str]]:
    """0.50*genre_match + 0.45*artist_match + 0.05*discovery, each in [0, 1].

    discovery is 1.0 for a song the user has not heard yet, else 0.0.
    A song with no genre or artist match has no reasons; callers should skip it.
    """
    genre_scores = normalize_map(profile.get("genre_scores", {}))
    artist_scores = normalize_map(profile.get("artist_scores", {}))

    best_genre, genre_match = None, 0.0
    for genre in song.get("genres_list", []) or []:
        value = genre_scores.get(genre, 0.0)
        if value > genre_match:
            best_genre, genre_match = genre, value

    artist_id = song.get("artist_id")
    artist_match = artist_scores.get(artist_id, 0.0)
    discovery = 0.0 if song.get("song_id") in profile.get("seen_ids", ()) else 1.0

    score = (
        config.for_you_genre_weight * genre_match
        + config.for_you_artist_weight * artist_match
        + config.for_you_discovery_weight * discovery
    )
    reasons: List[str] = []
    if genre_match > 0:
        reasons.append(f"Because you like {best_genre}")
    if artist_match > 0:
        followed = artist_id in profile.get("followed_artists", ())
        reasons.append("By an artist you follow" if followed else "By an artist you like")
    return score, reasons


# ------------------------------------------------------- Popular in Your Area
def region_levels(region_code: Optional[str]) -> List[str]:
    """'IN-TS-HYD' -> ['IN-TS-HYD', 'IN-TS', 'IN'] (most specific first)."""
    if not region_code:
        return []
    parts = str(region_code).strip().split("-")
    return ["-".join(parts[:i]) for i in range(len(parts), 0, -1)]


def summarize_activity(
    activity: pd.DataFrame,
    region_code: Optional[str],
    today: date,
    window_days: int = 7,
) -> pd.DataFrame:
    """Sum plays/listeners/likes per song inside the window.

    A region matches itself and its children ('IN-TS' includes 'IN-TS-HYD').
    region_code=None means every region. Note: summing unique_listeners over
    days double-counts people who listen on several days (fine for a prototype).
    """
    cols = ["plays", "unique_listeners", "likes"]
    cutoff = today - timedelta(days=window_days - 1)
    rows = activity[(activity["activity_date"] >= cutoff) & (activity["activity_date"] <= today)]
    if region_code:
        rc = rows["region_code"].astype(str)
        rows = rows[(rc == region_code) | rc.str.startswith(region_code + "-")]
    if rows.empty:
        empty = pd.DataFrame(columns=cols, dtype=float)
        empty.index.name = "song_id"
        return empty
    return rows.groupby("song_id")[cols].sum()


def popularity_from_totals(
    totals: pd.DataFrame,
    allowed_song_ids: Optional[Iterable[str]] = None,
    config: EngineConfig = DEFAULT_CONFIG,
) -> Dict[str, float]:
    """Log-scaled weighted popularity, normalised so the top candidate is 1.0."""
    allowed = set(allowed_song_ids) if allowed_song_ids is not None else None
    raw: Dict[str, float] = {}
    for song_id, row in totals.iterrows():
        if allowed is not None and song_id not in allowed:
            continue
        raw[song_id] = (
            config.popularity_plays_weight * math.log1p(max(0.0, row["plays"]))
            + config.popularity_listeners_weight * math.log1p(max(0.0, row["unique_listeners"]))
            + config.popularity_likes_weight * math.log1p(max(0.0, row["likes"]))
        )
    peak = max(raw.values(), default=0.0)
    return {k: v / peak for k, v in raw.items()} if peak > 0 else {}


def score_local_popularity(
    activity: pd.DataFrame,
    region_code: Optional[str],
    today: date,
    window_days: int = 7,
    allowed_song_ids: Optional[Iterable[str]] = None,
    config: EngineConfig = DEFAULT_CONFIG,
) -> Dict[str, float]:
    """Convenience wrapper: window + region filter + scoring in one call."""
    totals = summarize_activity(activity, region_code, today, window_days)
    return popularity_from_totals(totals, allowed_song_ids, config)


# ------------------------------------------------------------- New releases
def new_release_score(
    song: dict,
    artist_scores: Dict[str, float],
    today: date,
    window_days: int = 30,
    config: EngineConfig = DEFAULT_CONFIG,
) -> Optional[float]:
    """0.70*artist_affinity + 0.30*freshness, or None if the song doesn't qualify.

    artist_scores must already be normalised to [0, 1] (see normalize_map).
    Missing, future or out-of-window release dates never qualify, nor does an
    artist with no positive affinity.
    """
    release_date = song.get("release_date")
    if release_date is None or pd.isna(release_date):
        return None
    age_days = (today - release_date).days
    if age_days < 0 or age_days > window_days:
        return None

    affinity = artist_scores.get(song.get("artist_id"), 0.0)
    if affinity <= 0:
        return None

    freshness = 1.0 - (age_days / max(window_days, 1))
    return config.release_affinity_weight * affinity + config.release_freshness_weight * freshness
