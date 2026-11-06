"""Apply crew requests filed as GitHub issues (the site's Add / Log / Group buttons open prefilled issue forms).

Only issues from logins in data/crew.json are applied; anyone else gets one polite comment and waits for Ian
to add them (or to label the issue "approved"). Each applied issue gets a reply and is closed."""
import json
import re
import subprocess
from pathlib import Path

from . import db
from .fetch import url_ok
from .server import SECTORS, STATUSES, clean_url, num, txt

ROOT = Path(__file__).resolve().parent.parent
GH = str(Path.home() / ".local/bin/gh")
REPO = "spridgehub/gated"
CREW = ROOT / "data" / "crew.json"
WAIT_NOTE = "Thanks! You're not on the crew list yet, so this is waiting for Ian to approve."


def gh(*args, input=None):
    return subprocess.run([GH, *args], check=True, capture_output=True, text=True, input=input).stdout


def fields(body):
    """Issue-form bodies are '### Label' headings each followed by the answer."""
    out = {}
    for m in re.finditer(r"^###\s+(.+?)\s*$\n(.*?)(?=^###\s|\Z)", body or "", re.S | re.M):
        v = m.group(2).strip()
        out[m.group(1).strip().lower()] = "" if v == "_No response_" else v
    return out


def car_id(ref, con):
    m = re.match(r"\s*#?(\d+)", ref or "")
    if m and con.execute("SELECT 1 FROM cars WHERE id=?", (int(m.group(1)),)).fetchone():
        return int(m.group(1))
    row = con.execute("SELECT id FROM cars WHERE url=?", (clean_url(ref),)).fetchone()
    if row:
        return row[0]
    raise ValueError(f"Couldn't find the car '{ref}'. Use the Log button on the site so the car is filled in.")


def group_ids(con, names):
    ids = []
    for n in re.split(r"[,\n]", names or ""):
        n = n.strip()
        if n:
            row = con.execute("SELECT id FROM groups WHERE lower(name)=lower(?)", (n,)).fetchone()
            if row:
                ids.append(row[0])
    return ids


def add_car(f, who):
    url = clean_url(f.get("listing link"))
    if not url_ok(url):
        raise ValueError("The listing link needs to be a full public https:// address.")
    sector = f.get("model") if f.get("model") in SECTORS else "Other"
    price, views = num(f.get("asking price today (£)")), num(f.get("views today"), 0, 10_000_000)

    def go(con):
        if con.execute("SELECT 1 FROM cars WHERE url=? AND archived=0", (url,)).fetchone():
            raise ValueError("That listing is already on the tracker.")
        con.execute("DELETE FROM cars WHERE url=? AND archived=1", (url,))
        name = txt(f.get("your name for it"), 120) or "Unnamed car"
        cid = con.execute(
            "INSERT INTO cars(url,name,title,sector,year,mileage,seller,location,added_by,added_at,notes) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (url, name, name, sector, num(f.get("year"), 1950, 2030), num(f.get("mileage"), 0, 1_000_000),
             txt(f.get("seller"), 80), txt(f.get("location"), 80), who, db.now_iso(), txt(f.get("notes"), 600))
        ).lastrowid
        for g in group_ids(con, f.get("groups")):
            con.execute("INSERT OR IGNORE INTO car_groups VALUES(?,?)", (cid, g))
        if price is not None or views is not None:
            db.record_snapshot(con, cid, price, views, "live", "manual", who)
        return f"Added as car #{cid}: {name}."
    return db.write(go)


def log(f, who):
    price, views = num(f.get("asking price (£)")), num(f.get("views"), 0, 10_000_000)
    status = (f.get("status") or "").lower()
    status = status if status in STATUSES else None
    if price is None and views is None and status is None:
        raise ValueError("Nothing to log: add a price, a view count or a status.")

    def go(con):
        cid = car_id(f.get("car"), con)
        st = status or con.execute("SELECT status FROM cars WHERE id=?", (cid,)).fetchone()[0]
        con.execute("UPDATE cars SET status=? WHERE id=?", (st, cid))
        db.record_snapshot(con, cid, price, views, st, "manual", who)
        note = txt(f.get("note"), 300)
        if note:
            con.execute("UPDATE cars SET notes=trim(coalesce(notes,'') || ' · ' || ?, ' ·') WHERE id=?",
                        (f"{db.today()} {who}: {note}", cid))
        bits = [f"£{price:,}" if price else None, f"{views:,} views" if views is not None else None, st]
        return f"Logged for car #{cid} today: {', '.join(b for b in bits if b)}."
    return db.write(go)


def group(f, who):
    name = txt(f.get("group name"), 60)
    if not name:
        raise ValueError("The group needs a name.")

    def go(con):
        row = con.execute("SELECT id FROM groups WHERE lower(name)=lower(?)", (name,)).fetchone()
        if row:
            gid = row[0]
            if f.get("what links them"):
                con.execute("UPDATE groups SET description=? WHERE id=?", (txt(f["what links them"], 300), gid))
            con.execute("DELETE FROM car_groups WHERE group_id=?", (gid,))
        else:
            gid = con.execute("INSERT INTO groups(name,description,created_by,created_at) VALUES(?,?,?,?)",
                              (name, txt(f.get("what links them"), 300), who, db.now_iso())).lastrowid
        n = 0
        for line in (f.get("cars") or "").splitlines():
            if line.strip():
                con.execute("INSERT OR IGNORE INTO car_groups VALUES(?,?)", (car_id(line, con), gid))
                n += 1
        return f"{'Updated' if row else 'Created'} group '{name}' with {n} cars."
    return db.write(go)


def _ts(s):
    from datetime import datetime
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


HANDLERS = {"add-car": add_car, "log-update": log, "group": group}


def run():
    crew = {u.lower() for u in json.loads(CREW.read_text())}
    issues = json.loads(gh("issue", "list", "--repo", REPO, "--state", "open", "--limit", "100",
                           "--json", "number,body,labels,author,comments,updatedAt"))
    changed = 0
    for i in sorted(issues, key=lambda x: x["number"]):
        labels = {l["name"] for l in i["labels"]}
        kind = next((k for k in HANDLERS if k in labels), None)
        if not kind:
            continue
        who = i["author"]["login"]
        if who.lower() not in crew and "approved" not in labels:
            if not any(WAIT_NOTE in c["body"] for c in i["comments"]):
                gh("issue", "comment", str(i["number"]), "--repo", REPO, "--body", WAIT_NOTE)
            continue
        last = i["comments"][-1] if i["comments"] else None
        if last and last["body"].startswith("Couldn't apply") and \
                abs(_ts(i["updatedAt"]) - _ts(last["createdAt"])) < 90:
            continue   # already told them what's wrong and nothing has been edited since
        try:
            msg = HANDLERS[kind](fields(i["body"]), who)
            changed += 1
            gh("issue", "close", str(i["number"]), "--repo", REPO, "--comment", msg + " It'll show on the site within a few minutes.")
        except (ValueError, Exception) as e:
            gh("issue", "comment", str(i["number"]), "--repo", REPO, "--body",
               f"Couldn't apply this: {e} Edit the issue to fix it and it'll be retried.")
        print(i["number"], kind, who)
    return changed


if __name__ == "__main__":
    print("applied", run())
