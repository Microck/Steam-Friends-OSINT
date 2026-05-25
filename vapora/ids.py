from __future__ import annotations

import re
from typing import Optional, Tuple
from urllib.parse import urlparse

from .steam_api import SteamAPI

OFFSET = 76561197960265728


def _from_steam2(s2: str) -> Optional[str]:
    # STEAM_X:Y:Z
    m = re.match(r"^STEAM_([0-5]):([01]):(\d+)$", s2, re.IGNORECASE)
    if not m:
        return None
    universe, y, z = int(m.group(1)), int(m.group(2)), int(m.group(3))
    account_id = z * 2 + y
    return str(OFFSET + account_id)


def _from_steam3(s3: str) -> Optional[str]:
    # [U:1:ACCOUNTID] or U:1:ACCOUNTID
    m = re.match(r"^\[?([a-zA-Z]):(\d+):(\d+)\]?$", s3)
    if not m:
        # Also accept [U:1:XXXXX:XXXX] -> take third component as account id
        m2 = re.findall(r"(\d+)", s3)
        if len(m2) >= 1:
            account_id = int(m2[-1])
            return str(OFFSET + account_id)
        return None
    account_id = int(m.group(3))
    return str(OFFSET + account_id)


def _from_profiles_url(url: str) -> Optional[str]:
    try:
        p = urlparse(url)
        parts = [x for x in p.path.split("/") if x]
        if len(parts) >= 2 and parts[0].lower() == "profiles":
            if re.fullmatch(r"\d{17}", parts[1]):
                return parts[1]
    except Exception:
        return None
    return None


def _vanity_from_id_url(url: str) -> Optional[str]:
    try:
        p = urlparse(url)
        parts = [x for x in p.path.split("/") if x]
        if len(parts) >= 2 and parts[0].lower() == "id":
            return parts[1]
    except Exception:
        return None
    return None


def parse_any_steam_input(s: str, api: SteamAPI) -> Optional[str]:
    """
    Accepts:
    - SteamID2 (STEAM_X:Y:Z)
    - SteamID3 ([U:1:XXXXX] or U:1:XXXXX)
    - SteamID64 (17 digits)
    - Full profile URLs (/profiles/<id> or /id/<vanity>)
    - Vanity strings (customURL)
    """
    x = (s or "").strip()

    # 64-bit
    if re.fullmatch(r"\d{17}", x):
        return x

    # Steam2
    sid64 = _from_steam2(x)
    if sid64:
        return sid64

    # Steam3 variants
    sid64 = _from_steam3(x)
    if sid64:
        return sid64

    # /profiles/<id>
    sid64 = _from_profiles_url(x)
    if sid64:
        return sid64

    # /id/<vanity> → resolve
    vanity = _vanity_from_id_url(x)
    if vanity:
        return api.ensure_steam64_from_vanity(vanity)

    # Plain vanity string (letters, digits, dash, underscore)
    if re.fullmatch(r"[A-Za-z0-9_\-\.]{2,64}", x):
        return api.ensure_steam64_from_vanity(x)

    # Last resort: try to take the last path part as vanity
    try:
        p = urlparse(x)
        if p.scheme in ("http", "https"):
            tail = [z for z in p.path.split("/") if z]
            if tail:
                return api.ensure_steam64_from_vanity(tail[-1])
    except Exception:
        pass

    return None