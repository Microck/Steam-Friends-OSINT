	from __future__ import annotations
	
	import time
	from collections import deque
	from typing import Dict, List, Optional, Tuple
	
	import requests
	
	
	class RateLimiter:
	    def __init__(self, rpm: int = 60) -> None:
	        self.window = 60.0
	        self.rpm = max(1, rpm)
	        self.calls: deque[float] = deque()
	
	    def wait(self) -> None:
	        now = time.monotonic()
	        while self.calls and now - self.calls[0] > self.window:
	            self.calls.popleft()
	        if len(self.calls) >= self.rpm:
	            sleep_for = self.window - (now - self.calls[0]) + 0.01
	            time.sleep(max(0.0, sleep_for))
	        self.calls.append(time.monotonic())
	
	
	class SteamAPI:
	    BASE = "https://api.steampowered.com"
	
	    def __init__(self, key: str, rpm: int = 60) -> None:
	        self.key = key
	        self.session = requests.Session()
	        self.rl = RateLimiter(rpm=rpm)
	
	    def _get(self, path: str, params: Dict) -> Optional[Dict]:
	        self.rl.wait()
	        p = dict(params)
	        p["key"] = self.key
	        try:
	            r = self.session.get(self.BASE + path, params=p, timeout=25)
	            if r.status_code != 200:
	                return None
	            return r.json()
	        except requests.RequestException:
	            return None
	
	    def ensure_steam64(self, id_or_url: str) -> Optional[str]:
	        s = id_or_url.strip()
	        if s.isdigit():
	            return s
	        # attempt to extract vanity from url
	        for part in s.replace("/", " ").split():
	            if part and part.lower() not in {"profiles", "id", "steamcommunity.com"}:
	                candidate = part
	        else:
	            candidate = s
	
	        data = self._get(
	            "/ISteamUser/ResolveVanityURL/v1/", {"vanityurl": candidate}
	        )
	        if not data:
	            return None
	        try:
	            if data["response"]["success"] == 1:
	                return data["response"]["steamid"]
	        except Exception:
	            return None
	        return None
	
	    def get_friend_list(self, steamid: str) -> List[str]:
	        data = self._get(
	            "/ISteamUser/GetFriendList/v1/",
	            {"steamid": steamid, "relationship": "friend"},
	        )
	        if not data or "friendslist" not in data:
	            return []
	        return [f["steamid"] for f in data["friendslist"].get("friends", [])]
	
	    def get_player_summaries(self, ids: List[str]) -> Dict[str, Dict]:
	        out: Dict[str, Dict] = {}
	        for i in range(0, len(ids), 100):
	            sub = ids[i : i + 100]
	            data = self._get(
	                "/ISteamUser/GetPlayerSummaries/v2/",
	                {"steamids": ",".join(sub)},
	            )
	            if not data:
	                continue
	            for p in data.get("response", {}).get("players", []):
	                sid = p.get("steamid")
	                if sid:
	                    out[sid] = p
	        return out
	
	    def get_player_bans(self, ids: List[str]) -> Dict[str, Dict]:
	        out: Dict[str, Dict] = {}
	        for i in range(0, len(ids), 100):
	            sub = ids[i : i + 100]
	            data = self._get(
	                "/ISteamUser/GetPlayerBans/v1/",
	                {"steamids": ",".join(sub)},
	            )
	            if not data:
	                continue
	            for p in data.get("players", []):
	                sid = p.get("SteamId")
	                if sid:
	                    out[sid] = p
	        return out
	
	    def get_user_groups(self, steamid: str) -> List[str]:
	        data = self._get("/ISteamUser/GetUserGroupList/v1/", {"steamid": steamid})
	        if not data:
	            return []
	        groups = data.get("response", {}).get("groups", []) or []
	        return [g.get("gid") for g in groups if g.get("gid")]
