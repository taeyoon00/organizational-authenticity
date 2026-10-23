"""
Part 2, step 2: measure value emphasis and tone in each proxy statement.

Input : data/intermediate/part2_proxy_index.csv, data/raw/proxies/
Output: data/outputs/part2_firm_year.csv   (one row per company-year; columns
        documented in part2_disclosures/README.md)

Method (DECISIONS.md, D-012): a dictionary count, not an LLM. Each of the 12
value categories of the shared codebook (shared/value_codebook.py, also used
for Part 1) is counted with its keyword pattern, and expressed per 10,000
words so long and short proxies are comparable. Why a dictionary here:
proxies run to 30,000-100,000 words, the categories have distinctive
vocabularies, and a transparent count is fully reproducible and runs in
seconds; the price is that it counts mentions, not intentions (README,
limitations).

Tone is measured with three simple, interpretable rates per 10,000 words:
  commitment  commit*, pledge*, goal(s), target(s)
  hedging     may, might, could, seek*, strive*, aim*, endeavor*
  numbers     percentages ("12%", "12 percent"): how quantified the text is
"""
import gzip
import re
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from shared.value_codebook import CATEGORY_IDS, LEXICON  # noqa: E402

RAW = REPO / "data" / "raw" / "proxies"
PROCESSED = REPO / "data" / "intermediate"   # intermediate files
OUTPUTS = REPO / "data" / "outputs"          # final datasets and results

TONE = {
    "commitment": r"\bcommit(s|ted|ment|ments)?\b|\bpledge[sd]?\b|\bgoals?\b|\btargets?\b",
    "hedging": r"\bmay\b|\bmight\b|\bcould\b|\bseek(s|ing)?\b|\bstriv(e|es|ing)\b|\baim(s|ing)?\b|\bendeavou?r\w*",
    "numbers": r"\d+(\.\d+)?\s?(%|percent\b)",
}
PATTERNS = {**{c: re.compile(p, re.I) for c, p in LEXICON.items()},
            **{t: re.compile(p, re.I) for t, p in TONE.items()}}


def main():
    idx = pd.read_csv(PROCESSED / "part2_proxy_index.csv")
    companies = pd.read_csv(REPO / "data" / "companies.csv")
    rows = []
    for r in idx[idx.status == "ok"].itertuples():
        text = gzip.open(RAW / r.file, "rt", encoding="utf-8").read()
        n = len(text.split())
        row = {"ticker": r.ticker, "year": r.year, "filing_date": r.filing_date,
               "proxy_url": r.url, "n_words": n}
        for name, rx in PATTERNS.items():
            prefix = "tone_" if name in TONE else "rate_"
            row[prefix + name] = round(len(rx.findall(text)) / n * 10_000, 2)
        rows.append(row)
    df = pd.DataFrame(rows)
    # share of each category in the firm-year's total value language: a
    # profile that sums to 1, independent of how wordy the proxy is overall
    rates = df[[f"rate_{c}" for c in CATEGORY_IDS]]
    for c in CATEGORY_IDS:
        df[f"share_{c}"] = (df[f"rate_{c}"] / rates.sum(axis=1)).round(4)
    # every company-year is kept; years without an annual proxy have empty measures
    full = idx[["ticker", "year", "status"]].rename(columns={"status": "proxy_status"}) \
        .merge(companies[["ticker", "company_name", "sector_assignment"]]
               .rename(columns={"sector_assignment": "sector"}), on="ticker") \
        .merge(df, on=["ticker", "year"], how="left")
    lead = ["ticker", "company_name", "sector", "year", "proxy_status", "filing_date", "proxy_url", "n_words"]
    full = full[lead + [c for c in full.columns if c not in lead]]
    full.to_csv(OUTPUTS / "part2_firm_year.csv", index=False)
    print(f"{len(df)} proxies measured; median length {int(df.n_words.median())} words")


if __name__ == "__main__":
    main()
