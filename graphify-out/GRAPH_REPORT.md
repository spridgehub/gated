# Graph Report - /Users/ianspridgeon/projects/gated  (2026-11-16)

## Corpus Check
- Corpus is ~8,015 words - fits in a single context window. You may not need a graph.

## Summary
- 84 nodes · 153 edges · 6 communities
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 7 edges (avg confidence: 0.63)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Gated|Gated]]
- [[_COMMUNITY_Gated 2|Gated 2]]
- [[_COMMUNITY_Gated 3|Gated 3]]
- [[_COMMUNITY_Gated 4|Gated 4]]
- [[_COMMUNITY_Github|Github]]
- [[_COMMUNITY_Gated 5|Gated 5]]

## God Nodes (most connected - your core abstractions)
1. `Handler` - 14 edges
2. `Browser` - 8 edges
3. `clean_url()` - 8 edges
4. `txt()` - 8 edges
5. `url_ok()` - 7 edges
6. `config()` - 7 edges
7. `num()` - 7 edges
8. `check_cars()` - 6 edges
9. `auto_allowed()` - 6 edges
10. `parse()` - 6 edges

## Surprising Connections (you probably didn't know these)
- `Cars field (filled in by the site)` --semantically_similar_to--> `Car field (filled in by the site Log button)`  [INFERRED] [semantically similar]
  .github/ISSUE_TEMPLATE/group.yml → .github/ISSUE_TEMPLATE/log-update.yml
- `check_cars()` --calls--> `auto_allowed()`  [EXTRACTED]
  gated/daily.py → gated/fetch.py
- `check_cars()` --calls--> `Browser`  [EXTRACTED]
  gated/daily.py → gated/fetch.py
- `check_in_background()` --indirect_call--> `check_cars()`  [INFERRED]
  gated/server.py → gated/daily.py
- `add_car()` --calls--> `num()`  [EXTRACTED]
  gated/ingest.py → gated/server.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Gated tracker issue-form pipeline** — _github_issue_template_config_tracker_site, _github_issue_template_config, _github_issue_template_add_car, _github_issue_template_group, _github_issue_template_log_update [INFERRED 0.75]

## Communities (6 total, 0 thin omitted)

### Community 0 - "Gated"
Cohesion: 0.16
Nodes (13): auto_allowed(), Browser, host_is_public(), _int(), _jsonld(), _meta(), parse(), Read a listing page the way a visitor's browser would: once, in headless Chrome, (+5 more)

### Community 1 - "Gated 2"
Cohesion: 0.18
Nodes (14): url_ok(), add_car(), car_id(), fields(), gh(), group(), Apply crew requests filed as GitHub issues (the site's Add / Log / Group buttons, Issue-form bodies are '### Label' headings each followed by the answer. (+6 more)

### Community 2 - "Gated 3"
Cohesion: 0.29
Nodes (5): BaseHTTPRequestHandler, log(), Handler, num(), txt()

### Community 3 - "Gated 4"
Cohesion: 0.24
Nodes (7): Export the tracker to docs/data.json for the static GitHub Pages site., check_cars(), Daily check of every tracked listing. Off unless data/config.json has "auto_chec, check_in_background(), config(), main(), Gated: a shared tracker for UK analogue supercars.  Anyone with the link can loo

### Community 4 - "Github"
Cohesion: 0.20
Nodes (11): add-car issue form, Car model dropdown (add-car form), add-car issue label, Issue template config, Gated tracker site (spridgehub.github.io/gated), group issue form, Cars field (filled in by the site), group issue label (+3 more)

### Community 5 - "Gated 5"
Cohesion: 0.31
Nodes (9): connect(), now_iso(), SQLite store: cars friends add, groups that link them, and one snapshot per car, Run fn(con) under the process-wide write lock and commit., Upsert today's snapshot. A manual entry is never overwritten by an automatic one, record_snapshot(), state(), today() (+1 more)

## Knowledge Gaps
- **5 isolated node(s):** `Issue template config`, `Car model dropdown (add-car form)`, `add-car issue label`, `group issue label`, `log-update issue label`
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Handler` connect `Gated 3` to `Gated 4`?**
  _High betweenness centrality (0.090) - this node is a cross-community bridge._
- **Why does `Browser` connect `Gated` to `Gated 4`?**
  _High betweenness centrality (0.067) - this node is a cross-community bridge._
- **Why does `url_ok()` connect `Gated 2` to `Gated`, `Gated 3`, `Gated 4`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **What connects `Export the tracker to docs/data.json for the static GitHub Pages site.`, `Daily check of every tracked listing. Off unless data/config.json has "auto_chec`, `SQLite store: cars friends add, groups that link them, and one snapshot per car` to the rest of the system?**
  _20 weakly-connected nodes found - possible documentation gaps or missing edges._