"""Read a listing page the way a visitor's browser would: once, in headless Chrome, with requests to
private or home-network addresses blocked (friends paste URLs, and this runs on the Mac mini).

Returns only what the page states; anything it doesn't state stays None."""
import ipaddress
import json
import re
import socket
from functools import lru_cache
from urllib.parse import urlparse

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130 Safari/537.36")

GONE_PHRASES = ("no longer available", "this advert has been removed", "this vehicle has been sold",
                "this car has been sold", "advert has expired", "listing has ended", "page not found")
SOLD_PHRASES = ("this car is now sold", "status: sold", ">sold<")
RESERVED_PHRASES = ("reserved", "under offer", "sale agreed", "deposit taken")


@lru_cache(maxsize=512)
def host_is_public(host):
    """True only when every address the host resolves to is a public one."""
    if not host or host.endswith((".local", ".ts.net", ".internal", ".lan", ".home")) or host == "localhost":
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global or ip in ipaddress.ip_network("100.64.0.0/10"):
            return False
    return True


# Sites that block automated clients outright: never checked automatically, manual entry only.
REFUSE_HOSTS = ("collectingcars.com", "carandclassic.com", "elferspot.com")


def url_ok(url):
    p = urlparse(url)
    return p.scheme in ("http", "https") and host_is_public(p.hostname or "")


@lru_cache(maxsize=256)
def _robots(origin):
    from urllib.robotparser import RobotFileParser
    rp = RobotFileParser(origin + "/robots.txt")
    try:
        rp.read()
    except Exception:
        return None
    return rp


def auto_allowed(url):
    """Automatic checks only where the site permits them: not a refusing host, and robots.txt allows it."""
    p = urlparse(url)
    host = (p.hostname or "").removeprefix("www.")
    if any(host == h or host.endswith("." + h) for h in REFUSE_HOSTS):
        return False
    rp = _robots(f"{p.scheme}://{p.netloc}")
    return rp is None or rp.can_fetch(UA, url)


def _int(s):
    if s is None:
        return None
    s = re.sub(r"[^\d.]", "", str(s))
    try:
        return int(float(s)) if s else None
    except ValueError:
        return None


def _jsonld(html):
    out = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                out.append(d)
                stack.extend(v for v in d.values() if isinstance(v, (dict, list)))
            elif isinstance(d, list):
                stack.extend(d)
    return out


def _meta(html, name):
    m = re.search(r'<meta[^>]+(?:name|property)="%s"[^>]+content="([^"]*)"' % re.escape(name), html, re.I)
    return m.group(1) if m else None


def parse(html, text, final_url=""):
    """Pull price, views, mileage, title and status from rendered HTML plus visible text."""
    r = {"title": None, "price": None, "views": None, "mileage": None, "year": None,
         "seller": None, "location": None, "image": None, "listed_at": None, "status": "live"}
    for d in _jsonld(html):
        t = d.get("@type")
        types = t if isinstance(t, list) else [t]
        if any(x in ("Product", "Car", "Vehicle", "Offer", "AggregateOffer") for x in types):
            r["title"] = r["title"] or d.get("name")
            offers = d.get("offers") if isinstance(d.get("offers"), dict) else d
            if r["price"] is None and (offers.get("price") or offers.get("lowPrice")):
                r["price"] = _int(offers.get("price") or offers.get("lowPrice"))
            if isinstance(d.get("mileageFromOdometer"), dict):
                r["mileage"] = r["mileage"] or _int(d["mileageFromOdometer"].get("value"))
            seller = (offers.get("seller") or {}) if isinstance(offers.get("seller"), dict) else {}
            r["seller"] = r["seller"] or seller.get("name")
            img = d.get("image")
            r["image"] = r["image"] or (img[0] if isinstance(img, list) and img else img if isinstance(img, str) else None)
            r["year"] = r["year"] or _int(d.get("vehicleModelDate") or d.get("productionDate"))
            avail = str(offers.get("availability") or "")
            if "SoldOut" in avail or "OutOfStock" in avail:
                r["status"] = "sold"
    # PistonHeads publishes these as meta tags; price is in pence
    if r["price"] is None and _meta(html, "sailthru.price"):
        r["price"] = _int(_meta(html, "sailthru.price")) // 100
    r["mileage"] = r["mileage"] or _int(_meta(html, "sailthru.mileage"))
    r["price"] = r["price"] or _int(_meta(html, "product:price:amount") or _meta(html, "og:price:amount"))
    r["title"] = r["title"] or _meta(html, "og:title")
    if not r["title"]:
        m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
        r["title"] = m.group(1).strip() if m else None
    r["image"] = r["image"] or _meta(html, "og:image")
    m = re.search(r'\\?"createdDate\\?":\\?"(\d{4}-\d\d-\d\dT[\d:.]+Z)', html)
    if m:
        r["listed_at"] = m.group(1)
    m = re.search(r'\\?"location\\?":\\?"([^"\\]{2,60})', html)
    if m and "pistonheads" in final_url:
        r["location"] = m.group(1)
    m = re.search(r"([\d,]+)\s+Views?\b", text)
    if m:
        r["views"] = _int(m.group(1))
    if r["year"] is None and r["title"]:
        m = re.search(r"\b(19[89]\d|20[0-3]\d)\b", r["title"])
        r["year"] = int(m.group(1)) if m else None
    low = text.lower()[:20000]
    if any(p in low for p in GONE_PHRASES):
        r["status"] = "gone"
    elif any(p in low for p in SOLD_PHRASES) or any(p in html.lower() for p in SOLD_PHRASES[2:]):
        r["status"] = "sold"
    elif re.search(r"\b(reserved|under offer|sale agreed|deposit taken)\b", low[:6000]) and \
            "available to reserve" not in low[:6000]:
        r["status"] = "reserved"
    if r["title"]:
        r["title"] = re.sub(r"\s*[-|]\s*(PistonHeads|Auto ?Trader).*$", "", r["title"], flags=re.I).strip()[:200]
    return r


class Browser:
    """One headless Chrome for a batch of checks."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(channel="chrome", headless=True)
        self.ctx = self.browser.new_context(user_agent=UA, locale="en-GB", viewport={"width": 1280, "height": 900})
        self.ctx.route("**/*", self._guard)
        return self

    def __exit__(self, *exc):
        try:
            self.browser.close()
        finally:
            self._pw.stop()

    @staticmethod
    def _guard(route):
        req = route.request
        if req.resource_type in ("image", "media", "font"):
            return route.abort()
        host = urlparse(req.url).hostname or ""
        if req.url.startswith(("data:", "blob:")) or host_is_public(host):
            return route.continue_()
        return route.abort()

    def check(self, url):
        if not url_ok(url):
            return {"error": "That address isn't a public website"}
        if not auto_allowed(url):
            return {"error": "This site doesn't allow automatic checks; log price and views by hand"}
        page = self.ctx.new_page()
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            code = resp.status if resp else 0
            if "pistonheads" in url:
                try:
                    page.wait_for_selector("[class*=AdvertStatsPills_pill__]", timeout=12000)
                except Exception:
                    pass
            else:
                page.wait_for_timeout(2500)
            html, text = page.content(), page.inner_text("body")
            if code in (404, 410):
                return {"status": "gone", "http": code}
            if code >= 400:
                return {"error": f"The site refused the check (HTTP {code})", "http": code}
            r = parse(html, text, page.url)
            r["http"] = code
            return r
        except Exception as e:
            return {"error": f"Couldn't load the page ({type(e).__name__})"}
        finally:
            page.close()
