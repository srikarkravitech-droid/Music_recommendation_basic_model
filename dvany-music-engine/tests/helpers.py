"""Tiny builders so tests can use in-memory datasets."""

from datetime import date, timedelta

import pandas as pd

from music_engine.data_loader import (
    prepare_activity, prepare_follows, prepare_interactions, prepare_songs, prepare_users,
)

TODAY = date(2026, 10, 25)


def iso(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).isoformat()


def songs_df(rows):
    """rows: dicts with song_id plus optional overrides."""
    full = []
    for r in rows:
        base = {"song_id": "", "title": "T", "artist_id": "a1", "artist_name": "Artist 1",
                "genres": "pop", "release_date": "", "language": "English", "available": "true"}
        base.update(r)
        full.append(base)
    return prepare_songs(pd.DataFrame(full, dtype=str))


def interactions_df(rows):
    """rows: (user_id, song_id, action, days_ago[, duration])"""
    data = [{"user_id": r[0], "song_id": r[1], "action": r[2], "event_date": iso(r[3]),
             "duration_seconds": str(r[4]) if len(r) > 4 else ""} for r in rows]
    cols = ["user_id", "song_id", "action", "event_date", "duration_seconds"]
    return prepare_interactions(pd.DataFrame(data, columns=cols, dtype=str))


def activity_df(rows):
    """rows: (region_code, song_id, days_ago, plays, listeners, likes)"""
    data = [{"region_code": r[0], "song_id": r[1], "activity_date": iso(r[2]),
             "plays": str(r[3]), "unique_listeners": str(r[4]), "likes": str(r[5])} for r in rows]
    cols = ["region_code", "song_id", "activity_date", "plays", "unique_listeners", "likes"]
    return prepare_activity(pd.DataFrame(data, columns=cols, dtype=str))


def follows_df(rows):
    """rows: (user_id, artist_id, action, days_ago)"""
    data = [{"user_id": r[0], "artist_id": r[1], "action": r[2], "event_date": iso(r[3])} for r in rows]
    return prepare_follows(pd.DataFrame(data, columns=["user_id", "artist_id", "action", "event_date"], dtype=str))


def users_df(rows):
    return prepare_users(pd.DataFrame(rows, dtype=str))
