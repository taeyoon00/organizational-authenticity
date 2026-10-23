"""
Step 4c: one row per company-year that has no usable page text, with the reason.

Input : part1_snapshot_index.csv, part1_text.csv, part1_excluded_snapshots.csv,
        url_candidates.csv
Output: data/outputs/part1_gaps.csv
        (ticker, year, gap_reason, candidates_tried, rejected_snapshots, explanation)

The brief asks to "document and justify every gap". The reason codes are:
  no_snapshot_in_year     no candidate URL was archived that year
  all_snapshots_rejected  captures existed but every one failed a check in
                          step 2/3 (dead page, error page, JavaScript shell, ...)
  too_short               page extracted, but under 200 characters; kept in
                          the dataset but not analysed
"""
import pandas as pd

from common import OUTPUTS, PROCESSED, URLS_CSV, load_exclusions

EXPLAIN = {
    "http_404": "the archived URL redirects to a 404 page",
    "redirected_to_homepage": "the page was removed and redirects to the homepage",
    "redirect_out_of_year": "the redirect lands on a capture from another year",
    "js_rendered_shell": "the page is drawn by JavaScript; the archive holds no text",
    "soft_404": "the archive stored an error page served as HTTP 200",
    "no_prose": "the page text is only menus, link lists or figures (no running text)",
}


def main():
    idx = pd.read_csv(PROCESSED / "part1_snapshot_index.csv")
    text = pd.read_csv(PROCESSED / "part1_text.csv")
    excl = load_exclusions()
    cands = pd.read_csv(URLS_CSV)

    usable = text[text.extraction_flag == "ok"].set_index(["ticker", "year"]).index
    short = text[text.extraction_flag == "too_short"].set_index(["ticker", "year"])

    rows = []
    for r in idx.itertuples():
        key = (r.ticker, r.year)
        if key in usable:
            continue
        tried = cands[cands.ticker == r.ticker].url.tolist()
        rej = excl[(excl.ticker == r.ticker) & (excl.year == r.year)]
        reasons = rej.reason.str.replace("repeated_", "").unique().tolist()
        if key in short.index:
            reason = "too_short"
            explanation = f"only {short.n_chars[key]} characters extracted from {short.candidate_url[key]}"
        elif r.missing_reason == "all_snapshots_rejected":
            reason = r.missing_reason
            explanation = "; ".join(EXPLAIN.get(x, f"the archived URL returns HTTP {x[5:]}"
                                                if x.startswith("http_") else x) for x in reasons)
        else:
            reason = r.missing_reason or "unknown"
            explanation = f"none of {len(tried)} candidate URLs has a capture in {r.year}"
        rows.append({"ticker": r.ticker, "year": r.year, "gap_reason": reason,
                     "rejection_types": ", ".join(reasons) or None,
                     "candidates_tried": " | ".join(tried),
                     "rejected_snapshots": " | ".join(f"{u}@{t}" for u, t in
                                                      zip(rej.candidate_url, rej.timestamp)) or None,
                     "explanation": explanation})
    gaps = pd.DataFrame(rows)
    gaps.to_csv(OUTPUTS / "part1_gaps.csv", index=False)
    print(f"{len(gaps)} gaps / {len(idx)} company-years")
    print(gaps.groupby(["gap_reason", "rejection_types"], dropna=False).size().to_string())


if __name__ == "__main__":
    main()
