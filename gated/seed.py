"""Load a scan baseline (data/seed-*.json) into the tracker. Safe to re-run: existing URLs are skipped."""
import json
import sys

from . import db
from .server import clean_url


def load(path):
    data = json.load(open(path))

    def go(con):
        gid = {}
        for name, desc in data["groups"]:
            con.execute("INSERT OR IGNORE INTO groups(name,description,created_by,created_at) VALUES(?,?,?,?)",
                        (name, desc, "Claude scan", db.now_iso()))
            gid[name] = con.execute("SELECT id FROM groups WHERE name=?", (name,)).fetchone()[0]
        added = 0
        for sector, url, name, year, miles, price, seller, loc, notes, groups in data["cars"]:
            url = clean_url(url)
            if con.execute("SELECT 1 FROM cars WHERE url=?", (url,)).fetchone():
                continue
            cid = con.execute(
                "INSERT INTO cars(url,name,title,sector,year,mileage,seller,location,added_by,added_at,notes) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (url, name, name, sector, year, miles, seller, loc, "Claude scan", db.now_iso(), notes)).lastrowid
            for g in groups:
                con.execute("INSERT OR IGNORE INTO car_groups VALUES(?,?)", (cid, gid[g]))
            db.record_snapshot(con, cid, price, None, "live", "scan", "Claude scan")
            added += 1
        return added
    print("added", db.write(go))


if __name__ == "__main__":
    load(sys.argv[1])
