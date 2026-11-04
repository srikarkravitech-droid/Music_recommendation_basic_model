
DVANY --- Standalone Music Recommendation Engine
A Python-first, rule-based music recommendation engine that runs locally
using sample CSV datasets. It generates three recommendation lists:

For You --- songs matched to a user's liked genres and artists.
Popular in Your Area --- songs with strong recent listening and
like activity in the user's region.
New Releases from Your Artists --- recent releases from artists
the user likes or follows.
Project status: Standalone prototype / development guide. This
version is designed to run independently with local sample data. It
does not connect to DVANY's application, a production database, or a
live music API.

Table of Contents
Objectives
How It Works
Recommendation Logic
Technology Stack
Project Structure
Getting Started
Sample Data
Interaction Signals
Scoring Approach
Recommendation Output
Testing
Current Scope and Limitations
Development Roadmap
Future Improvements
Objectives
Build and test the recommendation logic independently of the main
application.
Personalize songs using positive genre and artist preferences
inferred from user interactions.
Surface songs that are popular in a user's sample city or region.
Discover recent releases from artists the user likes.
Explain why each song was recommended.
Keep the first version lightweight, understandable, and easy to
test.
How It Works
The engine reads local CSV files, builds a taste profile for a selected
sample user, scores candidate songs, and returns three independently
ranked recommendation sections.

                 Local CSV datasets
                         |
                         v
                 Data loading layer
                         |
                         v
                User preference profile
                  /        |         \
                 /         |          \
                v          v           v
           For You     Local Trends   New Releases
                \          |          /
                 \         |         /
                  v        v        v
                 Ranked recommendations
                         |
                         v
                 Console / JSON output
Recommendation sections
Section What it recommends Main signals

For You Songs matching the Liked genres, liked
user's taste artists

Popular in Your Songs popular in the Recent plays, unique
Area user's region listeners, likes

New Releases from Recent songs from Artist affinity,
Your Artists artists the user likes release date
Recommendation Logic
1. Genre and artist personalization
The engine examines a user's interactions with songs and builds
preference scores for:

Genres: genres attached to liked or saved songs contribute to
genre affinity.
Artists: likes and saves contribute to the corresponding
artist's affinity.
Plays: can provide a small positive signal when listening
activity is meaningful.
Skips: can reduce preference, particularly when repeated.
Dislikes: explicitly disliked songs are excluded from the
personalized list.
The engine normalizes preference scores and uses them to rank matching
songs.

2. Local popularity
The local-trending section uses regional activity data over a recent
time window. It considers:

Number of plays.
Number of unique listeners.
Number of likes.
Unique listeners receive a relatively strong contribution so a song
repeatedly played by one person does not automatically dominate a
regional chart.

The initial default window is 7 days. If there is not enough
activity for a city, the prototype can use a broader region or an
overall-popular fallback, clearly labeling that fallback.

3. New releases from liked artists
The engine checks the song catalog for tracks released within a
configurable recent-release window and keeps tracks from artists with
positive user affinity.

The initial default window is 30 days. A freshness score gives newer
releases a higher score. Tracks with missing or future release dates are
not treated as new releases.

Technology Stack
Technology Purpose

Python 3.11+ Main programming language

pandas Loading, validating, and processing
CSV datasets

pytest Unit testing recommendation logic

CSV Local sample catalog, user,
interaction, and regional activity
data

JSON Exporting recommendation results

Python standard library Dates, scoring utilities, file
paths, and command-line execution
The first version intentionally avoids a production database, web
framework, cache server, and machine-learning model. The focus is
validating the recommendation logic first.

Project Structure
dvany-music-engine/
│
├── data/
│   ├── songs.csv
│   ├── users.csv
│   ├── interactions.csv
│   └── regional_activity.csv
│
├── output/
│
├── music_engine/
│   ├── __init__.py
│   ├── data_loader.py
│   ├── preferences.py
│   ├── scoring.py
│   └── recommender.py
│
├── tests/
│   ├── test_scoring.py
│   └── test_recommender.py
│
├── main.py
├── requirements.txt
└── README.md
Module responsibilities
Module Responsibility

data_loader.py Load and normalize the CSV files

preferences.py Build genre and artist preference
profiles

scoring.py Calculate genre, artist,
local-popularity, and freshness
scores

recommender.py Generate and rank the three
recommendation sections

main.py Select a sample user, run the
engine, and display/export results

tests/ Validate ranking behavior and edge
cases
Getting Started
Prerequisites
Python 3.11 or newer
pip
1. Clone the repository
git clone <your-repository-url>
cd dvany-music-engine
Replace <your-repository-url> with the URL of your GitHub repository.

2. Create a virtual environment
Windows PowerShell

python -m venv .venv
.venv\Scripts\Activate.ps1
macOS / Linux

python3 -m venv .venv
source .venv/bin/activate
3. Install dependencies
pip install -r requirements.txt
If requirements.txt has not been created yet:

pip install pandas pytest
pip freeze > requirements.txt
4. Prepare the sample datasets
Place the CSV files in the data/ directory using the schemas described
below. Use fictional or appropriately licensed sample data for local
development.

5. Run the engine
python main.py
The intended command-line flow asks for a sample user ID, generates the
three recommendation sections, prints the results, and saves a JSON
result under output/.

The project is still under development. The complete recommend_all
orchestration and data files must be implemented before the full
end-to-end command works.

Sample Data
The standalone prototype uses four CSV files.

songs.csv
Column Description

song_id Unique song identifier
title Song title
artist_id Unique artist identifier
artist_name Artist display name
genres Genre labels separated by \|
release_date Release date in YYYY-MM-DD format
language Song language
available Whether the song is eligible for recommendation

Example:

song_id,title,artist_id,artist_name,genres,release_date,language,available
s001,Moonlight,a01,Example Artist,pop|indie,2026-10-10,English,true
users.csv
Column Description

user_id Sample user identifier

region_code Region used for local popularity

city Sample city

preferred_languages Optional language preferences
separated by \|
Example:

user_id,region_code,city,preferred_languages
u001,IN-TS-HYD,Hyderabad,Telugu|Hindi
interactions.csv
Column Description

user_id User who performed the action
song_id Song associated with the action
action like, save, play, skip, or dislike
event_date Date of the interaction

Example:

user_id,song_id,action,event_date
u001,s001,like,2026-10-20
Artist follows are artist-level events. If follow behavior is included,
represent it separately (for example, in an artist_follows.csv file
with user_id, artist_id, and event_date) rather than pretending it
is a song interaction.

regional_activity.csv
Column Description

region_code Region where activity occurred
song_id Song receiving activity
activity_date Date of activity
plays Number of plays
unique_listeners Number of distinct listeners
likes Number of likes

Example:

region_code,song_id,activity_date,plays,unique_listeners,likes
IN-TS-HYD,s001,2026-10-24,120,45,18
Data conventions
Use unique IDs for songs and artists; do not use song titles as
identifiers.
Store dates as ISO dates: YYYY-MM-DD.
Use | consistently for multi-value fields such as genres and
languages.
Normalize genre labels (for example, casing and common synonyms)
before scoring.
Sample regional activity is simulated data; it is not a real-world
popularity chart.
Interaction Signals
Initial heuristic weights:

Action Suggested weight Meaning

Like +3.0 Strong positive
preference

Save +3.5 Strong positive
preference

Play +0.5 Weak positive signal;
meaningful listening
duration is
preferable

Skip -1.0 Mild negative signal;
repeated skips can
matter more

Dislike -4.0 Strong negative
signal; exclude that
song from For You
These weights are starting values, not fixed rules. Keep them
configurable and adjust them after evaluating sample results.

Unlike and unsave should reverse the corresponding positive state. They
should not automatically be counted as unrelated new negative
interactions. Artist follows should contribute to artist affinity
through a separate artist-level dataset.

Scoring Approach
All component scores should be normalized to a range of 0 to 1
before being combined.

For You
For You Score =
    0.50 × Genre Match
  + 0.45 × Artist Match
  + 0.05 × Discovery / Diversity
The first prototype may initially use only genre and artist match while
the discovery component is being implemented.

Popular in Your Area
Use log-scaled activity counts to reduce the effect of very large raw
totals:

Local Popularity =
    0.25 × Plays
  + 0.45 × Unique Listeners
  + 0.30 × Likes
Normalize the resulting scores across the candidate songs for the
selected region and time window.

New Releases from Your Artists
New Release Score =
    0.70 × Artist Affinity
  + 0.30 × Freshness
Only songs inside the configured release window from artists with
positive user affinity are eligible.

Initial configuration
Setting Default

Local popularity window 7 days
New release window 30 days
Results per section 10 songs

These are prototype defaults and should be configurable.

Recommendation Output
Each recommendation should include at least:

Song ID
Song title
Artist name
Recommendation score
One or more reason labels
Example reason labels:

Match Reason

Genre preference Because you like this genre

Artist preference By an artist you like

Regional popularity Popular near you

Recent release from a preferred New release from an artist you like
artist
The engine should return fewer results rather than fill a section with
unrelated songs. Duplicate song IDs should be removed within each
section.

Example response shape:

{
  "sections": {
    "for_you": [
      {
        "song_id": "s001",
        "title": "Moonlight",
        "artist": "Example Artist",
        "score": 0.92,
        "reasons": [
          "Because you like this genre",
          "By an artist you like"
        ]
      }
    ],
    "popular_in_your_area": [],
    "new_from_your_artists": []
  }
}
Testing
Use pytest to validate the engine independently.

Important test cases
A song by a liked artist should rank above an otherwise comparable
unrelated artist.
A song matching a preferred genre should rank above a non-matching
song when other signals are equal.
Explicitly disliked songs should not appear in the For You section.
Recent regional activity should affect local ranking; activity
outside the configured window should not.
A recent release by a liked artist should qualify.
Old, future-dated, or missing-release-date tracks should not qualify
as new releases.
Unknown users, missing optional fields, and empty datasets should be
handled safely.
Duplicate song IDs should not appear twice in the same
recommendation section.
Run tests with:

pytest -q
Current Scope and Limitations
This is a local prototype using CSV files and sample data.
Local popularity is only as meaningful as the regional activity
dataset supplied to it.
It does not fetch real-time charts or new releases from an external
music service.
It does not stream or host music.
Genre labels need consistent normalization.
The first version uses transparent, rule-based scoring rather than
machine learning.
New-release recommendations depend on accurate release dates.
The current scope does not include a web API, frontend, production
database, authentication, or deployment.
Development Roadmap
Create the Python project structure and virtual environment.
Prepare sample songs, users, interactions, and regional activity
CSV files.
Implement CSV loading and data validation.
Build user genre and artist preference profiles.
Implement the For You ranking logic.
Implement regional popularity scoring with a rolling 7-day
window.
Implement new-release filtering with a configurable 30-day
default.
Generate the three recommendation sections with reason labels.
Export results to JSON.
Add and run unit tests.
Test with multiple sample users and regions.
Future Improvements
Once the standalone engine is stable, possible next steps include:

Replace sample CSV files with a real catalog and listening-event
source.
Add a database repository layer.
Expose the engine through an API.
Improve time-decay and preference-state handling.
Add artist-follow and onboarding preference support.
Introduce collaborative filtering or embeddings after enough
reliable interaction data exists.
Integrate the engine with DVANY's application as a separate phase.
Built as a standalone Python prototype for DVANY.




✕Merlin



