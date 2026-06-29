# Data Center Intelligence Suite

Tracks **data-center value-chain developments and partnerships across India + the GCC**
(Compute / Cooling / Power / Network / Colo / Build), split by *who is speaking*:

| Tab | Source type | Status |
|-----|-------------|--------|
| **SS1 News** | journalists talk about them (RSS firehose) | ✅ live |
| **SS2 Policy** | governments rule on them (think-tanks + India/GCC gov feeds) | ✅ live |
| **SS3 Disclosure** | they talk about themselves (SEC EDGAR full-text) | ✅ live |
| **SS4 OSINT** | footprints (Reddit + Greenhouse/Lever/Adzuna jobs) | ✅ live (add ATS tokens / Adzuna key for volume) |
| **SS5 Ranked** | scored roll-up over SS1–SS4 (BD Framework v3 weights) | ✅ live |

All five worksheets live in **one** Google Sheet ("Datacentre"). Config-driven,
runs entirely on GitHub Actions cron — no servers.

Two scheduled jobs: `dc-news.yml` (SS1, ~every 3h) and `dc-pipeline.yml`
(SS2–SS5, daily).

## DC Hub MCP (live grid / facilities / M&A intelligence)

[`dchub-mcp-server`](https://github.com/azmartone67/dchub-mcp-server) — 51 tools over
21,000+ facilities + live grid telemetry + 2,000+ M&A deals. Enable it for this
project to query DC intelligence interactively:

```bash
claude mcp add --transport http dchub https://dchub.cloud/mcp
```

Then: `/dchub:pick-a-market`, `/dchub:analyze-site`, etc. Free anonymous tier =
10 calls/day; free key (`https://dchub.cloud/signup`) = 50/day. Note its *live grid*
data is US/EU/AU/Taiwan — for India/GCC its value is facilities, M&A, and market intel.
It's the upgrade path for automated SS4 grid/interconnection enrichment.

## Adding a source (the whole workflow)

1. Open `dc_config.py` — the single source registry.
2. Append one line to the right dict/list (a feed URL, an ATS token, a query).
3. Run `python check_dc_sources.py` — confirms every source is live before it ships.

That's it. Dead/blocked sources are kept as commented stubs with the reason.

## Files

| File | Role |
|------|------|
| `dc_config.py` | **the source registry** (feeds, layers, EDGAR/jobs/Reddit configs) — the only file you normally edit |
| `check_dc_sources.py` | one-command validator (live/dead for everything) |
| `dc_ingest.py` | SS1 ingestion: pull feeds, tag layer + geo, scope-filter, dedup |
| `dc_models.py` | MiniLM embeddings + FinBERT sentiment (lazy) |
| `dc_engine.py` | clustering core (pure numpy) — cross-run event linking |
| `dc_sheets.py` | Google Sheets writer (one sheet, named tabs) |
| `dc_state.py` | seen-IDs + cluster state across runs |
| `dc_news.py` | SS1 entry point (`--no-ml`, `--no-sheets` for local smoke tests) |

## Secrets (GitHub → Settings → Secrets)

Public repo — **never** put credentials in code. Set as Actions secrets:

- `GOOGLE_SERVICE_ACCOUNT_JSON` — service-account JSON (share the Datacentre sheet with its email, Editor)
- `DC_SPREADSHEET_ID` — the Datacentre sheet id
- `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` — for SS4 Adzuna (when wired)
- `SEC_USER_AGENT` — "Name email@example.com" for EDGAR (when wired)

## Local run

```bash
pip install -r requirements.txt
python check_dc_sources.py             # validate sources
python dc_news.py --no-ml --no-sheets  # fast, torch-free dry run
DC_SPREADSHEET_ID=... GOOGLE_SERVICE_ACCOUNT_JSON="$(cat sa.json)" python dc_news.py
```
