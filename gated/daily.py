"""Daily check of every tracked listing. Off unless data/config.json has "auto_check": true.
Only sites that permit automated access are checked (see fetch.auto_allowed); the rest rely on
friends logging price and views by hand. Run: python -m gated.daily"""
import json
import sys
import time

from . import db


def check_cars(car_ids=None):
    from .fetch import Browser, auto_allowed
    from .server import config
    if not config().get("auto_check"):
        print("auto_check is off in data/config.json", file=sys.stderr)
        return
    con = db.connect()
    q = "SELECT id, url FROM cars WHERE archived=0 AND status NOT IN ('sold','gone')"
    rows = con.execute(q).fetchall() if car_ids is None else \
        con.execute(f"SELECT id, url FROM cars WHERE id IN ({','.join('?' * len(car_ids))})", car_ids).fetchall()
    con.close()
    rows = [r for r in rows if auto_allowed(r["url"])]
    if not rows:
        return
    with Browser() as b:
        for i, r in enumerate(rows):
            if i:
                time.sleep(8)   # one page at a time, unhurried
            res = b.check(r["url"])
            print(r["id"], json.dumps({k: v for k, v in res.items() if k != "image"}), flush=True)

            def save(con, r=r, res=res):
                if res.get("error"):
                    con.execute("UPDATE cars SET last_checked=?, last_error=? WHERE id=?",
                                (db.now_iso(), res["error"], r["id"]))
                    return
                car = con.execute("SELECT * FROM cars WHERE id=?", (r["id"],)).fetchone()
                status = res.get("status") or car["status"]
                con.execute(
                    "UPDATE cars SET title=COALESCE(?,title), year=COALESCE(year,?), mileage=COALESCE(?,mileage), "
                    "seller=COALESCE(seller,?), location=COALESCE(location,?), image=COALESCE(?,image), "
                    "listed_at=COALESCE(listed_at,?), status=?, last_checked=?, last_error=NULL WHERE id=?",
                    (res.get("title"), res.get("year"), res.get("mileage"), res.get("seller"), res.get("location"),
                     res.get("image"), res.get("listed_at"), status, db.now_iso(), r["id"]))
                db.record_snapshot(con, r["id"], res.get("price"), res.get("views"), status, "auto")
            db.write(save)


if __name__ == "__main__":
    check_cars()
