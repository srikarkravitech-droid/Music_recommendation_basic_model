"""Build a user's taste profile from their interaction history.

State model (so reversals work properly): events are replayed in date order
(file order breaks ties) and each song ends in a final state:

    like / unlike      -> liked on/off
    save / unsave      -> saved on/off
    dislike            -> disliked on; clears like and save
    undislike          -> disliked off
    like or save       -> clears an earlier dislike
    play               -> counted only if duration >= min_play_seconds
                          (or duration is unknown)
    skip               -> counted

A song's net weight is computed from that *final* state, then credited to its
genres and artist. Unknown songs and unknown actions are ignored.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, Optional

import pandas as pd

from .config import DEFAULT_CONFIG, EngineConfig


def _song_net_weight(state: dict, cfg: EngineConfig) -> float:
    w = cfg.action_weights
    net = 0.0
    if state["liked"]:
        net += w["like"]
    if state["saved"]:
        net += w["save"]
    if state["disliked"]:
        net += w["dislike"]
    net += min(state["plays"] * w["play"], cfg.max_play_bonus)
    net += state["skips"] * w["skip"]
    return net


def build_profile(
    user_id: str,
    songs: pd.DataFrame,
    interactions: pd.DataFrame,
    follows: Optional[pd.DataFrame] = None,
    config: EngineConfig = DEFAULT_CONFIG,
) -> Dict:
    song_lookup = songs.drop_duplicates("song_id").set_index("song_id").to_dict("index")
    events = interactions[interactions["user_id"] == user_id].sort_values("event_date", kind="stable")

    states: Dict[str, dict] = {}
    for event in events.to_dict("records"):
        song_id = event["song_id"]
        if song_id not in song_lookup:
            continue
        action = str(event["action"]).lower()
        st = states.setdefault(
            song_id, {"liked": False, "saved": False, "disliked": False, "plays": 0, "skips": 0, "heard": False}
        )
        if action == "like":
            st["liked"], st["disliked"], st["heard"] = True, False, True
        elif action == "unlike":
            st["liked"] = False
        elif action == "save":
            st["saved"], st["disliked"], st["heard"] = True, False, True
        elif action == "unsave":
            st["saved"] = False
        elif action == "dislike":
            st["disliked"], st["liked"], st["saved"] = True, False, False
        elif action == "undislike":
            st["disliked"] = False
        elif action == "play":
            st["heard"] = True
            duration = event.get("duration_seconds")
            if duration is None or pd.isna(duration) or duration >= config.min_play_seconds:
                st["plays"] += 1
        elif action == "skip":
            st["skips"] += 1
            st["heard"] = True

    genre_scores: Counter = Counter()
    artist_scores: Counter = Counter()
    disliked_ids, seen_ids = set(), set()
    for song_id, st in states.items():
        song = song_lookup[song_id]
        if st["disliked"]:
            disliked_ids.add(song_id)
        if st["heard"]:
            seen_ids.add(song_id)
        net = _song_net_weight(st, config)
        for genre in song.get("genres_list", []):
            genre_scores[genre] += net
        artist_scores[song["artist_id"]] += net

    # Artist follows are artist-level events (separate file); follow/unfollow replay.
    followed = set()
    if follows is not None and not follows.empty:
        user_follows = follows[follows["user_id"] == user_id].sort_values("event_date", kind="stable")
        for row in user_follows.to_dict("records"):
            if row["action"] in {"follow", "follow_artist"}:
                followed.add(row["artist_id"])
            elif row["action"] in {"unfollow", "unfollow_artist"}:
                followed.discard(row["artist_id"])
    for artist_id in followed:
        artist_scores[artist_id] += config.action_weights["follow_artist"]

    # Only positive affinities drive recommendations.
    return {
        "genre_scores": {k: v for k, v in genre_scores.items() if v > 0},
        "artist_scores": {k: v for k, v in artist_scores.items() if v > 0},
        "followed_artists": followed,
        "disliked_ids": disliked_ids,
        "seen_ids": seen_ids,
    }
