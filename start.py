from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Optional

import questionary as q
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.theme import Theme
from tqdm import tqdm

from steam_osint.enricher import export_gephi
from steam_osint.probable_friends import compute_probable_friends
from steam_osint.scanner import scan_network
from steam_osint.steam_api import SteamAPI
from steam_osint.utils import open_folder, stamp


THEME = Theme({"accent": "bold cyan", "hint": "cyan", "warn": "yellow"})
console = Console(theme=THEME)
ROOT = Path(__file__).parent.resolve()
ASSETS = ROOT / "assets"
OUTPUTS = ROOT / "outputs"
PROFILES = ROOT / "profiles"
DEFAULT_CFG = ROOT / "steam_osint" / "config_default.yaml"
ENV = ROOT / ".env"


def main() -> None:
    console.print(Panel(_banner(), title="[accent]steam-friends-osint"))
    _ensure_env()
    cfg = _load_default_cfg()

    while True:
        choice = q.select(
            "what do you want to do?",
            choices=[
                "scan by steamid64",
                "scan by profile url",
                "presets",
                "config",
                "dry-run estimate",
                "resume last run",
                "recent targets",
                "quit",
            ],
        ).ask()
        if not choice or choice == "quit":
            break

        if choice in {"scan by steamid64", "scan by profile url"}:
            target = _ask_target(choice == "scan by profile url")
            if not target:
                continue
            run_scan(target, cfg)

        elif choice == "presets":
            cfg = _pick_preset(cfg)

        elif choice == "config":
            cfg = _guided_config(cfg)

        elif choice == "dry-run estimate":
            target = _ask_target(True)
            if target:
                dry_run(target, cfg)

        elif choice == "resume last run":
            resume_last(cfg)

        elif choice == "recent targets":
            pick_recent(cfg)


def _banner() -> str:
    try:
        return (ASSETS / "banner.txt").read_text(encoding="utf-8")
    except Exception:
        return "steam-friends-osint"


def _ensure_env() -> None:
    load_dotenv(dotenv_path=ENV)
    key = os.getenv("STEAM_API_KEY", "").strip()
    if key:
        return
    console.print(
        "[hint]get your api key here: https://steamcommunity.com/dev/apikey"
    )
    key = q.text("paste your STEAM_API_KEY").ask()
    if not key:
        console.print("[warn]no key; exiting")
        sys.exit(1)
    ENV.write_text(f"STEAM_API_KEY={key}\n", encoding="utf-8")
    load_dotenv(dotenv_path=ENV, override=True)


def _load_default_cfg() -> Dict:
    data = yaml.safe_load(DEFAULT_CFG.read_text(encoding="utf-8"))
    ensure_profiles()
    return data


def ensure_profiles() -> None:
    PROFILES.mkdir(parents=True, exist_ok=True)


def _ask_target(is_url: bool) -> Optional[str]:
    prompt = "paste profile url" if is_url else "enter steamid64"
    s = q.text(prompt).ask()
    return s.strip() if s else None


def _pick_preset(cfg: Dict) -> Dict:
    choice = q.select(
        "choose a preset",
        choices=[
            "inner circle (depth 1, small)",
            "community map (depth 2, ~500 nodes)",
            "custom (load profile / save profile)",
            "back",
        ],
    ).ask()
    if choice == "inner circle (depth 1, small)":
        cfg["depth"] = 1
        cfg["max_nodes"] = 300
    elif choice == "community map (depth 2, ~500 nodes)":
        cfg["depth"] = 2
        cfg["max_nodes"] = 500
    elif choice == "custom (load profile / save profile)":
        cfg = _profiles_menu(cfg)
    return cfg


def _profiles_menu(cfg: Dict) -> Dict:
    ensure_profiles()
    profiles = [p.stem for p in PROFILES.glob("*.yaml")]
    choice = q.select(
        "profiles",
        choices=["save current as...", *profiles, "back"],
    ).ask()
    if choice == "save current as...":
        name = q.text("profile name").ask()
        if name:
            (PROFILES / f"{name}.yaml").write_text(
                yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8"
            )
            console.print(f"[accent]saved profiles/{name}.yaml")
    elif choice and choice != "back":
        cfg = yaml.safe_load((PROFILES / f"{choice}.yaml").read_text(encoding="utf-8"))
        console.print(f"[accent]loaded profiles/{choice}.yaml")
    return cfg


def _guided_config(cfg: Dict) -> Dict:
    console.print("[accent]guided config (press enter for default)")
    cfg["depth"] = int(
        q.text(f"depth (1..3) [default {cfg['depth']}]").ask() or cfg["depth"]
    )
    cfg["max_nodes"] = int(
        q.text(f"max_nodes [default {cfg['max_nodes']}]").ask() or cfg["max_nodes"]
    )
    cfg["rate_limit_rpm"] = int(
        q.text(f"rate_limit_rpm [default {cfg['rate_limit_rpm']}]").ask()
        or cfg["rate_limit_rpm"]
    )
    cfg["skip_private_profiles"] = q.confirm(
        f"skip_private_profiles? [default {cfg['skip_private_profiles']}]",
        default=cfg["skip_private_profiles"],
    ).ask()
    cfg["include_group_links"] = q.confirm(
        f"include_group_links? [default {cfg['include_group_links']}]",
        default=cfg["include_group_links"],
    ).ask()
    # advanced
    if q.confirm("advanced options (hub threshold etc.)?", default=False).ask():
        cfg["hub_percentile"] = float(
            q.text(
                f"hub_percentile (0.95..0.999) [default {cfg['hub_percentile']}]"
            ).ask()
            or cfg["hub_percentile"]
        )
    return cfg


def _make_api(cfg: Dict) -> SteamAPI:
    key = os.getenv("STEAM_API_KEY", "").strip()
    return SteamAPI(key, rpm=cfg["rate_limit_rpm"])


def _resolve_target(api: SteamAPI, s: str) -> Optional[str]:
    sid = api.ensure_steam64(s)
    if not sid:
        console.print("[warn]could not resolve target")
    return sid


def dry_run(target: str, cfg: Dict) -> None:
    api = _make_api(cfg)
    sid = _resolve_target(api, target)
    if not sid:
        return

    friends = api.get_friend_list(sid)
    sample = friends[: min(50, len(friends))]
    counts = []
    for f in tqdm(sample, desc="sampling friends", unit="ids"):
        try:
            counts.append(len(api.get_friend_list(f)))
        except Exception:
            continue

    avg = sum(counts) / len(counts) if counts else 0
    est_depth1 = len(friends)
    est_depth2 = min(cfg["max_nodes"], int(len(set(friends)) + avg * 5))
    console.print(
        Panel(
            f"seed friends ~ {est_depth1}\n"
            f"estimated nodes at depth=2 (cap {cfg['max_nodes']}): ~{est_depth2}",
            title="[accent]dry-run estimate",
        )
    )


def run_scan(target: str, cfg: Dict) -> None:
    api = _make_api(cfg)
    sid = _resolve_target(api, target)
    if not sid:
        return

    out_dir = OUTPUTS / sid / stamp()
    out_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[accent]output → {out_dir}")

    # crawl
    state = scan_network(
        api=api,
        seed_steamid=sid,
        depth=cfg["depth"],
        rpm=cfg["rate_limit_rpm"],
        max_nodes=cfg["max_nodes"],
        skip_private=cfg["skip_private_profiles"],
        include_group_links=cfg["include_group_links"],
        resume_state=None,
    )

    # export
    nodes_csv, edges_csv, raw_json = export_gephi(
        state=state, out_dir=out_dir, hub_percentile=cfg["hub_percentile"]
    )
    compute_probable_friends(
        state=state, out_dir=out_dir, weights=cfg.get("weights", {})
    )

    console.print(
        Panel(
            f"done.\n\ngephi:\n  {nodes_csv}\n  {edges_csv}\n\nraw:\n  {raw_json}\n",
            title="[accent]export complete",
        )
    )
    if q.confirm("open output folder?", default=True).ask():
        open_folder(out_dir)


def resume_last(cfg: Dict) -> None:
    seeds = sorted((OUTPUTS.glob("*")), key=lambda p: p.stat().st_mtime, reverse=True)
    if not seeds:
        console.print("[warn]no previous outputs found")
        return
    seed_dir = seeds[0]
    runs = sorted(
        (seed_dir.glob("*")), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not runs:
        console.print("[warn]no runs found")
        return
    run_dir = runs[0]
    raw = run_dir / "scan.json"
    if not raw.exists():
        console.print("[warn]latest run has no scan.json")
        return

    state = yaml.safe_load(raw.read_text(encoding="utf-8"))
    api = _make_api(cfg)
    sid = state["seed"]

    state2 = scan_network(
        api=api,
        seed_steamid=sid,
        depth=cfg["depth"],
        rpm=cfg["rate_limit_rpm"],
        max_nodes=cfg["max_nodes"],
        skip_private=cfg["skip_private_profiles"],
        include_group_links=cfg["include_group_links"],
        resume_state=state,
    )

    out_dir = OUTPUTS / sid / stamp()
    out_dir.mkdir(parents=True, exist_ok=True)
    export_gephi(state2, out_dir, hub_percentile=cfg["hub_percentile"])
    compute_probable_friends(state2, out_dir, cfg.get("weights", {}))
    console.print(f"[accent]resumed. output → {out_dir}")
    if q.confirm("open output folder?", default=True).ask():
        open_folder(out_dir)


def pick_recent(cfg: Dict) -> None:
    targets = sorted(
        [p.name for p in OUTPUTS.glob("*") if p.is_dir()],
        reverse=True,
    )
    if not targets:
        console.print("[warn]no targets yet")
        return
    sid = q.select("recent targets", choices=targets + ["back"]).ask()
    if not sid or sid == "back":
        return
    runs = sorted(
        [p.name for p in (OUTPUTS / sid).glob("*") if p.is_dir()],
        reverse=True,
    )
    if not runs:
        console.print("[warn]no runs for that target")
        return
    run = q.select("choose run", choices=runs + ["back"]).ask()
    if run and run != "back":
        open_folder(OUTPUTS / sid / run)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[warn]ctrl-c; bye")