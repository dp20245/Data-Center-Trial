# PRD — Data Centre Intelligence Suite, Phase 4: "Signal Engine → BD Product"

**Owner:** Darsh Puri (TAG) · **Repo:** `github.com/dp20245/Data-Center-Trial` · **Sheet:** "Datacentre"
**Version:** 1.0 · **Date:** 2026-07-04 · **Status:** Approved — build in progress
**Inputs:** ChatGPT review (`Feedback.txt`, grade B-/C+/C) + senior feedback + a live-sheet audit
(2026-07-04) that confirmed every defect below. Phases 1–3 shipped & verified.

---

## 1. Background
Across Phases 1–3 the suite became a **correct, legible market-intelligence dashboard**:
- **P1 (correctness):** split legal-entity match vs India-presence vs expansion-stage (killed the
  "no MCA match ⇒ market-entry" bug); Signal Score renamed + explained (G3 guide, per-row
  breakdown); graded geo; unique-event momentum; scoring-version Δ reset.
- **P2 (evidence + pipeline):** Evidence Register (every hash → publisher/headline/URL);
  descriptive links everywhere; BD Pipeline (P1/P2/P3) with grounded, marked `🤖AI-draft:` soft
  columns; GCC Watch.
- **P3 (polish + determinism + MD):** deal-value precision; deterministic RANKING/dossiers (AI
  writes prose only); MD View tab.

## 2. Problem (confirmed on the live sheet, 2026-07-04)
The product answers *"where is the market moving?"* but not TAG's real question: **"who should
TAG approach, why now, and what exactly should TAG pitch?"** Root cause: **every company is
treated as a prospect** with a pitch-like "TAG play". Confirmed defects:
- **No role/type** — Amazon (unreachable anchor), Sify (ecosystem node), AirTrunk (real lead),
  CoreWeave (noise) share one prospect universe.
- **Signal Score ≠ BD priority** — RANKING puts Sify #1; AirTrunk (the better lead) lower.
- **Source noise drives scores** — Evidence Register publishers include Whalesbook, Trade Brains,
  BeBeez, Crypto Briefing, vocal.media, TradingView, Top1 Markets, Veloxx, and a literal
  `"publisher"` placeholder.
- **Policy inflated** — India = **112 items, ALL "regulation"** (0 legislation/analysis); the
  ingest default tags every feed "regulation" and counts market-commentary, corrupting the
  `policy_tailwind` score.
- **Whitespace over-aggressive** — STACK = "India market-entry" with geo **Kuwait; Qatar (no
  India)**; CoreWeave "market-entry" off a BeBeez item (a Sweden deal); Brookfield off *Crypto
  Briefing*.
- *Already fixed (P3):* the AI Summary "1178" filler-cell artifact — now a clean table. STT GDC
  India still resolves to "no MCA entity" (needs an override).

## 3. Thesis to encode
India DC growth is a **power / land / state-policy / partner-selection** problem, not a
cloud-growth story. TAG's wedge:
> "We help data-centre operators, hyperscalers, infrastructure investors, and GCC capital
> navigate India's **state-level power, land, incentive, regulatory, and partner ecosystem** for
> AI infrastructure."

The product must sort by **TAG's realistic ability to help + buyer accessibility**, not news
volume.

## 4. Goals / Non-goals
**Goals:** role + type per company (G1); BD Priority distinct from Signal Score so real leads top
the list (G2); source tiering that down-weights noise (G3); whitespace integrity — no
"market-entry" without a direct India signal (G4); a real policy classifier (G5); a curated
top-10 BD pipeline + AirTrunk/Blackstone cluster (G6); presentation trust incl. STT GDC (G7).
**Non-goals (this phase):** outbound channels (email/CRM); MD/VC deck; moving off the single
Sheet; scraping real buyer contacts (accessibility is a rubric, not contact data).

## 5. Decisions (locked)
- **AI is downgrade-only** — deterministic rules + curated lists own role/type/priority; AI may
  only *downgrade* (flag Noise/Market-signal) or write grounded, marked `🤖AI-draft:` prose,
  never inflate a company into Prospect/P1. **Entity Overrides is the only human upgrade path.**
- **Balanced-slate top-10** — guarantee a portfolio mix (top foreign investor/operator, GCC-to-
  India, Indian partner, + anchor market-signals), not all one type.
- Additive only; Dashboard layout preserved; AI grounded on sheet data; free OpenRouter, cached,
  non-fatal.

## 6. Two-layer model
- **Layer 1 — signal engine (existing):** SS1–SS5, heatmaps, Evidence Register, Signal Score,
  dossiers; gains role/type/source-tier/BD-priority fields.
- **Layer 2 — curated BD pipeline (the deliverable):** ~10 rows a TAG partner can act on.

## 7. Requirements

**R1 — Company role + type** *(new `dc_classify.py`)* — `type` ∈ {Hyperscaler, Indian-operator,
Infra-investor, GCC-operator, Other} from curated lists; `role` ∈ {Prospect, Market-signal,
Partner, Case-study, Noise} from a rule table (Hyperscaler+India-deal ⇒ Market-signal; foreign
operator/investor + direct India signal ⇒ Prospect; Indian-operator ⇒ Partner; JV-only ⇒
Case-study; no direct India signal / T3-only ⇒ Noise). AI may only downgrade ambiguous rows.
*Accept:* Amazon/AWS=Market-signal, AirTrunk/Blackstone/Brookfield=Prospect, Sify/CtrlS=Partner,
Meta=Case-study, CoreWeave/STACK=Noise.

**R2 — Source tiering + confidence** — `SOURCE_TIERS` domain→tier map (T1 SEC/gov/PIB/Reuters/
Bloomberg/FT/Nikkei; T2 DCD/DC Knowledge/ET/Business Standard/Moneycontrol/Livemint/FE; T3
Invezz/TradingView/Stocktwits/BeBeez/Crypto Briefing/Whalesbook/Trade Brains/vocal.media/SEO;
unknown⇒T3). Evidence Register gains `source_tier` (+ fix the `"publisher"` placeholder). Momentum
down-weights T3; all-T3 companies can't exceed P3. *Accept:* Brookfield/CoreWeave (T3) can't be P1.

**R3 — BD Priority Score (multi-factor)** *(`dc_bd`)* — composite from trigger strength · TAG fit ·
buyer accessibility · cross-border · policy exposure · deal size · timing · source confidence.
Output P1/P2/P3/Exclude; **role gates it** (Market-signal/Noise ≠ P1); factor breakdown shown.
*Accept:* AirTrunk/Blackstone > Sify in BD Priority despite lower Signal Score.

**R4 — Whitespace direct-India-signal rule** — never "India market-entry" without ≥1 India-geo
evidence row + real trigger; else "Global AI infra — monitor for India" / "GCC-to-India
adjacency" / "Investor/platform lead" / "No India action yet". *Accept:* STACK & CoreWeave =
monitor, not market-entry.

**R5 — Policy re-classification** *(`dc_ingest`)* — keyword classifier into {law/regulation,
govt-scheme/incentive, state-DC-policy, power/open-access, land/env/water, data-localization/
DPDP/cyber, market-commentary}; only genuine classes feed `policy_tailwind`; heatmap excludes
commentary. *Accept:* forecast/market-size pieces ⇒ commentary, excluded from score.

**R6 — Curated top-10 + clustering** *(`dc_md`)* — MD View becomes `Priority | Account | Type |
Trigger | TAG wedge | Buyer | Access path | Next action`, **balanced** across types + BD Priority;
AirTrunk+Blackstone one clustered row; Meta↔Reliance a case-study note; Amazon an anchor signal.
Buyer/Access/Next are `🤖AI-draft:`. *Accept:* ≤10 rows, balanced mix, cluster merged.

**R7 — Entity fixes** — seed Entity Overrides with STT GDC India (+ known-good); AI Summary stays
artifact-free.

## 8. Delivery sub-phases
- **4a Legibility core:** R1 + R4 + R7 (new `dc_classify.py`).
- **4b Trust inputs:** R2 + R5.
- **4c Actionability:** R3 + R6.
Each: build → offline self-checks → live CI + `inspect_sheet` readback → scope-guard subagent
(additive; Dashboard preserved) → commit.

## 9. Success metrics
Every operator has role+type; nothing reads as a pitch unless role=Prospect; BD Priority ≠ Signal
Score (AirTrunk>Sify, with a visible breakdown); source_tier on every evidence row (T3-only ⇒
≤P3); zero bad "market-entry" labels; policy count reflects genuine classes only; a
senior-review-ready balanced top-10 (AirTrunk/Blackstone #1, Amazon=signal); STT GDC corrected;
all existing tabs populate; Dashboard layout intact.

## 10. Constraints (unchanged)
Public repo; creds = GitHub Secrets. Free OpenRouter Nemotron; grounded on sheet data; cached;
non-fatal; AI cells marked `🤖AI-draft:`. Config-as-registry (extend lists/maps in one line).
Read the live sheet only via `gh workflow run inspect.yml` (service-account creds are CI-only).

---

## Addendum — AI-boundary carve-out (agreed 2026-07-07)

The SS3 multi-signal judge (`dc_ai.judge_filings`) is an **extraction/filter**
AI: it may only drop passages or label them from the `SIGNAL_LABELS` registry,
with every returned quote substring-verified against its source passage. This
sits *within* the "AI is downgrade-only" rule: labeling/filtering evidence can
reduce, never inflate, a company's role or priority. Only deterministic rules
(`dc_classify`, `dc_bd`) may raise role/priority, and only Entity Overrides may
override them upward by human hand.
