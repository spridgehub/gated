"""SQLite store: cars friends add, groups that link them, and one snapshot per car per day."""
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "gated.db"
LONDON = ZoneInfo("Europe/London")
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS cars (
  id INTEGER PRIMARY KEY,
  url TEXT NOT NULL UNIQUE,
  name TEXT,              -- friend's own label, e.g. "Blue 675LT, MSO roof scoop"
  title TEXT,             -- title as the listing states it
  sector TEXT,            -- e.g. "McLaren 675LT"
  year INTEGER,
  mileage INTEGER,
  seller TEXT,
  location TEXT,
  image TEXT,
  listed_at TEXT,         -- when the advert went up, if the site says
  added_by TEXT,
  added_at TEXT NOT NULL,
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'live',   -- live | reserved | sold | gone
  archived INTEGER NOT NULL DEFAULT 0,
  last_checked TEXT,
  last_error TEXT
);
CREATE TABLE IF NOT EXISTS groups (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  created_by TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS car_groups (
  car_id INTEGER NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
  group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  PRIMARY KEY (car_id, group_id)
);
CREATE TABLE IF NOT EXISTS snapshots (
  car_id INTEGER NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
  day TEXT NOT NULL,      -- Europe/London date
  price INTEGER,
  views INTEGER,
  status TEXT,
  source TEXT NOT NULL,   -- auto | manual
  by TEXT,
  at TEXT NOT NULL,
  PRIMARY KEY (car_id, day)
);
"""


def now_iso():
    return datetime.now(LONDON).isoformat(timespec="seconds")


def today():
    return datetime.now(LONDON).date().isoformat()


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def write(fn):
    """Run fn(con) under the process-wide write lock and commit."""
    with _lock:
        con = connect()
        try:
            out = fn(con)
            con.commit()
            return out
        finally:
            con.close()


def record_snapshot(con, car_id, price, views, status, source, by=None):
    """Upsert today's snapshot. A manual entry is never overwritten by an automatic one the same day,
    and fields an automatic check could not read are kept from what was already there."""
    day = today()
    old = con.execute("SELECT * FROM snapshots WHERE car_id=? AND day=?", (car_id, day)).fetchone()
    if old and old["source"] == "manual" and source == "auto":
        price = old["price"] if old["price"] is not None else price
        views = old["views"] if old["views"] is not None else views
        source, by = "manual", old["by"]
    elif old:
        price = price if price is not None else old["price"]
        views = views if views is not None else old["views"]
    con.execute(
        "INSERT OR REPLACE INTO snapshots(car_id,day,price,views,status,source,by,at) VALUES(?,?,?,?,?,?,?,?)",
        (car_id, day, price, views, status, source, by, now_iso()),
    )


def state(days=90):
    con = connect()
    try:
        cars = [dict(r) for r in con.execute("SELECT * FROM cars WHERE archived=0 ORDER BY added_at")]
        groups = [dict(r) for r in con.execute("SELECT * FROM groups ORDER BY name")]
        links = con.execute("SELECT car_id, group_id FROM car_groups").fetchall()
        snaps = con.execute(
            "SELECT car_id,day,price,views,status,source,by FROM snapshots "
            "WHERE day >= date('now', ?) ORDER BY day", (f"-{days} days",)
        ).fetchall()
    finally:
        con.close()
    by_car = {c["id"]: c for c in cars}
    for c in cars:
        c["groups"], c["snaps"] = [], []
    for l in links:
        if l["car_id"] in by_car:
            by_car[l["car_id"]]["groups"].append(l["group_id"])
    for s in snaps:
        if s["car_id"] in by_car:
            by_car[s["car_id"]]["snaps"].append(
                {k: s[k] for k in ("day", "price", "views", "status", "source", "by")}
            )
    return {"today": today(), "cars": cars, "groups": groups}
