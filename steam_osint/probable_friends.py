	from __future__ import annotations
	
	from pathlib import Path
	from typing import Dict, List, Set, Tuple
	
	from .utils import ensure_dir
	
	
	def compute_probable_friends(
	    state: Dict,
	    out_dir: Path,
	    weights: Dict[str, float],
	) -> Path:
	    """Rank likely close associates of the seed and export CSV."""
	    seed = state["seed"]
	    nodes = state["nodes"]
	
	    seed_friends: Set[str] = set(nodes.get(seed, {}).get("friends", []) or [])
	
	    # build neighbor sets (friendship only)
	    neigh: Dict[str, Set[str]] = {}
	    for sid, n in nodes.items():
	        neigh[sid] = set(n.get("friends", []) or [])
	
	    # optional auxiliary data
	    groups_map: Dict[str, Set[str]] = {
	        sid: set(n.get("groups", []) or []) for sid, n in nodes.items()
	    }
	
	    rows: List[Tuple[str, float, int, float, int, int]] = []
	
	    for candidate in seed_friends:
	        # mutual count among seed's other friends
	        mutual = sum(1 for fr in seed_friends if candidate in neigh.get(fr, set()))
	        # jaccard with seed
	        a = neigh.get(candidate, set())
	        inter = len(a & seed_friends)
	        union = len(a | seed_friends) or 1
	        jacc = inter / union
	
	        # shared groups with seed
	        sg = len(groups_map.get(candidate, set()) & groups_map.get(seed, set()))
	
	        # games overlap omitted by default; weight can be set to 0.0
	        games = 0
	
	        score = (
	            mutual * weights.get("mutual", 1.0)
	            + jacc * weights.get("jaccard", 1.0)
	            + sg * weights.get("groups", 0.5)
	            + games * weights.get("games", 0.0)
	        )
	
	        rows.append((candidate, score, mutual, jacc, sg, games))
	
	    rows.sort(key=lambda r: r[1], reverse=True)
	
	    path = out_dir / "probable_friends.csv"
	    ensure_dir(out_dir)
	    with path.open("w", encoding="utf-8", newline="") as f:
	        f.write(
	            "candidate_steamid,score,mutual_count,jaccard_with_seed,"
	            "shared_groups,shared_games\n"
	        )
	        for r in rows:
	            f.write(
	                f"{r[0]},{round(r[1],4)},{r[2]},{round(r[3],4)},{r[4]},{r[5]}\n"
	            )
	    return path
