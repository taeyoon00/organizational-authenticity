"""
Part 2, step 1: collect one annual proxy statement (SEC form DEF 14A) per
company per year, 2016-2024, from SEC EDGAR, and keep its plain text.

Input : data/companies.csv (CIK numbers; cik_predecessor for firms whose
        registrant changed, e.g. Broadcom's 2018 redomiciliation)
Output: data/raw/proxies/<ticker>/<year>_<accession>.txt.gz   (text, not committed)
        data/intermediate/part2_proxy_index.csv                   (one row per company-year)

Why proxy statements (DECISIONS.md, D-012): every US-listed firm must file
one each year, so coverage is complete and the same document type exists for
all 50 firms; since the late 2010s proxies also report on board diversity,
human capital, ESG oversight and culture. ESG/DEI reports are voluntary,
start in different years, and have no common location.

Selection: for each proxy year (calendar year of filing; a December filing
counts for the next year's meeting), candidate filings of form DEF 14A or
DEFC14A (contested elections, e.g. ExxonMobil 2021) are tried in date order;
the first whose opening text mentions an annual (general / shareholders')
meeting is kept, which skips special-meeting proxies such as merger votes.

The SEC requires automated clients to identify themselves: set the
environment variable SEC_USER_AGENT to "<name> <email>" before running.
Requests are spaced to stay under the SEC's 10 requests/second limit.
"""
import gzip
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "raw" / "proxies"
PROCESSED = REPO / "data" / "intermediate"   # intermediate files
OUTPUTS = REPO / "data" / "outputs"          # final datasets and results
YEARS = range(2016, 2025)

UA = os.environ.get("SEC_USER_AGENT")
if not UA:
    sys.exit('set SEC_USER_AGENT, e.g. "Jane Doe jane@example.com" (required by the SEC)')
session = requests.Session()
session.headers.update({"User-Agent": UA})


def get(url):
    time.sleep(0.15)
    for attempt in range(4):
        r = session.get(url, timeout=60)
        if r.status_code == 200:
            return r
        time.sleep(2 ** attempt)
    r.raise_for_status()


FORMS = {"DEF 14A", "DEFC14A"}            # DEFC14A: definitive proxy in a contested election
# "Annual Meeting", "Annual General Meeting", "Annual Shareholders' Meeting";
# \W{0,3} also accepts a curly apostrophe that was decoded as garbage
ANNUAL = re.compile(r"annual (general )?((share|stock)holders\W{0,3} )?meeting", re.I)


def proxy_year(date):
    """Proxy season a filing belongs to: a proxy filed in December is for the
    next year's meeting (e.g. Apple's December filings)."""
    return int(date[:4]) + (date[5:7] == "12")


def proxy_filings(cik):
    """All annual-proxy-type filings for proxy years 2016-2024, oldest first."""
    sub = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()
    blocks = [sub["filings"]["recent"]]
    for f in sub["filings"]["files"]:            # older filings live in extra pages
        if f["filingTo"] >= "2015-12-01" and f["filingFrom"] <= "2024-11-30":
            blocks.append(get(f"https://data.sec.gov/submissions/{f['name']}").json())
    rows = []
    for b in blocks:
        for form, date, acc, doc in zip(b["form"], b["filingDate"], b["accessionNumber"], b["primaryDocument"]):
            if form in FORMS and 2016 <= proxy_year(date) <= 2024:
                rows.append({"filing_date": date, "proxy_year": proxy_year(date),
                             "accession": acc, "document": doc, "form": form})
    return sorted(rows, key=lambda r: r["filing_date"])


def to_text(raw):
    soup = BeautifulSoup(raw, "lxml")
    for t in soup(["script", "style"]):
        t.decompose()
    return " ".join(soup.get_text(" ").split())


def main():
    companies = pd.read_csv(REPO / "data" / "companies.csv")
    out = []
    for co in companies.itertuples():
        filings = proxy_filings(int(co.cik))
        ciks = {}                                 # accession -> filer CIK, when not co.cik
        if pd.notna(co.cik_predecessor):         # e.g. Broadcom Ltd -> Broadcom Inc. (2018)
            older = proxy_filings(int(co.cik_predecessor))
            ciks = {f["accession"]: int(co.cik_predecessor) for f in older}
            filings = sorted(filings + older, key=lambda r: r["filing_date"])
        for year in YEARS:
            row = {"ticker": co.ticker, "year": year, "filing_date": None, "accession": None,
                   "url": None, "file": None, "n_words": None, "status": "no_annual_proxy"}
            for f in (f for f in filings if f["proxy_year"] == year):
                folder = RAW / co.ticker.replace(".", "_")
                path = folder / f"{year}_{f['accession']}.txt.gz"
                url = (f"https://www.sec.gov/Archives/edgar/data/{ciks.get(f['accession'], int(co.cik))}/"
                       f"{f['accession'].replace('-', '')}/{f['document']}")
                if path.exists():
                    text = gzip.open(path, "rt", encoding="utf-8").read()
                else:
                    text = to_text(get(url).content)
                    if not ANNUAL.search(text[:30000]):
                        continue                       # special meeting: try the next filing
                    folder.mkdir(parents=True, exist_ok=True)
                    with gzip.open(path, "wt", encoding="utf-8") as fh:
                        fh.write(text)
                row.update(filing_date=f["filing_date"], form=f["form"], accession=f["accession"], url=url,
                           file=str(path.relative_to(RAW)), n_words=len(text.split()), status="ok")
                break
            out.append(row)
        got = sum(r["status"] == "ok" for r in out if r["ticker"] == co.ticker)
        print(f"{co.ticker:6s} {got}/9 proxies", flush=True)
    df = pd.DataFrame(out)
    df.to_csv(PROCESSED / "part2_proxy_index.csv", index=False)
    print(f"\n{(df.status == 'ok').sum()} / {len(df)} company-years have an annual proxy")


if __name__ == "__main__":
    main()
