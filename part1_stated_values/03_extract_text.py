"""
Step 3: turn raw HTML into clean body text.

Input : data/intermediate/part1_download_log.csv and the HTML files it lists
Output: data/intermediate/part1_text.csv  (ticker, year, candidate_url, page_text_clean,
        n_chars, extraction_flag, download_flag)

Method (DECISIONS.md, D-006):
  1. trafilatura: a main-content extractor that drops navigation,
     footers, cookie banners and sidebars. It is the best-performing
     open-source tool in published benchmarks and needs no per-site rules.
  2. Fallback: if trafilatura returns almost nothing (JS-heavy pages,
     unusual layouts), strip <nav>, <header>, <footer>, <script>, <style>,
     <form> with BeautifulSoup and keep the remaining visible text.
  3. Quality flag: pages under MIN_CHARS characters are flagged
     `too_short` for manual review rather than silently dropped.
     Short pages built by a JavaScript framework (React/Next/Nuxt shells
     whose text is fetched in the browser) are flagged `js_rendered_shell`:
     the archived HTML holds no body text, so the year is unobservable
     from this URL.
  4. Archived error pages served with HTTP 200 ("soft 404") are flagged
     `soft_404`; pages that are almost all menus, link lists or stat boxes
     (under 20% of words in lines of 8+ words) are flagged `no_prose`.
     Flagged snapshots are recorded so step 1 can pick another
     capture or candidate on the next run (see common.py, run_part1.py).
"""
import re

import pandas as pd
import trafilatura
from bs4 import BeautifulSoup

from common import PROCESSED, RAW_DIR, record_exclusions

MIN_CHARS = 200
JS_SHELL = re.compile(rb'id="root"|id="__next"|id="app"|window\.__NUXT__|/_next/static/|/_nuxt/')


# an archived error page served with HTTP 200 ("soft 404"); only checked on
# short pages, so a real page that merely mentions an error is not caught
SOFT_404 = re.compile(r"page (you.{0,40})?(was |is )?(not found|cannot be found|could not be found|"
                      r"can.t be found|does not exist|doesn.t exist|no longer exists)|"
                      r"something has gone wrong on our end|the error number is|"
                      r"we can.t find (that|the|this) page|404 error|error 404", re.I)
SOFT_404_MAX_CHARS = 1500

# site-search / account widgets that trafilatura keeps as body text; one
# line each, removed before comparison so they do not count as content
UI_LINES = re.compile(r"^(view accounts|sign in|back|oracle account|no results found|"
                      r"your search did not match any results\.?|"
                      r"we suggest you try the following to help find what you.re looking for:|"
                      r"- check the spelling of your keyword search\.|"
                      r"- use synonyms for the keyword you typed.*|"
                      r"- try one of the popular searches shown below\.|- start a new search\.|"
                      r"trending questions)$", re.I)


# Pages whose text is almost all menus, link lists, contact details or stat
# boxes: share of words standing in lines of at least PROSE_LINE_WORDS words.
# Real About/values pages score 0.86-1.0 (interquartile range); menu-only
# extractions score below 0.15.
PROSE_LINE_WORDS = 8
MIN_PROSE_SHARE = 0.2


def prose_share(text):
    lines = [l.split() for l in text.split("\n")]
    total = sum(len(l) for l in lines)
    return sum(len(l) for l in lines if len(l) >= PROSE_LINE_WORDS) / max(1, total)


def quality_flag(text, html):
    if len(text) < SOFT_404_MAX_CHARS and SOFT_404.search(text):
        return "soft_404"
    if len(text) < MIN_CHARS:
        return "js_rendered_shell" if JS_SHELL.search(html) else "too_short"
    if prose_share(text) < MIN_PROSE_SHARE:
        return "no_prose"
    return "ok"


def strip_ui_lines(text):
    return "\n".join(l for l in text.split("\n") if not UI_LINES.match(l.strip()))


BOILERPLATE_TAGS = ["nav", "header", "footer", "script", "style", "noscript",
                    "form", "aside", "iframe", "svg"]


def normalise(text):
    """Collapse whitespace so diffs between years reflect wording, not layout."""
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return strip_ui_lines(text).strip()


def fallback_extract(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(BOILERPLATE_TAGS):
        tag.decompose()
    # also drop elements whose id/class clearly marks them as chrome
    for el in soup.find_all(attrs={"class": re.compile(r"(nav|menu|footer|cookie|breadcrumb)", re.I)}):
        el.decompose()
    return soup.get_text("\n")


def extract(html):
    """Return (clean_text, method_used)."""
    text = trafilatura.extract(html, include_comments=False, include_tables=False,
                               favor_recall=True) or ""
    if len(text) >= MIN_CHARS:
        return normalise(text), "trafilatura"
    fb = normalise(fallback_extract(html))
    return (fb, "fallback_bs4") if len(fb) > len(text) else (normalise(text), "trafilatura")


def main():
    log = pd.read_csv(PROCESSED / "part1_download_log.csv", dtype={"timestamp": str})
    rows = []
    for _, r in log[log.file.notna()].iterrows():
        f = RAW_DIR / r.file
        if not f.exists() or r.download_flag == "redirect_out_of_year":
            continue
        # bytes, not text: the parsers detect the page's own encoding
        # (reading as text would use the OS default, cp949 on Korean Windows)
        html = f.read_bytes()
        text, method = extract(html)
        rows.append({"ticker": r.ticker, "year": r.year,
                     "candidate_url": r.candidate_url, "download_flag": r.download_flag,
                     "page_text_clean": text, "n_chars": len(text),
                     "extraction_method": method,
                     "extraction_flag": quality_flag(text, html)})
    df = pd.DataFrame(rows)
    df.to_csv(PROCESSED / "part1_text.csv", index=False)
    # unusable pages are skipped by step 1 on the next run
    bad = df.merge(log[["ticker", "year", "timestamp"]], on=["ticker", "year"])         .rename(columns={"extraction_flag": "reason"})
    n = record_exclusions(bad[["ticker", "year", "candidate_url", "timestamp", "reason"]]
                          .astype({"timestamp": str}).to_dict("records"))
    print(f"{n} newly rejected snapshots")
    print(df.groupby("extraction_flag").size())


if __name__ == "__main__":
    main()
