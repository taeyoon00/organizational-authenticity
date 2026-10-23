"""
Step 2: download the raw HTML of every chosen snapshot.

Input : data/intermediate/part1_snapshot_index.csv   (from step 1)
Output: data/raw/wayback/<ticker>/<year>_<timestamp>.html  (cached, never re-downloaded;
        the timestamp in the name means a changed snapshot choice is re-fetched)
        data/intermediate/part1_download_log.csv

Why the `id_` suffix: https://web.archive.org/web/<ts>id_/<url> returns
the page exactly as archived, without the Wayback toolbar and without
rewritten links, which makes text extraction cleaner.

Redirect rule (DECISIONS.md, D-005): we let `requests` follow up to 10
redirects. The full chain is logged. If the final URL looks like a
homepage (path is empty or "/"), the snapshot is flagged
`redirected_to_homepage`, because the About page no longer existed and
the archive fell back to the front page. Candidates that are themselves
a site root (about.nike.com, berkshirehathaway.com) are never flagged.

If the redirect chain lands on a capture from a different year, the row
is flagged `redirect_out_of_year` and not used (D-004: no borrowing).
"""
import json
from urllib.parse import urlparse

import pandas as pd

from common import PROCESSED, RAW_DIR, polite_get, record_exclusions


def wayback_raw_url(timestamp, url):
    return f"https://web.archive.org/web/{timestamp}id_/{url}"


def url_path(url):
    return urlparse(url if "://" in url else "http://" + url).path


def classify(final_url, redirected, candidate_url, year):
    """Flag a successful (HTTP 200) download; see the module docstring."""
    # final_url looks like https://web.archive.org/web/<ts>id_/<original>
    ts, _, original = final_url.split("/web/", 1)[-1].partition("id_/")
    if redirected and not ts.startswith(str(year)):
        return "redirect_out_of_year"
    if redirected and url_path(original) in ("", "/")             and url_path(candidate_url) not in ("", "/"):
        return "redirected_to_homepage"
    return "ok"


def main():
    idx = pd.read_csv(PROCESSED / "part1_snapshot_index.csv", dtype={"timestamp": str})
    log_file = PROCESSED / "part1_download_log.csv"
    log = []
    for _, r in idx.iterrows():
        rec = {"ticker": r.ticker, "year": r.year,
               "candidate_url": r.candidate_url, "timestamp": r.timestamp, "file": None,
               "final_url": None, "redirect_chain": None, "http_status": None,
               "download_flag": r.missing_reason}
        if pd.isna(r.timestamp):
            log.append(rec)
            continue

        out = RAW_DIR / r.ticker.replace(".", "_") / f"{r.year}_{r.timestamp}.html"
        rec["file"] = str(out.relative_to(RAW_DIR))
        # each download keeps its redirect metadata in a sidecar file, so a
        # cached page can be re-flagged under the current rules
        meta_file = out.with_suffix(".json")
        if out.exists() and meta_file.exists():   # cached from a previous run
            rec.update(json.loads(meta_file.read_text()))
            rec["download_flag"] = classify(rec["final_url"], rec["redirect_chain"] is not None,
                                            r.candidate_url, r.year)
            log.append(rec)
            continue

        try:
            resp = polite_get(wayback_raw_url(r.timestamp, r.candidate_url))
        except Exception as e:
            rec["download_flag"] = f"download_error: {e}"
            log.append(rec)
            continue

        rec["http_status"] = resp.status_code
        rec["final_url"] = resp.url
        rec["redirect_chain"] = " -> ".join(h.url for h in resp.history) or None
        if resp.status_code != 200:
            rec["download_flag"] = f"http_{resp.status_code}"
        else:
            rec["download_flag"] = classify(resp.url, bool(resp.history), r.candidate_url, r.year)
            if rec["download_flag"] != "redirect_out_of_year":
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(resp.content)
                meta_file.write_text(json.dumps({k: rec[k] for k in
                                                 ("final_url", "redirect_chain", "http_status")}))
        print(r.ticker, r.year, rec["download_flag"])
        log.append(rec)

    df = pd.DataFrame(log)
    df.to_csv(log_file, index=False)
    # failed snapshots are skipped by step 1 on the next run
    bad = df.rename(columns={"download_flag": "reason"})[["ticker", "year", "candidate_url", "timestamp", "reason"]]
    n = record_exclusions(bad.dropna(subset=["timestamp"]).to_dict("records"))
    print(f"{n} newly rejected snapshots")


if __name__ == "__main__":
    main()
