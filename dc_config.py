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

# ===========================================================================
# 11. PHASE 4 REGISTRIES  (approved PRD 2026-07-04 — see docs/PHASE4_PRD.md)
# ===========================================================================
# All registries below are INERT until their consumer milestone lands (config-as-
# registry discipline: extend any list/map in one line). AI BOUNDARY (locked):
# deterministic rules + curated lists own role/type/priority; AI may only DROP or
# LABEL evidence, flag Noise/Market-signal downgrades, or write grounded
# 🤖AI-draft prose. Entity Overrides is the only human upgrade path.

# --- Shared signal taxonomy -------------------------------------------------
# ONE vocabulary consumed by (a) the SS3 multi-signal judge (menu; off-menu labels
# are dropped in code), (b) R1 role rules ("direct India signal" = direct_action
# AND region India), (c) R3 BD trigger-strength (trigger_weight × recency decay).
# label: (trigger_weight 0-1, direct_action, description-for-judge-prompt)
SIGNAL_LABELS = {
    "capex-commitment":     (1.0, True,  "committed capital expenditure for a DC build"),
    "capacity-commitment":  (1.0, True,  "MW/GW or sqft data-centre capacity commitment"),
    "land-acquisition":     (0.9, True,  "land purchase/allotment for a DC site"),
    "acquisition":          (0.9, True,  "M&A of a DC operator/asset"),
    "jv-partnership":       (0.8, True,  "JV/partnership/MoU for DC development"),
    "market-entry-intent":  (0.7, True,  "stated intent to enter a market"),
    "expansion-existing":   (0.7, True,  "expansion of an existing facility"),
    "energy-procurement":   (0.6, True,  "PPA/captive power/grid deal for a DC"),
    "customer-contract":    (0.5, True,  "colocation/cloud capacity contract"),
    "financing":            (0.5, True,  "debt/equity raise earmarked for DC"),
    "regulatory-engagement":(0.4, False, "license/approval/incentive application"),
    "hiring-buildout":      (0.3, False, "DC-ops hiring signal"),
    "risk-disclosure":      (0.1, False, "risk-factor mention of the region"),
    "boilerplate-mention":  (0.0, False, "incidental mention — drop from scoring"),
}
# Deterministic bridge: SS1/SS3 keyword deal_type -> SIGNAL_LABELS key (so news
# events and filings feed R3 trigger-strength through one vocabulary).
DEAL_TYPE_TO_LABEL = {
    "JV": "jv-partnership", "partnership": "jv-partnership",
    "acquisition": "acquisition", "supply-agreement": "customer-contract",
    "capex": "capex-commitment", "facility-expansion": "expansion-existing",
}

# --- R1: company type (curated; role comes from the dc_classify rule table) --
COMPANY_TYPES = {
    "Hyperscaler":     ["AWS", "Amazon", "Microsoft", "Google", "Meta", "Oracle"],
    "Indian-operator": WATCH_OPERATORS_INDIA + ["Web Werks", "Pi Datacenters", "ESDS",
                        "Tata Communications", "Reliance", "Yotta"],
    "Infra-investor":  ["Blackstone", "Brookfield", "GIC", "Keppel", "KKR", "Macquarie",
                        "Kotak"],
    "GCC-operator":    WATCH_OPERATORS_GCC + ["G42"],
    # Foreign operators/platforms default to "Other" unless listed above; dc_classify
    # treats "Other"+foreign as operator/platform for the Prospect rule.
}

# --- R2: source tiering (domain OR publisher-name -> tier; unknown => T3) ----
# T1 = primary/official/wire-of-record. T2 = credible trade/business press.
# T3 = SEO/retail/aggregator noise. Momentum weights applied in dc_score (M3).
SOURCE_TIERS = {
    # T1 — official / primary / global wire
    "sec.gov": "T1", "pib.gov.in": "T1", "eprocure.gov.in": "T1", "data.gov.in": "T1",
    "reuters.com": "T1", "bloomberg.com": "T1", "ft.com": "T1", "nikkei.com": "T1",
    "apnews.com": "T1", "peeringdb.com": "T1", "sttelemediagdc.com": "T1",
    "equinix.com": "T1", "nvidia.com": "T1", "qna.org.qa": "T1", "omannews.gov.om": "T1",
    "sebi.gov.in": "T1", "boursakuwait.com.kw": "T1", "parivesh.nic.in": "T1",
    "cci.gov.in": "T1", "moiat.gov.ae": "T1",
    # T2 — credible trade/business press
    "datacenterdynamics.com": "T2", "datacenterknowledge.com": "T2",
    "datacenterfrontier.com": "T2", "economictimes.indiatimes.com": "T2",
    "indiatimes.com": "T2", "business-standard.com": "T2", "moneycontrol.com": "T2",
    "livemint.com": "T2", "financialexpress.com": "T2", "hindustantimes.com": "T2",
    "thehindu.com": "T2", "medianama.com": "T2", "theregister.com": "T2",
    "blocksandfiles.com": "T2", "prnewswire.com": "T2", "cset.georgetown.edu": "T2",
    # T3 — noise (explicit; anything unknown also resolves to T3)
    "whalesbook.com": "T3", "tradebrains.in": "T3", "bebeez.it": "T3",
    "cryptobriefing.com": "T3", "vocal.media": "T3", "tradingview.com": "T3",
    "invezz.com": "T3", "stocktwits.com": "T3",
}
SOURCE_TIER_DEFAULT = "T3"
SOURCE_TIER_MOMENTUM_WEIGHTS = {"T1": 1.0, "T2": 0.8, "T3": 0.3}

# --- R5: policy classes (keyword classifier; first match wins; default =
# market-commentary which is EXCLUDED from policy_tailwind + heatmap) ----------
POLICY_CLASSES = {
    "state-DC-policy":       ["data centre policy", "data center policy", "dc policy",
                              "state incentive", "maharashtra", "uttar pradesh", "telangana",
                              "tamil nadu", "andhra pradesh", "odisha", "gujarat",
                              "west bengal", "karnataka", "haryana"],
    "power-open-access":     ["open access", "wheeling", "transmission", "tariff",
                              "electricity duty", "captive power", "ppa", "discom",
                              "distribution license"],
    "land-env-water":        ["land allotment", "land subsidy", "zoning", "environment",
                              "environmental clearance", "water", "crz", "parivesh"],
    "data-localization-dpdp":["data localisation", "data localization", "dpdp",
                              "data protection", "cybersecurity", "cert-in", "meity rules"],
    "govt-scheme-incentive": ["pli", "scheme", "subsidy", "incentive", "grant",
                              "mission", "budget allocation"],
    "law-regulation":        ["bill", "act", "amendment", "notification", "gazette",
                              "regulation", "sebi", "trai", "ordinance"],
    # default class (no keywords — assigned when nothing above matches):
    "market-commentary":     [],
}
POLICY_GENUINE_CLASSES = [k for k in POLICY_CLASSES if k != "market-commentary"]

# --- R3: BD Priority factor weights + cutoffs (consumed by dc_bd in M7) ------
# Composite 0-100; role gates: Noise=>Exclude, Market-signal/Case-study<=P3, all-T3<=P3.
BD_FACTORS = {
    "trigger_strength":  0.25,  # max SIGNAL_LABELS weight over verified signals × recency
    "tag_fit":           0.15,  # role/type/stage rubric — TAG's realistic ability to help
    "buyer_access":      0.15,  # accessibility rubric by company type
    "cross_border":      0.10,  # foreign->India / GCC->India motion
    "policy_exposure":   0.10,  # genuine policy classes relevant to layer/geo/state
    "deal_size":         0.10,  # deal_value buckets merged with fee-viability scale
    "timing":            0.10,  # recency of last signal
    "source_confidence": 0.05,  # T1 share of the evidence mix
}
BD_PRIORITY_CUTOFFS = {"P1": 65, "P2": 40}   # >=P1 cut => P1, >=P2 cut => P2, else P3

# --- Fee-viability inputs (computed ONLY for role Prospect/Partner, ~5-20 rows) ---
# Backer scale: named backers/parents that clear TAG's fee bar on their own.
BACKER_SCALE = {
    "mega-fund":   ["Blackstone", "Brookfield", "GIC", "KKR", "Macquarie", "Keppel",
                    "Kotak", "Mubadala", "ADIA", "PIF"],
    "hyperscaler": ["AWS", "Amazon", "Microsoft", "Google", "Oracle", "Meta"],
    "platform":    ["AirTrunk", "Vantage", "STACK Infrastructure", "EdgeConneX",
                    "Princeton Digital", "Digital Realty", "Equinix", "NTT", "G42"],
}
FEE_VIABILITY_DEAL_USD = {"high": 500_000_000, "medium": 50_000_000}  # deal_value buckets

# --- R7: Entity Overrides seed rows (appended once if absent; humans own the tab) ---
# company -> (entity_match, india_presence, expansion_stage, note)
PRESET_OVERRIDES = {
    "STT GDC India": ("matched", "established", "scaling",
                      "Operates 30+ India DCs; Chennai Siruseri 4th DC + INR 4,200 cr TN MoU (Feb 2026)"),
}

# --- R6: MD View curation ----------------------------------------------------
CLUSTER_ACCOUNTS = {   # accounts presented as ONE clustered MD View row
    "AirTrunk": {"with": "Blackstone", "label": "AirTrunk + Blackstone (platform + sponsor)"},
}
CASE_STUDY_NOTES = {   # role=Case-study framing notes (never pitched as prospects)
    "Meta": "Meta↔Reliance JV — case-study of hyperscaler+Indian-partner structure, not a prospect",
    "Amazon": "Anchor market-signal — validates India DC demand; not an accessible buyer",
}

# --- SS3 overhaul constants (M4; fetch/scoping constants live in section 5) ---
EDGAR_DOC_CAP        = 16_000_000  # bytes; fetch cap for inline-XBRL 20-Fs (multi-MB)
KWIC_WORDS           = EDGAR_SIGNAL_WORDS  # alias: ±words around each DC-term hit
MAX_SIGNALS_PER_FILING = 12        # judge returns at most this many labeled signals
KWIC_DEDUP_COSINE    = 0.90        # semantic near-dupe threshold (dc_models.embed)

# --- M6: India state intelligence --------------------------------------------
STATE_BANK_PATH = "knowledge/india_state_bank.md"   # source of truth (verbatim, sourced)
STATE_BANK_STALE_DAYS = 90                          # warn when "Checked:" older than this
CITY_STATE_MAP = {
    "mumbai": "Maharashtra", "navi mumbai": "Maharashtra", "pune": "Maharashtra",
    "visakhapatnam": "Andhra Pradesh", "vizag": "Andhra Pradesh",
    "chennai": "Tamil Nadu", "siruseri": "Tamil Nadu", "ambattur": "Tamil Nadu",
    "hosur": "Tamil Nadu", "thoothukudi": "Tamil Nadu",
    "hyderabad": "Telangana",
    "noida": "Uttar Pradesh", "greater noida": "Uttar Pradesh", "lucknow": "Uttar Pradesh",
    "kanpur": "Uttar Pradesh", "varanasi": "Uttar Pradesh", "agra": "Uttar Pradesh",
    "ghaziabad": "Uttar Pradesh",
    "dholera": "Gujarat", "gift city": "Gujarat", "ahmedabad": "Gujarat",
    "kolkata": "West Bengal", "new town": "West Bengal",
    "bengaluru": "Karnataka", "bangalore": "Karnataka", "mangaluru": "Karnataka",
    "mysuru": "Karnataka",
    "gurugram": "Haryana", "gurgaon": "Haryana", "manesar": "Haryana",
    "bhubaneswar": "Odisha", "khurda": "Odisha", "cuttack": "Odisha",
    "shimla": "Himachal Pradesh", "kangra": "Himachal Pradesh",
}

# --- Sheet header freeze (append-only discipline; offline migration test) -----
# dc_export self-check compares live writer headers against these frozen lists.
# APPEND new columns at the END and update here in the same PR; any insert or
# rename fails the self-check BEFORE a live write.
EXPECTED_HEADERS = {}  # populated by dc_export._selfcheck from the writer modules (M1)
