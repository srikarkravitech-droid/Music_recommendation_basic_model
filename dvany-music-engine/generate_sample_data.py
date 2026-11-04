"""Generate the fictional sample dataset in data/, dated relative to a reference day.

    python generate_sample_data.py                    # relative to today
    python generate_sample_data.py --today 2026-10-25 # reproducible

The data deliberately includes edge cases: an unavailable song, a future-dated
release, a song with no release date, a release just outside the 30-day window,
a song disliked by a user, like->unlike reversals, a follow->unfollow, a too-short
play, an unknown song id, a cold-start user, and a city with too little activity.
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

ARTISTS = {
    "a01": "Neon Harbor",
    "a02": "Riya & The Monsoons",
    "a03": "Delta Circuit",
    "a04": "Kaveri Strings",
    "a05": "Block Seven",
    "a06": "Saffron Skies",
    "a07": "Iron Lantern",
    "a08": "Velvet Hours",
}

# (song_id, title, artist_id, genres, language, days_since_release, available)
# days_since_release: None = missing date, negative = release is in the future
SONGS = [
    ("s001", "Moonlight Drive", "a01", "pop|indie", "English", 400, True),
    ("s002", "Glass Skyline", "a01", "pop", "English", 150, True),
    ("s003", "Paper Lanterns", "a01", "pop|indie", "English", 12, True),
    ("s004", "Midnight Static", "a01", "pop|electronic", "English", 70, True),
    ("s005", "Golden Hour Loop", "a01", "indie", "English", 3, True),
    ("s006", "Rain On Tin Roofs", "a02", "indie|folk", "English", 300, True),
    ("s007", "Chai Stains", "a02", "indie|folk", "Hindi", 220, True),
    ("s008", "Barefoot Road", "a02", "folk", "Telugu", 90, True),
    ("s009", "Lantern Fields", "a02", "indie|folk", "Hindi", 20, True),
    ("s010", "Slow Train Home", "a02", "folk", "English", 600, True),
    ("s011", "Voltage Bloom", "a03", "electronic|house", "English", 200, True),
    ("s012", "Night Bus To Nowhere", "a03", "electronic", "English", 45, True),
    ("s013", "Pulse Garden", "a03", "house|electronic", "English", 8, True),
    ("s014", "Static Saints", "a03", "electronic|pop", "English", 130, True),
    ("s015", "Afterglow Protocol", "a03", "electronic", "English", -10, True),  # future release
    ("s016", "Raga Rewired", "a04", "classical|fusion", "Instrumental", 500, True),
    ("s017", "Veena Nights", "a04", "classical", "Instrumental", 260, True),
    ("s018", "Monsoon Alap", "a04", "classical|fusion", "Instrumental", 28, True),
    ("s019", "Temple Bells Remix", "a04", "fusion|electronic", "Instrumental", 100, True),
    ("s020", "Sitar Sunrise", "a04", "classical", "Instrumental", 31, True),  # just outside window
    ("s021", "Hyderabad Hustle", "a05", "hip-hop|rap", "Telugu", 80, True),
    ("s022", "Concrete Poetry", "a05", "hip-hop|rap", "English", 160, True),
    ("s023", "Charminar Cypher", "a05", "hip-hop", "Telugu", 5, True),
    ("s024", "Late Fee", "a05", "rap", "English", 350, True),
    ("s025", "Gully Gold", "a05", "hip-hop|pop", "Hindi", 40, False),  # unavailable
    ("s026", "Dil Ka Postcard", "a06", "pop|filmi", "Hindi", 60, True),
    ("s027", "Baarish Wali Raat", "a06", "filmi", "Hindi", 15, True),
    ("s028", "Sundari Sundari", "a06", "pop|filmi", "Telugu", 110, True),
    ("s029", "Pyaar Ki Playlist", "a06", "pop|filmi", "Hindi", 240, True),
    ("s030", "Mehndi Beats", "a06", "filmi|pop", "Hindi", None, True),  # missing release date
    ("s031", "Thunder Ledger", "a07", "rock|metal", "English", 420, True),
    ("s032", "Broken Compass", "a07", "rock", "English", 180, True),
    ("s033", "Steel Monsoon", "a07", "rock|metal", "English", 22, True),
    ("s034", "Ash And Ember", "a07", "rock", "English", 75, True),
    ("s035", "Last Train Riot", "a07", "rock|punk", "English", 700, True),
    ("s036", "Blue Hour Letters", "a08", "jazz|r&b", "English", 140, True),
    ("s037", "Honey In The Rain", "a08", "lofi|r&b", "English", 95, True),
    ("s038", "Coffee At Two", "a08", "jazz|lofi", "English", 25, True),
    ("s039", "Satin Skyline", "a08", "r&b|pop", "English", 10, True),
    ("s040", "Quiet Neon", "a08", "lofi|jazz", "English", 55, True),
]

USERS = [
    ("u001", "IN-TS-HYD", "Hyderabad", "Telugu|Hindi"),
    ("u002", "IN-MH-MUM", "Mumbai", "Hindi|English"),
    ("u003", "IN-KA-BLR", "Bengaluru", "English|Kannada"),
    ("u004", "IN-TS-WGL", "Warangal", "Telugu"),  # cold start + sparse city
]

# (user_id, song_id, action, days_ago, duration_seconds or "")
INTERACTIONS = [
    # u001: pop/indie + Telugu hip-hop listener
    ("u001", "s001", "like", 40, ""), ("u001", "s002", "like", 35, ""),
    ("u001", "s002", "play", 30, 200), ("u001", "s001", "play", 20, 190),
    ("u001", "s005", "play", 2, 185), ("u001", "s006", "save", 28, ""),
    ("u001", "s008", "like", 25, ""), ("u001", "s021", "like", 18, ""),
    ("u001", "s021", "play", 10, 210), ("u001", "s022", "play", 9, 15),  # too short -> ignored
    ("u001", "s004", "dislike", 15, ""),
    ("u001", "s014", "like", 12, ""), ("u001", "s014", "unlike", 7, ""),  # reversal
    ("u001", "s031", "skip", 14, ""), ("u001", "s031", "skip", 13, ""),
    ("u001", "s035", "skip", 12, ""), ("u001", "s026", "play", 8, 120),
    ("u001", "s999", "play", 5, 120),  # unknown song -> ignored
    # u002: filmi/pop + jazz
    ("u002", "s026", "like", 50, ""), ("u002", "s029", "like", 45, ""),
    ("u002", "s028", "save", 30, ""), ("u002", "s027", "play", 2, 200),
    ("u002", "s036", "like", 22, ""), ("u002", "s038", "play", 10, 160),
    ("u002", "s032", "dislike", 14, ""), ("u002", "s037", "play", 6, 100),
    ("u002", "s031", "skip", 12, ""),
    # u003: electronic + rock + a little classical
    ("u003", "s011", "like", 33, ""), ("u003", "s012", "play", 20, 240),
    ("u003", "s013", "like", 3, ""), ("u003", "s014", "like", 26, ""),
    ("u003", "s031", "like", 40, ""), ("u003", "s034", "save", 18, ""),
    ("u003", "s033", "play", 5, 200), ("u003", "s017", "play", 11, 300),
    ("u003", "s024", "skip", 10, ""), ("u003", "s022", "dislike", 9, ""),
]

# (user_id, artist_id, action, days_ago)
FOLLOWS = [
    ("u001", "a01", "follow", 60), ("u001", "a05", "follow", 22),
    ("u001", "a07", "follow", 30), ("u001", "a07", "unfollow", 29),  # reversal
    ("u002", "a06", "follow", 55), ("u002", "a08", "follow", 20),
    ("u003", "a03", "follow", 40), ("u003", "a07", "follow", 35),
]

REGION_TASTE = {
    "IN-TS-HYD": {"hip-hop": 1.6, "rap": 1.4, "pop": 1.3, "filmi": 1.3, "indie": 1.0, "folk": 1.0, "electronic": 0.8, "rock": 0.7},
    "IN-MH-MUM": {"filmi": 1.8, "pop": 1.4, "jazz": 1.2, "r&b": 1.2, "hip-hop": 1.1, "indie": 0.9, "rock": 0.8},
    "IN-KA-BLR": {"electronic": 1.7, "house": 1.5, "rock": 1.6, "metal": 1.3, "indie": 1.3, "classical": 1.1, "lofi": 1.2},
}


def d(today: date, days_ago: int) -> str:
    return (today - timedelta(days=days_ago)).isoformat()


def write(path: Path, header: list, rows: list) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def build_activity(today: date, rng: random.Random) -> list:
    songs = {s[0]: s for s in SONGS}
    base_pop = {sid: rng.uniform(0.4, 1.6) for sid in songs}
    rows = []
    for region, taste in REGION_TASTE.items():
        for sid, (_, _, _, genres, _, age, _) in songs.items():
            if rng.random() > 0.78:  # not every song is active in every region
                continue
            genre_list = genres.split("|")
            mult = max(taste.get(g, 0.6) for g in genre_list)
            for days_ago in range(0, 28):
                if age is not None and age - days_ago < 0:
                    continue  # nothing is played before it is released
                m = base_pop[sid] * mult
                if sid == "s025" and region == "IN-TS-HYD":
                    m *= 3  # popular but unavailable -> must never be recommended
                if sid == "s031" and region == "IN-TS-HYD":
                    m *= 8 if days_ago >= 10 else 0.2  # old spike outside the 7-day window
                if age is not None and age < 30:
                    m *= 1.5  # new releases get a bump
                plays = max(0, int(m * rng.randint(45, 75)))
                rows.append([
                    region, sid, d(today, days_ago), plays,
                    int(plays * rng.uniform(0.30, 0.50)), int(plays * rng.uniform(0.05, 0.12)),
                ])
    for sid in ("s021", "s023", "s028"):  # Warangal: too sparse -> falls back to IN-TS
        for days_ago in range(0, 3):
            rows.append(["IN-TS-WGL", sid, d(today, days_ago), 20 + 5 * days_ago, 9, 2])
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--today", help="reference date, YYYY-MM-DD (default: today)")
    parser.add_argument("--out", default=str(DATA_DIR), help="output folder")
    args = parser.parse_args()
    today = date.fromisoformat(args.today) if args.today else date.today()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)

    write(out / "songs.csv",
          ["song_id", "title", "artist_id", "artist_name", "genres", "release_date", "language", "available"],
          [[sid, title, aid, ARTISTS[aid], genres, "" if age is None else d(today, age), lang, str(avail).lower()]
           for sid, title, aid, genres, lang, age, avail in SONGS])
    write(out / "users.csv", ["user_id", "region_code", "city", "preferred_languages"], [list(u) for u in USERS])
    write(out / "interactions.csv",
          ["user_id", "song_id", "action", "event_date", "duration_seconds"],
          [[u, s, a, d(today, n), dur] for u, s, a, n, dur in INTERACTIONS])
    write(out / "artist_follows.csv", ["user_id", "artist_id", "action", "event_date"],
          [[u, a, act, d(today, n)] for u, a, act, n in FOLLOWS])
    write(out / "regional_activity.csv",
          ["region_code", "song_id", "activity_date", "plays", "unique_listeners", "likes"],
          build_activity(today, rng))
    print(f"Sample data written to {out} (reference date {today}).")


if __name__ == "__main__":
    main()
