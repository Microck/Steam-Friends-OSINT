from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

import webview
import yaml

from vapora.enricher import export_gephi
from vapora.ids import parse_any_steam_input
from vapora.irl import FriendProbOpts, LocationProbOpts, build_estimates
from vapora.scanner import scan_network
from vapora.steam_api import SteamAPI
from vapora.utils import stamp, RunLogger, open_folder

ROOT = Path(__file__).parent
OUTPUTS = ROOT / "outputs"
CONFIG_PATH = ROOT / "vapora" / "config_default.yaml"
UI_DIR = ROOT / "ui"
PROFILES = ROOT / "profiles"
ENV_PATH = ROOT / ".env"
ENV_EXAMPLE_PATH = ROOT / ".env.example"


PLACEHOLDER_LINE = "STEAM_API_KEY=your_api_key_here"


def _load_env_file() -> None:
    """Minimal .env loader: sets os.environ for key=value pairs."""
    path = ENV_PATH if ENV_PATH.exists() else (ENV_EXAMPLE_PATH if ENV_EXAMPLE_PATH.exists() else None)
    if not path:
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip().strip("\"\'")
            # Skip placeholder
            if k == "STEAM_API_KEY" and (not v or v == "your_api_key_here"):
                continue
            if k and v and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


def _mode_caps(mode: str) -> Dict[str, bool]:
    m = (mode or "full").lower()
    if m == "graphi":
        return {"graphi": True, "estimates": False}
    if m == "basic":
        return {"graphi": False, "estimates": True}
    return {"graphi": True, "estimates": True}


class Bridge:
    def __init__(self, cfg: Dict):
        self.cfg = cfg
        self._window: Optional[webview.window.Window] = None  # type: ignore[attr-defined]
        self._pos = (0, 0)  # last known window position (x, y)
        PROFILES.mkdir(parents=True, exist_ok=True)
        # Ensure .env is loaded on startup so os.getenv works everywhere
        _load_env_file()

    # Window control hooks for frameless UI
    def attach(self, win) -> bool:
        self._window = win
        return True

    def win_close(self) -> bool:
        try:
            if self._window:
                self._window.destroy()
                return True
        except Exception:
            return False
        return False

    def win_minimize(self) -> bool:
        try:
            if self._window:
                self._window.minimize()
                return True
        except Exception:
            return False
        return False

    def win_move_by(self, dx: int, dy: int) -> bool:
        """Move window by a delta amount (manual drag fallback)."""
        try:
            if not self._window:
                return False
            x = int(self._pos[0]) + int(dx)
            y = int(self._pos[1]) + int(dy)
            # clamp a little to avoid negative overshoot causing OS snap glitches
            x = max(-32000, x)
            y = max(-32000, y)
            self._window.move(x, y)
            self._pos = (x, y)
            return True
        except Exception:
            return False

    def win_resize(self, width: int, height: int) -> bool:
        """Resize window to an explicit size."""
        try:
            if not self._window:
                return False
            w = max(640, int(width))
            h = max(400, int(height))
            self._window.resize(w, h)
            return True
        except Exception:
            return False

    # ----- Config I/O -----
    def get_config(self) -> Dict:
        # return only GUI-editable keys to keep UI simple
        return {
            "run_mode": self.cfg.get("run_mode", "full"),
            "depth": self.cfg["depth"],
            "max_nodes": self.cfg["max_nodes"],
            "rate_limit_rpm": self.cfg["rate_limit_rpm"],
            "skip_private_profiles": self.cfg["skip_private_profiles"],
            "include_group_links": self.cfg["include_group_links"],
            "include_game_overlap": self.cfg.get("include_game_overlap", False),
            "hub_percentile": self.cfg["hub_percentile"],
        }

    def set_config(self, partial: Dict) -> Dict:
        # Only allow the listed keys to be modified from GUI
        self.cfg["run_mode"] = partial.get("run_mode", self.cfg.get("run_mode", "full"))
        self.cfg["depth"] = int(partial.get("depth", self.cfg["depth"]))
        self.cfg["max_nodes"] = int(partial.get("max_nodes", self.cfg["max_nodes"]))
        self.cfg["rate_limit_rpm"] = int(
            partial.get("rate_limit_rpm", self.cfg["rate_limit_rpm"])
        )
        self.cfg["skip_private_profiles"] = bool(
            partial.get("skip_private_profiles", self.cfg["skip_private_profiles"])
        )
        self.cfg["include_group_links"] = bool(
            partial.get("include_group_links", self.cfg["include_group_links"])
        )
        self.cfg["include_game_overlap"] = bool(
            partial.get("include_game_overlap", self.cfg.get("include_game_overlap", False))
        )
        self.cfg["hub_percentile"] = float(
            partial.get("hub_percentile", self.cfg["hub_percentile"])
        )
        return self.get_config()

    # ----- Presets / Profiles -----
    def apply_preset(self, name: str) -> Dict:
        n = (name or "").lower()
        if n.startswith("inner"):
            self.cfg["depth"] = 1
            self.cfg["max_nodes"] = 300
        elif n.startswith("community"):
            self.cfg["depth"] = 2
            self.cfg["max_nodes"] = 500
        return self.get_config()

    def list_profiles(self) -> List[str]:
        return [p.stem for p in PROFILES.glob("*.yaml")]

    def load_profile(self, name: str) -> Dict:
        path = PROFILES / f"{name}.yaml"
        if not path.exists():
            return self.get_config()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        # Keep only GUI-editable subset
        return self.set_config(
            {
                "run_mode": data.get("run_mode", self.cfg.get("run_mode", "full")),
                "depth": data.get("depth", self.cfg["depth"]),
                "max_nodes": data.get("max_nodes", self.cfg["max_nodes"]),
                "rate_limit_rpm": data.get("rate_limit_rpm", self.cfg["rate_limit_rpm"]),
                "skip_private_profiles": data.get(
                    "skip_private_profiles", self.cfg["skip_private_profiles"]
                ),
                "include_group_links": data.get(
                    "include_group_links", self.cfg["include_group_links"]
                ),
                "include_game_overlap": data.get(
                    "include_game_overlap", self.cfg.get("include_game_overlap", False)
                ),
                "hub_percentile": data.get("hub_percentile", self.cfg["hub_percentile"]),
            }
        )

    def save_profile(self, name: str, subset: Dict) -> bool:
        if not name:
            return False
        path = PROFILES / f"{name}.yaml"
        cfg_subset = self.set_config(subset)  # normalize/validate
        yaml.safe_dump(cfg_subset, path.open("w", encoding="utf-8"), sort_keys=False)
        return True

    # ----- Scan / Estimate -----
    def run_scan(self, payload: Dict) -> Dict:
        """
        payload = { target: "steam id/vanity/url" }
        """
        target = (payload.get("target") or "").strip()
        if not target:
            return {"ok": False, "error": "Target is required."}

        mode = self.cfg.get("run_mode", "full")
        caps = _mode_caps(mode)

        # Steam API
        key = os.getenv("STEAM_API_KEY", "").strip()
        api = SteamAPI(key, rpm=self.cfg["rate_limit_rpm"])

        # Resolve any type of steam identifier
        sid = parse_any_steam_input(target, api)
        if not sid:
            return {"ok": False, "error": "Could not resolve target."}

        out_dir = OUTPUTS / sid / stamp()
        out_dir.mkdir(parents=True, exist_ok=True)
        logger = RunLogger(out_dir / "run.log")
        logger.write(f"Target resolved to SteamID64: {sid}")

        # Scan
        logger.write("Scanning network...")
        state = scan_network(
            api=api,
            seed_steamid=sid,
            depth=self.cfg["depth"],
            rpm=self.cfg["rate_limit_rpm"],
            max_nodes=self.cfg["max_nodes"],
            skip_private=self.cfg["skip_private_profiles"],
            include_group_links=self.cfg["include_group_links"],
            resume_state=None,
        )
        (out_dir / "scan.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
        logger.write("Wrote scan.json")

        nodes_csv = edges_csv = None
        if caps["graphi"]:
            nodes_csv, edges_csv = export_gephi(
                state=state,
                out_dir=out_dir,
                hub_percentile=self.cfg["hub_percentile"],
            )
            logger.write("Wrote graphi files")

        estimates = None
        if caps["estimates"]:
            # internal defaults (not exposed in GUI) for IRL and location calcs
            fopts = FriendProbOpts(top_n_for_mean=5, reasonable_count=50)
            lopts = LocationProbOpts(reasonable_count=100, score_strategy="multiply")
            estimates = build_estimates(state, fopts, lopts)
            (out_dir / "estimates.json").write_text(
                json.dumps(estimates, indent=2), encoding="utf-8"
            )
            logger.write("Wrote estimates.json")

        logger.write("Done.")
        logger.close()

        return {
            "ok": True,
            "outputDir": str(out_dir),
            "nodesCsv": str(nodes_csv) if nodes_csv else None,
            "edgesCsv": str(edges_csv) if edges_csv else None,
            "estimates": estimates,
            "runlog": str(out_dir / "run.log"),
        }

    def dry_run(self, target: str) -> Dict:
        target = (target or "").strip()
        if not target:
            return {"ok": False, "error": "Target is required."}
        key = os.getenv("STEAM_API_KEY", "").strip()
        api = SteamAPI(key, rpm=self.cfg["rate_limit_rpm"])
        sid = parse_any_steam_input(target, api)
        if not sid:
            return {"ok": False, "error": "Could not resolve target."}
        friends = api.get_friend_list(sid)
        return {"ok": True, "seed_friends": len(friends)}

    # ----- API key management -----
    def has_api_key(self) -> Dict:
        """Report whether a Steam API key is present and where it comes from.
        Returns { ok, present, source } where source in { 'file', 'env', 'none' }.
        'file' means .env/.env.example contains a non-placeholder key (persisted),
        'env' means only current environment has the key (not persisted),
        'none' means no key detected.
        """
        source = "none"
        present = False
        # Load files first to prefer persisted keys
        file_key_found = False
        for p in (ENV_PATH, ENV_EXAMPLE_PATH):
            try:
                if p.exists():
                    txt = p.read_text(encoding="utf-8")
                    for ln in txt.splitlines():
                        s = ln.strip()
                        if s.startswith("STEAM_API_KEY="):
                            val = s.split("=", 1)[1].strip().strip("\"'")
                            if val and val != "your_api_key_here":
                                file_key_found = True
                            break
            except Exception:
                pass
        if file_key_found:
            source = "file"
            present = True
        else:
            # Fallback to environment
            _load_env_file()
            if os.getenv("STEAM_API_KEY", "").strip():
                source = "env"
                present = True
        return {"ok": True, "present": present, "source": source}

    def set_api_key(self, key: str) -> Dict:
        key = (key or "").strip().upper()
        if not key:
            return {"ok": False, "error": "Key is empty."}
        # Ensure we operate on .env (rename .env.example if needed)
        try:
            if ENV_EXAMPLE_PATH.exists() and not ENV_PATH.exists():
                # If the example contains placeholder, we will rename it to .env
                ENV_EXAMPLE_PATH.rename(ENV_PATH)
        except Exception:
            # Fallback: ignore rename errors and just write .env below
            pass
        # Write/update .env
        lines: List[str] = []
        existed = ENV_PATH.exists()
        if existed:
            try:
                lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
            except Exception:
                lines = []
        updated = False
        out_lines: List[str] = []
        for ln in lines:
            if ln.strip().startswith("STEAM_API_KEY="):
                out_lines.append(f"STEAM_API_KEY={key}")
                updated = True
            else:
                out_lines.append(ln)
        if not updated:
            out_lines.append(f"STEAM_API_KEY={key}")
        ENV_PATH.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        # Set for current process
        os.environ["STEAM_API_KEY"] = key
        return {"ok": True}

    def validate_api_key(self, key: str) -> Dict:
        """Perform a lightweight call that requires a valid key.
        Returns {ok: True} if accepted, else {ok: False, error: msg}.
        """
        key = (key or "").strip().upper()
        # quick format check first
        import re
        if not re.fullmatch(r"[A-Z0-9]{25,40}", key or ""):
            return {"ok": False, "error": "Invalid key format."}
        try:
            api = SteamAPI(key, rpm=max(1, int(self.cfg.get("rate_limit_rpm", 60))))
            # Known public SteamID64 (any valid one works)
            test_id = "76561197960435530"
            data = api.get_player_summaries([test_id])
            if data and test_id in data:
                return {"ok": True}
            return {"ok": False, "error": "Steam rejected the API key."}
        except Exception:
            return {"ok": False, "error": "Validation call failed."}

    def resolve_target(self, target: str) -> Dict:
        """
        Resolve any Steam identifier to steamid64 and return basic profile info
        for UI verification (personaname and avatar URL).

        Returns: { ok, steamid64, personaname, avatar }
        """
        target = (target or "").strip()
        if not target:
            return {"ok": False, "error": "Target is required."}

        key = os.getenv("STEAM_API_KEY", "").strip()
        if not key:
            return {"ok": False, "error": "Steam API key not set."}

        api = SteamAPI(key, rpm=self.cfg["rate_limit_rpm"])
        sid = parse_any_steam_input(target, api)
        if not sid:
            return {"ok": False, "error": "Could not resolve target."}

        try:
            summaries = api.get_player_summaries([sid])
            info = summaries.get(sid, {})
            name = info.get("personaname") or ""
            avatar = (
                info.get("avatarfull")
                or info.get("avatarmedium")
                or info.get("avatar")
                or ""
            )
            return {"ok": True, "steamid64": sid, "personaname": name, "avatar": avatar}
        except Exception:
            # Fallback to just returning the resolved sid
            return {"ok": True, "steamid64": sid, "personaname": "", "avatar": ""}

    def list_recent(self) -> Dict:
        OUTPUTS.mkdir(parents=True, exist_ok=True)
        targets = sorted([p for p in OUTPUTS.glob("*") if p.is_dir()], key=lambda p: p.name, reverse=True)
        data: List[Dict] = []
        for t in targets:
            runs = sorted([r for r in t.glob("*") if r.is_dir()], key=lambda p: p.name, reverse=True)
            data.append({"steamid64": t.name, "runs": [r.name for r in runs]})
        return {"ok": True, "items": data}

    def open_outputs(self) -> bool:
        try:
            OUTPUTS.mkdir(parents=True, exist_ok=True)
            open_folder(OUTPUTS)
            return True
        except Exception:
            return False

    def open_run(self, steamid64: str, run: str) -> bool:
        try:
            path = OUTPUTS / steamid64 / run
            if path.exists():
                open_folder(path)
                return True
            return False
        except Exception:
            return False


def main() -> None:
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    bridge = Bridge(cfg)
    window = webview.create_window(
        "steam-friends-osint",
        str((UI_DIR / "index.html").as_uri()),
        width=1280,
        height=640,
        resizable=False,
        frameless=True,
        easy_drag=False,
        js_api=bridge,
    )
    # Attach back-reference so JS can call minimize/close via Bridge
    bridge.attach(window)
    # Center window and enforce height tweak on start
    def _center() -> None:
        try:
            # Ensure final size
            window.resize(1280, 640)
            # Try to center on primary screen (Windows)
            x = y = None
            if os.name == "nt":
                try:
                    import ctypes  # type: ignore

                    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
                    sw = int(user32.GetSystemMetrics(0))
                    sh = int(user32.GetSystemMetrics(1))
                    x = max(0, (sw - 1280) // 2)
                    y = max(0, (sh - 700) // 2)
                except Exception:
                    x = y = None
            if x is not None and y is not None:
                window.move(x, y)
                bridge._pos = (x, y)
        except Exception:
            pass

    # EdgeHTML/Chromium on Windows if available; default elsewhere
    webview.start(_center, gui="edgechromium" if os.name == "nt" else None)


if __name__ == "__main__":
    main()