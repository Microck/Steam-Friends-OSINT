from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class FriendProbOpts:
    top_n_for_mean: int = 5
    reasonable_count: int = 50  # constant baseline


@dataclass
class LocationProbOpts:
    reasonable_count: int = 100
    score_strategy: str = "multiply"  # "multiply" | "sum"


def _neighbor_map(nodes: Dict[str, Dict]) -> Dict[str, Set[str]]:
    neigh: Dict[str, Set[str]] = {}
    for sid, n in nodes.items():
        neigh[sid] = set(n.get("friends", []) or [])
    return neigh


def compute_irl_friends(
    state: Dict,
    opts: Optional[FriendProbOpts] = None,
) -> List[Dict]:
    """
    IRL probability for seed's direct friends using mutual-counts:
      - mutual = number of seed's other friends who also have this candidate
      - probability blend mirrors the JS/TS logic from your app
    """
    opts = opts or FriendProbOpts()
    seed = state["seed"]
    nodes = state["nodes"]
    seed_friends = list(set(nodes.get(seed, {}).get("friends", []) or []))
    neigh = _neighbor_map(nodes)

    rows: List[Tuple[str, int]] = []
    seed_set = set(seed_friends)
    for cand in seed_friends:
        mutual = sum(1 for fr in seed_set if cand in neigh.get(fr, set()))
        rows.append((cand, mutual))

    if not rows:
        return []

    rows.sort(key=lambda r: r[1], reverse=True)
    biggest = max(1, rows[0][1])

    top_k = rows[: max(1, min(opts.top_n_for_mean, len(rows)))]
    mean_top = sum(c for _, c in top_k) / max(1, len(top_k))
    denom_mean = max(1.0, mean_top * 1.5)

    out: List[Dict] = []
    for sid, count in rows:
        mean_method = min(1.0, count / denom_mean)
        max_method = min(1.0, count / biggest)
        const_method = min(1.0, count / float(opts.reasonable_count))
        prob = ((mean_method * 2) + (max_method * 2) + const_method) / 5.0
        prob_pct = max(0.0, min(100.0, prob * 100.0))

        n = nodes.get(sid, {})
        out.append(
            {
                "steamid": sid,
                "personaname": n.get("personaname"),
                "profileurl": n.get("profileurl"),
                "count": count,
                "probability": round(prob_pct, 2),
            }
        )
    return out


def _city_key(n: Dict) -> Optional[str]:
    cc = n.get("loccountrycode")
    st = n.get("locstatecode") or ""
    cid = n.get("loccityid")
    if cc and cid is not None:
        return f"{cc}/{st}/{cid}"
    return None


def infer_possible_locations(
    state: Dict,
    friend_irl: List[Dict],
    opts: Optional[LocationProbOpts] = None,
) -> List[Dict]:
    """
    Multiply accumulation per city key for the seed's friends that expose
    location fields, then probability = (2*share + 1*constant)/3, scaled.
    """
    opts = opts or LocationProbOpts()
    nodes = state["nodes"]
    ids = [r["steamid"] for r in friend_irl] if friend_irl else []
    if not ids:
        return []

    scores: Dict[str, float] = {}
    for sid in ids:
        n = nodes.get(sid, {})
        key = _city_key(n)
        if not key:
            continue
        c = max(
            0, int(next((r["count"] for r in friend_irl if r["steamid"] == sid), 0))
        )
        if opts.score_strategy == "sum":
            scores[key] = scores.get(key, 0.0) + float(c)
        else:
            scores[key] = (scores[key] * float(c)) if key in scores else float(c)

    if not scores:
        return []

    items = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(v for _, v in items) or 1.0

    out: List[Dict] = []
    for key, score in items:
        cc, st, cid = key.split("/")
        share = score / total
        const = min(1.0, score / float(opts.reasonable_count))
        prob = ((share * 2.0) + const) / 3.0
        prob_pct = max(0.0, min(100.0, prob * 100.0))
        out.append(
            {
                "location": {
                    "countryCode": cc,
                    "stateCode": st or None,
                    "cityID": int(cid) if str(cid).isdigit() else cid,
                    "countryName": None,
                    "stateName": None,
                    "cityName": None,
                },
                "count": score,
                "probability": round(prob_pct, 2),
            }
        )
    return out


def build_estimates(
    state: Dict, fopts: Optional[FriendProbOpts], lopts: Optional[LocationProbOpts]
) -> Dict:
    """
    Returns a single dict ready to save as estimates.json:
    {
      closestFriends: [...],
      possibleLocations: [...]
    }
    """
    friends = compute_irl_friends(state, fopts)
    locs = infer_possible_locations(state, friends, lopts) if friends else []
    return {"closestFriends": friends, "possibleLocations": locs}