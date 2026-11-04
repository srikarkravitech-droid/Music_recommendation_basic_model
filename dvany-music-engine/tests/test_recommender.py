import logging
from datetime import date
from dataclasses import replace

import pandas as pd
import pytest

from music_engine import DEFAULT_CONFIG, DataError, load_data, recommend_all
from music_engine.data_loader import prepare_interactions, prepare_songs
from music_engine.preferences import build_profile
from helpers import TODAY, activity_df, follows_df, interactions_df, iso, songs_df, users_df

SAMPLE_TODAY = date(2026, 10, 25)  # the date data/ was generated for


def ids(shelf):
    return [item["song_id"] for item in shelf]


def run(songs, interactions=None, activity=None, follows=None, user=None, uid="u1", **kw):
    return recommend_all(
        user_id=uid, user=user if user is not None else {"region_code": "R", "city": "Rville"},
        songs=songs,
        interactions=interactions if interactions is not None else interactions_df([]),
        activity=activity if activity is not None else activity_df([]),
        today=TODAY, follows=follows, **kw,
    )


# ------------------------------------------------------------ profile rules
def test_unlike_reverses_like():
    songs = songs_df([{"song_id": "s1", "genres": "pop"}])
    inter = interactions_df([("u1", "s1", "like", 5), ("u1", "s1", "unlike", 3)])
    assert build_profile("u1", songs, inter)["genre_scores"] == {}


def test_unsave_reverses_save_but_like_remains():
    songs = songs_df([{"song_id": "s1", "genres": "pop"}])
    inter = interactions_df([("u1", "s1", "like", 6), ("u1", "s1", "save", 5), ("u1", "s1", "unsave", 4)])
    assert build_profile("u1", songs, inter)["genre_scores"] == {"pop": 3.0}


def test_short_plays_are_ignored_and_long_plays_counted():
    songs = songs_df([{"song_id": "s1", "genres": "pop"}])
    short = interactions_df([("u1", "s1", "play", 1, 5)])
    long = interactions_df([("u1", "s1", "play", 1, 120)])
    assert build_profile("u1", songs, short)["genre_scores"] == {}
    assert build_profile("u1", songs, long)["genre_scores"] == {"pop": 0.5}


def test_skips_reduce_affinity():
    songs = songs_df([{"song_id": "s1", "genres": "pop"}])
    inter = interactions_df([("u1", "s1", "like", 5), ("u1", "s1", "skip", 4), ("u1", "s1", "skip", 3)])
    assert build_profile("u1", songs, inter)["genre_scores"] == {"pop": 1.0}


def test_follow_and_unfollow():
    songs = songs_df([{"song_id": "s1"}])
    inter = interactions_df([])
    f1 = follows_df([("u1", "a1", "follow", 5)])
    f2 = follows_df([("u1", "a1", "follow", 5), ("u1", "a1", "unfollow", 2)])
    assert "a1" in build_profile("u1", songs, inter, f1)["artist_scores"]
    assert build_profile("u1", songs, inter, f2)["artist_scores"] == {}


def test_unknown_song_and_unknown_action_ignored():
    songs = songs_df([{"song_id": "s1"}])
    inter = interactions_df([("u1", "nope", "like", 2), ("u1", "s1", "teleport", 2)])
    p = build_profile("u1", songs, inter)
    assert p["genre_scores"] == {} and p["disliked_ids"] == set()


# ------------------------------------------------------------ For You shelf
def test_dislikes_never_appear_in_any_shelf():
    songs = songs_df([
        {"song_id": "s1", "genres": "pop", "release_date": iso(2)},
        {"song_id": "s2", "genres": "pop", "release_date": iso(2)},
    ])
    inter = interactions_df([("u1", "s1", "like", 9), ("u1", "s2", "dislike", 3)])
    act = activity_df([("R", "s1", 1, 50, 20, 5), ("R", "s2", 1, 5000, 2000, 500)])
    res = run(songs, inter, act)
    for shelf in ("for_you", "popular_in_your_area", "new_releases_from_your_artists"):
        assert "s2" not in ids(res[shelf])


def test_unavailable_songs_excluded_everywhere():
    songs = songs_df([
        {"song_id": "s1", "genres": "pop"},
        {"song_id": "s2", "genres": "pop", "available": "false", "release_date": iso(1)},
    ])
    inter = interactions_df([("u1", "s1", "like", 9)])
    act = activity_df([("R", "s2", 1, 9999, 999, 99), ("R", "s1", 1, 1, 1, 0)])
    res = run(songs, inter, act)
    for shelf in ("for_you", "popular_in_your_area", "new_releases_from_your_artists"):
        assert "s2" not in ids(res[shelf])


def test_unreleased_songs_excluded_from_every_shelf_but_missing_dates_allowed():
    songs = songs_df([
        {"song_id": "liked", "genres": "pop", "release_date": iso(100)},
        {"song_id": "future", "genres": "pop", "release_date": iso(-10)},
        {"song_id": "nodate", "genres": "pop", "release_date": ""},
    ])
    inter = interactions_df([("u1", "liked", "like", 9)])
    act = activity_df([("R", s, 1, 500, 200, 40) for s in ("liked", "future", "nodate")])
    res = run(songs, inter, act)
    for shelf in ("for_you", "popular_in_your_area", "new_releases_from_your_artists"):
        assert "future" not in ids(res[shelf])
    assert "nodate" in ids(res["for_you"]) and "nodate" in ids(res["popular_in_your_area"])


def test_liked_artist_beats_unrelated_artist_in_for_you():
    songs = songs_df([
        {"song_id": "s1", "artist_id": "a1", "genres": "pop"},
        {"song_id": "s2", "artist_id": "a1", "genres": "pop"},   # same artist as the liked song
        {"song_id": "s3", "artist_id": "a9", "genres": "pop"},   # same genre, unrelated artist
    ])
    inter = interactions_df([("u1", "s1", "like", 9)])
    got = ids(run(songs, inter)["for_you"])
    assert "s2" in got and "s3" in got
    assert got.index("s2") < got.index("s3")


def test_seen_penalty_lowers_already_heard_songs():
    songs = songs_df([
        {"song_id": "s1", "artist_id": "a1", "genres": "pop"},   # liked -> heard
        {"song_id": "s2", "artist_id": "a2", "genres": "pop"},   # unheard, genre match only
    ])
    inter = interactions_df([("u1", "s1", "like", 9)])
    default = {i["song_id"]: i["score"] for i in run(songs, inter)["for_you"]}
    harsh = {i["song_id"]: i["score"] for i in run(songs, inter, config=replace(DEFAULT_CONFIG, seen_penalty=0.1))["for_you"]}
    none = {i["song_id"]: i["score"] for i in run(songs, inter, config=replace(DEFAULT_CONFIG, seen_penalty=1.0))["for_you"]}
    assert harsh["s1"] < default["s1"] < none["s1"]
    assert harsh["s2"] == default["s2"] == none["s2"]            # unheard songs are never penalised
    assert harsh["s2"] > harsh["s1"]                             # a harsh penalty flips the order


def test_duplicate_song_ids_appear_once():
    raw = pd.DataFrame([
        {"song_id": "s1", "title": "A", "artist_id": "a1", "artist_name": "X", "genres": "pop", "release_date": iso(3), "language": "", "available": "true"},
        {"song_id": "s1", "title": "A again", "artist_id": "a1", "artist_name": "X", "genres": "pop", "release_date": iso(3), "language": "", "available": "true"},
        {"song_id": "s2", "title": "B", "artist_id": "a1", "artist_name": "X", "genres": "pop", "release_date": iso(3), "language": "", "available": "true"},
    ], dtype=str)
    songs = prepare_songs(raw)
    inter = interactions_df([("u1", "s2", "like", 9)])
    act = activity_df([("R", "s1", 1, 10, 5, 1), ("R", "s1", 2, 10, 5, 1)])
    res = run(songs, inter, act)
    for shelf in ("for_you", "popular_in_your_area", "new_releases_from_your_artists"):
        got = ids(res[shelf])
        assert len(got) == len(set(got))


def test_top_k_limits_each_shelf():
    songs = songs_df([{"song_id": f"s{i}", "genres": "pop"} for i in range(8)])
    inter = interactions_df([("u1", "s0", "like", 5)])
    assert len(run(songs, inter, top_k=3)["for_you"]) == 3


# ------------------------------------------------------ Popular + fallback
def test_popular_uses_city_when_enough_data():
    songs = songs_df([{"song_id": f"s{i}"} for i in range(6)])
    act = activity_df([("IN-TS-HYD", f"s{i}", 1, 100 + i, 40, 5) for i in range(6)])
    res = run(songs, activity=act, user={"region_code": "IN-TS-HYD", "city": "Hyderabad"})
    assert res["popularity_scope"] == "local"
    assert res["popular_in_your_area"][0]["reasons"][0] == "Trending in Hyderabad"


def test_popular_falls_back_to_state_then_overall():
    songs = songs_df([{"song_id": f"s{i}"} for i in range(8)])
    act = activity_df(
        [("IN-TS-WGL", "s0", 1, 10, 4, 1)]
        + [("IN-TS-HYD", f"s{i}", 1, 100, 40, 5) for i in range(1, 7)]
    )
    state = run(songs, activity=act, user={"region_code": "IN-TS-WGL", "city": "Warangal"})
    assert state["popularity_scope"] == "regional"
    assert "IN-TS" in state["popular_in_your_area"][0]["reasons"][0]

    # Unknown state widens to the country level ("IN") before going global.
    country = run(songs, activity=act, user={"region_code": "IN-XX-ABC", "city": "Nowhere"})
    assert country["popularity_scope"] == "regional"
    assert "IN" in country["popular_in_your_area"][0]["reasons"][0]

    # A region with no shared prefix at all falls back to overall popularity.
    nowhere = run(songs, activity=act, user={"region_code": "ZZ-XX-ABC", "city": "Nowhere"})
    assert nowhere["popularity_scope"] == "overall"
    assert nowhere["popular_in_your_area"]


def test_popular_with_no_activity_returns_empty_not_garbage():
    res = run(songs_df([{"song_id": "s1"}]))
    assert res["popular_in_your_area"] == []


# ------------------------------------------------------ New releases shelf
def test_new_releases_only_liked_artists_in_window():
    songs = songs_df([
        {"song_id": "old", "artist_id": "a1", "release_date": iso(60)},
        {"song_id": "new", "artist_id": "a1", "release_date": iso(4)},
        {"song_id": "future", "artist_id": "a1", "release_date": iso(-5)},
        {"song_id": "nodate", "artist_id": "a1", "release_date": ""},
        {"song_id": "other", "artist_id": "a2", "release_date": iso(4)},
        {"song_id": "liked", "artist_id": "a1", "release_date": iso(100)},
    ])
    inter = interactions_df([("u1", "liked", "like", 10)])
    assert ids(run(songs, inter)["new_releases_from_your_artists"]) == ["new"]


def test_new_release_window_configurable():
    songs = songs_df([{"song_id": "new", "artist_id": "a1", "release_date": iso(20)},
                      {"song_id": "liked", "artist_id": "a1", "release_date": iso(100)}])
    inter = interactions_df([("u1", "liked", "like", 10)])
    cfg = replace(DEFAULT_CONFIG, new_release_window_days=14)
    assert run(songs, inter, config=cfg)["new_releases_from_your_artists"] == []


# ----------------------------------------------------- cold start / unknown
def test_unknown_user_and_missing_fields_do_not_crash():
    songs = songs_df([{"song_id": "s1"}])
    res = recommend_all("ghost", None, songs, interactions_df([]), activity_df([]), TODAY)
    assert res["for_you"] == [] and res["new_releases_from_your_artists"] == []
    assert res["region_code"] is None and res["notes"]


def test_cold_start_user_still_gets_popular_shelf():
    songs = songs_df([{"song_id": f"s{i}"} for i in range(6)])
    act = activity_df([("R", f"s{i}", 1, 100 + i, 40, 5) for i in range(6)])
    res = run(songs, activity=act)
    assert res["for_you"] == [] and len(res["popular_in_your_area"]) == 6


def test_every_item_has_score_and_reasons():
    songs = songs_df([{"song_id": "s1", "release_date": iso(2)}, {"song_id": "s2", "genres": "pop"}])
    inter = interactions_df([("u1", "s1", "like", 5)])
    act = activity_df([("R", "s1", 1, 10, 5, 1), ("R", "s2", 1, 10, 5, 1)])
    res = run(songs, inter, act)
    for shelf in ("for_you", "popular_in_your_area", "new_releases_from_your_artists"):
        for item in res[shelf]:
            assert isinstance(item["score"], float) and item["reasons"]


# ------------------------------------------------------------- data loader
def test_loader_rejects_missing_columns():
    with pytest.raises(DataError):
        prepare_songs(pd.DataFrame({"song_id": ["s1"]}))


def test_loader_missing_file(tmp_path):
    with pytest.raises(DataError):
        load_data(tmp_path)


def test_invalid_dates_are_dropped_with_warning(caplog):
    raw = pd.DataFrame([
        {"user_id": "u1", "song_id": "s1", "action": "like", "event_date": "not-a-date"},
        {"user_id": "u1", "song_id": "s1", "action": "LIKE ", "event_date": "2026-10-01"},
    ], dtype=str)
    with caplog.at_level(logging.WARNING):
        df = prepare_interactions(raw)
    assert len(df) == 1 and df.iloc[0]["action"] == "like"
    assert "invalid event_date" in caplog.text


# ------------------------------------------- end-to-end on the shipped data
@pytest.fixture(scope="module")
def sample():
    return load_data()


def sample_run(sample, uid):
    songs, users, inter, act, follows = sample
    user = users[users["user_id"] == uid].iloc[0].to_dict()
    return recommend_all(uid, user, songs, inter, act, SAMPLE_TODAY, follows=follows)


def test_sample_data_meets_size_requirements(sample):
    songs, users, *_ = sample
    assert len(songs) >= 30 and songs["artist_id"].nunique() >= 5 and len(users) >= 3


def test_sample_u001_all_three_shelves_and_edge_cases(sample):
    res = sample_run(sample, "u001")
    assert res["for_you"] and res["popular_in_your_area"] and res["new_releases_from_your_artists"]
    assert res["popularity_scope"] == "local"
    assert "s004" not in ids(res["for_you"])                       # disliked
    for shelf in ("for_you", "popular_in_your_area", "new_releases_from_your_artists"):
        assert "s025" not in ids(res[shelf])                       # unavailable
        assert "s015" not in ids(res[shelf])                       # not released yet
    new = ids(res["new_releases_from_your_artists"])
    assert not {"s015", "s030", "s020"} & set(new)                 # future / no date / day 31
    assert "s033" not in new                                       # a07 was unfollowed, never liked
    assert "s031" not in ids(res["popular_in_your_area"][:3])      # old spike is ignored


def test_sample_unlike_reverses_for_u001(sample):
    songs, _, inter, _, follows = sample
    profile = build_profile("u001", songs, inter, follows)
    assert "electronic" not in profile["genre_scores"]             # only evidence was like->unlike
    assert "a07" not in profile["followed_artists"]


def test_sample_other_users_get_different_results(sample):
    a, b, c = (sample_run(sample, u) for u in ("u001", "u002", "u003"))
    assert ids(a["for_you"]) != ids(b["for_you"]) != ids(c["for_you"])
    assert "s032" not in ids(b["for_you"])                         # u002 disliked it
    assert "s022" not in ids(c["for_you"])                         # u003 disliked it


def test_sample_cold_start_sparse_city_u004(sample):
    res = sample_run(sample, "u004")
    assert res["for_you"] == [] and res["new_releases_from_your_artists"] == []
    assert res["popularity_scope"] == "regional" and res["popular_in_your_area"]


def test_sample_future_release_never_recommended_to_follower_of_its_artist(sample):
    res = sample_run(sample, "u003")                               # follows a03, who has s015 scheduled
    for shelf in ("for_you", "popular_in_your_area", "new_releases_from_your_artists"):
        assert "s015" not in ids(res[shelf])
