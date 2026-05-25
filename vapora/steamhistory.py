from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests


def fetch_profile_json(url_or_path: str, timeout: int = 25) -> Dict:
    """
    Fetch JSON/NDJSON from URL or local file path.
    If NDJSON is given, try to parse it as a single JSON object if possible.
    """
    s = (url_or_path or "").strip()
    if not s:
        raise ValueError("Empty URL or path.")
    parsed = urlparse(s)
    if parsed.scheme in ("http", "https"):
        r = requests.get(s, timeout=timeout)
        r.raise_for_status()
        txt = r.text
    else:
        txt = Path(s).read_text(encoding="utf-8")

    # Heuristic: NDJSON vs JSON
    if txt.lstrip().startswith("{"):
        return json.loads(txt)
    # NDJSON cleaned elsewhere; the caller will normalize as needed.
    # Here we try to collect first JSON object that looks like a profile.
    # For your workflow, you typically pass the cleaned JSON.
    try:
        lines = [json.loads(line) for line in txt.splitlines() if line.strip()]
        # Return best-effort merge if present
        for obj in lines:
            if isinstance(obj, dict) and ("historic" in obj or "steamID64" in obj):
                return obj
        return {"_raw": lines}
    except Exception:
        return {"_text": txt}


def analyze_closeness_by_duration(profile: Dict) -> List[Dict]:
    """
    Duration-based closeness as fallback when only SteamHistory JSON is present.
    """
    hist = (profile or {}).get("historic", {}) or {}
    friends = hist.get("friends") or []
    if not friends:
        return []

    now = int(profile.get("lastChecked") or int(time.time()))
    rows: List[Tuple[str, int, Optional[str]]] = []
    for f in friends:
        sid = str(f.get("Friend"))
        start = int(f.get("FriendDate") or 0)
        end = int(f.get("UnfriendDate") or 0) or now
        dur = max(0, end - start)
        name = f.get("Name")
        rows.append((sid, dur, name))

    rows.sort(key=lambda r: r[1], reverse=True)
    max_d = max(1, rows[0][1])
    out: List[Dict] = []
    for sid, dur, name in rows:
        prob = min(1.0, dur / float(max_d)) * 100.0
        out.append(
            {
                "steamid": sid,
                "name": name,
                "duration_seconds": dur,
                "probability": round(prob, 2),
            }
        )
    return out


def extract_main_info(profile: Dict) -> Dict:
    """
    Extracts basic main info (name, urls, pfp history, persona history).
    Works with normalized SteamHistory JSON produced by your normalizer.
    """
    user = {
        "steamID64": profile.get("steamID64") or profile.get("steamid64"),
        "name": profile.get("name") or profile.get("personaname"),
        "communityURL": profile.get("communityURL") or profile.get("profileurl"),
        "avatarHash": profile.get("avatarHash"),
        "creationDate": profile.get("creationDate"),
        "lastUpdated": profile.get("lastUpdated"),
        "vacBanned": profile.get("vacBanned"),
        "communityBanned": profile.get("communityBanned"),
        "gameBans": profile.get("gameBans"),
        "economyBanned": profile.get("economyBanned"),
    }
    hist = profile.get("historic") or {}
    persona = hist.get("persona") or []
    urls = hist.get("url") or []
    pfp = hist.get("pfp") or []
    comments = hist.get("comments") or []

    return {
        "user": user,
        "historic": {
            "persona": persona,
            "url": urls,
            "pfp": pfp,
            "comments": comments,
            "counts": {
                "persona": len(persona),
                "url": len(urls),
                "pfp": len(pfp),
                "comments": len(comments),
            },
        },
    }