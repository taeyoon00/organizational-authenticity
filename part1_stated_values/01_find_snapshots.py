"""
Step 1: find which archived snapshots exist (Wayback CDX API).

Input : data/companies.csv, part1_stated_values/url_candidates.csv
Output: data/intermediate/part1_snapshot_index.csv
        one row per company-year with the chosen snapshot (or why none).

Selection rule (documented in DECISIONS.md, D-004):
  * For each company, candidate URLs are tried in `priority` order.
  * Within a year, we keep snapshots with HTTP status 200 (or 3xx, which
    are followed in step 2) and choose the one closest to 1 July.
  * The first candidate URL (in priority order) with an HTTP 200 capture
    in that year wins; only if no candidate has a 200 capture is the first
    candidate with a redirect capture used. A dead URL that left only
    redirects therefore does not block a live lower-priority page. A
    company can switch URL across years when its site was restructured.
  * If no candidate has any snapshot in that year -> row kept with
    missing_reason = "no_snapshot_in_year". We never borrow a snapshot
    from another year, so every row is a true observation of that year.
"""
import json
from datetime import datetime

import pandas as pd

from common import (COMPANIES_CSV, URLS_CSV, PROCESSED, YEARS, TARGET_MMDD,
                    load_exclusions, polite_get)

CDX = "https://web.archive.org/cdx/search/cdx"
CACHE = PROCESSED / "cdx_cache"     # raw CDX answers, so reruns are free


def query_cdx(url):
    """Return all captures of `url` in 2016-2024 as a list of dicts.

    Results are cached to disk as JSON, keyed by the URL.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / (url.replace("/", "_").replace(":", "_") + ".json")
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    params = {
        "url": url,
        "from": str(YEARS[0]),
        "to": str(YEARS[-1]),
        "output": "json",
        "fl": "timestamp,original,statuscode,mimetype,digest",
        # keep only 200 and redirect captures; drop 404s and errors
        "filter": "statuscode:[23]..",
        # at most one capture per day: busy pages have tens of thousands of
        # captures, and day resolution is all pick_closest needs
        "collapse": "timestamp:8",
    }
    r = polite_get(CDX, params=params)
    rows = r.json() if r.text.strip() else []
    # first row of CDX JSON output is the header
    captures = [dict(zip(rows[0], row)) for row in rows[1:]] if rows else []
    cache_file.write_text(json.dumps(captures))
    return captures


def pick_closest(captures, year, only_200=False):
    """From captures, choose the one in `year` closest to 1 July.

    Status 200 is preferred over a redirect when both exist; with
    `only_200`, redirect captures are ignored.
    """
    in_year = [c for c in captures if c["timestamp"].startswith(str(year))
               and (c["statuscode"] == "200" or not only_200)]
    if not in_year:
        return None
    target = datetime.strptime(f"{year}{TARGET_MMDD}", "%Y%m%d")

    def score(c):
        ts = datetime.strptime(c["timestamp"][:8], "%Y%m%d")
        is_redirect = 0 if c["statuscode"] == "200" else 1
        return (is_redirect, abs((ts - target).days))

    return min(in_year, key=score)


def main():
    companies = pd.read_csv(COMPANIES_CSV)
    cands = pd.read_csv(URLS_CSV).sort_values(["ticker", "priority"])

    # snapshots rejected by steps 2-3 in earlier runs (see common.py)
    excl = load_exclusions()
    bad_capture = set(zip(excl.candidate_url[excl.scope == "capture"],
                          excl.timestamp[excl.scope == "capture"]))
    bad_url_year = set(zip(excl.candidate_url[excl.scope == "url_year"],
                           excl.year[excl.scope == "url_year"].astype(int)))

    out = []
    for _, co in companies.iterrows():
        urls = cands[cands.ticker == co.ticker]
        # query every candidate once (cached), then decide per year
        captures_by_url = {}
        for _, u in urls.iterrows():
            try:
                captures_by_url[u.url] = query_cdx(u.url)
            except Exception as e:          # network failure: record, keep going
                print(f"[{co.ticker}] CDX failed for {u.url}: {e}")
                captures_by_url[u.url] = []
            print(f"[{co.ticker}] {u.url}: {len(captures_by_url[u.url])} captures")

        for year in YEARS:
            row = {"ticker": co.ticker, "company_name": co.company_name,
                   "sector": co.sector_assignment, "year": year,
                   "candidate_url": None, "page_type": None,
                   "timestamp": None, "statuscode": None, "digest": None,
                   "missing_reason": None}
            # pass 1: live pages (200) only; pass 2: accept redirects
            for only_200 in (True, False):
                for _, u in urls.iterrows():
                    if (u.url, year) in bad_url_year:
                        continue
                    usable = [c for c in captures_by_url[u.url]
                              if (u.url, c["timestamp"]) not in bad_capture]
                    best = pick_closest(usable, year, only_200)
                    if best:
                        row.update(candidate_url=u.url, page_type=u.page_type,
                                   timestamp=best["timestamp"],
                                   statuscode=best["statuscode"],
                                   digest=best["digest"])
                        break
                if row["timestamp"]:
                    break
            else:
                archived = any(pick_closest(captures_by_url[u.url], year) for _, u in urls.iterrows())
                row["missing_reason"] = "all_snapshots_rejected" if archived else "no_snapshot_in_year"
            out.append(row)

    df = pd.DataFrame(out)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED / "part1_snapshot_index.csv", index=False)

    # coverage table: companies x years, 1 = snapshot found
    cov = df.assign(found=df.timestamp.notna().astype(int)) \
            .pivot(index="ticker", columns="year", values="found")
    cov.to_csv(PROCESSED / "part1_coverage_matrix.csv")
    print(f"\nFound {df.timestamp.notna().sum()} / {len(df)} company-years")


if __name__ == "__main__":
    main()
