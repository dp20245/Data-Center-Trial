"""
dc_config.py  —  THE source registry. The only file you normally edit.

Add a source  ->  append one line to the right dict/list below.
Validate it   ->  `python check_dc_sources.py`  (prints live/dead for everything).
Nothing else needs to change.

Layout mirrors the TAG engine's config.py: feeds + keyword buckets + thresholds.
The engine ("config" shim) treats each value-chain LAYER as a "sector", so the
proven clustering/sentiment code runs unchanged.

All statuses below were HTTP-verified 2026-06-29 (PRD sources + Codex SOURCE_CATALOG.md).
Dead/blocked sources are kept as commented stubs so we remember why they're out.
"""

# ===========================================================================
# 1. SS1 — NEWS FEEDS  (direct publisher RSS; highest volume)
# ===========================================================================
DC_NEWS_FEEDS = {
    # --- Specialist DC trade press (all ✅ verified) ---
    "Data Center Dynamics":  "https://www.datacenterdynamics.com/en/rss/",
    "Data Center Knowledge": "https://www.datacenterknowledge.com/rss.xml",
    "Data Center Frontier":  "https://www.datacenterfrontier.com/__rss/website-scheduled-content.xml?input=%7B%22sectionAlias%22%3A%22home%22%7D",
    "Blocks & Files":        "https://blocksandfiles.com/feed/",
    "The Register":          "https://www.theregister.com/headlines.atom",
    # --- India trade/IT press (✅ verified this session) ---
    "DataCentreNews India":  "https://datacentrenews.in/feed",
    "DataCenterNews Asia":   "https://datacenternews.asia/feed",
    "Express Computer":      "https://www.expresscomputer.in/feed/",
    # --- Press wires (✅ verified 2026-06-29) — geo-filter keeps India/GCC only ---
    "PR Newswire Tech":      "https://www.prnewswire.com/rss/business-technology-latest-news/business-technology-latest-news-list.rss",
    "PR Newswire Energy":    "https://www.prnewswire.com/rss/energy-latest-news/energy-latest-news-list.rss",
    "GNews BusinessWire":    "https://news.google.com/rss/search?q=site:businesswire.com+%28%22data+center%22+OR+datacentre%29+%28India+OR+UAE+OR+Saudi+OR+Qatar+OR+GCC%29+when:7d&hl=en",
    # --- ET Data Centers vertical (DC-native, India-aware; ✅ 10 feeds live 2026-07-02) ---
    #     policy-land-power routes to SS2 (see DC_POLICY_FEEDS); the other 9 land here.
    "ET DC Top":             "https://datacenters.economictimes.indiatimes.com/rss/topstories",
    "ET DC Recent":          "https://datacenters.economictimes.indiatimes.com/rss/recentstories",
    "ET DC Investments":     "https://datacenters.economictimes.indiatimes.com/rss/investments-deals",
    "ET DC Cloud/Colo":      "https://datacenters.economictimes.indiatimes.com/rss/cloud-colocation-connectivity",
    "ET DC AI/Compute":      "https://datacenters.economictimes.indiatimes.com/rss/ai-compute-infrastructure",
    "ET DC Energy/Cooling":  "https://datacenters.economictimes.indiatimes.com/rss/energy-cooling-sustainability",
    "ET DC Construction":    "https://datacenters.economictimes.indiatimes.com/rss/construction-site-development",
    "ET DC Operations":      "https://datacenters.economictimes.indiatimes.com/rss/operations-resilience",
    "ET DC Market Insights": "https://datacenters.economictimes.indiatimes.com/rss/market-insights-analysis",
    # --- India publisher RSS (✅ verified 2026-07-02; geo/DC filter trims to India DC) ---
    "ET Telecom":            "https://telecom.economictimes.indiatimes.com/rss/topstories",
    "ETCIO":                 "https://cio.economictimes.indiatimes.com/rss/topstories",
    "Moneycontrol Business": "https://www.moneycontrol.com/rss/business.xml",
    # --- Foreign-hyperscaler investment discovery (GNews, NO when: — returns empty w/ it) ---
    "GNews India Investment": "https://news.google.com/rss/search?q=India+data+center+investment&hl=en-IN&gl=IN&ceid=IN:en",
    "GNews Foreign Players":  "https://news.google.com/rss/search?q=%28Blackstone+OR+AirTrunk+OR+G42+OR+Microsoft+OR+AWS+OR+Google+OR+Oracle+OR+CoreWeave+OR+%22Digital+Realty%22+OR+Brookfield%29+India+%28data+centre+OR+data+center%29&hl=en-IN&gl=IN&ceid=IN:en",
    "GNews Hyperscale India": "https://news.google.com/rss/search?q=hyperscale+India+data+centre&hl=en-IN&gl=IN&ceid=IN:en",
    # <-- ADD A NEWS FEED: "Name": "https://.../feed",
    # Available but noisy (firehose): PRN all releases
    #   https://www.prnewswire.com/rss/news-releases-list.rss
    # Business Standard topic RSS: DROPPED — Akamai 403 to scripts (Google News geo covers it).
    # Business Wire: no stable RSS (redirects to newsroom) → discover via GNews site query below.
}

# ===========================================================================
# 2. SS1 — GEO DISCOVERY  (one Google News query per market; ID-rot immune)
# ===========================================================================
# Per Codex rule: never combine markets into one feed. Each query is scoped to
# DC + development verbs so the noise filter has something to bite on.
_GNEWS = ("https://news.google.com/rss/search?q=%28%22data+center%22+OR+datacentre%29"
          "+%28{q}%29+%28partnership+OR+%22joint+venture%22+OR+launch+OR+expansion"
          "+OR+campus+OR+MW%29+when:7d&hl=en&gl={gl}&ceid={gl}:en")
DC_GNEWS_GEO = {
    "GNews India":   _GNEWS.format(q="India", gl="IN"),
    "GNews UAE":     _GNEWS.format(q="UAE", gl="AE"),
    "GNews Saudi":   _GNEWS.format(q="%22Saudi+Arabia%22", gl="SA"),
    "GNews Qatar":   _GNEWS.format(q="Qatar", gl="QA"),
    "GNews Bahrain": _GNEWS.format(q="Bahrain", gl="BH"),
    "GNews Kuwait":  _GNEWS.format(q="Kuwait", gl="KW"),
    "GNews Oman":    _GNEWS.format(q="Oman", gl="OM"),
}

# ===========================================================================
# 3. LAYERS  (value-chain layer -> trigger keywords, lowercase, whole-word)
# ===========================================================================
# This is the engine's "SECTORS". An article is tagged to the layer it matches
# most. PRD §1 buckets, expanded. ponytail: single best-layer per article for
# v1 (PRD allows multi-value; add a multi-tag pass only if review needs it).
LAYERS = {
    "Compute": [
        "nvidia", "amd", "tsmc", "broadcom", "gpu", "accelerator", "hbm",
        "wafer", "h100", "h200", "b200", "blackwell", "ai chip", "asic",
        "semiconductor", "fab", "foundry", "inference", "training cluster",
        "cerebras", "supercomputer", "sovereign ai", "sovereign compute",
    ],
    "Cooling": [
        "vertiv", "liquid cooling", "immersion cooling", "immersion", "submer",
        "liquidstack", "asetek", "nvent", "cdu", "rear door", "chiller",
        "direct-to-chip", "free cooling", "pue",
    ],
    "Power": [
        "ups", "smr", "nuscale", "oklo", "grid", "ppa", "genset", "schneider",
        "substation", "interconnection", "megawatt", " mw ", "power purchase",
        "energy procurement", "transmission", "diesel generator", "battery storage",
        "nuclear", "solar", "captive power",
    ],
    "Network": [
        "subsea cable", "submarine cable", "interconnect", "equinix fabric",
        "peering", "dark fiber", "dark fibre", "ix", "internet exchange",
        "backbone", "transit", "landing station",
    ],
    "Colo": [
        "equinix", "digital realty", "ntt", "stt", "adaniconnex", "yotta",
        "ctrls", "princeton digital", "sify", "nxtra", "khazna", "moro hub",
        "gulf data hub", "center3", "edgnex", "ooredoo", "colocation", "colo",
        "hyperscale", "aws", "azure", "google cloud", "oracle cloud", "meta",
    ],
    "Build": [
        "campus", "land bank", "construction", "epc", "ground-break",
        "groundbreaking", "site selection", "greenfield", "build-out",
        "facility expansion", "new facility", "capacity addition",
    ],
}

# ===========================================================================
# 4. SS2 — POLICY  (extra feeds beyond the leg_* stack; routed to SS2)
# ===========================================================================
# Think-tank analysis (type:analysis) + India/GCC government wires. GCC
# regulators (TDRA/CST/WAM/SPA/KUNA) expose NO usable RSS -> Google News proxy.
DC_POLICY_FEEDS = {
    "CSET Georgetown":           "https://cset.georgetown.edu/feed/",         # analysis ✅
    # "Takshashila Technopolitik": substack/feed now 301s to a profile page (dead since 2026-06-25).
    #   -> covered by GNews policy queries; re-add if the publication exposes a working feed again.
    "PIB India":                 "https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=1",
    "SEBI":                      "https://www.sebi.gov.in/sebirss.xml",
    "Boursa Kuwait":             "https://rss.boursakuwait.com.kw/rss/FeedFull.aspx",
    "Oman News Agency Economy":  "https://www.omannews.gov.om/rss.ona?rsslang=en&cat=80&limit=100",
    # --- India DC policy (✅ verified 2026-07-02) ---
    "ET DC Policy/Land/Power":   "https://datacenters.economictimes.indiatimes.com/rss/policy-land-power",
    "MediaNama":                 "https://www.medianama.com/feed/",
    "MediaNama Data Localisation": "https://www.medianama.com/tag/data-localisation/feed/",
    "GNews India DC Policy":     "https://news.google.com/rss/search?q=India+data+centre+policy&hl=en-IN&gl=IN&ceid=IN:en",
    "GNews Data Localisation":   "https://news.google.com/rss/search?q=data+localisation+India+DPDP&hl=en-IN&gl=IN&ceid=IN:en",
    "GNews DC State Incentive":  "https://news.google.com/rss/search?q=India+data+centre+policy+state+incentive&hl=en-IN&gl=IN&ceid=IN:en",
    # QUARANTINED (auto-skipped at runtime, kept for memory):
    # "Qatar News Agency": "https://qna.org.qa/en/Pages/RSS-Feeds/Economy-Local",  # 404 (path dead)
    # "Bahrain News Agency": "https://api.bna.bh/rss/business",                    # 502 (server down)
}
# Oman blocks generic HTTP clients -> we always send a browser User-Agent (see check_dc_sources).
POLICY_GNEWS_GEO = {
    # GCC regulator/market policy where no RSS exists. Same per-market rule.
    "GNews UAE Policy":   _GNEWS.format(q="UAE+%28TDRA+OR+regulation+OR+free+zone%29", gl="AE"),
    "GNews Saudi Policy": _GNEWS.format(q="%22Saudi+Arabia%22+%28CST+OR+regulation+OR+cloud%29", gl="SA"),
}

# ===========================================================================
# 5. SS3 — CORPORATE DISCLOSURE  (primary source)
# ===========================================================================
# SEC EDGAR full-text search: free JSON, NO key. Requires a descriptive
# User-Agent set via the SEC_USER_AGENT env var (e.g. "Name email@x.com").
EDGAR_FTS_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_FORMS   = "8-K,6-K,10-K,20-F"
# FTS ANDs terms and ignores OR/parens, so we run one phrase query per market.
EDGAR_GEO_TERMS = ['"data center" India', '"data center" UAE',
                   '"data center" "Saudi Arabia"', '"data center" Qatar',
                   '"data centre" India']
# --- Evidence-extraction taxonomy (Sheet 7 pattern: find DC term near geo near action) ---
# Geo terms reuse dc_ingest.GEO_KEYWORDS. These drive the evidence window + matched_terms.
DC_TERMS = ["data center", "data centre", "datacenter", "datacentre",
            "hyperscale", "colocation", "colo ", "server farm", "campus"]
# Polished 2026-07-06: dropped over-broad "facility"/"plant"/"capacity" (they matched
# pipe plants, corporate campuses, generic capacity talk); kept "new facility". "acquisition"
# stays but only counts when it lands inside the DC-anchored window (SPAC "Acquisition Corp"
# names in boilerplate no longer qualify a row on their own).
ACTION_TERMS = ["invest", "investment", "capex", "capital expenditure", "expand",
                "expansion", "new facility", "construct", "construction",
                "megawatt", " mw ", "partnership", "joint venture", " jv ",
                "mou", "memorandum of understanding", "acquisition", "acquire",
                "supply agreement", "ground-break"]
# Ordered: first match wins as deal_type (most specific first).
DEAL_TYPE_TERMS = [
    ("joint venture", "JV"), (" jv ", "JV"),
    ("acquisition", "acquisition"), ("acquire", "acquisition"),
    ("supply agreement", "supply-agreement"),
    ("capital expenditure", "capex"), ("capex", "capex"),
    ("partnership", "partnership"), ("mou", "partnership"),
    ("memorandum of understanding", "partnership"),
    ("expansion", "facility-expansion"), ("new facility", "facility-expansion"),
    ("facility", "facility-expansion"), ("construction", "facility-expansion"),
]
EDGAR_EVIDENCE_WINDOW = 500   # chars: DC↔geo↔action proximity for keyword "high" confidence
EDGAR_AI_WHOLE_WORDS = 50000  # AI context budget: send the whole search-region to the judge at
                              # or under this size; above it, window. Set high on purpose —
                              # pure-play DC operators (e.g. Sify) saturate the ENTIRE 20-F Item
                              # 3-5 block (~41k words) with data-center content, so a small window
                              # drops ~85% of it (incl. the Item 4 facility descriptions). Nemotron
                              # 128k ctx + no token cap → send the whole block, don't clip. Only a
                              # genuinely enormous region falls through to windowing.
EDGAR_SIGNAL_WORDS = 30       # KWIC: words of context each side of a DC keyword hit; overlapping
                              # catches merge, so this self-scales (dense 20-F → paragraphs, lone
                              # 8-K mention → ~60 words). The passage list is what the judge labels.
EDGAR_MAX_DOCS = 25           # fetch+parse the N most-recent hits per run (perf cap)

# Evidence section prioritization (2026-07-06): a filing mentions "data center" in many
# places; prefer intentional forward-looking prose. The extractor scans sections in THIS
# order and anchors on the first Risk-Factors/Growth hit before falling back to Other, so a
# country-list in an exhibit never wins over a real risk/growth passage. (regex on lowered
# section headers; label lands in the SS3 `section` column and is told to the AI judge.)
EDGAR_SECTION_PRIORITY = [
    ("Risk Factors", r"item\s+1a\.?\s+risk factors|item\s+3\.?\s*d\.?\s*[-—]?\s*risk factors|(?<![a-z])risk factors(?![a-z])"),
    ("Growth Outlook", r"and prospects|growth strateg|business strateg|(?<![a-z])our strategy|future outlook|(?<![a-z])outlook(?![a-z])|opportunit|(?<![a-z])guidance(?![a-z])"),
    ("Business", r"item\s+4\.?\s+information on the company|management.s discussion|(?<![a-z])business overview|item\s+1\.?\s+business"),
]
# Poll these CIKs' submissions feeds directly (data.sec.gov/submissions/CIK##########.json):
EDGAR_CIKS = {
    "Equinix":        "0001101239",
    # <-- ADD: "Digital Realty": "0001297996", "NTT": "...", "Vertiv": "...", etc. (look up real CIKs)
}
# IR / wire RSS where a company exposes one (per-company; add as found):
IR_FEEDS = {
    # "Some Operator IR": "https://.../rss",
}
# Named operators to watch via Google News, then confirm on their newsroom (SS3 evidence):
WATCH_OPERATORS_INDIA = ["CtrlS", "Nxtra", "STT GDC India", "Yotta", "AdaniConneX", "Sify", "NTT"]
WATCH_OPERATORS_GCC   = ["Khazna", "Moro Hub", "Gulf Data Hub", "center3", "EDGNEX", "Ooredoo"]
# Non-Indian hyperscalers / investors building DC infra in India — the senior's #1 BD
# target (foreign co entering/growing in India). Scored + flagged is_foreign in SS5.
WATCH_OPERATORS_FOREIGN = ["Blackstone", "AirTrunk", "G42", "Microsoft", "AWS", "Amazon",
                           "Google", "Meta", "Oracle", "CoreWeave", "Digital Realty",
                           "Equinix", "Brookfield", "GIC", "Keppel", "Princeton Digital",
                           "STACK Infrastructure", "Vantage", "EdgeConneX", "Colt", "RMZ"]

# ===========================================================================
# 6. SS4 — OSINT / LEADING INDICATORS
# ===========================================================================
# (a) Job postings — public ATS JSON, no key.
#     Greenhouse: https://boards-api.greenhouse.io/v1/boards/{token}/jobs
#     Lever:      https://api.lever.co/v0/postings/{token}?mode=json
#     Tokens must be the company's REAL ATS slug (verify each; many hyperscalers
#     use Workday and won't be here). Add only confirmed-working tokens.
GREENHOUSE_TOKENS = [
    # "digitalrealty",  # verify before adding
]
LEVER_TOKENS = [
    # "somecompany",
]
# (b) Adzuna keyword/geo search — free, needs ADZUNA_APP_ID + ADZUNA_APP_KEY env.
#     country code -> search query. Broad India/GCC coverage.
ADZUNA_QUERIES = {
    "in": "data centre engineer",
    # Adzuna has NO GCC countries (ae/sa/qa all 404) — India only. ✅ verified: 'in'
    # returns ~268 "data centre engineer" hits. GCC hiring signal needs another source.
}
# (c) Reddit subreddit RSS — free, no key.
REDDIT_FEEDS = {
    "r/datacenter": "https://www.reddit.com/r/datacenter/.rss",
    "r/aws":        "https://www.reddit.com/r/aws/.rss",
    "r/india":      "https://www.reddit.com/r/india/.rss",
    "r/dubai":      "https://www.reddit.com/r/dubai/.rss",
    "r/saudiarabia": "https://www.reddit.com/r/saudiarabia/.rss",
    # search-as-feed (.rss form — feedparser-compatible; .json is not):
    "r/datacenter?India": "https://www.reddit.com/r/datacenter/search.rss?q=India+colocation&restrict_sr=1&sort=new",
    # <-- ADD a subreddit: "r/name": "https://www.reddit.com/r/name/.rss",
}
# (c2) CPPP India tenders — auth-free "latest active tenders" listing (search form is
#      CAPTCHA-walled; the ?page=N listing is not). Keyword pre-filter, then AI triage.
#      signal_type=tender, confidence=med, geo=India. ✅ verified 2026-07-01.
CPPP_TENDER_URL   = "https://eprocure.gov.in/cppp/latestactivetendersnew/cpppdata?page={page}"
CPPP_TENDER_PAGES = 10           # ~10 rows/page => ~100 newest tenders scanned/day
TENDER_KEYWORDS   = ["data cent", "colocation", "server farm", "cooling", "ups system",
                     "it park", "hyperscale", "cloud data"]
# (c3) OSM Overpass — free, no key (needs a real UA; default UA 406s). Building-centric
#      facilities complement PeeringDB. India telecom=data_center is NOISY, so keep only
#      building=data_center / operator-tagged / gazetteer-matched. signal_type=facility-presence, med.
OVERPASS_URL = "https://overpass-api.de/api/interpreter"    # POST body data=<query> (GET 406s)
OVERPASS_ISO = {"India": "IN", "UAE": "AE", "Saudi Arabia": "SA", "Qatar": "QA",
                "Bahrain": "BH", "Kuwait": "KW", "Oman": "OM"}
# (d) PeeringDB — free JSON, no key. Facility + internet-exchange presence (Network/Colo).
#     ✅ verified: 245 India facs, 59 GCC facs, 54 IXs. Confirms PRESENCE, not a new
#     development (signal_type=facility-presence, confidence=high). One-time census, then deduped.
PEERINGDB_FAC_URLS = {
    "India": "https://www.peeringdb.com/api/fac?country=IN&limit=1000",
    "GCC":   "https://www.peeringdb.com/api/fac?country__in=AE%2CSA%2CQA%2CBH%2CKW%2COM&limit=1000",
}
PEERINGDB_IX_URL = "https://www.peeringdb.com/api/ix?country__in=IN%2CAE%2CSA%2CQA%2CBH%2CKW%2COM&limit=1000"

# (e) GDELT — no-key JSON, but hard rate-limited (≤1 req/5s, often 429).
#     DAILY BACKFILL ONLY, never the hourly path. Throttle hard.
GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_QUERY   = '"data center" (India OR UAE OR "Saudi Arabia" OR Qatar OR Bahrain OR Kuwait OR Oman)'

# ===========================================================================
# 6b. REGISTERED — validated, not yet wired (each needs a connector; build next)
# ===========================================================================
# India power/capacity context (CEA, free JSON, no key). ✅ live. Macro context, NOT
# per-development rows — wire as enrichment/reference, keep out of the SS4 firehose.
# renewable_energy.php returns malformed data → excluded.
CEA_APIS = {
    "installed_capacity_statewise": "https://cea.nic.in/api/installed_capacity_statewise.php",
    "psp_peak":                     "https://cea.nic.in/api/psp_peak.php",
    "transmission_lines":           "https://cea.nic.in/api/transmission_lines.php",
    "transformation_substations":   "https://cea.nic.in/api/transformation_substations.php",
}
# Entity spine (for SS5 NER, future): GLEIF legal identity (free, no key, paginated).
GLEIF_LEI_SEARCH = "https://api.gleif.org/api/v1/lei-records?filter%5Bentity.legalName%5D={name}&page%5Bsize%5D=10"
# India entity spine — MCA Company Master Data via data.gov.in (needs DATA_GOV_IN_API_KEY env).
DATA_GOV_IN_API_PAGE = "https://www.data.gov.in/apis/ec58dab7-d891-4abb-936e-d5d274a6ce9b"
# DC Hub facility enrichment — MANUAL/optional only. MCP is 10/day; this backend REST
# answered with no auth (count+data) but is an undocumented internal URL — do not auto-pull.
DCHUB_BACKEND_FAC = "https://dchub-backend-production.up.railway.app/api/v1/facilities?country={cc}&limit=20"
# Deferred (validated-and-rejected for v1): Hacker News Algolia (India≈Indiana noise),
# Bluesky/Mastodon (403 / noisy — wait for curated handles), regulations.gov NEPA (US scope),
# eProcurement portals (no stable API).
# ponytail: DEFERRED OSINT (build when jobs+Adzuna+Reddit prove SS4 earns its keep):
#   - Twitter/X handles  (no free API; needs X key or stable nitter mirror)
#   - Interconnection queues / power filings (LBNL Excel, National Grid CSV) — Cloudflare-blocked to curl
#   - Tender portals (eprocure.gov.in, Etimad, Monaqasat, ...) — portal monitors, not feeds
#   - Satellite / construction trackers (highest cost)

# ===========================================================================
# 7. THRESHOLDS / LIFECYCLE  (consumed by the copied engine via config.py shim)
# ===========================================================================
EVENT_MATCH_THRESHOLD = 0.55
TREND_MATCH_THRESHOLD = 0.60
CLUSTER_THRESHOLD     = 0.60
MIN_SOURCES_FOR_EVENT  = 3
MIN_ARTICLES_FOR_EVENT = 5
MIN_SPAN_HOURS         = 24
TREND_TTL_HOURS        = 48
EVENT_ACTIVE_HOURS     = 48
EVENT_DORMANT_DAYS     = 7
SEEN_ARTICLE_TTL_DAYS  = 14
MAX_MEMBERS_STORED     = 60
SENTIMENT_POS_CUTOFF = 0.15
SENTIMENT_NEG_CUTOFF = -0.15

# ===========================================================================
# 8. WORKSHEET (TAB) NAMES  — fixed contracts in the ONE "Datacentre" sheet.
# ===========================================================================
# Renaming a tab or reordering its header silently breaks the writer.
SS1_NEWS_TAB    = "SS1 News"
SS2_POLICY_TAB  = "SS2 Policy"
SS3_DISCLOSE_TAB = "SS3 Disclosure"
SS4_OSINT_TAB   = "SS4 OSINT"
SS5_RANKED_TAB  = "SS5 Ranked"
ENTITIES_TAB    = "Entities"        # CIN-keyed India company spine; SS5 links by CIN
DASHBOARD_TAB   = "Dashboard"       # computed heatmaps + whitespace + emphasis (no AI)
AI_SUMMARY_TAB  = "AI Summary"      # Nemotron narrative, grounded + cached

# ===========================================================================
# 10. DASHBOARD + AI SUMMARY
# ===========================================================================
# Heatmap markets (country-level; matches the geo column values). Layers reuse LAYERS.
MARKETS = ["India", "UAE", "Saudi Arabia", "Qatar", "Bahrain", "Kuwait", "Oman"]
# OpenRouter (OpenAI-compatible). Free Nemotron, 1M context. Reads OPENROUTER_API_KEY.
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
DC_AI_MODEL     = "nvidia/nemotron-3-super-120b-a12b:free"
AI_MAX_TOKENS   = 4000              # 11 per-company dossiers need room (reasoning is OFF; one call/run)

# 6-month horizon (senior ask): code-side date cutoff for discovery feeds. Google News
# `when:6m` silently returns empty, so we filter by article date instead.
RECENT_MONTHS = 6

# Bump when the Signal Score formula changes -> dashboard resets the Δ baseline so
# deltas across formula versions aren't shown as real movement.
SCORING_VERSION = "v2"   # v2: graded geo (India 1.0/GCC 0.5) + unique-event momentum
ENTITY_OVERRIDES_TAB = "Entity Overrides"
EVIDENCE_TAB    = "Evidence Register"   # every hash -> readable, clickable record
BD_PIPELINE_TAB = "BD Pipeline"         # actionable India opportunities (P1/P2/P3)
GCC_WATCH_TAB   = "GCC Watch"           # GCC-only operators, out of the India pipeline
MD_VIEW_TAB     = "MD View"             # curated P1/P2 top-slice for leadership
# Companies KNOWN to already operate in India (established presence) — prevents the
# "no MCA match => market-entry" misclassification (Codex: AWS/Google/MS/Meta/AirTrunk
# are established; their play is expansion/partnership, not entry). One line to extend.
KNOWN_INDIA_PLAYERS = [
    "AWS", "Amazon", "Google", "Microsoft", "Meta", "Oracle", "AirTrunk", "Equinix",
    "CtrlS", "STT GDC", "STT GDC India", "NTT", "Sify", "Nxtra", "AdaniConneX",
    "Yotta", "Web Werks", "Digital Realty", "Princeton Digital", "Reliance",
    "Tata Communications", "Pi Datacenters", "ESDS", "Nvidia",
]
# NewsData.io — India DC news (key via NEWSDATA_API_KEY secret; non-fatal if absent).
# Use qInTitle (not q) + country=in for precision. ✅ verified 2026-07-02.
NEWSDATA_URL     = "https://newsdata.io/api/1/latest"
NEWSDATA_QUERIES = ["data centre", "colocation", "hyperscale"]

# ===========================================================================
# 9. MCA — India entity spine (data.gov.in OGD API). Enrichment, NOT a trigger.
# ===========================================================================
# Company Master Data: 4.06M companies, exact company_name match only (no fuzzy),
# snapshot ~Dec-2024 (stale -> resolution good, fresh-incorporation signal weak).
# Reads DATA_GOV_IN_API_KEY env. See dc_mca.py.
MCA_API_BASE = "https://api.data.gov.in/resource/ec58dab7-d891-4abb-936e-d5d274a6ce9b"
# Legal-suffix variants tried when the exact name is unknown (cheap, exact queries).
MCA_NAME_SUFFIXES = [
    "PRIVATE LIMITED", "LIMITED", "INDIA PRIVATE LIMITED",
    "TECHNOLOGIES PRIVATE LIMITED", "TECHNOLOGIES LIMITED",
    "DATA SERVICES PRIVATE LIMITED", "DATACENTERS PRIVATE LIMITED",
    "DATA CENTRES PRIVATE LIMITED", "DATA LIMITED", "INFRA PRIVATE LIMITED",
]
# Verified exact legal names (✅ probed). Add one line per operator as resolved.
MCA_ALIASES = {
    "Sify":    "SIFY TECHNOLOGIES LIMITED",
    "Equinix": "EQUINIX INDIA PRIVATE LIMITED",   # FTC = foreign subsidiary
    "Nxtra":   "NXTRA DATA LIMITED",
    # <-- ADD: "Operator": "EXACT MCA LEGAL NAME",
}
# Dictionary-NER gazetteer: known DC value-chain companies to spot in SS1-SS4 text
# and resolve into the Entities spine (the "some NER" layer; spaCy NER is the upgrade).
DC_COMPANY_GAZETTEER = sorted(set(WATCH_OPERATORS_INDIA + WATCH_OPERATORS_GCC + [
    "Digital Realty", "Princeton Digital", "Web Werks", "Pi Datacenters", "ESDS",
    "Tata Communications", "Reliance", "Nvidia", "AMD", "TSMC", "Vertiv",
    "Schneider", "Microsoft", "Amazon", "Google", "Oracle", "Meta",
] + WATCH_OPERATORS_FOREIGN))
