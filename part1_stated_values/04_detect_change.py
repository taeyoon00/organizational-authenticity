"""
Step 4: did the page change from the prior year?  (task item (a))

Input : data/intermediate/part1_text.csv
Output: data/intermediate/part1_change.csv

Two-stage rule (DECISIONS.md, D-007):
  * similarity = difflib SequenceMatcher ratio between this year's and
    last year's clean text, compared as lower-cased word sequences
    (0 = completely different, 1 = identical). autojunk is switched off:
    on long inputs it discards frequent elements as "junk", which made
    near-identical pages score below 0.1 in character-level tests.
  * similarity >= 0.95  -> "unchanged"   (only cosmetic edits)
  * similarity <  0.60  -> "major_change"
  * in between           -> "minor_change", and these borderline cases
                            are the ones later sent to the LLM for a
                            qualitative description.
  * first observed year or prior year missing -> "no_prior"
  * either year's text failed the extraction check (too_short,
    js_rendered_shell) -> "not_comparable"; two empty shells would
    otherwise score as "unchanged"
  * url_changed = True when this year's page came from a different
    candidate URL than last year's; such a "change" may only reflect a
    switch between pages, so it is flagged for review.
Doing the cheap deterministic comparison first makes the result
reproducible and keeps LLM calls (and cost) for the cases that need judgment.
"""
import re
from difflib import SequenceMatcher

import pandas as pd

from common import PROCESSED

UNCHANGED, MAJOR = 0.95, 0.60


def words(text):
    return re.findall(r"\w+", str(text).lower())


def similarity(a, b):
    return SequenceMatcher(None, words(a), words(b), autojunk=False).ratio()


def main():
    df = pd.read_csv(PROCESSED / "part1_text.csv").sort_values(["ticker", "year"])
    out = []
    for ticker, g in df.groupby("ticker"):
        prev = None
        for _, r in g.iterrows():
            if prev is None or r.year - prev.year != 1:
                sim, label = None, "no_prior"
            elif r.extraction_flag != "ok" or prev.extraction_flag != "ok":
                sim, label = None, "not_comparable"
            else:
                sim = similarity(prev.page_text_clean, r.page_text_clean)
                label = "unchanged" if sim >= UNCHANGED else "major_change" if sim < MAJOR else "minor_change"
            out.append({"ticker": ticker, "year": r.year,
                        "similarity_to_prior": sim, "changed_from_prior": label,
                        "url_changed": label != "no_prior" and r.candidate_url != prev.candidate_url})
            prev = r
    pd.DataFrame(out).to_csv(PROCESSED / "part1_change.csv", index=False)


if __name__ == "__main__":
    main()
