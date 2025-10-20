from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Optional

import questionary as q
import yaml
from dotenv import load_dotenv
from questionary import Style
from rich.console import Console
from rich.theme import Theme
from tqdm import tqdm
from colorama import init as colorama_init, Fore, Style as CStyle

from vapora.enricher import export_gephi
from vapora.probable_friends import compute_probable_friends
from vapora.scanner import scan_network
from vapora.steam_api import SteamAPI
from vapora.utils import open_folder, stamp


# ────────────────────────────── Initialization

colorama_init(autoreset=True)

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
# Simple color names — always safe in Windows CMD.
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
    os.system("cls")


def print_banner() -> None:
    clear_cmd()
    banner_file = ASSETS / "banner.txt"
    if banner_file.exists():
        banner = banner_file.read_text(encoding="utf-8", errors="ignore")
        print(Fore.CYAN + CStyle.BRIGHT + banner + CStyle.RESET_ALL)
    else:
        print(Fore.CYAN + "steam-friends-osint")
    print(Fore.CYAN + "-" * 70 + "\n")


# ────────────────────────────── ENV / Config

def _ensure_env() -> None:
    load_dotenv(dotenv_path=ENV)
    key = os.getenv("STEAM_API_KEY", "").strip()
    if key:
        return
    console.print("Get your API key: https://steamcommunity.com/dev/apikey", style="hint")
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


# ────────────────────────────── Prompts

def _ask_target(is_url: bool) -> Optional[str]:
    prompt = "Paste profile URL" if is_url else "Enter SteamID64"
    s = q.text(prompt, style=CUSTOM_STYLE).ask()
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
    console.print("Guided Config (Press Enter for default)", style="accent")
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
    if q.confirm(
        "Advanced options (hub threshold etc.)?",
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
    return cfg


# ────────────────────────────── Core logic

def _make_api(cfg: Dict) -> SteamAPI:
    key = os.getenv("STEAM_API_KEY", "").strip()
    return SteamAPI(key, rpm=cfg["rate_limit_rpm"])


def _resolve_target(api: SteamAPI, s: str) -> Optional[str]:
    sid = api.ensure_steam64(s)
    if not sid:
        console.print("Could not resolve target.", style="warn")
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
        f"Seed friends ~ {est_depth1}\n"
        f"Estimated nodes at depth=2 (cap {cfg['max_nodes']}): ~{est_depth2}",
        style="accent",
    )


def run_scan(target: str, cfg: Dict) -> None:
    api = _make_api(cfg)
    sid = _resolve_target(api, target)
    if not sid:
        return
    out_dir = OUTPUTS / sid / stamp()
    out_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"Output → {out_dir}", style="accent")

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

    nodes_csv, edges_csv, raw_json = export_gephi(
        state=state, out_dir=out_dir, hub_percentile=cfg["hub_percentile"]
    )
    compute_probable_friends(
        state=state, out_dir=out_dir, weights=cfg.get("weights", {})
    )
    console.print(
        f"Done.\n\nGephi:\n  {nodes_csv}\n  {edges_csv}\n\nRaw:\n  {raw_json}\n",
        style="accent",
    )
    if q.confirm("Open output folder?", default=True, style=CUSTOM_STYLE).ask():
        open_folder(out_dir)


def resume_last(cfg: Dict) -> None:
    seeds = sorted(OUTPUTS.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not seeds:
        console.print("No previous outputs found", style="warn")
        return
    seed_dir = seeds[0]
    runs = sorted(seed_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        console.print("No runs found", style="warn")
        return
    run_dir = runs[0]
    raw = run_dir / "scan.json"
    if not raw.exists():
        console.print("Latest run has no scan.json", style="warn")
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
    console.print(f"Resumed → {out_dir}", style="accent")
    if q.confirm("Open output folder?", default=True, style=CUSTOM_STYLE).ask():
        open_folder(out_dir)


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
    if os.name == "nt":
        os.system("chcp 65001 >nul")
    print_banner()
    _ensure_env()
    cfg = _load_default_cfg()

    while True:
        choice = q.select(
            "What do you want to do?",
            choices=[
                "Scan by steamid64",
                "Scan by profile URL",
                "Presets",
                "Config",
                "Dry-run estimate",
                "Resume last run",
                "Recent targets",
                "Quit",
            ],
            style=CUSTOM_STYLE,
        ).ask()

        if not choice or choice == "Quit":
            break
        if choice == "Scan by steamid64":
            target = _ask_target(False)
            if target:
                run_scan(target, cfg)
        elif choice == "Scan by profile URL":
            target = _ask_target(True)
            if target:
                run_scan(target, cfg)
        elif choice == "Presets":
            cfg = _pick_preset(cfg)
        elif choice == "Config":
            cfg = _guided_config(cfg)
        elif choice == "Dry-run estimate":
            target = _ask_target(True)
            if target:
                dry_run(target, cfg)
        elif choice == "Resume last run":
            resume_last(cfg)
        elif choice == "Recent targets":
            pick_recent(cfg)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[warn]ctrl-c; bye")