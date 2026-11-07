#!/usr/bin/env python3
"""Temporary: find United Cloud community with Serbian N1 / Nova S / Sport Klub."""
import json, urllib.request
B = "https://api-web.ug-be.cdn.united.cloud"
BASIC = "MjdlMTFmNWUtODhlMi00OGU0LWJkNDItOGUxNWFiYmM2NmY1OjEyejJzMXJ3bXdhZmsxMGNkdzl0cjloOWFjYjZwdjJoZDhscXZ0aGc="
def req(url, h, data=None):
    r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", **h}, data=data, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(r, timeout=30) as f:
        return json.load(f)
tok = req(f"{B}/oauth/token?grant_type=client_credentials", {"Authorization": f"Basic {BASIC}"}, b"")["access_token"]
H = {"Authorization": f"Bearer {tok}"}
for c in range(1, 41):
    for lang in ("", "&languageId=59", "&languageId=10001"):
        try:
            d = req(f"{B}/v1/public/channels?channelType=TV&communityId={c}{lang}&imageSize=L", H)
        except Exception as e:
            continue
        if isinstance(d, list) and d:
            hits = [f"{x.get('id')}:{x.get('name')}" for x in d if any(k in (x.get('name') or '').upper() for k in ("N1", "NOVA", "SK ", "SPORT KLUB", "RTS"))]
            print(f"community {c}{lang}: {len(d)} channels | " + " ; ".join(hits[:25]), flush=True)
            break
