from dataclasses import replace

from music_engine.config import DEFAULT_CONFIG
from music_engine.scoring import (
    new_release_score, normalize_map, region_levels, score_for_you, score_local_popularity,
)
from helpers import TODAY, activity_df, iso, songs_df

PROFILE = {
    "genre_scores": {"pop": 3.0},
    "artist_scores": {"a1": 3.0},
    "followed_artists": set(),
    "disliked_ids": set(),
    "seen_ids": set(),
}


def test_liked_artist_has_positive_score():
    song = {"artist_id": "a1", "genres_list": ["pop"]}
    profile = {"genre_scores": {"pop": 1.0}, "artist_scores": {"a1": 1.0}, "disliked_ids": set(), "seen_ids": set()}
    score, reasons = score_for_you(song, profile)
    assert score > 0
    assert "By an artist you like" in reasons


def test_liked_artist_ranks_above_unrelated_artist():
    liked = {"song_id": "x", "artist_id": "a1", "genres_list": ["rock"]}
    other = {"song_id": "y", "artist_id": "a9", "genres_list": ["rock"]}
    profile = {**PROFILE, "genre_scores": {"rock": 1.0}}
    assert score_for_you(liked, profile)[0] > score_for_you(other, profile)[0]


def test_liked_genre_ranks_above_non_matching_genre():
    match = {"song_id": "x", "artist_id": "a9", "genres_list": ["pop"]}
    miss = {"song_id": "y", "artist_id": "a8", "genres_list": ["jazz"]}
    assert score_for_you(match, PROFILE)[0] > score_for_you(miss, PROFILE)[0]


def test_no_match_has_no_reasons():
    _, reasons = score_for_you({"song_id": "z", "artist_id": "a9", "genres_list": ["jazz"]}, PROFILE)
    assert reasons == []


def test_followed_artist_reason():
    profile = {**PROFILE, "followed_artists": {"a1"}}
    _, reasons = score_for_you({"song_id": "z", "artist_id": "a1", "genres_list": []}, profile)
    assert reasons == ["By an artist you follow"]


def test_normalize_map_edge_cases():
    assert normalize_map({}) == {}
    assert normalize_map({"a": 0.0}) == {}
    assert normalize_map({"a": 4.0, "b": 2.0, "c": -1.0}) == {"a": 1.0, "b": 0.5}


def test_recent_local_activity_ranks_songs():
    act = activity_df([("R", "s1", 1, 1000, 400, 80), ("R", "s2", 1, 10, 4, 1)])
    scores = score_local_popularity(act, "R", TODAY)
    assert scores["s1"] == 1.0 and scores["s2"] < scores["s1"]


def test_old_activity_outside_window_is_ignored():
    act = activity_df([("R", "s1", 20, 99999, 5000, 900), ("R", "s2", 2, 10, 4, 1)])
    scores = score_local_popularity(act, "R", TODAY, window_days=7)
    assert "s1" not in scores and "s2" in scores


def test_window_is_configurable_and_inclusive():
    act = activity_df([("R", "s1", 6, 10, 5, 1), ("R", "s2", 7, 10, 5, 1)])
    assert set(score_local_popularity(act, "R", TODAY, window_days=7)) == {"s1"}
    assert set(score_local_popularity(act, "R", TODAY, window_days=8)) == {"s1", "s2"}


def test_other_region_ignored_and_children_included():
    act = activity_df([("IN-TS-HYD", "s1", 1, 10, 5, 1), ("IN-MH-MUM", "s2", 1, 10, 5, 1)])
    assert set(score_local_popularity(act, "IN-TS-HYD", TODAY)) == {"s1"}
    assert set(score_local_popularity(act, "IN-TS", TODAY)) == {"s1"}
    assert set(score_local_popularity(act, None, TODAY)) == {"s1", "s2"}


def test_popularity_empty_activity():
    assert score_local_popularity(activity_df([]), "R", TODAY) == {}


def test_region_levels():
    assert region_levels("IN-TS-HYD") == ["IN-TS-HYD", "IN-TS", "IN"]
    assert region_levels("") == [] and region_levels(None) == []


def _song(days_ago, artist="a1"):
    release = "" if days_ago is None else iso(days_ago)
    return songs_df([{"song_id": "s", "artist_id": artist, "release_date": release}]).to_dict("records")[0]


def test_new_release_rules():
    aff = {"a1": 1.0}
    assert new_release_score(_song(5), aff, TODAY) is not None          # recent: qualifies
    assert new_release_score(_song(30), aff, TODAY) is not None         # window edge: qualifies
    assert new_release_score(_song(31), aff, TODAY) is None             # too old
    assert new_release_score(_song(-3), aff, TODAY) is None             # future
    assert new_release_score(_song(None), aff, TODAY) is None           # missing date
    assert new_release_score(_song(5, artist="a9"), aff, TODAY) is None  # unknown artist


def test_new_release_fresher_scores_higher_and_window_configurable():
    aff = {"a1": 1.0}
    assert new_release_score(_song(1), aff, TODAY) > new_release_score(_song(20), aff, TODAY)
    assert new_release_score(_song(20), aff, TODAY, window_days=14) is None
    cfg = replace(DEFAULT_CONFIG, release_affinity_weight=1.0, release_freshness_weight=0.0)
    assert new_release_score(_song(10), aff, TODAY, config=cfg) == 1.0
