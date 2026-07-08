# Data-Centre Pre-Announcement Sources PRD

**Verified:** 6 July 2026  
**Geography:** India, UAE, Saudi Arabia, Qatar, Bahrain, Kuwait and Oman  
**Purpose:** Detect data-centre developments and announced partnerships using verified pre-announcement signals.

## Existing Sheets

- **SS1:** News and discovery sources.
- **SS2:** Government, policy, incentives and regulatory activity.
- **SS3:** Corporate disclosures, CAPEX and supplier announcements.
- **SS4:** Leading indicators such as jobs, permits and ecosystem footprints.
- **SS5:** Corroborated and ranked developments.

## Credentials

```bash
ALPHAVANTAGE_API_KEY=<supplied-and-verified>
CURRENTS_API_KEY=<supplied-and-verified>
DATA_GOV_IN_API_KEY=<supplied-and-verified>
```

The build must read these from environment variables. Credential values must never be stored in code, logs, URLs or Sheets.

# 1. Supply Chain and Logistics

## 1.1 Vendor Footprints

| Verified source | Access | Sheet fit |
|---|---|---|
| UAE MOIAT industrial licences | [`GetIndustrialLicensesList`](https://api.moiat.gov.ae/api/OpenDataAPI/GetIndustrialLicensesList?LanguageId=2&PageNumber=1&PageSize=10) | Daily vendor/factory footprint signals. Paginate in groups of 10 and match product names and HS codes for cooling, electrical, UPS, batteries, transformers and prefabricated facilities. — `[SS4]` |
| PeeringDB India facilities | [API](https://www.peeringdb.com/api/fac?country=IN&limit=1000) | Weekly facility and operator presence enrichment. — `[SS4]` |
| PeeringDB GCC facilities | [API](https://www.peeringdb.com/api/fac?country__in=AE%2CSA%2CQA%2CBH%2CKW%2COM&limit=1000) | Weekly regional facility footprint enrichment. — `[SS4]` |
| PeeringDB regional exchanges | [API](https://www.peeringdb.com/api/ix?country__in=IN%2CAE%2CSA%2CQA%2CBH%2CKW%2COM&limit=1000) | Weekly network and interconnection ecosystem enrichment. — `[SS4]` |
| Wikidata | `https://query.wikidata.org/sparql?query={SPARQL}&format=json` | Resolve aliases, parents, subsidiaries, websites and geographic identifiers. — `[SS4-enrichment]` |
| India MCA company data | `https://api.data.gov.in/resource/ec58dab7-d891-4abb-936e-d5d274a6ce9b?api-key=${DATA_GOV_IN_API_KEY}&format=json&offset={OFFSET}&limit={LIMIT}` | Resolve Indian companies, registration state, status and registered address. — `[SS4-enrichment]` |

PeeringDB and entity records must never independently create an SS5 development.

## 1.2 Customs and Port Data

No production source is admitted.

- UN Comtrade returned no records across the tested India equipment queries and lacks buyer, supplier and shipment identities.
- Panjiva has no suitable free public API.
- Customs and port intelligence remains an explicit project gap.
- Do not implement placeholder Comtrade ingestion.

## 1.3 Manufacturing Localization

Use MOIAT product descriptions and HS codes to identify equipment manufactured inside the UAE. Use MCA company data to resolve Indian manufacturers.

This provides partial localization evidence but does not establish component origin or compliance with local-content mandates. Store it as contextual SS4 evidence only.

# 2. Regulatory and Government Filings

## 2.1 Environmental and Zoning Approvals

| Verified source | Access | Sheet fit |
|---|---|---|
| India PARIVESH | [Main portal](https://parivesh.nic.in/) | Daily page monitor for environmental, forest, wildlife and CRZ proposals. — `[SS4]` |
| PARIVESH searchable portal | [Search](https://cpc.parivesh.nic.in/) | Search tracked companies, project names, districts and data-centre terminology. — `[SS4]` |

State pollution-control boards, SEZ land records, municipal zoning and GCC environmental approvals remain future gaps.

## 2.2 Subsidies, Grants and Government Announcements

| Verified source | Access | Sheet fit |
|---|---|---|
| India PIB | [Latest releases](https://www.pib.gov.in/index.aspx?lang=1&reg=1) | Daily page monitor for infrastructure schemes, incentives, approvals and government partnerships. — `[SS2]` |
| Qatar News Agency | [Economy RSS](https://qna.org.qa/en/Pages/RSS-Feeds/Economy-Local) | Hourly monitoring of Qatar investments and state-backed projects. Parse the XML body despite its `text/html` content type. — `[SS2]` |
| Oman News Agency | [Economy RSS](https://www.omannews.gov.om/rss.ona?rsslang=en&cat=80&limit=100) | Hourly monitoring of Oman investment and government-project announcements. — `[SS2]` |

The previously supplied PIB RSS URL must not be used because it currently returns an empty feed.

## 2.3 Technology, Patents and JV Approvals

| Verified source | Access | Sheet fit |
|---|---|---|
| Competition Commission of India | [Combination orders](https://www.cci.gov.in/combination/orders-section31) | Daily page monitor for acquisitions, combinations and joint ventures involving tracked companies. — `[SS4]` |

PATENTSCOPE does not provide a universal public feed. Patent monitoring remains deferred until a WIPO account and targeted saved-query feeds are configured.

# 3. People Signals

## 3.1 Executive and Specialist Hiring

| Verified source | Access | Sheet fit |
|---|---|---|
| AirTrunk | [Greenhouse API](https://boards-api.greenhouse.io/v1/boards/airtrunk/jobs?content=true) | Daily India/GCC permitting, government-relations, construction, power and procurement roles. — `[SS4]` |
| Submer | [Greenhouse API](https://boards-api.greenhouse.io/v1/boards/submer/jobs?content=true) | Daily cooling, BIM, engineering and data-centre procurement roles. — `[SS4]` |
| Together AI | [Greenhouse API](https://boards-api.greenhouse.io/v1/boards/togetherai/jobs?content=true) | Daily India GPU infrastructure and deployment roles. — `[SS4]` |

Future company boards may use:

```text
https://api.lever.co/v0/postings/{validated_company_slug}?mode=json
https://api.ashbyhq.com/posting-api/job-board/{validated_board_name}?includeCompensation=false
```

Do not activate Lever or Ashby until a real tracked-company board identifier has returned jobs successfully. Do not scrape LinkedIn.

## 3.2 Lobbying Disclosures

No production lobbying source is admitted.

US LDA and FARA records are too indirect for routine India/GCC development detection. Lobbying remains a documented coverage gap and must not receive a placeholder adapter.

# 4. CAPEX and Supplier Disclosures

## 4.1 Earnings-Call Subtext

| Verified source | Access | Sheet fit |
|---|---|---|
| Alpha Vantage | `https://www.alphavantage.co/query?function=EARNINGS_CALL_TRANSCRIPT&symbol={TICKER}&quarter={YYYY}Q{N}&apikey=${ALPHAVANTAGE_API_KEY}` | Daily during earnings periods. Extract India/GCC CAPEX, capacity, construction, leasing, RFP, energy-risk and partnership language. — `[SS3]` |
| SEC filing search | [EDGAR full-text API](https://efts.sec.gov/LATEST/search-index?q=%22data%20center%22&forms=8-K%2C6-K%2C10-K%2C10-Q%2C20-F) | Every four hours for multinational commitments and material contracts. — `[SS3]` |
| SEC company submissions | `https://data.sec.gov/submissions/CIK{PADDED_CIK}.json` | Track new filings for the operator and supplier watchlists. — `[SS3]` |

Use a descriptive User-Agent for SEC requests.

## 4.2 Supplier Contracts and Press Releases

| Verified source | Access | Sheet fit |
|---|---|---|
| Equinix | [Press-release RSS](https://investor.equinix.com/news-events/press-releases/rss) | Operator developments and partnerships. — `[SS3]` |
| NVIDIA | [Press-release RSS](https://nvidianews.nvidia.com/cats/press_release.xml) | GPU infrastructure, sovereign-AI and partner announcements. — `[SS3]` |
| PR Newswire Technology | [RSS](https://www.prnewswire.com/rss/business-technology-latest-news/business-technology-latest-news-list.rss) | Supplier and contractor announcement discovery. — `[SS3]` |
| PR Newswire Energy | [RSS](https://www.prnewswire.com/rss/energy-latest-news/energy-latest-news-list.rss) | Power, cooling and energy-contract discovery. — `[SS3]` |
| Boursa Kuwait | [Disclosure RSS](https://rss.boursakuwait.com.kw/rss/FeedFull.aspx) | Kuwait listed-company investments, contracts and partnerships. — `[SS3]` |
| Currents | `https://api.currentsapi.services/v2/search` | India news discovery only. GCC results remain experimental and require strict geographic validation. — `[SS1]` |

Currents should search for data-centre terms plus construction, expansion, partnership, investment and contract language. Accept only results whose title, description or article text explicitly contains a target location.

# 5. Promotion Rules

- SS4 footprints, jobs and permits remain leading indicators.
- News aggregators and PR wires are discovery sources, not standalone confirmation.
- Promote a record to SS5 only when it names a company or partnership, identifies an India/GCC location, and describes a concrete development action.
- Promotion requires one government/regulatory/official-company source or two independent secondary sources.
- Capture partners, city, site, stage, capacity MW, CAPEX and target date whenever available.
- Deduplicate using normalized URL, title, companies, geography and publication date.

# 6. Explicit Exclusions

Do not build active adapters for:

- MODON API: currently blocked by its web-application firewall.
- UN Comtrade: tested queries returned no usable records.
- PIB RSS: valid XML but empty.
- Currents country filters for Bahrain and Oman: unsupported.
- Panjiva: paid and no suitable public API.
- LinkedIn scraping.
- Etimad, ZATCA or PATENTSCOPE until a producing endpoint or account-specific feed is verified.
