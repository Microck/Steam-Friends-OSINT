from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from tqdm import tqdm

from .steam_api import SteamAPI


def scan_network(
    api: SteamAPI,
    seed_steamid: str,
    depth: int,
    rpm: int,
    max_nodes: int,
    skip_private: bool,
    include_group_links: bool,
    resume_state: Optional[Dict] = None,
) -> Dict:
    """BFS crawl of friends; returns a state dict suitable for export."""
    state = resume_state or {
        "seed": seed_steamid,
        "nodes": {},       # steamid -> data
        "edges": [],       # dicts: {a,b,type}
        "visited": [],
        "queue": [],
        "meta": {"depth": depth},
    }

    visited: Set[str] = set(state.get("visited", []))
    nodes: Dict[str, Dict] = state.get("nodes", {})
    edges: List[Dict] = state.get("edges", [])
    q: deque[Tuple[str, int]] = deque(state.get("queue", []))  # (sid, depth)

    if not q:
        q.append((seed_steamid, 0))

    pbar = tqdm(total=max_nodes, desc="scanning", unit="nodes")

    while q and len(nodes) < max_nodes:
        sid, d = q.popleft()
        if sid in visited:
            continue
        visited.add(sid)

        # ensure node
        if sid not in nodes:
            nodes[sid] = {"steamid": sid}

        # fetch friends
        friends = api.get_friend_list(sid)
        nodes[sid]["friends"] = friends

        # enqueue next layer
        if d < depth:
            for f in friends:
                if f not in visited:
                    q.append((f, d + 1))

        # friend edges
        for f in friends:
            edges.append({"a": sid, "b": f, "type": "friend"})

        pbar.update(1)
        if len(nodes) >= max_nodes:
            break

    pbar.close()

    # summaries/bans for all discovered nodes
    all_ids = list(nodes.keys())
    summaries = api.get_player_summaries(all_ids)
    bans = api.get_player_bans(all_ids)

    for sid in all_ids:
        p = summaries.get(sid, {})
        vis = p.get("communityvisibilitystate")
        nodes[sid]["personaname"] = p.get("personaname")
        nodes[sid]["profileurl"] = p.get("profileurl")
        nodes[sid]["is_public"] = True if vis == 3 else False

        b = bans.get(sid, {})
        nodes[sid]["bans"] = {
            "VACBanned": b.get("VACBanned", False),
            "NumberOfVACBans": b.get("NumberOfVACBans", 0),
            "NumberOfGameBans": b.get("NumberOfGameBans", 0),
        }

    # group edges (optional)
    if include_group_links:
        gmap: Dict[str, List[str]] = {}
        for sid in all_ids:
            if skip_private and not nodes[sid].get("is_public", False):
                continue
            groups = api.get_user_groups(sid)
            nodes[sid]["groups"] = groups
            for gid in groups:
                gmap.setdefault(gid, []).append(sid)

        for gid, members in gmap.items():
            if len(members) < 2:
                continue
            mems = list(set(members))
            for i, a in enumerate(mems):
                for b in mems[i + 1 :]:
                    edges.append({"a": a, "b": b, "type": "group"})

    state["visited"] = list(visited)
    state["nodes"] = nodes
    state["edges"] = edges
    state["queue"] = list(q)
    return state
