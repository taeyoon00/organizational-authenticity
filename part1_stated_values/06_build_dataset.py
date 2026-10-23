"""
Step 6: assemble the final Part 1 dataset, one row per company-year (50 x 9).

Inputs : outputs of steps 1-5b in data/intermediate/
Output : data/outputs/part1_company_year.csv
         (every column is documented in part1_stated_values/README.md)

Every company-year is kept, including gaps: `observation_status` says
whether the year was observed and, if not, why (from part1_gaps.csv), so the
coverage of any analysis can be traced row by row.

`changed_from_prior` combines the deterministic and the LLM judgement:
  unchanged               text similarity >= 0.95 with the prior year
  changed_values          a value / mission / principle statement was added,
                          removed or materially rewritten  (LLM)
  changed_wording         same values, reworded  (LLM)
  changed_other_content   only news, figures or products changed  (LLM)
  no_substantive_change   texts differ only through layout/extraction  (LLM)
  page_switch             the two years come from different pages  (LLM)
  no_prior                first observed year, or prior year not usable
  pending_llm             text changed but step 5 has not coded it yet
"""
import pandas as pd

from common import COMPANIES_CSV, OUTPUTS, PROCESSED

LLM_TO_LABEL = {
    "values_content_changed": "changed_values",
    "wording_only": "changed_wording",
    "non_values_content_changed": "changed_other_content",
    "no_substantive_change": "no_substantive_change",
    "different_page": "page_switch",
}


def read(name, **kw):
    f = PROCESSED / name if (PROCESSED / name).exists() else OUTPUTS / name
    return pd.read_csv(f, **kw) if f.exists() else None


def final_change(r):
    if r.text_change in ("no_prior", "not_comparable") or pd.isna(r.text_change):
        return "no_prior"
    if r.text_change == "unchanged":
        return "unchanged"
    if isinstance(r.change_vs_prior_llm, str) and r.change_vs_prior_llm in LLM_TO_LABEL:
        return LLM_TO_LABEL[r.change_vs_prior_llm]
    return "pending_llm"


def main():
    companies = pd.read_csv(COMPANIES_CSV)
    idx = read("part1_snapshot_index.csv", dtype={"timestamp": str})
    text = read("part1_text.csv")
    change = read("part1_change.csv").rename(columns={
        "changed_from_prior": "text_change", "similarity_to_prior": "text_similarity_to_prior"})
    gaps = read("part1_gaps.csv")
    llm = read("part1_llm_snapshots.csv")
    notes = read("part1_llm_notes.csv")

    df = idx[["ticker", "year", "candidate_url", "page_type", "timestamp"]] \
        .merge(companies, on="ticker") \
        .merge(text[["ticker", "year", "page_text_clean", "n_chars", "extraction_flag"]],
               on=["ticker", "year"], how="left") \
        .merge(change, on=["ticker", "year"], how="left") \
        .merge(gaps[["ticker", "year", "gap_reason", "explanation"]], on=["ticker", "year"], how="left")
    df = df.merge(llm, on=["ticker", "year"], how="left") if llm is not None else \
        df.assign(page_content_type=None, theme_categories=None, primary_themes=None,
                  theme_evidence=None, other_themes=None, change_vs_prior_llm=None, change_summary=None,
                  themes_from_year=None)
    df = df.merge(notes, on=["ticker", "year"], how="left") if notes is not None else \
        df.assign(analyst_notes=None)

    usable = df.extraction_flag == "ok"
    df["observation_status"] = ["observed" if ok else (g if isinstance(g, str) else "unusable")
                                for ok, g in zip(usable, df.gap_reason)]
    # the firm-level LLM call occasionally omits a year; fall back to a
    # note built from that year's step-5 coding, marked as automatic
    auto = usable & df.analyst_notes.isna()
    df.loc[auto, "analyst_notes"] = [
        f"[auto] page type: {r.page_content_type}; primary themes: {r.primary_themes or 'none'}"
        + (f"; change: {r.change_summary}" if isinstance(r.change_summary, str) and r.change_summary else "")
        for r in df[auto].fillna({"primary_themes": ""}).itertuples()]
    df["gap_explanation"] = df.explanation
    # text of unusable pages is not analysed; keep it out of the clean column
    df.loc[~usable, "page_text_clean"] = None
    df["wayback_url"] = [f"https://web.archive.org/web/{t}/{u}" if pd.notna(t) else None
                         for t, u in zip(df.timestamp, df.candidate_url)]
    df["changed_from_prior"] = [final_change(r) if ok else None
                                for r, ok in zip(df.itertuples(), usable)]
    df = df.rename(columns={"sector_assignment": "sector", "candidate_url": "source_url",
                            "timestamp": "wayback_timestamp"})

    cols = ["ticker", "company_name", "sector", "gics_sector_actual", "year",
            "observation_status", "gap_explanation",
            "source_url", "page_type", "wayback_timestamp", "wayback_url",
            "page_content_type", "page_text_clean", "n_chars",
            "changed_from_prior", "text_change", "text_similarity_to_prior", "url_changed",
            "change_summary", "theme_categories", "primary_themes", "themes_from_year", "theme_evidence",
            "other_themes", "analyst_notes"]
    out = df[cols].sort_values(["ticker", "year"])
    out.to_csv(OUTPUTS / "part1_company_year.csv", index=False, encoding="utf-8")
    print(f"{len(out)} rows; observed {int((out.observation_status == 'observed').sum())}")
    print(out.changed_from_prior.value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
