from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import questionary as q
import yaml
from dotenv import load_dotenv
from questionary import Style
from rich.console import Console
from rich.theme import Theme

from vapora.enricher import export_gephi
from vapora.ids import parse_any_steam_input
from vapora.irl import (
    FriendProbOpts,
    LocationProbOpts,
    build_estimates,
)
from vapora.scanner import scan_network
from vapora.steamhistory import (
    fetch_profile_json,
    analyze_closeness_by_duration,
    extract_main_info,
)
from vapora.steam_api import SteamAPI
from vapora.utils import open_folder, stamp, RunLogger


# ────────────────────────────── Initialization

THEME = Theme({"accent": "cyan", "hint": "cyan", "warn": "yellow"})
console = Console(theme=THEME)


def resource_path(*parts: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).parent
    return base.joinpath(*parts)


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


ROOT = app_root()
ASSETS = resource_path("assets")
OUTPUTS = ROOT / "outputs"
PROFILES = ROOT / "profiles"
DEFAULT_CFG = resource_path("vapora", "config_default.yaml")
ENV = ROOT / ".env"

# ────────────────────────────── Styles (CMD-Safe)
CUSTOM_STYLE = Style(
    [
        ("qmark", "fg:yellow bold"),
        ("question", "fg:cyan bold"),
        ("answer", "fg:green bold"),
        ("pointer", "fg:yellow bold"),
        ("selected", "fg:black bg:yellow bold"),
        ("highlighted", "fg:black bg:yellow bold"),
        ("instruction", "fg:gray"),
        ("text", ""),
        ("disabled", "fg:gray"),
    ]
)


# ────────────────────────────── Banner

def clear_cmd() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def print_banner(cfg: Optional[Dict] = None) -> None:
    clear_cmd()
    banner_file = ASSETS / "banner.txt"
    if banner_file.exists():
        banner = banner_file.read_text(encoding="utf-8", errors="ignore")
        print(banner)
    else:
        print("steam-friends-osint")
    mode = (cfg or {}).get("run_mode", "full").upper()
    print(f"Mode: {mode}")
    print("-" * 70 + "\n")


# ────────────────────────────── ENV / Config

def _ensure_env() -> None:
    load_dotenv(dotenv_path=ENV)
    key = os.getenv("STEAM_API_KEY", "").strip()
    if key:
        return
    console.print(
        "Get your API key: https://steamcommunity.com/dev/apikey", style="hint"
    )
    key = q.text("Paste your STEAM_API_KEY", style=CUSTOM_STYLE).ask()
    if not key:
        console.print("No key; exiting.", style="warn")
        sys.exit(1)
    ENV.write_text(f"STEAM_API_KEY={key}\n", encoding="utf-8")
    load_dotenv(dotenv_path=ENV, override=True)


def _load_default_cfg() -> Dict:
    data = yaml.safe_load(DEFAULT_CFG.read_text(encoding="utf-8"))
    PROFILES.mkdir(parents=True, exist_ok=True)
    return data


# ────────────────────────────── Mode helpers

def _mode_caps(cfg: Dict) -> Dict[str, bool]:
    """Feature gates for modes."""
    mode = cfg.get("run_mode", "full").lower()
    if mode == "graphi":
        return {
            "graphi": True,
            "estimates": False,
            "steamhistory": False,
        }
    if mode == "basic":
        return {
            "graphi": False,
            "estimates": True,
            "steamhistory": True,
        }
    # full
    return {
        "graphi": True,
        "estimates": True,
        "steamhistory": True,
    }


def _pick_mode(cfg: Dict) -> Dict:
    mode = q.select(
        "Select run mode:",
        choices=["Full", "Basic", "Graphi", "Back"],
        style=CUSTOM_STYLE,
    ).ask()
    if not mode or mode == "Back":
        return cfg
    cfg["run_mode"] = mode.lower()
    console.print(f"Mode set to {mode}", style="accent")
    return cfg


# ────────────────────────────── Prompts

def _ask_target() -> Optional[str]:
    s = q.text(
        "Target (SteamID / SteamID3 / SteamID64 / vanity / URL):",
        style=CUSTOM_STYLE,
    ).ask()
    return s.strip() if s else None


def _pick_preset(cfg: Dict) -> Dict:
    choice = q.select(
        "Choose a preset:",
        choices=[
            "Inner circle (depth 1, small)",
            "Community map (depth 2, ~500 nodes)",
            "Custom (load/save profile)",
            "Back",
        ],
        style=CUSTOM_STYLE,
    ).ask()
    if choice == "Inner circle (depth 1, small)":
        cfg.update({"depth": 1, "max_nodes": 300})
    elif choice == "Community map (depth 2, ~500 nodes)":
        cfg.update({"depth": 2, "max_nodes": 500})
    elif choice == "Custom (load/save profile)":
        cfg = _profiles_menu(cfg)
    return cfg


def _profiles_menu(cfg: Dict) -> Dict:
    PROFILES.mkdir(parents=True, exist_ok=True)
    profiles = [p.stem for p in PROFILES.glob("*.yaml")]
    choice = q.select(
        "Profiles:",
        choices=["Save current as...", *profiles, "Back"],
        style=CUSTOM_STYLE,
    ).ask()
    if choice == "Save current as...":
        name = q.text("Profile name:", style=CUSTOM_STYLE).ask()
        if name:
            path = PROFILES / f"{name}.yaml"
            path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
            console.print(f"Saved profiles/{name}.yaml", style="accent")
    elif choice and choice != "Back":
        path = PROFILES / f"{choice}.yaml"
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
        console.print(f"Loaded profiles/{choice}.yaml", style="accent")
    return cfg


def _guided_config(cfg: Dict) -> Dict:
    caps = _mode_caps(cfg)
    console.print("Guided Config (Press Enter for default)", style="accent")

    # Common scan parameters
    cfg["depth"] = int(
        q.text(f"Depth (1–3) [default {cfg['depth']}]", style=CUSTOM_STYLE).ask()
        or cfg["depth"]
    )
    cfg["max_nodes"] = int(
        q.text(f"max_nodes [default {cfg['max_nodes']}]", style=CUSTOM_STYLE).ask()
        or cfg["max_nodes"]
    )
    cfg["rate_limit_rpm"] = int(
        q.text(
            f"rate_limit_rpm [default {cfg['rate_limit_rpm']}]",
            style=CUSTOM_STYLE,
        ).ask()
        or cfg["rate_limit_rpm"]
    )
    cfg["skip_private_profiles"] = q.confirm(
        f"skip_private_profiles? [default {cfg['skip_private_profiles']}]",
        default=cfg["skip_private_profiles"],
        style=CUSTOM_STYLE,
    ).ask()
    cfg["include_group_links"] = q.confirm(
        f"include_group_links? [default {cfg['include_group_links']}]",
        default=cfg["include_group_links"],
        style=CUSTOM_STYLE,
    ).ask()

    if caps["graphi"]:
        if q.confirm(
            "Advanced (hub threshold etc.)?",
            default=False,
            style=CUSTOM_STYLE,
        ).ask():
            cfg["hub_percentile"] = float(
                q.text(
                    f"hub_percentile (0.95–0.999) [default {cfg['hub_percentile']}]",
                    style=CUSTOM_STYLE,
                ).ask()
                or cfg["hub_percentile"]
            )

    if caps["estimates"]:
        irl = cfg.get("irl", {})
        irl["top_n_for_mean"] = int(
            q.text(
                f"IRL top_n_for_mean [default {irl.get('top_n_for_mean', 5)}]",
                style=CUSTOM_STYLE,
            ).ask()
            or irl.get("top_n_for_mean", 5)
        )
        irl["reasonable_count"] = int(
            q.text(
                f"IRL reasonable_count [default {irl.get('reasonable_count', 50)}]",
                style=CUSTOM_STYLE,
            ).ask()
            or irl.get("reasonable_count", 50)
        )
        cfg["irl"] = irl

        loc = cfg.get("location", {})
        loc["reasonable_count"] = int(
            q.text(
                f"Location reasonable_count [default {loc.get('reasonable_count', 100)}]",
                style=CUSTOM_STYLE,
            ).ask()
            or loc.get("reasonable_count", 100)
        )
        loc["score_strategy"] = (
            q.select(
                "Location score_strategy",
                choices=["multiply", "sum"],
                style=CUSTOM_STYLE,
            ).ask()
            or loc.get("score_strategy", "multiply")
        )
        cfg["location"] = loc

    if caps["steamhistory"]:
        cfg["request_timeout"] = int(
            q.text(
                f"steamhistory request_timeout [default {cfg.get('request_timeout', 25)}]",
                style=CUSTOM_STYLE,
            ).ask()
            or cfg.get("request_timeout", 25)
        )

    return cfg


# ────────────────────────────── Core logic

def _make_api(cfg: Dict) -> SteamAPI:
    key = os.getenv("STEAM_API_KEY", "").strip()
    return SteamAPI(key, rpm=cfg["rate_limit_rpm"])


def _resolve_any_target(api: SteamAPI, s: str) -> Optional[str]:
    sid64 = parse_any_steam_input(s, api)
    if not sid64:
        console.print("Could not resolve target.", style="warn")
    return sid64


def dry_run(target: str, cfg: Dict) -> None:
    api = _make_api(cfg)
    sid = _resolve_any_target(api, target)
    if not sid:
        return

    friends = api.get_friend_list(sid)
    est_depth1 = len(friends)
    console.print(f"Seed friends ~ {est_depth1}", style="accent")


def _maybe_load_steamhistory(
    cfg: Dict, logger: RunLogger
) -> Optional[Tuple[Dict, Dict]]:
    """
    Ask user to paste a SteamHistory JSON/NDJSON URL or file path (optional).
    Returns (main_info, closeness_by_duration) or None if skipped.
    """
    s = q.text(
        "Optional: SteamHistory JSON/NDJSON URL or file path (Enter to skip)",
        style=CUSTOM_STYLE,
    ).ask()
    if not s:
        return None
    try:
        data = fetch_profile_json(s, timeout=cfg.get("request_timeout", 25))
        main_info = extract_main_info(data)
        closeness = {"friends": analyze_closeness_by_duration(data)}
        logger.write("Loaded SteamHistory JSON.")
        return main_info, closeness
    except Exception as e:
        logger.write(f"SteamHistory fetch failed: {e}")
        return None


def run_scan(target: str, cfg: Dict) -> None:
    caps = _mode_caps(cfg)
    api = _make_api(cfg)
    sid = _resolve_any_target(api, target)
    if not sid:
        return

    out_dir = OUTPUTS / sid / stamp()
    out_dir.mkdir(parents=True, exist_ok=True)
    runlog = RunLogger(out_dir / "run.log")
    runlog.write(f"Target resolved to SteamID64: {sid}")
    console.print(f"Output → {out_dir}", style="accent")

    # Optional SteamHistory analysis (Full/Basic only)
    sh = None
    if caps["steamhistory"]:
        sh = _maybe_load_steamhistory(cfg, runlog)

    # Scan network
    runlog.write("Scanning network...")
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
    runlog.write(
        f"Scan complete. Nodes={len(state['nodes'])}, "
        f"Edges={len(state['edges'])}."
    )

    # Save scan.json (always)
    scan_path = out_dir / "scan.json"
    scan_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    runlog.write(f"Wrote scan.json")

    # Graph output (nodes/edges under 'graphi/')
    if caps["graphi"]:
        nodes_csv, edges_csv = export_gephi(
            state=state, out_dir=out_dir, hub_percentile=cfg["hub_percentile"]
        )
        runlog.write(f"Wrote graphi: {nodes_csv.name}, {edges_csv.name}")

    # Estimates (Closest friends + Possible locations) in one file
    estimates = None
    if caps["estimates"]:
        friend_opts = FriendProbOpts(
            top_n_for_mean=cfg.get("irl", {}).get("top_n_for_mean", 5),
            reasonable_count=cfg.get("irl", {}).get("reasonable_count", 50),
        )
        loc_opts = LocationProbOpts(
            reasonable_count=cfg.get("location", {}).get("reasonable_count", 100),
            score_strategy=cfg.get("location", {}).get("score_strategy", "multiply"),
        )
        estimates = build_estimates(state, friend_opts, loc_opts)
        # If we have SH duration results and network gave none, fallback
        if not estimates["closestFriends"] and sh:
            estimates["closestFriends"] = sh[1]["friends"][:20]
            runlog.write("No network-based closest friends; "
                         "used SteamHistory duration fallback.")
        est_path = out_dir / "estimates.json"
        est_path.write_text(json.dumps(estimates, indent=2), encoding="utf-8")
        runlog.write(f"Wrote estimates.json")

    # Show results in CLI
    if estimates:
        cf = estimates.get("closestFriends", [])[:10]
        pl = estimates.get("possibleLocations", [])[:5]
        if cf:
            console.print("Top closest friends:", style="accent")
            for r in cf:
                label = r.get("personaname") or r.get("name") or r["steamid"]
                console.print(f"- {label}: {round(r['probability'],2)}%")
        if pl:
            console.print("Top possible locations:", style="accent")
            for r in pl:
                loc = r["location"]
                cc = loc.get("countryCode") or "?"
                st = loc.get("stateCode") or ""
                cid = loc.get("cityID")
                console.print(
                    f"- {cc}-{st}-{cid}: {round(r['probability'],2)}%"
                )

    runlog.write("Done.")
    runlog.close()
    if q.confirm("Open output folder?", default=True, style=CUSTOM_STYLE).ask():
        open_folder(out_dir)


def resume_last(cfg: Dict) -> None:
    seeds = sorted(
        OUTPUTS.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not seeds:
        console.print("No previous outputs found", style="warn")
        return
    seed_dir = seeds[0]
    runs = sorted(
        seed_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not runs:
        console.print("No runs found", style="warn")
        return
    open_folder(runs[0])


def pick_recent(cfg: Dict) -> None:
    targets = sorted([p.name for p in OUTPUTS.glob("*") if p.is_dir()], reverse=True)
    if not targets:
        console.print("No targets yet", style="warn")
        return
    sid = q.select("Recent targets", choices=targets + ["Back"], style=CUSTOM_STYLE).ask()
    if not sid or sid == "Back":
        return
    runs = sorted([p.name for p in (OUTPUTS / sid).glob("*") if p.is_dir()], reverse=True)
    if not runs:
        console.print("No runs for that target", style="warn")
        return
    run = q.select("Choose run", choices=runs + ["Back"], style=CUSTOM_STYLE).ask()
    if run and run != "Back":
        open_folder(OUTPUTS / sid / run)


# ────────────────────────────── Entry point

def main() -> None:
    cfg = _load_default_cfg()
    print_banner(cfg)
    _ensure_env()

    while True:
        caps = _mode_caps(cfg)
        choices = [
            "Scan target",
            "Mode",
            "Presets",
            "Config",
            "Dry-run estimate",
            "Recent targets",
            "Quit",
        ]
        choice = q.select(
            "What do you want to do?",
            choices=choices,
            style=CUSTOM_STYLE,
        ).ask()

        if not choice or choice == "Quit":
            break
        if choice == "Scan target":
            target = _ask_target()
            if target:
                run_scan(target, cfg)
        elif choice == "Mode":
            cfg = _pick_mode(cfg)
            print_banner(cfg)
        elif choice == "Presets":
            cfg = _pick_preset(cfg)
        elif choice == "Config":
            cfg = _guided_config(cfg)
            print_banner(cfg)
        elif choice == "Dry-run estimate":
            target = _ask_target()
            if target:
                dry_run(target, cfg)
        elif choice == "Recent targets":
            pick_recent(cfg)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nctrl-c; bye")