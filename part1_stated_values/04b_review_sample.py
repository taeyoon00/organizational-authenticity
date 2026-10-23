"""
Step 4b: draw a sample of year-over-year changes for manual validation.

Input : data/intermediate/part1_change.csv, part1_text.csv, part1_download_log.csv
Output: data/intermediate/part1_change_review.csv   (open in Excel; UTF-8 with BOM)

Why: the change label (D-007) comes from a similarity threshold. Before it is
used, a human checks a sample to see whether "major_change" means the stated
values changed, or only news/figures/extraction noise. The sample is drawn
with a fixed seed so it can be reproduced.

  * 20 major changes on the same URL, at most one per firm
  * 4 major changes caused by a URL switch (url_changed)
  * 6 minor changes, to check the 0.60 / 0.95 cut-offs from the other side

For each pair the file lists sentences that disappeared and appeared, plus
Wayback links to both captures. The reviewer fills `human_label`:
  values_change   wording of mission / values / principles changed
  other_content   page changed, but not its values content (news, figures, products)
  extraction      same page content, different text extracted
  page_switch     a different page was compared
"""
import pandas as pd

from common import PROCESSED, sentence_diff

SEED = 2026
N_MAJOR, N_SWITCH, N_MINOR = 20, 4, 6
SNIPPETS, SNIPPET_LEN = 3, 160


def diff_snippets(old, new):
    """Sentences present in one year only, longest first (most informative)."""
    gone, came = sentence_diff(old, new)
    gone = sorted(gone, key=len, reverse=True)
    came = sorted(came, key=len, reverse=True)
    fmt = lambda xs: " || ".join(s[:SNIPPET_LEN] for s in xs[:SNIPPETS])
    return fmt(gone), fmt(came), len(gone), len(came)


def wayback(ts, url):
    return f"https://web.archive.org/web/{ts}/{url}" if pd.notna(ts) else None


def main():
    target = PROCESSED / "part1_change_review.csv"
    if target.exists() and pd.read_csv(target).human_label.notna().any():
        print("part1_change_review.csv already has human labels; not overwriting it")
        return
    ch = pd.read_csv(PROCESSED / "part1_change.csv")
    text = pd.read_csv(PROCESSED / "part1_text.csv")
    log = pd.read_csv(PROCESSED / "part1_download_log.csv", dtype={"timestamp": str})

    major = ch[ch.changed_from_prior == "major_change"]
    same_url = major[~major.url_changed].sample(frac=1, random_state=SEED) \
        .drop_duplicates("ticker").head(N_MAJOR)
    switch = major[major.url_changed].sample(N_SWITCH, random_state=SEED)
    minor = ch[ch.changed_from_prior == "minor_change"].sample(N_MINOR, random_state=SEED)
    sample = pd.concat([same_url, switch, minor])

    t = text.set_index(["ticker", "year"])
    lg = log.set_index(["ticker", "year"])
    rows = []
    for r in sample.itertuples():
        prev, cur = (r.ticker, r.year - 1), (r.ticker, r.year)
        gone, came, n_gone, n_came = diff_snippets(t.page_text_clean[prev], t.page_text_clean[cur])
        rows.append({
            "ticker": r.ticker, "year": r.year,
            "label_auto": r.changed_from_prior, "similarity": round(r.similarity_to_prior, 3),
            "url_changed": r.url_changed,
            "chars_prev": t.n_chars[prev], "chars_cur": t.n_chars[cur],
            "n_sent_removed": n_gone, "n_sent_added": n_came,
            "removed_examples": gone, "added_examples": came,
            "wayback_prev": wayback(lg.timestamp[prev], lg.candidate_url[prev]),
            "wayback_cur": wayback(lg.timestamp[cur], lg.candidate_url[cur]),
            "human_label": "", "notes": "",
        })
    out = pd.DataFrame(rows).sort_values(["label_auto", "url_changed", "similarity"])
    out.to_csv(PROCESSED / "part1_change_review.csv", index=False, encoding="utf-8-sig")
    print(f"{len(out)} pairs -> part1_change_review.csv")


if __name__ == "__main__":
    main()
