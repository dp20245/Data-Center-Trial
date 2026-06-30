"""
dc_mca.py  —  India entity spine via MCA Company Master Data (data.gov.in OGD API).

MCA is an ENTITY SPINE, not a BD trigger (Sheet 7 rule): a signal from SS1-SS4 is
the trigger; MCA resolves a loose company name into a real CIN-backed Indian legal
entity and enriches it. The OGD API has NO fuzzy search (exact company_name match
only), so we try an alias map + a few legal-suffix variants. The snapshot is ~18mo
stale -> great for resolution/enrichment, weak for fresh-incorporation signals.

The CIN string itself is BD-rich: parse_cin() yields listed/unlisted, NIC industry
class, state, incorporation year, and ownership (FTC = foreign subsidiary = a foreign
DC player with confirmed India presence). Reads DATA_GOV_IN_API_KEY. Local file cache
(incl. misses) so we never re-query the same name within/across local runs.
"""
import os
import re
import json
import time
import urllib.request
import urllib.error
import urllib.parse

import dc_config as dc

CACHE_PATH = os.path.join(os.path.dirname(__file__), "mca_cache.json")


class _MCAError(Exception):
    """A query couldn't be completed (429/network) — distinct from a genuine miss."""

# CIN layout (21 chars): [L/U][5 NIC][2 state][4 year][3 ownership][6 reg-no]
_OWNERSHIP = {"PLC": "public", "PTC": "private", "FTC": "foreign-subsidiary",
              "FLC": "foreign-public", "GAP": "guarantee", "GOI": "govt",
              "NPL": "sec8-nonprofit", "SGC": "state-govt", "OPC": "one-person",
              "ULL": "unlimited", "ULT": "unlimited"}
# NIC prefix -> coarse class (validates the resolved entity is genuinely DC/IT/infra).
_NIC_CLASS = [("631", "data-processing/hosting"), ("582", "software-publish"),
              ("72", "IT/software"), ("61", "telecom"), ("351", "power-gen"),
              ("35", "power"), ("42", "construction"), ("41", "construction"),
              ("64", "finance"), ("70", "consulting")]
_ACTIVE = {"active", "actv"}


def parse_cin(cin):
    cin = (cin or "").strip().upper()
    if len(cin) != 21:
        return {"listed": "", "nic_code": "", "nic_class": "", "inc_year": "",
                "ownership": ""}
    nic = cin[1:6]
    nic_class = next((lbl for pre, lbl in _NIC_CLASS if nic.startswith(pre)), "other")
    return {"listed": cin[0] == "L", "nic_code": nic, "nic_class": nic_class,
            "inc_year": cin[8:12], "ownership": _OWNERSHIP.get(cin[12:15], cin[12:15])}


def normalize_status(s):
    s = (s or "").strip().lower()
    if s in _ACTIVE:
        return "active"
    if any(k in s for k in ("strike", "dissolv", "liquidat", "amalgamat", "defunct")):
        return "inactive"
    return s or "unknown"


def load_cache():
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cache(cache):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, separators=(",", ":"))


def _norm(name):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())).strip()


def _query_exact(legal_name):
    """Return the record (hit) or None (genuine empty). Raise _MCAError if the
    request couldn't be completed (429/network) so we don't cache it as a miss."""
    key = os.environ.get("DATA_GOV_IN_API_KEY")
    if not key:
        raise _MCAError("no DATA_GOV_IN_API_KEY")
    url = (f"{dc.MCA_API_BASE}?api-key={key}&format=json&limit=1"
           f"&filters%5Bcompany_name%5D={urllib.parse.quote(legal_name)}")
    delay = 2
    for attempt in range(4):
        try:
            time.sleep(0.4)  # be gentle on OGD
            req = urllib.request.Request(url, headers={"User-Agent": "dc-mca"})
            with urllib.request.urlopen(req, timeout=25) as r:
                recs = json.loads(r.read().decode("utf-8", "ignore")).get("records", [])
            return recs[0] if recs else None
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(delay)
                delay = min(delay * 2, 16)
                continue
            raise _MCAError(f"{legal_name}: HTTP {e.code}")
        except Exception as e:
            raise _MCAError(f"{legal_name}: {e}")
    raise _MCAError(f"{legal_name}: retries exhausted")


def _candidates(name):
    """Alias-mapped exact names first, then base + legal-suffix variants."""
    aliases = dc.MCA_ALIASES.get(name) or dc.MCA_ALIASES.get(name.title()) or []
    if isinstance(aliases, str):
        aliases = [aliases]
    base = name.upper().strip()
    out = []
    for n in list(aliases) + [base] + [f"{base} {sfx}" for sfx in dc.MCA_NAME_SUFFIXES]:
        if n and n not in out:
            out.append(n)
    return out


def resolve(name, cache):
    """Return an entity record dict or None. Caches hits AND misses by normalized name."""
    k = _norm(name)
    if k in cache:
        return cache[k] or None
    rec, errored = None, False
    for cand in _candidates(name):
        try:
            hit = _query_exact(cand)
        except _MCAError as exc:
            print(f"  [mca] {exc}")
            errored = True
            break
        if hit:
            cin = hit.get("corporate_identification_number", "")
            rec = {"cin": cin, "legal_name": hit.get("company_name", ""),
                   "matched_as": cand, "queried_name": name,
                   "status": normalize_status(hit.get("company_status", "")),
                   "status_raw": hit.get("company_status", ""),
                   "state": hit.get("registered_state", ""),
                   "company_class": hit.get("company_class", ""),
                   "category": hit.get("company_category", ""),
                   "paidup_capital": hit.get("paidup_capital", ""),
                   "roc": hit.get("registrar_of_companies", ""),
                   **parse_cin(cin)}
            break
    if not errored:                 # only cache when we actually determined hit/miss
        cache[k] = rec or {}
    return rec


def extract_orgs(text):
    """NER-lite: dictionary NER over signal text using the DC company gazetteer."""
    t = (text or "").lower()
    return [name for name in dc.DC_COMPANY_GAZETTEER
            if re.search(r"\b" + re.escape(name.lower()) + r"\b", t)]


if __name__ == "__main__":
    cache = load_cache()
    for n in ["Sify", "Equinix", "Nxtra", "CtrlS", "Yotta"]:
        r = resolve(n, cache)
        if r:
            print(f"  ✅ {n:8} -> {r['cin']} | {r['status']} | {r['ownership']} | "
                  f"{r['nic_class']} | {r['state']} | {r['inc_year']}")
        else:
            print(f"  ❌ {n:8} unresolved")
    save_cache(cache)
