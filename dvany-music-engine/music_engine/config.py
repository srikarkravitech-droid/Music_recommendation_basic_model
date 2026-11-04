"""All tunable numbers live here (guide sections 6 and 8).

The values are starting heuristics, not claims of optimality. Change them in
one place, or build a modified copy in tests/experiments:

    from dataclasses import replace
    cfg = replace(DEFAULT_CONFIG, new_release_window_days=14)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class EngineConfig:
    # --- Interaction weights (section 6) ---------------------------------
    action_weights: Dict[str, float] = field(
        default_factory=lambda: {
            "like": 3.0,
            "save": 3.5,
            "follow_artist": 4.0,
            "play": 0.5,
            "skip": -1.0,
            "dislike": -4.0,
        }
    )
    # A play shorter than this is treated as noise (needs a duration_seconds column).
    min_play_seconds: float = 30.0
    # Plays are a weak signal: cap how much repeated plays of one song can add.
    max_play_bonus: float = 2.5

    # --- For You (section 8) ----------------------------------------------
    for_you_genre_weight: float = 0.50
    for_you_artist_weight: float = 0.45
    for_you_discovery_weight: float = 0.05
    # Multiplier applied to songs the user has already heard (1.0 = no penalty).
    seen_penalty: float = 0.70

    # --- Popular in Your Area ----------------------------------------------
    popularity_window_days: int = 7
    popularity_plays_weight: float = 0.25
    popularity_listeners_weight: float = 0.45
    popularity_likes_weight: float = 0.30
    # If the user's own region has fewer songs than this, widen to the parent
    # region (IN-TS-HYD -> IN-TS -> IN -> overall).
    min_local_songs: int = 5

    # --- New Releases from Your Artists ------------------------------------
    new_release_window_days: int = 30
    release_affinity_weight: float = 0.70
    release_freshness_weight: float = 0.30

    # --- Output -------------------------------------------------------------
    top_k: int = 10


DEFAULT_CONFIG = EngineConfig()
