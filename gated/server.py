"""Gated: a shared tracker for UK analogue supercars.

Anyone with the link can look. Adding or editing needs the crew code, which rides in the share link
(?k=...) and is remembered in the browser. Run: python -m gated.server  (port 8812)."""
import json
import os
import re
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from . import db
from .fetch import url_ok

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
CONFIG = ROOT / "data" / "config.json"
PORT = int(os.environ.get("GATED_PORT", "8812"))
SECTORS = [
    "Ferrari 430 Scuderia / 16M", "Ferrari F430 manual", "McLaren 675LT", "Aston Martin V12 manual",
    "Porsche 997.1 GT3 / RS", "Porsche 997.2 GT3 / RS", "Porsche 991.1 GT3", "Audi R8 V10 manual", "Other",
]
STATUSES = ("live", "reserved", "sold", "gone")


def config():
    if not CONFIG.exists():
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps({"code": secrets.token_urlsafe(6), "auto_check": False}, indent=2))
    return json.loads(CONFIG.read_text())


def clean_url(u):
    """Strip tracking query strings so the same advert pasted twice is one car."""
    u = (u or "").strip()
    p = urlparse(u)
    host = (p.hostname or "").lower()
    keep_query = not any(h in host for h in ("pistonheads", "autotrader"))
    return urlunparse((p.scheme.lower(), p.netloc.lower().replace("www-cdn.", "www."), p.path.rstrip("/") or "/",
                       "", p.query if keep_query else "", ""))


def txt(v, n=200):
    v = (v or "").strip() if isinstance(v, str) else ""
    return re.sub(r"[\x00-\x1f]", " ", v)[:n] or None


def num(v, lo=0, hi=50_000_000):
    if v in (None, ""):
        return None
    try:
        n = int(float(str(v).replace(",", "").replace("£", "").strip()))
    except ValueError:
        raise ValueError(f"'{v}' isn't a number")
    if not lo <= n <= hi:
        raise ValueError(f"{n} is out of range")
    return n


def set_groups(con, car_id, group_ids):
    con.execute("DELETE FROM car_groups WHERE car_id=?", (car_id,))
    for g in group_ids or []:
        con.execute("INSERT OR IGNORE INTO car_groups(car_id, group_id) SELECT ?, id FROM groups WHERE id=?",
                    (car_id, int(g)))


def check_in_background(car_ids):
    if not config().get("auto_check"):
        return
    from .daily import check_cars
    threading.Thread(target=check_cars, args=(car_ids,), daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    server_version = "Gated/1"

    def log_message(self, fmt, *args):
        pass

    # helpers
    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20_000:
            raise ValueError("Too much data")
        return json.loads(self.rfile.read(n) or b"{}")

    def authed(self, data):
        return secrets.compare_digest(str(data.get("code") or self.headers.get("X-Crew-Code") or ""),
                                      config()["code"])

    # routes
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self.send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/state":
            s = db.state()
            s["sectors"], s["auto_check"] = SECTORS, bool(config().get("auto_check"))
            return self.send(200, s)
        if path == "/api/auth":
            return self.send(200, {"ok": self.authed({})})
        if path.startswith("/assets/") and ".." not in path:
            f = STATIC / path.lstrip("/")
            if f.is_file():
                ctype = {"svg": "image/svg+xml", "png": "image/png", "webmanifest": "application/manifest+json"}
                return self.send(200, f.read_bytes(), ctype.get(f.suffix.lstrip("."), "application/octet-stream"))
        self.send(404, {"error": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self.body()
        except (ValueError, json.JSONDecodeError):
            return self.send(400, {"error": "Couldn't read that"})
        if not self.authed(data):
            return self.send(403, {"error": "Enter the crew code from the share link to make changes"})
        who = txt(data.get("by"), 40) or "someone"
        try:
            if path == "/api/cars":
                return self.add_car(data, who)
            m = re.fullmatch(r"/api/cars/(\d+)(/log|/archive)?", path)
            if m:
                car_id, action = int(m.group(1)), m.group(2)
                if action == "/log":
                    return self.log(car_id, data, who)
                if action == "/archive":
                    db.write(lambda con: con.execute("UPDATE cars SET archived=1 WHERE id=?", (car_id,)))
                    return self.send(200, {"ok": True})
                return self.edit_car(car_id, data)
            if path == "/api/groups":
                return self.add_group(data, who)
            m = re.fullmatch(r"/api/groups/(\d+)", path)
            if m:
                return self.edit_group(int(m.group(1)), data)
        except ValueError as e:
            return self.send(400, {"error": str(e)})
        self.send(404, {"error": "Not found"})

    def add_car(self, d, who):
        url = clean_url(d.get("url"))
        if not url_ok(url):
            raise ValueError("Paste the full listing link (https://...) from a public site")
        price, views, mileage = num(d.get("price")), num(d.get("views"), 0, 10_000_000), num(d.get("mileage"), 0, 1_000_000)
        year = num(d.get("year"), 1950, 2030)
        sector = d.get("sector") if d.get("sector") in SECTORS else "Other"

        def go(con):
            if con.execute("SELECT 1 FROM cars WHERE url=? AND archived=0", (url,)).fetchone():
                raise ValueError("That listing is already on the tracker")
            con.execute("DELETE FROM cars WHERE url=? AND archived=1", (url,))
            cur = con.execute(
                "INSERT INTO cars(url,name,title,sector,year,mileage,seller,location,added_by,added_at,notes) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (url, txt(d.get("name"), 120), txt(d.get("name"), 120), sector, year, mileage,
                 txt(d.get("seller"), 80), txt(d.get("location"), 80), who, db.now_iso(), txt(d.get("notes"), 600)))
            car_id = cur.lastrowid
            set_groups(con, car_id, d.get("groups"))
            if price is not None or views is not None:
                db.record_snapshot(con, car_id, price, views, "live", "manual", who)
            return car_id

        car_id = db.write(go)
        check_in_background([car_id])
        self.send(200, {"ok": True, "id": car_id})

    def edit_car(self, car_id, d):
        fields, vals = [], []
        for k, n in (("name", 120), ("notes", 600), ("seller", 80), ("location", 80)):
            if k in d:
                fields.append(f"{k}=?"); vals.append(txt(d[k], n))
        if "sector" in d and d["sector"] in SECTORS:
            fields.append("sector=?"); vals.append(d["sector"])
        for k, lo, hi in (("year", 1950, 2030), ("mileage", 0, 1_000_000)):
            if k in d:
                fields.append(f"{k}=?"); vals.append(num(d[k], lo, hi))

        def go(con):
            if fields:
                con.execute(f"UPDATE cars SET {', '.join(fields)} WHERE id=?", (*vals, car_id))
            if "groups" in d:
                set_groups(con, car_id, d["groups"])
        db.write(go)
        self.send(200, {"ok": True})

    def log(self, car_id, d, who):
        price, views = num(d.get("price")), num(d.get("views"), 0, 10_000_000)
        status = d.get("status") if d.get("status") in STATUSES else None
        if price is None and views is None and status is None:
            raise ValueError("Enter a price, a view count or a status")

        def go(con):
            car = con.execute("SELECT status FROM cars WHERE id=?", (car_id,)).fetchone()
            if not car:
                raise ValueError("No such car")
            st = status or car["status"]
            con.execute("UPDATE cars SET status=? WHERE id=?", (st, car_id))
            db.record_snapshot(con, car_id, price, views, st, "manual", who)
        db.write(go)
        self.send(200, {"ok": True})

    def add_group(self, d, who):
        name = txt(d.get("name"), 60)
        if not name:
            raise ValueError("Give the group a name")

        def go(con):
            try:
                cur = con.execute("INSERT INTO groups(name,description,created_by,created_at) VALUES(?,?,?,?)",
                                  (name, txt(d.get("description"), 300), who, db.now_iso()))
            except Exception:
                raise ValueError("There's already a group with that name")
            for c in d.get("cars") or []:
                con.execute("INSERT OR IGNORE INTO car_groups(car_id, group_id) VALUES(?,?)", (int(c), cur.lastrowid))
            return cur.lastrowid
        self.send(200, {"ok": True, "id": db.write(go)})

    def edit_group(self, gid, d):
        def go(con):
            if d.get("delete"):
                con.execute("DELETE FROM groups WHERE id=?", (gid,))
                return
            if "name" in d and txt(d["name"], 60):
                con.execute("UPDATE groups SET name=? WHERE id=?", (txt(d["name"], 60), gid))
            if "description" in d:
                con.execute("UPDATE groups SET description=? WHERE id=?", (txt(d["description"], 300), gid))
            if "cars" in d:
                con.execute("DELETE FROM car_groups WHERE group_id=?", (gid,))
                for c in d["cars"]:
                    con.execute("INSERT OR IGNORE INTO car_groups(car_id, group_id) VALUES(?,?)", (int(c), gid))
        db.write(go)
        self.send(200, {"ok": True})


def main():
    config()
    db.connect().close()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Gated on :{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
