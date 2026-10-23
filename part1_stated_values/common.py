"""
Shared helpers for Part 1.

All network calls to the Wayback Machine go through `polite_get`, which
(1) waits between requests, (2) retries with exponential backoff on
errors / HTTP 429 / 5xx, and (3) identifies us with a User-Agent.
The Internet Archive throttles aggressive clients, so being slow is
cheaper than being blocked.
"""
import re
import time
from pathlib import Path

import pandas as pd
import requests

# ---- Paths (everything is relative to the repository root) -------------
REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
RAW_DIR = DATA / "raw" / "wayback"          # cached HTML snapshots
PROCESSED = DATA / "intermediate"           # intermediate files and caches
OUTPUTS = DATA / "outputs"                  # final datasets and results
COMPANIES_CSV = DATA / "companies.csv"
URLS_CSV = Path(__file__).parent / "url_candidates.csv"

# ---- Study window ----------------------------------------------------
YEARS = list(range(2016, 2025))   # 2016..2024 inclusive = 9 time points
TARGET_MMDD = "0701"              # pick the snapshot closest to 1 July each year

# ---- HTTP settings ---------------------------------------------------
HEADERS = {"User-Agent": "RA-assignment-research-scraper (academic use)"}
SLEEP_BETWEEN = 1.5   # seconds between requests
MAX_RETRIES = 5
RATE_LIMIT_WAIT = 60  # seconds per attempt after an HTTP 429

# ---- Snapshots rejected by later steps ---------------------------------
# Steps 2 and 3 record captures that turned out unusable; step 1 skips them
# on the next run and falls back to the next-closest capture or the next
# candidate URL (run_part1.py repeats this until nothing new is rejected).
#   scope "capture":  only this capture is bad (e.g. a transient error page)
#   scope "url_year": this URL is unusable for the whole year (page gone,
#                     JavaScript shell), so move to the next candidate URL
EXCLUSIONS_CSV = PROCESSED / "part1_excluded_snapshots.csv"
EXCLUSION_COLS = ["ticker", "year", "candidate_url", "timestamp", "scope", "reason"]
CAPTURE_SCOPE = {"soft_404", "redirect_out_of_year"}
URL_YEAR_SCOPE = {"http_404", "redirected_to_homepage", "js_rendered_shell", "no_prose"}


def load_exclusions():
    if not EXCLUSIONS_CSV.exists():
        return pd.DataFrame(columns=EXCLUSION_COLS)
    return pd.read_csv(EXCLUSIONS_CSV, dtype={"timestamp": str})


def record_exclusions(rows):
    """Add rejected snapshots (dicts with ticker/year/candidate_url/timestamp/
    reason); returns how many were new."""
    def rejected(reason):      # any HTTP error status (404, 403, 410, ...) means the page is gone
        return reason in CAPTURE_SCOPE | URL_YEAR_SCOPE or str(reason).startswith("http_")

    new = pd.DataFrame([{**r, "scope": "capture" if r["reason"] in CAPTURE_SCOPE else "url_year"}
                        for r in rows if rejected(r["reason"])],
                       columns=EXCLUSION_COLS)
    old = load_exclusions()
    both = pd.concat([old, new.astype({"timestamp": str})]) \
        .drop_duplicates(["candidate_url", "timestamp", "scope"])
    # a second bad capture of the same URL in the same year: stop trying
    # captures one by one and move on to the next candidate URL
    caps = both[both.scope == "capture"]
    repeated = caps[caps.duplicated(["candidate_url", "year"], keep=False)] \
        .drop_duplicates(["candidate_url", "year"], keep="last") \
        .assign(scope="url_year", reason=lambda d: "repeated_" + d.reason)
    both = pd.concat([both, repeated]).drop_duplicates(["candidate_url", "timestamp", "scope"])
    both.to_csv(EXCLUSIONS_CSV, index=False)
    return len(both) - len(old)


def sentences(text):
    """Split clean page text into sentences / lines worth comparing."""
    parts = re.split(r"(?<=[.!?])\s+|\n+", str(text))
    return [p.strip() for p in parts if len(p.strip()) > 25]


def sentence_diff(old, new):
    """Sentences only in the old text, and only in the new text (in page order)."""
    a, b = sentences(old), sentences(new)
    sa, sb = set(a), set(b)
    removed = list(dict.fromkeys(s for s in a if s not in sb))
    added = list(dict.fromkeys(s for s in b if s not in sa))
    return removed, added


_session = requests.Session()
_session.headers.update(HEADERS)


def polite_get(url, params=None, allow_redirects=True, timeout=60):
    """GET with a pause before every call and exponential backoff on failure.

    Returns the `requests.Response` or raises the last exception after
    MAX_RETRIES attempts.
    """
    last_err = None
    rate_limited = False
    for attempt in range(MAX_RETRIES):
        # after a 429 the Archive expects a long pause; short retries can
        # escalate to a temporary IP block
        wait = RATE_LIMIT_WAIT * attempt if rate_limited else \
            SLEEP_BETWEEN * (2 ** attempt if attempt else 1)
        time.sleep(wait)
        try:
            r = _session.get(url, params=params, timeout=timeout,
                             allow_redirects=allow_redirects)
            # 429 = rate limited, 5xx = archive hiccup -> retry
            if r.status_code == 429 or r.status_code >= 500:
                rate_limited = r.status_code == 429
                last_err = RuntimeError(f"HTTP {r.status_code}")
                continue
            return r
        except requests.RequestException as e:
            last_err = e
    raise last_err
