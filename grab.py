#!/usr/bin/env python3
"""Grab EPG (mts.rs for Serbia, Hrvatski Telekom for Croatia/SK/CineStar) and write XMLTV
using the IPTV provider's channel IDs."""
import datetime as dt, re, zoneinfo, gzip, hashlib, json, sys, time, uuid, urllib.parse, urllib.request
from xml.sax.saxutils import escape, quoteattr

DAYS = 3
TZ = zoneinfo.ZoneInfo("Europe/Belgrade")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0 Safari/537.36"

def log(*a):
    print(*a, file=sys.stderr, flush=True)

def get_json(url, headers=None, tries=3):
    for attempt in range(tries):
        try:
            h = {"User-Agent": UA, "Accept": "application/json"}
            h.update(headers() if callable(headers) else (headers or {}))
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=120) as r:
                return json.load(r)
        except Exception as e:
            log(f"  attempt {attempt+1} failed: {url[:120]}: {e}")
            time.sleep(5)
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

def dates():
    today = dt.datetime.now(TZ).date()
    return [(today + dt.timedelta(days=d)).isoformat() for d in range(-1, DAYS)]

# ---------- mts.rs ----------
MTS_URL = ("https://mts.rs/hybris/ecommerce/b2c/v1/products/search?sort=pozicija-rastuce"
           "&searchQueryContext=CHANNEL_PROGRAM&query=" +
           urllib.parse.quote(":pozicija-rastuce:tip-kanala-radio:TV kanali:channelProgramDates:", safe=":") +
           "{date}&pageSize=50&currentPage={page}")

def source_mts(wanted):
    out = {}
    for date in dates():
        page, n = 0, 0
        while page < 40:
            data = get_json(MTS_URL.format(date=date, page=page))
            items = (data or {}).get("products") or []
            if not items:
                break
            n += len(items)
            for ch in items:
                code = ch.get("code")
                if code not in wanted:
                    continue
                for p in ch.get("programs") or []:
                    out.setdefault(code, []).append({
                        "start": p.get("start"), "stop": p.get("end"), "title": p.get("title"),
                        "desc": p.get("description"), "category": p.get("category"),
                        "icon": (p.get("picture") or {}).get("url")})
            page += 1
            tp = (data.get("pagination") or {}).get("totalPages")
            if tp is not None and page >= int(tp):
                break
        log(f"mts {date}: {n} channels")
    return out

# ---------- Hrvatski Telekom (MojMAXtv) ----------
HT_API = "https://tv-hr-prod.yo-digital.com/hr-bifrost"
HT_APP_KEY = "GWaBW4RTloLwpUgYVzOiW5zUxFLmoMj5"
HT_NATCO_KEY = "l2lyvGVbUm2EKJE96ImQgcc8PKMZWtbE"
HT_VER = "02.0.1470"
HT_DEV, HT_SESS = str(uuid.uuid4()), str(uuid.uuid4())

def ht_headers():
    track, now = str(uuid.uuid4()), str(int(time.time() * 1000))
    return {
        "app_key": HT_APP_KEY, "app_version": HT_VER, "device-id": HT_DEV, "tenant": "tv",
        "origin": "https://mojmaxtv.hrvatskitelekom.hr", "x-call-type": "GUEST_USER",
        "x-call-time": now, "x-request-session-id": HT_SESS, "x-request-tracking-id": track,
        "x-tv-step": "EPG_SCHEDULES", "x-tv-flow": "EPG", "x-user-agent": f"web|web|Chrome-149|{HT_VER}|1",
        "x-txn-id": hashlib.sha256((track + HT_SESS + HT_DEV + now).encode()).hexdigest()[:32]}

def source_ht(wanted):
    chans = get_json(f"{HT_API}/epg/channel?channelMap_id=&includeVirtualChannels=false"
                     f"&natco_key={HT_NATCO_KEY}&app_language=hr&natco_code=hr", ht_headers)
    if not chans:
        log("ht: channel list failed")
        return {}
    by_station = {}
    lw = {w.lower(): w for w in wanted}
    for c in chans.get("channels", []):
        w = lw.get((c.get("title") or "").lower())
        if w:
            by_station.setdefault(str(c.get("station_id")), w)
    log(f"ht: {len(chans.get('channels', []))} channels, matched {len(set(by_station.values()))}/{len(wanted)}")
    missing = sorted(set(wanted) - set(by_station.values()))
    if missing:
        log("ht names not found: " + ", ".join(missing))
    out = {}
    for date in dates():
        for off in range(0, 24, 3):
            data = get_json(f"{HT_API}/epg/channel/schedules?date={date}&hour_offset={off}&hour_range=3"
                            f"&channelMap_id=&filler=true&app_language=hr&natco_code=hr", ht_headers)
            for sid, items in ((data or {}).get("channels") or {}).items():
                name = by_station.get(str(sid))
                if not name:
                    continue
                for it in items or []:
                    t = it.get("description")
                    if it.get("episode_name"):
                        t = f"{t} - {it['episode_name']}"
                    out.setdefault(name, []).append({
                        "start": it.get("start_time"), "stop": it.get("end_time"), "title": t,
                        "category": ", ".join(g.get("name", "") for g in it.get("genres") or []) or None})
        log(f"ht {date}: {len(out)} channels so far")
    return out


# ---------- United Cloud (SBB / EON / Telemach) ----------
UC = "https://api-web.ug-be.cdn.united.cloud"
UC_BASIC = "MjdlMTFmNWUtODhlMi00OGU0LWJkNDItOGUxNWFiYmM2NmY1OjEyejJzMXJ3bXdhZmsxMGNkdzl0cjloOWFjYjZwdjJoZDhscXZ0aGc="
UC_COMMUNITY, UC_LANG = 30, 59

def source_united(wanted):
    try:
        r = urllib.request.Request(f"{UC}/oauth/token?grant_type=client_credentials", data=b"", method="POST",
                                   headers={"User-Agent": UA, "Authorization": f"Basic {UC_BASIC}"})
        with urllib.request.urlopen(r, timeout=60) as f:
            tok = json.load(f)["access_token"]
    except Exception as e:
        log(f"united: token failed: {e}")
        return {}
    H = {"Authorization": f"Bearer {tok}", "Referer": "https://epg.telemach.ba/"}
    chans = get_json(f"{UC}/v1/public/channels?channelType=TV&communityId={UC_COMMUNITY}&languageId={UC_LANG}&imageSize=L", H) or []
    resolve = {}  # wanted key -> cid
    for w in wanted:
        if w.isdigit():
            resolve[w] = w
            continue
        norm = lambda n: re.sub(r"\s*(\(.*?\)|HD|SD)\s*", " ", n.upper()).strip()
        exact = [c for c in chans if norm(c.get("name") or "") == w.upper()]
        loose = [c for c in chans if (c.get("name") or "").upper().startswith(w.upper())]
        hit = (exact or loose or [None])[0]
        if hit:
            resolve[w] = str(hit["id"])
            log(f"united: {w} -> {hit['id']} {hit.get('name')}")
    missing = sorted(set(wanted) - set(resolve))
    log(f"united: {len(chans)} channels, resolved {len(resolve)}/{len(wanted)}" + (f", not found: {missing}" if missing else ""))
    out = {}
    for d in dates():
        day = dt.datetime.fromisoformat(d).replace(tzinfo=TZ).astimezone(dt.timezone.utc)
        frm = day.strftime("%Y-%m-%dT%H:%M:%S-00:00")
        to = (day + dt.timedelta(days=1, seconds=-1)).strftime("%Y-%m-%dT%H:%M:%S-00:00")
        for w, cid in resolve.items():
            data = get_json(f"{UC}/v1/public/events/epg?fromTime={frm}&toTime={to}"
                            f"&communityId={UC_COMMUNITY}&languageId={UC_LANG}&cid={cid}", H, tries=2) or {}
            for items in data.values() if isinstance(data, dict) else []:
                for it in items or []:
                    img = (it.get("images") or [{}])[0].get("path")
                    out.setdefault(w, []).append({
                        "start": it.get("startTime"), "stop": it.get("endTime"), "title": it.get("title"),
                        "desc": it.get("shortDescription"),
                        "icon": f"https://images-web.ug-be.cdn.united.cloud{img}" if img else None})
        log(f"united {d}: {len(out)} channels so far")
    return out

SOURCES = {"mts": source_mts, "united": source_united, "ht": source_ht}

def main():
    cfg = json.load(open("mapping.json"))
    chosen = {}  # provider id -> (source, list of progs)
    names = {}
    for src, fn in SOURCES.items():
        mapping = cfg.get(src) or {}
        try:
            data = fn(set(mapping.values()))
        except Exception as e:
            log(f"{src}: failed: {e}")
            data = {}
        for pid, code in mapping.items():
            names.setdefault(pid, code)
            if pid not in chosen and data.get(code):
                chosen[pid] = (src, data[code])

    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv generator-info-name="aca-epg">']
    for pid in sorted(names):
        out.append(f'<channel id={quoteattr(pid)}><display-name>{escape(names[pid])}</display-name></channel>')
    total = 0
    for pid, (src, progs) in sorted(chosen.items()):
        seen = {}
        for p in progs:
            s, e = ts(p.get("start")), ts(p.get("stop"))
            if s and e:
                seen[s] = (s, e, p)
        for s, e, p in sorted(seen.values()):
            body = f'<title lang="sr">{escape(p.get("title") or "")}</title>'
            if p.get("desc"):
                body += f'<desc lang="sr">{escape(p["desc"])}</desc>'
            if p.get("category"):
                body += f'<category lang="sr">{escape(str(p["category"]))}</category>'
            if p.get("icon"):
                body += f'<icon src={quoteattr(p["icon"])}/>'
            out.append(f'<programme start="{s}" stop="{e}" channel={quoteattr(pid)}>{body}</programme>')
            total += 1
    out.append("</tv>")
    log(f"provider channels with data: {len(chosen)}/{len(names)}, programmes: {total}")
    log("no data for: " + ", ".join(sorted(set(names) - set(chosen))))
    if total == 0:
        sys.exit("no programmes grabbed")
    xml = "\n".join(out).encode()
    open("public/epg.xml", "wb").write(xml)
    with gzip.open("public/epg.xml.gz", "wb") as f:
        f.write(xml)

if __name__ == "__main__":
    main()
