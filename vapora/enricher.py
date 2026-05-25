from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import networkx as nx
from community import community_louvain

from .utils import ensure_dir


def _clean_edges(nodes: Dict[str, Dict], edges: List[Dict]) -> List[Dict]:
    keep = set(nodes.keys())
    out = []
    seen = set()
    for e in edges:
        a, b = e.get("a"), e.get("b")
        t = e.get("type", "friend")
        if not a or not b:
            continue
        if a not in keep or b not in keep:
            continue
        key = tuple(sorted((a, b)) + [t])
        if key in seen:
            continue
        seen.add(key)
        out.append({"a": a, "b": b, "type": t})
    return out


def _build_graph(nodes: Dict[str, Dict], edges: List[Dict]) -> nx.Graph:
    G = nx.Graph()
    for sid, n in nodes.items():
        G.add_node(
            sid,
            label=n.get("personaname") or sid,
            is_public=n.get("is_public", False),
            is_banned=bool(
                n.get("bans", {}).get("VACBanned")
                or n.get("bans", {}).get("NumberOfGameBans", 0) > 0
            ),
        )
    for e in edges:
        G.add_edge(e["a"], e["b"], kind=e.get("type", "friend"))
    return G


def export_gephi(
    state: Dict,
    out_dir: Path,
    hub_percentile: float = 0.99,
) -> Tuple[Path, Path]:
    """
    Compute metrics and export CSVs under 'graphi' folder.
    Returns (nodes_csv, edges_csv). scan.json is not written here.
    """
    nodes = state["nodes"]
    edges = _clean_edges(nodes, state["edges"])
    G = _build_graph(nodes, edges)
    seed = state["seed"]

    # metrics
    deg = dict(G.degree())
    bet = nx.betweenness_centrality(G)
    mod = community_louvain.best_partition(G)

    # hub flag threshold
    if bet:
        idx = max(0, int(len(bet) * hub_percentile) - 1)
        thresh = sorted(bet.values(), reverse=True)[idx]
    else:
        thresh = 1.0

    gephi_dir = out_dir / "graphi"
    ensure_dir(gephi_dir)
    nodes_csv = gephi_dir / "nodes.csv"
    edges_csv = gephi_dir / "edges.csv"

    with nodes_csv.open("w", encoding="utf-8", newline="") as f:
        f.write(
            "Id,Label,degree,betweenness,modularity_class,"
            "is_seed,is_hub,is_banned,is_public\n"
        )
        for sid in G.nodes():
            n = nodes.get(sid, {})
            label = n.get("personaname") or sid
            is_banned = bool(
                n.get("bans", {}).get("VACBanned")
                or n.get("bans", {}).get("NumberOfGameBans", 0) > 0
            )
            is_public = n.get("is_public", False)
            is_hub = bet.get(sid, 0.0) >= thresh if bet else False
            is_seed = sid == seed
            f.write(
                f"{sid},{_esc(label)},{deg.get(sid,0)},{bet.get(sid,0.0)},"
                f"{mod.get(sid,-1)},{str(is_seed).lower()},"
                f"{str(is_hub).lower()},{str(is_banned).lower()},"
                f"{str(is_public).lower()}\n"
            )

    with edges_csv.open("w", encoding="utf-8", newline="") as f:
        f.write("Source,Target,Kind\n")
        for e in edges:
            f.write(f"{e['a']},{e['b']},{e.get('type','friend')}\n")

    return nodes_csv, edges_csv


def _esc(s: str) -> str:
    return (
        s.replace(",", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace('"', "'")
        .strip()
    )