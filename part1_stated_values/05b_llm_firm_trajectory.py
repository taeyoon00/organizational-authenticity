"""
Step 5b: firm-level reading of all years at once  (task item (c))

Input : data/intermediate/part1_llm_snapshots.csv (step 5), part1_text.csv, part1_change.csv
Output: data/intermediate/part1_llm_firms.csv      (one row per company)
        data/intermediate/part1_llm_notes.csv      (one analyst note per company-year)

Linguistic shifts are a property of a sequence, so this step gives the model
a company's full 2016-2024 series in one request. The series is given as the
step-5 codings of each year (page type, themes, verbatim evidence quotes,
other themes, change judgement and summary) rather than the raw pages: this
keeps every firm inside a small local model's context and makes the firm-
level reading traceable to the per-year evidence. It returns
  * trajectory_summary  how the company's self-description evolved
  * linguistic_shifts   dated shifts (from_year -> to_year), with the value
                        categories involved
  * year_notes          one analyst note per observed year; these become
                        the `analyst_notes` column of the final dataset

Usage: python 05b_llm_firm_trajectory.py [--dry-run] [--limit N]
"""
import argparse
import sys

import pandas as pd

from common import PROCESSED, REPO, YEARS
from llm import cached, call_json, estimate_cost, input_sha

sys.path.insert(0, str(REPO))
from shared.value_codebook import CATEGORY_IDS, codebook_text  # noqa: E402

TASK = "firm_v1"

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["trajectory_summary", "linguistic_shifts", "year_notes"],
    "properties": {
        # length limits keep a small local model from looping (see llm.py)
        "trajectory_summary": {"type": "string", "maxLength": 900},
        "linguistic_shifts": {"type": "array", "maxItems": 8, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["from_year", "to_year", "shift", "categories"],
            "properties": {
                "from_year": {"type": "integer"},
                "to_year": {"type": "integer"},
                "shift": {"type": "string", "maxLength": 300},
                "categories": {"type": "array", "maxItems": 4,
                               "items": {"type": "string", "enum": CATEGORY_IDS}}}}},
        "year_notes": {"type": "array", "maxItems": len(YEARS), "items": {
            "type": "object", "additionalProperties": False,
            "required": ["year", "note"],
            "properties": {"year": {"type": "integer"}, "note": {"type": "string", "maxLength": 250}}}},
    },
}

SYSTEM = f"""You are a research assistant analysing how a large US company's publicly stated values changed between 2016 and 2024, for an academic study of organizational authenticity.

For each year in which the company's archived "About us" / mission / values page was observed you receive: the URL, the page type, the value categories coded on that page (primary = emphasised), short verbatim evidence quotes, other value language, and a judgement (with summary) of whether the values content changed from the prior year. Years with no usable page are listed as missing; do not guess their content.

Value categories used in the study:
{codebook_text()}

Return:
- trajectory_summary: 3-5 sentences on how the company's self-description evolved: which values were stable, which appeared or faded, and how tone or framing changed (e.g. from product-centric to purpose-centric, from shareholder to stakeholder language, adoption of ESG or DEI vocabulary, and any later retreat from it).
- linguistic_shifts: each notable shift, dated by the last year before and the first year after it, with a one-sentence description quoting short phrases from the evidence, and the categories involved. A change of URL that only reflects a site reorganisation is not a shift unless the wording changed. Empty list if the language was stable.
- year_notes: for every observed year, one sentence an analyst would write next to that year's row (what the page emphasises, what is new that year, or that it is unchanged). Do not write notes for missing years.

Base every statement on the information given; when the evidence is thin (short or non-values pages), say so."""


def s(x):
    return x if isinstance(x, str) and x else "-"


def build_user(co, g):
    """The firm's series as step-5 codings (not full texts): page type,
    themes with verbatim evidence, other themes, and the change judgement
    and summary per year. Keeps every firm inside a small model's context."""
    parts = [f"Company: {co.company_name} ({co.ticker}), sector: {co.sector}\n"]
    for year in YEARS:
        row = g[g.year == year]
        if row.empty:
            parts.append(f"=== {year}: missing (no usable archived page) ===")
            continue
        r = row.iloc[0]
        unchanged = r.text_change == "unchanged"
        parts.append(
            f"=== {year} | URL: {r.candidate_url} | page type: {s(r.page_content_type)} ===\n"
            f"change vs prior: {'text unchanged' if unchanged else s(r.change_vs_prior_llm)}"
            f"{'' if unchanged else ' - ' + s(r.change_summary)}\n"
            f"primary themes: {s(r.primary_themes)}\n"
            f"all themes: {s(r.theme_categories)}\n"
            f"other themes: {s(r.other_themes)}\n"
            f"evidence: {s(r.theme_evidence)}")
    return "\n\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    text = pd.read_csv(PROCESSED / "part1_text.csv")
    text = text[text.extraction_flag == "ok"][["ticker", "year", "candidate_url"]]
    change = pd.read_csv(PROCESSED / "part1_change.csv")         .rename(columns={"changed_from_prior": "text_change"})[["ticker", "year", "text_change"]]
    llm = pd.read_csv(PROCESSED / "part1_llm_snapshots.csv")     # step 5 must have run
    df = text.merge(change, on=["ticker", "year"], how="left") \
        .merge(llm, on=["ticker", "year"], how="inner")
    companies = pd.read_csv(PROCESSED / "part1_snapshot_index.csv") \
        .drop_duplicates("ticker")[["ticker", "company_name", "sector"]]
    if args.limit:
        companies = companies.head(args.limit)

    pending = [co for co in companies.itertuples()
               if cached(TASK, co.ticker.replace(".", "_"),
                         input_sha(SYSTEM, build_user(co, df[df.ticker == co.ticker]), SCHEMA)) is None]
    chars = sum(len(SYSTEM) + len(build_user(co, df[df.ticker == co.ticker])) for co in pending)
    print(f"{len(companies)} firms, {len(pending)} not yet analysed; "
          f"estimated cost ${estimate_cost(chars, len(pending), out_tokens_per_call=3000):.2f}")
    if args.dry_run:
        return

    firms, notes = [], []
    for co in companies.itertuples():
        g = df[df.ticker == co.ticker]
        try:
            a = call_json(TASK, co.ticker.replace(".", "_"), SYSTEM, build_user(co, g), SCHEMA)
        except Exception as e:
            print(f"  {co.ticker} failed: {e}")
            continue
        firms.append({"ticker": co.ticker, "trajectory_summary": a["trajectory_summary"],
                      "n_shifts": len(a["linguistic_shifts"]),
                      "linguistic_shifts": " || ".join(
                          f"{s['from_year']}->{s['to_year']}: {s['shift']} [{', '.join(s['categories'])}]"
                          for s in a["linguistic_shifts"])})
        observed = set(g.year)
        notes += [{"ticker": co.ticker, "year": n["year"], "analyst_notes": n["note"]}
                  for n in a["year_notes"] if n["year"] in observed]
    pd.DataFrame(firms).to_csv(PROCESSED / "part1_llm_firms.csv", index=False)
    pd.DataFrame(notes).to_csv(PROCESSED / "part1_llm_notes.csv", index=False)
    print(f"wrote {len(firms)} firms, {len(notes)} year notes")


if __name__ == "__main__":
    main()
