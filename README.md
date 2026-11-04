DVANY
Standalone Music Recommendation Engine
Build Guide • Python-first • No application integration
This guide describes how to build and run a self-contained music recommendation engine on a local computer. It uses Python and sample CSV data, does not connect to DVANY, a production database, or a live music API, and can later be adapted for integration once the recommendation logic is tested.
1. Goal and Scope
The standalone engine must produce three independently ranked recommendation lists:
•	For You: songs matching genres and artists a sample user likes.
•	Popular in Your Area: songs with strong recent likes, plays, and listener counts in the user's sample region.
•	New Releases from Your Artists: recent releases by artists the user likes or follows.
The program should accept a sample user ID, read local CSV files, calculate scores, print the top results with human-readable reasons, and optionally export recommendations to JSON/CSV.
Out of scope for this stage: web API, frontend, production database, authentication, cloud deployment, live music catalog ingestion, and machine-learning model training.
2. Tools and Requirements
Tool	Purpose
Python 3.11+	Main implementation language
pandas	Load and manipulate CSV datasets
pytest	Test scoring and edge cases
CSV / JSON	Store sample songs, users, and interactions
Standard library	Dates, math, paths, JSON output and CLI
Keep the first version lightweight. Do not add PostgreSQL, FastAPI, Redis, or machine-learning libraries until the standalone engine works correctly.
3. Project Structure
dvany-music-engine/
  data/
    songs.csv
    users.csv
    interactions.csv
    regional_activity.csv
  output/
  music_engine/
    __init__.py
    data_loader.py
    preferences.py
    scoring.py
    recommender.py
  tests/
    test_scoring.py
    test_recommender.py
  main.py
  requirements.txt
  README.md
Keep recommendation logic in small modules so it is easier to debug and later reuse behind an API.
4. Create the Environment
# Create and enter the project folder
mkdir dvany-music-engine
cd dvany-music-engine

python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate

pip install pandas pytest
pip freeze > requirements.txt
If PowerShell blocks activation, use the appropriate local execution-policy guidance for your machine or run the virtual environment's Python executable directly. Do not disable security settings globally just to run this project.
5. Sample Data Design
Use fictional/sample catalog entries for the first run. The sample data must be enough to demonstrate all three recommendation types and several edge cases.
File	Required columns	Example
songs.csv	song_id, title, artist_id, artist_name, genres, release_date, language, available	s001, Moonlight, a01, Example Artist, pop|indie, 2026-10-10, English, true
users.csv	user_id, region_code, city, preferred_languages	u001, IN-TS-HYD, Hyderabad, Telugu|Hindi
interactions.csv	user_id, song_id, action, event_date	u001, s001, like, 2026-10-20
regional_activity.csv	region_code, song_id, activity_date, plays, unique_listeners, likes	IN-TS-HYD, s001, 2026-10-24, 120, 45, 18
For CSV fields containing multiple genres or languages, use a consistent delimiter such as |. Parse it into a list in Python. Keep dates in ISO format (YYYY-MM-DD). Use unique IDs for songs and artists; do not use titles as IDs.
6. Interaction Rules
Action	Suggested weight	Interpretation
like	+3.0	Strong positive preference
save	+3.5	Strong positive preference
follow_artist	+4.0	Strong artist preference
play	+0.5	Weak positive signal; preferably require meaningful play duration
skip	-1.0	Mild negative signal, especially if repeated
dislike	-4.0	Strong negative signal; exclude the song from For You
unlike / unsave	Reversal	Remove or reverse the earlier positive action instead of treating it as a new independent event
These values are starting heuristics. Keep them in one configuration file so they can be tuned. In this offline prototype, events can be supplied as rows in interactions.csv.
7. Algorithm Overview
1.	Load and validate all CSV files.
2.	Select a sample user and their region.
3.	Build positive genre and artist preference scores from their interaction history.
4.	Generate the For You candidate list from matching genres and artists.
5.	Calculate local popularity using recent regional activity.
6.	Filter new releases to artists with positive affinity and a configurable release window.
7.	Exclude unavailable songs and explicit dislikes; deduplicate candidates.
8.	Rank each shelf separately and attach reason labels.
9.	Print results and export a JSON file for inspection.
8. Ranking Formula
Keep the three shelves separate because each has a different purpose. Normalize each component between 0 and 1 before combining it.
Shelf	Initial formula	Notes
For You	0.50 × genre_match + 0.45 × artist_match + 0.05 × discovery	Personalized relevance first; weights are tunable
Popular in Your Area	0.25 × plays + 0.45 × unique listeners + 0.30 × likes	Use log-scaled counts and normalize across candidates
New Releases from Your Artists	0.70 × artist_affinity + 0.30 × freshness	Only include releases inside the configured window
For local popularity, count recent activity only (suggested default: last 7 days). For new releases, start with a 30-day window. Keep both windows configurable. The formula is an initial baseline, not a claim that these weights are universally optimal.
9. Core Python Implementation
9.1 Load and normalize data
from pathlib import Path
import pandas as pd

DATA_DIR = Path("data")

def load_data():
    songs = pd.read_csv(DATA_DIR / "songs.csv", keep_default_na=False)
    users = pd.read_csv(DATA_DIR / "users.csv", keep_default_na=False)
    interactions = pd.read_csv(DATA_DIR / "interactions.csv", keep_default_na=False)
    activity = pd.read_csv(DATA_DIR / "regional_activity.csv", keep_default_na=False)

    songs["release_date"] = pd.to_datetime(
        songs["release_date"], errors="coerce"
    ).dt.date
    interactions["event_date"] = pd.to_datetime(
        interactions["event_date"], errors="coerce"
    ).dt.date
    activity["activity_date"] = pd.to_datetime(
        activity["activity_date"], errors="coerce"
    ).dt.date

    songs["genres_list"] = songs["genres"].apply(
        lambda value: [g.strip().lower() for g in str(value).split("|") if g.strip()]
    )
    users["preferred_languages_list"] = users["preferred_languages"].apply(
        lambda value: [x.strip().lower() for x in str(value).split("|") if x.strip()]
    )
    songs["available_bool"] = songs["available"].astype(str).str.lower().isin(
        ["true", "1", "yes"]
    )
    return songs, users, interactions, activity
9.2 Build a user taste profile
from collections import Counter

ACTION_WEIGHTS = {
    "like": 3.0,
    "save": 3.5,
    "follow_artist": 4.0,
    "play": 0.5,
    "skip": -1.0,
    "dislike": -4.0,
}

def build_profile(user_id, songs, interactions):
    user_events = interactions[interactions["user_id"] == user_id]
    song_lookup = songs.set_index("song_id").to_dict("index")
    genre_scores, artist_scores = Counter(), Counter()
    disliked_ids, seen_ids = set(), set()

    # Prototype behavior: process events in date order.
    for event in user_events.sort_values("event_date").to_dict("records"):
        action = str(event["action"]).lower()
        song = song_lookup.get(event["song_id"])
        if not song:
            continue

        if action == "dislike":
            disliked_ids.add(event["song_id"])
        elif action in {"like", "save", "play", "skip"}:
            seen_ids.add(event["song_id"])

        weight = ACTION_WEIGHTS.get(action, 0.0)
        for genre in song.get("genres_list", []):
            genre_scores[genre] += weight

        if action != "follow_artist":
            artist_scores[song["artist_id"]] += weight

    # Keep only positive affinities for recommendation ranking.
    genre_scores = {k: v for k, v in genre_scores.items() if v > 0}
    artist_scores = {k: v for k, v in artist_scores.items() if v > 0}
    return {
        "genre_scores": genre_scores,
        "artist_scores": artist_scores,
        "disliked_ids": disliked_ids,
        "seen_ids": seen_ids,
    }
Prototype limitation: follow_artist events are artist-level events, so a production-grade format should store artist_id directly for those events instead of requiring a song_id. For this starter dataset, either represent follows in a separate artist_follows.csv file or omit that action until implemented.
9.3 Score personalized songs
def normalize_map(values):
    if not values:
        return {}
    max_value = max(values.values())
    if max_value <= 0:
        return {}
    return {key: value / max_value for key, value in values.items()}

def score_for_you(song, profile):
    genre_scores = normalize_map(profile["genre_scores"])
    artist_scores = normalize_map(profile["artist_scores"])

    genres = song.get("genres_list", [])
    genre_match = max((genre_scores.get(g, 0.0) for g in genres), default=0.0)
    artist_match = artist_scores.get(song["artist_id"], 0.0)

    score = 0.50 * genre_match + 0.45 * artist_match
    reasons = []
    if genre_match > 0:
        reasons.append("Because you like this genre")
    if artist_match > 0:
        reasons.append("By an artist you like")
    return score, reasons
9.4 Score local popularity
import math
from datetime import timedelta

def score_local_popularity(activity_rows, region_code, today, window_days=7):
    cutoff = today - timedelta(days=window_days - 1)
    rows = activity_rows[
        (activity_rows["region_code"] == region_code)
        & (activity_rows["activity_date"] >= cutoff)
        & (activity_rows["activity_date"] <= today)
    ]
    if rows.empty:
        return {}

    grouped = rows.groupby("song_id")[["plays", "unique_listeners", "likes"]].sum()
    raw = {}
    for song_id, row in grouped.iterrows():
        raw[song_id] = (
            0.25 * math.log1p(max(0, row["plays"]))
            + 0.45 * math.log1p(max(0, row["unique_listeners"]))
            + 0.30 * math.log1p(max(0, row["likes"]))
        )
    peak = max(raw.values(), default=0.0)
    return {k: v / peak for k, v in raw.items()} if peak else {}
If activity is too sparse for a city, widen to a broader region or use a clearly labeled overall-popular fallback. Never infer a precise location from unrelated data.
9.5 Find new releases by liked artists
from datetime import date

def new_release_score(song, artist_scores, today, window_days=30):
    release_date = song.get("release_date")
    if pd.isna(release_date) or release_date is None:
        return None
    age_days = (today - release_date).days
    if age_days < 0 or age_days > window_days:
        return None

    affinity = artist_scores.get(song["artist_id"], 0.0)
    if affinity <= 0:
        return None

    freshness = 1.0 - (age_days / max(window_days, 1))
    return 0.70 * affinity + 0.30 * freshness
Use reliable release dates, deduplicate tracks, and keep the release window configurable. Missing dates should not qualify as new releases.
10. Recommendation Assembly
The final recommender module should coordinate the helpers above and return three lists. Recommended behavior:
•	For You: score available songs; exclude explicit dislikes; sort descending; attach genre/artist reasons; optionally reduce already-heard tracks.
•	Popular in Your Area: select the user's region, score recent activity, join scores to song metadata, and label results as local trends.
•	New Releases from Your Artists: filter by date window and positive artist affinity, rank by affinity and freshness, and explain the match.
•	Return a configurable top_k (for example 10) per shelf; avoid duplicate song IDs inside a shelf.
•	If a shelf has too few results, return fewer songs rather than adding irrelevant entries.
11. Main Program and Output
# main.py — orchestration sketch
from datetime import date
import json
from pathlib import Path
from music_engine.data_loader import load_data
from music_engine.preferences import build_profile
from music_engine.recommender import recommend_all

def main():
    songs, users, interactions, activity = load_data()
    user_id = input("Sample user ID (e.g. u001): ").strip()
    user_rows = users[users["user_id"] == user_id]
    if user_rows.empty:
        raise SystemExit(f"Unknown sample user: {user_id}")

    user = user_rows.iloc[0].to_dict()
    results = recommend_all(
        user_id=user_id,
        user=user,
        songs=songs,
        interactions=interactions,
        activity=activity,
        today=date.today(),
        top_k=10,
    )
    print(json.dumps(results, indent=2, default=str))
    Path("output").mkdir(exist_ok=True)
    Path("output/recommendations.json").write_text(
        json.dumps(results, indent=2, default=str),
        encoding="utf-8",
    )
    print("Saved output/recommendations.json")

if __name__ == "__main__":
    main()
This main.py is an orchestration sketch: implement recommend_all in recommender.py by composing the functions in this guide. Keeping it modular makes testing much easier.
12. Testing
Required test cases
•	A song by a liked artist ranks above an otherwise comparable unrelated artist.
•	A song in a liked genre ranks above a non-matching song when other signals are equal.
•	Explicitly disliked songs never appear in For You.
•	Recent local activity affects local rankings; old activity outside the window is ignored.
•	A recent release by a liked artist qualifies; an old release, future release, or missing release date does not.
•	Unknown user IDs and missing optional fields are handled cleanly.
•	Duplicate song IDs do not appear twice in one recommendation shelf.
Example pytest tests
from music_engine.scoring import score_for_you

def test_liked_artist_has_positive_score():
    song = {"artist_id": "a1", "genres_list": ["pop"]}
    profile = {
        "genre_scores": {"pop": 1.0},
        "artist_scores": {"a1": 1.0},
        "disliked_ids": set(),
        "seen_ids": set(),
    }
    score, reasons = score_for_you(song, profile)
    assert score > 0
    assert "By an artist you like" in reasons
13. Limitations and Important Decisions
•	Sample local popularity is only as meaningful as the simulated regional activity data. It is not a real chart.
•	Genre labels must be consistent; normalize casing and synonyms before scoring.
•	Likes and saves should be reversible. Avoid treating unlike/unsave as new independent positive or negative events without a clear state model.
•	Artist follows are artist-level events and should have a separate artist_follows.csv or artist_id event field.
•	New releases depend on accurate release dates and a catalog that is refreshed often.
•	Rule-based recommendations are explainable but will not capture complex musical similarity like embeddings or audio features.
14. Completion Checklist
☐ Project runs locally without network access or DVANY credentials.
☐ CSV files include songs, users, interactions, and regional activity.
☐ One command generates all three recommendation shelves.
☐ Every recommended song includes score and reason label.
☐ Explicit dislikes are excluded from personalized recommendations.
☐ New-release and local-trend time windows are configurable.
☐ Tests cover scoring, dates, location fallback, duplicates, and missing data.
☐ Results are written to output/recommendations.json.
15. Recommended Build Order
10.	Create the folder structure, virtual environment, and requirements.
11.	Prepare a small fictional catalog and CSV files with at least 30 songs, 5 artists, 3 users, and regional activity.
12.	Implement data loading and validation first.
13.	Implement profile building and test genre/artist scoring.
14.	Implement local popularity scoring with a rolling 7-day window.
15.	Implement new-release filtering with a 30-day default.
16.	Compose all three shelves in recommend_all and attach reasons.
17.	Write JSON output and add pytest tests.
18.	Run the engine with different sample users and inspect whether results make sense.
19.	Only after the standalone version is reliable, plan future database/API integration separately.
Final Recommendation
Build this as a local Python package driven by CSV sample data. Keep the core algorithm independent of files, databases, and web frameworks: data loaders should provide normalized records, scoring functions should rank them, and the CLI should display/export results. That separation makes the engine easy to test now and straightforward to connect to DVANY later.
