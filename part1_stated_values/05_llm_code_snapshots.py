"""
Step 5: LLM coding of every usable snapshot  (task items (a) and (b))

Input : data/intermediate/part1_text.csv, part1_change.csv
Output: data/intermediate/part1_llm_snapshots.csv  (one row per company-year)

For each company-year with usable text the model returns:
  * page_content_type  values_statement / general_about / mixed / not_an_about_page
                       (a validity check on the page choice, D-003)
  * themes             which of the 12 codebook categories are present
                       (shared/value_codebook.py, D-008), each with salience
                       primary/secondary and a short verbatim evidence quote
  * other_themes       value language that fits no category, so the
                       codebook does not silently force a fit
  * change_vs_prior    (a) a second, dedicated call, only when the text
                       differs from last year (similarity < 0.95 in step 4):
                       the model sees the sentences removed since last year
                       and the sentences added this year, and must say
                       whether the *values content* changed, or only
                       wording, other content, or the page itself.
                       Unchanged pairs need no LLM call. Sending the
                       difference rather than both texts keeps long pages
                       inside a small model's context and points the model
                       at what changed.

Why two calls: the first version asked for themes and change in one call.
The 7B model then invented change labels for 26 snapshots that had no
prior-year comparison and skipped the judgement for 20 that had one
(DECISIONS.md, D-011). The theme call's own change field is therefore
ignored, and change comes only from the dedicated call, whose label set
has no "not assessed" option.

Backend and model: llm.py (default: local Qwen2.5-7B via Ollama, D-011).
Usage:  python 05_llm_code_snapshots.py --dry-run     (size / cost estimate)
        python 05_llm_code_snapshots.py --limit 5     (pilot)
        python 05_llm_code_snapshots.py               (all)
"""
import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from common import PROCESSED, REPO, sentence_diff
from llm import (BACKEND, MAX_CONTEXT, MODEL, approx_tokens, call_json, cached,
                 context_tier, estimate_cost, input_sha)

sys.path.insert(0, str(REPO))
from shared.value_codebook import CATEGORY_IDS, codebook_text  # noqa: E402

TASK = "snapshot_v1"          # bump when the prompt or schema changes
WORKERS = 1 if BACKEND == "ollama" else 4     # one local GPU serves one request at a time

CHANGE_LABELS = ["not_assessed", "no_substantive_change", "wording_only",
                 "values_content_changed", "non_values_content_changed", "different_page"]

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["page_content_type", "themes", "other_themes", "change_vs_prior", "change_summary"],
    "properties": {
        "page_content_type": {"type": "string", "enum": [
            "values_statement", "general_about", "mixed", "not_an_about_page"]},
        # length limits keep a small local model from looping inside an array
        "themes": {"type": "array", "maxItems": len(CATEGORY_IDS), "items": {
            "type": "object", "additionalProperties": False,
            "required": ["category", "salience", "evidence"],
            "properties": {
                "category": {"type": "string", "enum": CATEGORY_IDS},
                "salience": {"type": "string", "enum": ["primary", "secondary"]},
                "evidence": {"type": "string", "maxLength": 200}}}},
        "other_themes": {"type": "array", "maxItems": 5, "items": {"type": "string", "maxLength": 60}},
        "change_vs_prior": {"type": "string", "enum": CHANGE_LABELS},
        "change_summary": {"type": "string", "maxLength": 500},
    },
}

SYSTEM = f"""You are a research assistant coding corporate web pages for an academic study of the values firms state publicly.

You receive the cleaned body text of one archived "About us" / mission / values page of a large US company for one year. Some pages are rich values statements; others are general company descriptions with news, products or figures mixed in.

Code the page against this codebook of value categories:
{codebook_text()}

Rules:
- A category is present only if the page itself expresses it as something the company values, stands for, or commits to. Do not infer values from the industry or from what the company sells.
- salience "primary": the category is a named value, a headline, or a repeated emphasis. "secondary": it is mentioned but not emphasised.
- evidence: a short verbatim quote (at most 25 words) from the page that supports the category.
- other_themes: short labels for value language that fits none of the categories; empty if none.
- page_content_type: "values_statement" if the page is mainly mission/values/principles; "general_about" if mainly a company description; "mixed" if both are substantial; "not_an_about_page" if it is something else (news feed, product page, error page, login page).

Change from the prior year (only when REMOVED / ADDED SENTENCES are given; otherwise answer "not_assessed" and an empty change_summary). The removed sentences were on last year's page and are gone; the added sentences are new this year:
- "no_substantive_change": the removed and added sentences say the same things, or are only navigation, layout or legal remnants.
- "wording_only": values content is the same in meaning but reworded.
- "values_content_changed": a value, principle, mission or purpose statement was added, removed or materially rewritten.
- "non_values_content_changed": only news, figures, products or other non-values content changed.
- "different_page": almost everything was replaced and the two years are evidently different pages (the URL may also differ), not two versions of one page.
change_summary: one or two sentences naming what changed; quote short phrases where useful."""


def build_user(r, prior, page_chars=None):
    head = (f"Company: {r.company_name} ({r.ticker}), sector: {r.sector}\n"
            f"Year: {r.year}\nURL: {r.candidate_url}\n")
    page = r.page_text_clean if page_chars is None else r.page_text_clean[:page_chars] + " [...truncated]"
    body = f"\nTHIS YEAR TEXT:\n<<<\n{page}\n>>>"
    if prior is None:
        return head + body
    removed, added = sentence_diff(prior.page_text_clean, r.page_text_clean)
    fmt = lambda xs: "\n".join(f"- {x}" for x in xs) or "(none)"
    return (head + f"Last year's URL: {prior.candidate_url}\n" + body +
            f"\n\nREMOVED SENTENCES (on the {r.year - 1} page, gone in {r.year}):\n{fmt(removed)}"
            f"\n\nADDED SENTENCES (new in {r.year}):\n{fmt(added)}")


def load_inputs():
    text = pd.read_csv(PROCESSED / "part1_text.csv")
    change = pd.read_csv(PROCESSED / "part1_change.csv")
    idx = pd.read_csv(PROCESSED / "part1_snapshot_index.csv")[["ticker", "year", "company_name", "sector"]]
    df = text[text.extraction_flag == "ok"].merge(change, on=["ticker", "year"]).merge(idx)
    return df.sort_values(["ticker", "year"]).reset_index(drop=True)


def jobs(df):
    """(key, row, prior_row_or_None) for every usable company-year."""
    by_key = df.set_index(["ticker", "year"])
    for r in df.itertuples():
        # step 4 labels a pair minor/major only when both years are usable
        needs_prior = r.changed_from_prior in ("minor_change", "major_change")
        prior = by_key.loc[(r.ticker, r.year - 1)] if needs_prior else None
        yield f"{r.ticker.replace('.', '_')}_{r.year}", r, prior


def fit_prompt(r, prior):
    """The user prompt, with this year's page cut to fit a local model's
    context if necessary; returns (prompt, truncated). Only a few very long
    pages are affected, and the flag is kept in the output."""
    user = build_user(r, prior)
    budget = MAX_CONTEXT - 2048 - approx_tokens(SYSTEM)     # 2048: room for the answer
    if BACKEND != "ollama" or approx_tokens(user) <= budget:
        return user, False
    excess_chars = int((approx_tokens(user) - budget) * 3.5) + 500
    return build_user(r, prior, page_chars=len(r.page_text_clean) - excess_chars), True


CHANGE_TASK = "change_v1"
CHANGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["change_vs_prior", "change_summary"],
    "properties": {
        "change_vs_prior": {"type": "string", "enum": CHANGE_LABELS[1:]},   # no "not_assessed"
        "change_summary": {"type": "string", "maxLength": 500},
    },
}

CHANGE_SYSTEM = """You compare two consecutive yearly versions of a company's archived "About us" / mission / values web page, for an academic study of the values firms state publicly.

You receive the sentences that were on last year's page and are gone this year (REMOVED), and the sentences that are new this year (ADDED). Sentences present in both years are not shown.

Choose exactly one label:
- "values_content_changed": a value, principle, mission, purpose or belief statement was added, removed, or rewritten so that its meaning changed. Example: a new principle such as "Strive to be Earth's Best Employer" appears.
- "wording_only": a values or mission statement was rephrased but means the same.
- "non_values_content_changed": only news, figures (revenue, employees, locations), products, people or events changed; no statement of what the company values changed.
- "no_substantive_change": REMOVED and ADDED say essentially the same thing, or are only navigation, layout, cookie or legal text.
- "different_page": nearly everything was replaced and the two versions are evidently different pages (often the URL also differs).

change_summary: one sentence naming what changed, quoting a short phrase where useful."""


def build_change_user(r, prior):
    removed, added = sentence_diff(prior.page_text_clean, r.page_text_clean)
    fmt = lambda xs: "\n".join(f"- {x}" for x in xs) or "(none)"
    return (f"Company: {r.company_name} ({r.ticker})\n"
            f"Last year: {r.year - 1}, URL: {prior.candidate_url}\n"
            f"This year: {r.year}, URL: {r.candidate_url}\n\n"
            f"REMOVED (on the {r.year - 1} page, gone in {r.year}):\n{fmt(removed)}\n\n"
            f"ADDED (new in {r.year}):\n{fmt(added)}")


# Qwen models occasionally emit a stray CJK character where an English
# string is cut at its length limit; the pages are all English
CJK = re.compile(r"[　-鿿가-힯＀-￯]+")


def clean(s):
    return CJK.sub("", s).strip()


def run_one(key, r, prior):
    user, truncated = fit_prompt(r, prior)
    ans = call_json(TASK, key, SYSTEM, user, SCHEMA)
    return key, r, {**ans, "input_truncated": truncated}


THEME_COLS = ["page_content_type", "theme_categories", "primary_themes", "theme_evidence", "other_themes"]


def inherit_unchanged(out, df):
    """A page whose text did not change from last year (similarity >= 0.95,
    step 4) takes over last year's theme coding.

    Coding identical texts separately gave different theme sets 39% of the
    time (mean Jaccard 0.85), because the prompt also carries the year and
    URL; left as is, that noise would show up as spurious year-to-year shifts
    in stated values. The rule makes "text unchanged" imply "coding
    unchanged". The model's own coding is kept in *_raw columns, and
    themes_from_year says which year's coding a row carries."""
    out = out.merge(df[["ticker", "year", "changed_from_prior"]], on=["ticker", "year"]) \
        .sort_values(["ticker", "year"]).reset_index(drop=True)
    for c in THEME_COLS:
        out[c + "_raw"] = out[c]
    out["themes_from_year"] = out.year
    for i in range(1, len(out)):
        cur, prev = out.loc[i], out.loc[i - 1]
        if (cur.changed_from_prior == "unchanged" and cur.ticker == prev.ticker
                and cur.year - prev.year == 1):
            for c in THEME_COLS + ["themes_from_year"]:
                out.loc[i, c] = prev[c]
    return out.drop(columns="changed_from_prior")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    df = load_inputs()
    todo = list(jobs(df))
    if BACKEND == "ollama":     # group by context size: fewer model reloads
        todo.sort(key=lambda j: context_tier(SYSTEM, fit_prompt(j[1], j[2])[0]))
    if args.limit:
        todo = todo[:args.limit]
    pending = [j for j in todo
               if cached(TASK, j[0], input_sha(SYSTEM, fit_prompt(j[1], j[2])[0], SCHEMA)) is None]
    chars = sum(len(SYSTEM) + len(build_user(r, p)) for _, r, p in pending)
    print(f"{BACKEND}:{MODEL}  {len(todo)} snapshots, {len(pending)} not yet coded, "
          f"{sum(p is not None for _, _, p in pending)} with prior-year comparison; "
          f"estimated cost ${estimate_cost(chars, len(pending)):.2f}")
    if args.dry_run:
        return

    results = {}
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(run_one, *j) for j in todo]
        for i, f in enumerate(as_completed(futures), 1):
            try:
                key, r, ans = f.result()
                results[key] = (r, ans)
            except Exception as e:           # keep going; rerun picks it up
                print(f"  failed: {e}")
            if i % 25 == 0:
                print(f"  {i}/{len(todo)}")

    # pass 2: dedicated change judgement for pairs whose text changed
    pairs = [j for j in todo if j[2] is not None]
    print(f"change pass: {len(pairs)} pairs, "
          f"{sum(cached(CHANGE_TASK, k, input_sha(CHANGE_SYSTEM, build_change_user(r, p), CHANGE_SCHEMA)) is None for k, r, p in pairs)} not yet judged")
    changes = {}
    for i, (key, r, prior) in enumerate(pairs, 1):
        try:
            changes[key] = call_json(CHANGE_TASK, key, CHANGE_SYSTEM,
                                     build_change_user(r, prior), CHANGE_SCHEMA)
        except Exception as e:
            print(f"  change {key} failed: {e}")
        if i % 25 == 0:
            print(f"  {i}/{len(pairs)}")

    rows = []
    for key, (r, a) in sorted(results.items()):
        themes = a["themes"]
        ch = changes.get(key)
        rows.append({
            "ticker": r.ticker, "year": r.year,
            "page_content_type": a["page_content_type"],
            "theme_categories": ";".join(sorted({t["category"] for t in themes})),
            "primary_themes": ";".join(sorted({t["category"] for t in themes if t["salience"] == "primary"})),
            "theme_evidence": " || ".join(f"{t['category']}: {clean(t['evidence'])}" for t in themes),
            # drop entries that just repeat a codebook category
            "other_themes": ";".join(o for o in (clean(x) for x in a["other_themes"])
                                     if o and o.lower().replace(" ", "_") not in CATEGORY_IDS),
            "change_vs_prior_llm": ch["change_vs_prior"] if ch else "not_assessed",
            "change_summary": clean(ch["change_summary"]) if ch else "",
            "input_truncated": a["input_truncated"],
        })
    out = inherit_unchanged(pd.DataFrame(rows), df)
    out.to_csv(PROCESSED / "part1_llm_snapshots.csv", index=False)
    print(f"wrote {len(out)} rows; failures: {len(todo) - len(out)}")


if __name__ == "__main__":
    main()
