#!/usr/bin/env python3
"""Grab Serbian EPG from mts.rs and write XMLTV with the IPTV provider's channel IDs."""
import datetime as dt, zoneinfo, gzip, json, sys, time, urllib.parse, urllib.request
from xml.sax.saxutils import escape, quoteattr

DAYS = 3
TZ = zoneinfo.ZoneInfo("Europe/Belgrade")
URL = ("https://mts.rs/hybris/ecommerce/b2c/v1/products/search?sort=pozicija-rastuce"
       "&searchQueryContext=CHANNEL_PROGRAM&query=" +
       urllib.parse.quote(":pozicija-rastuce:tip-kanala-radio:TV kanali:channelProgramDates:", safe=":") +
       "{date}&pageSize=10000")

def fetch(date):
    req = urllib.request.Request(URL.format(date=date), headers={
        "User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception as e:
            print(f"{date}: attempt {attempt+1} failed: {e}", file=sys.stderr)
            time.sleep(10)
    return None

def ts(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) or str(v).isdigit():
        t = dt.datetime.fromtimestamp(int(v) / (1000 if int(v) > 1e11 else 1), dt.timezone.utc)
    else:
        t = dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=TZ)
    return t.strftime("%Y%m%d%H%M%S %z")

def main():
    mapping = {k: v for k, v in json.load(open("mapping.json")).items() if not k.startswith("_")}
    by_code = {}
    for pid, code in mapping.items():
        by_code.setdefault(code, []).append(pid)

    progs = {}   # code -> {start: prog}
    names = {}
    today = dt.datetime.now(TZ).date()
    for d in range(-1, DAYS):
        date = (today + dt.timedelta(days=d)).isoformat()
        data = fetch(date)
        if not data:
            continue
        for ch in data.get("products", []):
            code = ch.get("code")
            if code not in by_code:
                continue
            names[code] = ch.get("name", code)
            for p in ch.get("programs") or []:
                s, e = ts(p.get("start")), ts(p.get("end"))
                if s and e:
                    progs.setdefault(code, {})[s] = (s, e, p)
        print(f"{date}: {len(data.get('products', []))} channels", file=sys.stderr)

    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv generator-info-name="aca-epg (mts.rs)">']
    for code, pids in by_code.items():
        for pid in pids:
            out.append(f'<channel id={quoteattr(pid)}><display-name>{escape(names.get(code, pid))}</display-name></channel>')
    total = 0
    for code, items in progs.items():
        for s, e, p in sorted(items.values()):
            body = f'<title lang="sr">{escape(p.get("title") or "")}</title>'
            if p.get("description"):
                body += f'<desc lang="sr">{escape(p["description"])}</desc>'
            if p.get("category"):
                body += f'<category lang="sr">{escape(str(p["category"]))}</category>'
            img = (p.get("picture") or {}).get("url")
            if img:
                body += f'<icon src={quoteattr(img)}/>'
            for pid in by_code[code]:
                out.append(f'<programme start="{s}" stop="{e}" channel={quoteattr(pid)}>{body}</programme>')
                total += 1
    out.append("</tv>")
    missing = sorted(set(by_code) - set(progs))
    print(f"channels with data: {len(progs)}/{len(by_code)}, programmes: {total}", file=sys.stderr)
    if missing:
        print("no data for: " + ", ".join(missing), file=sys.stderr)
    if total == 0:
        sys.exit("no programmes grabbed - keeping previous file")
    xml = "\n".join(out).encode()
    open("public/epg.xml", "wb").write(xml)
    with gzip.open("public/epg.xml.gz", "wb") as f:
        f.write(xml)

if __name__ == "__main__":
    main()
