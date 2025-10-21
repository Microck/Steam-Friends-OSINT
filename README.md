<p align="center">
  <a href="https://github.com/Microck/vapora">
    <img src="assets/vapora.png" alt="vapora Logo" width="600">
  </a>
</p>

<p align="center">an OSINT tool for gathering information on Steam users' friends lists.</p>

<p align="center">
  <a href="https://github.com/Microck/vapora/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/Microck/vapora?style=flat-square" /></a>
  <a href="https://github.com/Microck/vapora/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/Microck/vapora?style=flat-square" /></a>
  <a href="https://github.com/Microck/vapora/issues"><img alt="Issues" src="https://img.shields.io/github/issues/Microck/vapora?style=flat-square" /></a>
</p>

---

## tl;dr

- install python 3.10+
- get a steam api key (free): https://steamcommunity.com/dev/apikey
- `pip install -r requirements.txt`
- `python start.py` → paste key → choose preset → paste steam url → done
- open the folder in gephi (see how‑to below)

---

## features

- blue terminal wizard (reads ascii from `assets/banner.txt`)
- works with steamid64 or profile url (auto vanity resolver)
- safe presets:
  - inner circle (fast) → depth 1, ~200–300 nodes
  - community map (default) → depth 2, ~500 nodes
  - custom → full control with explanations
- dry‑run estimator (samples seed friends to predict node counts)
- resume last run + recent targets menu
- rate‑limit handling, retries, progress bars
- automatic cleaning (no phantom nodes in gephi)
- gephi‑ready exports (no html):
  - `gephi/nodes.csv` | label + metrics
  - `gephi/edges.csv` | `friend` vs `group` edges
  - `probable_friends.csv` | ranked close‑associate guesses
- enrichment for osint:
  - degree (popularity)
  - betweenness centrality (bridges / hubs)
  - modularity class (communities; louvain)
  - “is_hub” flag (top percentile of betweenness)
- cross‑platform; outputs per target with timestamp
- optional packaged exe (pyinstaller) for windows

---

## how it works

1. the wizard collects:
   - steam api key (stores to `.env`; can skip if already set)
   - target (steamid64 or profile url)
   - preset / custom config (depth, caps, rate limit, etc.)
2. scanner hits the steam web api (depth‑limited bfs).
3. cleaner removes dangling edges; keeps `Kind = friend|group`.
4. enricher computes degree, betweenness, modularity, is_hub.
5. probable‑friends analyzer ranks likely close associates.
6. exports gephi csvs + raw scan json into a dated folder.

no scraping; only public web‑api endpoints. private data is skipped.

---

## layout

```
.
├─ start.py                                       # cli wizard
├─ vapora-X.X.X.exe                               # windows executable
├─ .env.example                                   # steam api key placeholder
├─ requirements.txt
├─ assets/
│  └─ banner.txt
├─ vapora/
│  ├─ steam_api.py                                # api wrapper + rate limiting + vanity resolver
│  ├─ scanner.py                                  # bfs crawler (depth, caps, resume)
│  ├─ enricher.py                                 # clean + metrics + gephi csv export
│  ├─ probable_friends.py                         # close-associate ranking
│  ├─ utils.py                                    # helpers (paths, time, io)
│  └─ config_default.yaml                         # defaults with inline docs
├─ profiles/                                      # saved config profiles
├─ outputs/                                       # results
├─ .gitignore
├─ LICENSE
└─ README.md
```

outputs per run:
```
outputs/<steamid64>/<yyyymmdd_hhmmss>/
├─ gephi/
│  ├─ nodes.csv
│  └─ edges.csv
├─ probable_friends.csv
├─ scan.json
└─ run.log
```

---

## installation

prereqs
- python 3.10+
- steam api key: https://steamcommunity.com/dev/apikey

clone + install
```bash
git clone https://github.com/Microck/vapora.git
cd vapora

python -m venv .venv
# windows
.venv\Scripts\activate
# macos/linux
source .venv/bin/activate

pip install -r requirements.txt
```

set your key
- copy `.env.example` → `.env` and paste your key, or
- just run the wizard; it can create `.env` for you

---

## quickstart

```bash
python start.py
```

you’ll see:
- a short tip + link to get your api key
- menu:
  - scan by steamid64
  - scan by profile url (vanity / full)
  - presets (inner circle / community map / custom)
  - config (guided editor with recommended defaults)
  - dry‑run estimate
  - resume last run
  - recent targets
  - run

after the run it asks to open the output folder. the readme below explains
how to import into gephi.

---

## configuration

the wizard shows a one‑liner help for each option and saves your choices to
`profiles/` so you can reuse them later.

defaults (also in `vapora/config_default.yaml`):
```yaml
depth: 2                          # 1 = only friends; 2 = friends of friends, 3 = you get how it goes
max_nodes: 500                    # hard cap; keeps graphs tidy
rate_limit_rpm: 120               # requests per minute
skip_private_profiles: true
include_group_links: true         # group edges (toggle off in gephi if noisy)
include_game_overlap: false
hub_percentile: 0.99              # top 1% betweenness → is_hub=true
weights:                          # probable-friends scoring
  mutual: 1.0
  jaccard: 1.0
  groups: 0.5
  games: 0.5
```

advanced:
- hub threshold is adjustable (percentile) from the wizard “advanced” section.
- profiles can be saved/loaded with a name.

---

## output files schemas

`gephi/nodes.csv`
- Id
- Label
- degree
- betweenness
- modularity_class
- is_seed (true/false)
- is_hub (true/false)
- is_banned (true/false)
- is_public (true/false)

`gephi/edges.csv`
- Source
- Target
- Kind (`friend` | `group`)

`probable_friends.csv` (ranked)
- candidate_steamid
- score
- mutual_count
- jaccard_with_seed
- shared_groups
- shared_games

---

## gephi how‑to (step‑by‑step)

1) open gephi → new project  
2) import `gephi/nodes.csv` as “nodes table”  
3) import `gephi/edges.csv` as “edges table” (undirected, append)  
4) layout → forceatlas 2  
   - scaling 25  
   - linlog ✓  
   - prevent overlap ✓  
   - run 20–30s → stop, then “noverlap” a few seconds  
5) appearance  
   - nodes → partition → `modularity_class` → apply (color communities)  
   - nodes → ranking → `betweenness` → apply (size hubs: 8–50)  
6) optional filter  
   - filters → edges → attributes → partition → `Kind` → select `friend`  
   - toggle `friend` vs `group` to see core friendships vs shared context

---

## probable friends

aim: guess close associates of the seed using public signals:
- mutual friend count with seed (triadic closure)
- neighbor‑set jaccard with seed
- shared groups bonus
- shared games bonus (if public)

weights are tunable in config. the analyzer skips private data silently.

---

## tips for osint in gephi

- start with `Kind = friend` (skeleton); toggle `group` later for context
- “degree range” filter (min 2–3) removes tails and reveals the core
- “k‑core” (k=3→6) finds inner circles (mutually connected cliques)
- gatekeepers: large betweenness nodes between different colors
- leaders: isolate one color (partition filter) then size by degree

---

## troubleshooting

- forbidden / “verify key” → check `.env` contains a valid `STEAM_API_KEY`
- gephi stuck at 0% → lower `max_nodes` (default 500), use `Kind=friend`
- “ghost nodes” → we export clean edges; import nodes first, then edges
- slow scans → reduce `depth`, ensure `rate_limit_rpm` ≥ 60

---


## faq

- does this scrape?  
  no, it uses the official web api; private data is skipped.

- is this allowed?  
  use a legitimate api key and respect rate limits; do not bypass restrictions.

---

## license


mit © microck — see [license](LICENSE)

