"""Compose the three shelves: For You, Popular in Your Area, New Releases."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Dict, List, Optional

import pandas as pd

from .config import DEFAULT_CONFIG, EngineConfig
from .preferences import build_profile
from .scoring import (
    new_release_score,
    normalize_map,
    popularity_from_totals,
    region_levels,
    score_for_you,
    summarize_activity,
)


def _item(song: dict, score: float, reasons: List[str], rank: int) -> dict:
    release = song.get("release_date")
    return {
        "rank": rank,
        "song_id": song["song_id"],
        "title": song.get("title", ""),
        "artist_id": song.get("artist_id", ""),
        "artist_name": song.get("artist_name", ""),
        "genres": list(song.get("genres_list", [])),
        "language": song.get("language", ""),
        "release_date": release.isoformat() if release is not None and not pd.isna(release) else None,
        "score": round(float(score), 4),
        "reasons": reasons,
    }


def _rank(scored: List[tuple], top_k: int) -> List[dict]:
    """scored = [(score, song, reasons)]; highest score first, song_id breaks ties."""
    scored.sort(key=lambda t: (-t[0], t[1]["song_id"]))
    return [_item(song, score, reasons, i) for i, (score, song, reasons) in enumerate(scored[:top_k], start=1)]


def _candidate_catalog(songs: pd.DataFrame, profile: dict, today: date) -> List[dict]:
    """Available, already-released, non-disliked, de-duplicated songs.

    A song with a *missing* release date stays eligible for For You/Popular
    (it just can never qualify as a new release); a *future* date is excluded
    from every shelf because the song is not out yet.
    """
    seen, catalog = set(), []
    for song in songs.to_dict("records"):
        song_id = song["song_id"]
        if song_id in seen or song_id in profile["disliked_ids"]:
            continue
        if not song.get("available_bool", True):
            continue
        release = song.get("release_date")
        if release is not None and not pd.isna(release) and release > today:
            continue
        seen.add(song_id)
        catalog.append(song)
    return catalog


def _local_totals(activity: pd.DataFrame, region_code: str, today: date, allowed: set, cfg: EngineConfig):
    """Try city -> state -> country -> everywhere until enough songs have activity."""
    chosen, chosen_level = None, None
    for level in region_levels(region_code) + [None]:
        totals = summarize_activity(activity, level, today, cfg.popularity_window_days)
        totals = totals[totals.index.isin(allowed)]
        chosen, chosen_level = totals, level
        if len(totals) >= cfg.min_local_songs:
            break
    return chosen, chosen_level


def recommend_all(
    user_id: str,
    user: Optional[dict],
    songs: pd.DataFrame,
    interactions: pd.DataFrame,
    activity: pd.DataFrame,
    today: date,
    top_k: Optional[int] = None,
    follows: Optional[pd.DataFrame] = None,
    config: EngineConfig = DEFAULT_CONFIG,
) -> Dict:
    cfg = config if top_k is None else replace(config, top_k=top_k)
    user = user or {}
    region_code = str(user.get("region_code", "") or "").strip()
    city = str(user.get("city", "") or "").strip()

    profile = build_profile(user_id, songs, interactions, follows, cfg)
    catalog = _candidate_catalog(songs, profile, today)
    notes: List[str] = []

    # ---- For You --------------------------------------------------------
    scored = []
    for song in catalog:
        score, reasons = score_for_you(song, profile, cfg)
        if not reasons:  # no genre/artist match -> irrelevant, leave it out
            continue
        if song["song_id"] in profile["seen_ids"]:
            score *= cfg.seen_penalty
        scored.append((score, song, reasons))
    for_you = _rank(scored, cfg.top_k)

    # ---- Popular in Your Area ------------------------------------------
    by_id = {s["song_id"]: s for s in catalog}
    totals, level = _local_totals(activity, region_code, today, set(by_id), cfg)
    pop_scores = popularity_from_totals(totals, set(by_id), cfg)
    if level and level == region_code:
        scope, place = "local", city or region_code
    elif level:
        scope, place = "regional", level
    else:
        scope, place = "overall", None

    scored = []
    for song_id, score in pop_scores.items():
        row = totals.loc[song_id]
        stats = (
            f"{int(row['plays']):,} plays, {int(row['unique_listeners']):,} listeners "
            f"in the last {cfg.popularity_window_days} days"
        )
        if scope == "local":
            reasons = [f"Trending in {place}", stats]
        elif scope == "regional":
            reasons = [f"Popular across {place} (not enough activity in {city or region_code} yet)", stats]
        else:
            suffix = " (not enough regional activity)" if region_code else ""
            reasons = [f"Popular overall{suffix}", stats]
        scored.append((score, by_id[song_id], reasons))
    popular = _rank(scored, cfg.top_k)
    if scope != "local":
        notes.append(f"Popularity shelf uses '{scope}' data" + (f" ({place})." if place else "."))

    # ---- New Releases from Your Artists --------------------------------
    artist_affinity = normalize_map(profile["artist_scores"])
    scored = []
    for song in catalog:
        score = new_release_score(song, artist_affinity, today, cfg.new_release_window_days, cfg)
        if score is None:
            continue
        age = (today - song["release_date"]).days
        who = "follow" if song["artist_id"] in profile["followed_artists"] else "like"
        when = "Released today" if age == 0 else f"Released {age} day{'s' if age != 1 else ''} ago"
        scored.append((score, song, [f"New release from an artist you {who}", when]))
    new_releases = _rank(scored, cfg.top_k)

    if not profile["genre_scores"] and not profile["artist_scores"]:
        notes.append("No positive listening history for this user: personalised shelves are empty.")

    return {
        "user_id": user_id,
        "region_code": region_code or None,
        "generated_for_date": today.isoformat(),
        "popularity_scope": scope,
        "notes": notes,
        "for_you": for_you,
        "popular_in_your_area": popular,
        "new_releases_from_your_artists": new_releases,
    }
