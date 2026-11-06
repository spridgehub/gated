"""Export the tracker to docs/data.json for the static GitHub Pages site."""
import json
from pathlib import Path

from . import db
from .server import SECTORS

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data.json"
KEEP = ("id", "url", "name", "sector", "year", "mileage", "seller", "location", "listed_at", "added_by",
        "added_at", "notes", "status", "groups", "snaps")


def build():
    s = db.state(days=400)
    data = {
        "today": s["today"],
        "built": db.now_iso(),
        "repo": "spridgehub/gated",
        "sectors": SECTORS,
        "groups": [{k: g[k] for k in ("id", "name", "description", "created_by")} for g in s["groups"]],
        "cars": [{k: c[k] for k in KEEP} for c in s["cars"]],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print(f"data.json: {len(data['cars'])} cars, {len(data['groups'])} groups")


if __name__ == "__main__":
    build()
