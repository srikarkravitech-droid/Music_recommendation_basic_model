"""Command-line runner for the standalone music recommendation engine.

    python main.py --user u001
    python main.py                      # prompts for a user id
    python main.py --all-users --csv
    python main.py --user u001 --today 2026-10-25 --top-k 5
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import date
from pathlib import Path

from music_engine import DEFAULT_CONFIG, DataError, load_data, recommend_all
from music_engine.config import EngineConfig
from dataclasses import replace

SHELVES = [
    ("for_you", "For You"),
    ("popular_in_your_area", "Popular in Your Area"),
    ("new_releases_from_your_artists", "New Releases from Your Artists"),
]


def format_report(results: dict, user: dict) -> str:
    city = user.get("city") or "unknown city"
    lines = [f"=== {results['user_id']} | {city} ({results['region_code'] or 'no region'}) | {results['generated_for_date']} ==="]
    for note in results["notes"]:
        lines.append(f"  note: {note}")
    for key, title in SHELVES:
        lines.append("")
        lines.append(title)
        items = results[key]
        if not items:
            lines.append("  (no matching songs)")
        for item in items:
            lines.append(f"  {item['rank']:>2}. {item['title']} - {item['artist_name']}   [score {item['score']:.3f}]")
            lines.append(f"      * " + "; ".join(item["reasons"]))
    return "\n".join(lines)


def write_json(results: dict, path: Path) -> None:
    path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")


def write_csv(all_results: list, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["user_id", "shelf", "rank", "song_id", "title", "artist_name", "score", "reasons"])
        for results in all_results:
            for key, _ in SHELVES:
                for item in results[key]:
                    writer.writerow([
                        results["user_id"], key, item["rank"], item["song_id"], item["title"],
                        item["artist_name"], item["score"], "; ".join(item["reasons"]),
                    ])


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone music recommendation engine")
    parser.add_argument("--user", help="sample user id, e.g. u001 (prompted if omitted)")
    parser.add_argument("--all-users", action="store_true", help="run every user in users.csv")
    parser.add_argument("--today", help="reference date YYYY-MM-DD (default: today)")
    parser.add_argument("--top-k", type=int, default=DEFAULT_CONFIG.top_k, help="songs per shelf")
    parser.add_argument("--data-dir", help="folder containing the CSV files (default: ./data)")
    parser.add_argument("--output-dir", default="output", help="where to write results")
    parser.add_argument("--csv", action="store_true", help="also export output/recommendations.csv")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="warning: %(message)s")
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        raise SystemExit(f"--today must be YYYY-MM-DD, got: {args.today}")

    try:
        songs, users, interactions, activity, follows = load_data(args.data_dir)
    except DataError as exc:
        raise SystemExit(f"Data error: {exc}")

    if args.all_users:
        user_ids = list(users["user_id"])
    else:
        user_id = (args.user or input("Sample user ID (e.g. u001): ")).strip()
        if users[users["user_id"] == user_id].empty:
            raise SystemExit(f"Unknown sample user: {user_id!r}. Available: {', '.join(users['user_id'])}")
        user_ids = [user_id]

    config: EngineConfig = replace(DEFAULT_CONFIG, top_k=args.top_k)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results = []
    for user_id in user_ids:
        user = users[users["user_id"] == user_id].iloc[0].to_dict()
        results = recommend_all(
            user_id=user_id, user=user, songs=songs, interactions=interactions,
            activity=activity, today=today, top_k=config.top_k, follows=follows, config=config,
        )
        all_results.append(results)
        print(format_report(results, user))
        print()
        name = f"recommendations_{user_id}.json" if args.all_users else "recommendations.json"
        write_json(results, out_dir / name)
        print(f"Saved {out_dir / name}")
        print()

    if args.csv:
        write_csv(all_results, out_dir / "recommendations.csv")
        print(f"Saved {out_dir / 'recommendations.csv'}")


if __name__ == "__main__":
    sys.exit(main())
