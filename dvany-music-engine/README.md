# DVANY Standalone Music Recommendation Engine

A self-contained, offline recommendation engine built from the *DVANY Standalone Music
Recommendation Engine Guide*. It reads local CSV files, scores songs with an explainable
rule-based formula, and produces three independently ranked shelves per user:

| Shelf | Meaning |
| --- | --- |
| **For You** | Songs matching genres/artists the user likes |
| **Popular in Your Area** | Songs with strong recent plays, listeners and likes in the user's region |
| **New Releases from Your Artists** | Recent releases by artists the user likes or follows |

No DVANY connection, database, web API or ML libraries are used.

## Quick start

```bash
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# macOS/Linux:         source .venv/bin/activate
pip install -r requirements.txt

python main.py --user u001 --today 2026-10-25
pytest
```

The shipped sample data was generated for **2026-10-25**. Time windows (7-day popularity,
30-day new releases) are relative to "today", so on any other day either pass
`--today 2026-10-25` or regenerate the data relative to today:

```bash
python generate_sample_data.py          # dates relative to today
python main.py --user u001
```

### CLI options

| Option | Purpose |
| --- | --- |
| `--user u001` | Sample user (prompts if omitted) |
| `--all-users` | Run every user; writes `output/recommendations_<user>.json` each |
| `--top-k 5` | Songs per shelf (default 10) |
| `--today YYYY-MM-DD` | Reference date |
| `--csv` | Also export `output/recommendations.csv` |
| `--data-dir`, `--output-dir` | Use other folders |

Results are printed with human-readable reasons and saved to `output/recommendations.json`.

## Sample users

| User | City | What it demonstrates |
| --- | --- | --- |
| u001 | Hyderabad | Pop/indie + Telugu hip-hop, follows, a dislike, like→unlike, follow→unfollow, a too-short play, an unknown song id |
| u002 | Mumbai | Filmi/pop + jazz, a disliked rock song |
| u003 | Bengaluru | Electronic + rock; follows the artist who has a not-yet-released song |
| u004 | Warangal | **Cold start** (no history) in a city with too little activity → popularity falls back to the state |

The catalog also contains an unavailable song, a future-dated song, a song with no release
date, and a song 31 days old (just outside the 30-day window) to exercise the filters.

## Data files (`data/`)

| File | Columns |
| --- | --- |
| `songs.csv` | song_id, title, artist_id, artist_name, genres, release_date, language, available |
| `users.csv` | user_id, region_code, city, preferred_languages |
| `interactions.csv` | user_id, song_id, action, event_date, duration_seconds *(optional)* |
| `artist_follows.csv` *(optional)* | user_id, artist_id, action (`follow`/`unfollow`), event_date |
| `regional_activity.csv` | region_code, song_id, activity_date, plays, unique_listeners, likes |

Multi-value fields (genres, languages) use `|`. Dates are ISO `YYYY-MM-DD`. Region codes are
hierarchical (`IN-TS-HYD` → `IN-TS` → `IN`). Interaction actions: `like`, `unlike`, `save`,
`unsave`, `dislike`, `undislike`, `play`, `skip`. Artist follows live in their own file
because they are artist-level events (as the guide recommends).

## How it works

1. **Profile** (`preferences.py`): replays each user's events in date order into a final
   per-song state, so `unlike`/`unsave` truly reverse the earlier action. A later `dislike`
   overrides likes and saves. Plays shorter than `min_play_seconds` are ignored, and repeated
   plays are capped. Follows add artist affinity. Only positive affinities are kept.
2. **For You** = `0.50·genre_match + 0.45·artist_match + 0.05·discovery` (all 0–1). Songs with
   no genre or artist match are left out rather than padded in; already-heard songs are
   multiplied by `seen_penalty`.
3. **Popular in Your Area** = `0.25·log(plays) + 0.45·log(listeners) + 0.30·log(likes)` over
   the last 7 days, normalised so the top candidate is 1.0. If the user's city has fewer than
   `min_local_songs` songs, it widens city → state → country → overall and says so in the reason.
4. **New Releases** = `0.70·artist_affinity + 0.30·freshness` for songs released within
   30 days by artists with positive affinity. Future, missing or old dates never qualify.
5. Every shelf excludes unavailable songs, explicit dislikes, **unreleased songs**, and duplicates.

All weights and windows are in `music_engine/config.py` (one frozen dataclass).
To experiment: `replace(DEFAULT_CONFIG, new_release_window_days=14)`.

## Project layout

```
music_engine/
  config.py        tunable weights/windows
  data_loader.py   CSV loading, validation, normalisation (prepare_* work on DataFrames)
  preferences.py   taste profile + reversal state model
  scoring.py       pure scoring functions
  recommender.py   recommend_all(): assembles the three shelves
main.py            CLI
generate_sample_data.py
tests/             44 pytest tests (scoring, windows, fallback, dedupe, bad data, end-to-end)
```

## Limitations

- Local popularity is only as meaningful as the simulated regional data; it is not a real chart.
- `unique_listeners` is summed across days, which double-counts people who listen on several days.
- Genre labels must be consistent (the loader lowercases but does not map synonyms).
- Rule-based scoring is explainable but cannot capture musical similarity like embeddings can.
- `preferred_languages` is loaded but not yet used in scoring (a natural next tweak).

## Integrating later

`recommend_all(...)` takes plain DataFrames and returns plain dicts, with no file, database or
web dependency. To integrate with DVANY, replace `load_data` with a loader that produces the
same normalised DataFrames and put an API in front of `recommend_all`.
