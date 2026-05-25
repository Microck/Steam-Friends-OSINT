# AI contributor guide for this repo

This project is a Python OSINT tool that maps a Steam user’s friend network, enriches it with graph metrics, and exports Gephi‑ready CSVs plus lightweight "probable friends" and IRL/location estimates.

## Big picture
- Entrypoints
  - `app.py` — primary CLI with modes (full/basic/graphi) and optional SteamHistory support. Saves `scan.json`, exports CSVs, writes `estimates.json`, and logs to `run.log`.
  - `start.py` — simple wizard subset (legacy), focused on scan + Gephi CSVs + probable friends.
  - `gui.py` — optional PyWebView UI that calls Python via a `Bridge` API; static HTML/JS in `ui/` (currently demo‑level wiring).
- Core modules (in `vapora/`)
  - `steam_api.py` — HTTP wrapper + RPM rate limiter; vanity resolver; batched summaries/bans; optional group list.
  - `scanner.py` — breadth‑first crawl up to `depth`, with `max_nodes` cap, producing a serializable `state` dict.
  - `enricher.py` — cleans edges, builds `networkx` graph, computes degree/betweenness/modularity, exports CSVs under `graphi/`.
  - `probable_friends.py` — ranks close associates using mutuals/Jaccard/shared groups; writes `probable_friends.csv`.
  - `irl.py` — IRL friend probability and possible location inference from the scanned network; outputs are embedded in `estimates.json`.
  - `steamhistory.py` — helpers to ingest normalized SteamHistory JSON and derive duration‑based closeness (fallback when network signals are absent).
  - `utils.py` — small helpers (timestamps, open folder, simple file logger).

State contract (produced by `scanner.scan_network` and consumed elsewhere):
- `state = { seed: str, nodes: {steamid: {...}}, edges: [{a,b,type}], visited: [..], queue: [..], meta: {depth} }`
- `nodes[steamid]` contains at least: `friends: [steamid]`, `personaname`, `profileurl`, `is_public`, optional `bans`, `groups`, and location codes.
- `edges[i]` has `a`, `b`, and `type` in `{friend|group}`. `enricher._clean_edges` removes duplicates/dangling edges.

Important repo conventions
- Config source of truth: `vapora/config_default.yaml`. CLI can persist user profiles to `profiles/*.yaml`.
- Output layout: `outputs/<steamid64>/<yyyymmdd_hhmmss>/` containing `scan.json`, `run.log`, optional `estimates.json`, and a `graphi/` folder with `nodes.csv` and `edges.csv`.
  - Note: folder name is `graphi` in code (typo vs README’s "gephi"). Keep code/doc consistent or fix both together.
- Modes gate features (see `app._mode_caps`):
  - `full`: graphi + estimates + SteamHistory fallback
  - `basic`: estimates + SteamHistory only (no CSVs)
  - `graphi`: CSV export only (no estimates/SH)
- Identifiers: Accepts SteamID2/3/64, profile URLs, or vanity; resolve via `ids.parse_any_steam_input` + `SteamAPI.ensure_steam64_from_vanity`.
- Rate limiting: simple in‑process windowed RPM limiter in `steam_api.RateLimiter.wait()` used by every call.

## Developer workflows
- Prereqs: Python 3.10+, a Steam Web API key.
- Setup (Windows PowerShell)
  - Create venv and install deps, then run the CLI:
    - `python -m venv .venv; .venv\Scripts\Activate.ps1; pip install -r requirements.txt; python app.py`
  - On first run, paste `STEAM_API_KEY` when prompted (stored in `.env` next to the script).
  - Quick wizard (legacy): `python start.py`.
- Optional GUI: `gui.py` uses PyWebView; install `pywebview` to use it, then `python gui.py`. The current `ui/app.js` is a demo; the Python `Bridge` is the source of truth for actions.
- Debugging tips
  - Use recent outputs via menu options in CLI, or open the newest run dir under `outputs/`.
  - Inspect `run.log` for step‑by‑step notes (scan, exports, estimates).
  - If APIs look slow/noisy, lower `depth`/`max_nodes`, or raise `rate_limit_rpm` (default 120).

## Extending the tool (patterns)
- New analysis that uses the scanned network:
  - Add a pure function `def analyze(state: Dict, out_dir: Path, **opts) -> Path|Dict` under `vapora/`.
  - Consume the `state` contract above; don’t make new network calls unless necessary.
  - Write results next to existing outputs (e.g., `out_dir / "your_feature.json"`).
  - Wire it in `app.run_scan` and/or `gui.Bridge.run_scan` behind a mode/config flag.
- Exporters: follow `enricher.export_gephi(state, out_dir, hub_percentile)`; keep CSV schemas stable.
- Steam API calls: prefer adding thin wrappers in `SteamAPI` and reuse the existing batching + limiter.

## External dependencies and IO
- HTTP: `requests` to official Web API endpoints only; no scraping.
- Graph/communities: `networkx`, `python-louvain`.
- CLI UX: `questionary`, `rich` (Windows‑safe colors configured), `tqdm` for progress.
- Optional GUI: `pywebview` (not listed in requirements.txt by default).

## Gotchas to know
- Output folder is `graphi/` in code. If the README says `gephi/`, that’s a known mismatch.
- Group links can explode edge count on large public groups; consider toggling `include_group_links` off.
- Private profiles are silently kept with `is_public=False`; group membership lookups are skipped when `skip_private_profiles=true`.
- `requirements.txt` omits `pywebview` (GUI) and `colorama` (used in `start.py`); install them explicitly if needed.

## Handy references
- Examples:
  - BFS scan: `vapora/scanner.py: scan_network(...)`
  - CSV export: `vapora/enricher.py: export_gephi(...)`
  - Probable friends: `vapora/probable_friends.py: compute_probable_friends(...)`
  - IRL estimates + locations: `vapora/irl.py`
  - SteamHistory helpers: `vapora/steamhistory.py`
- Config defaults and flags: `vapora/config_default.yaml`
