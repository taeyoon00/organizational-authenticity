"""
Part 3: the Organizational Authenticity Index (OAI).

Inputs : data/outputs/part1_company_year.csv  (stated values, Part 1)
         data/outputs/part2_firm_year.csv     (disclosed emphasis, Part 2)
Outputs: data/outputs/part3_index.csv          (one row per company-year)
         data/outputs/part3_results.txt        (distribution and validity checks)

Definition (DECISIONS.md, D-013). For each company-year, over the 12 value
categories of the shared codebook:
  S  stated score     2 = primary value on the About/values page,
                      1 = mentioned, 0 = absent                       (Part 1)
  D  disclosed score  the category's share of value language in that
                      year's proxy statement, standardised against all
                      firms in the same year (z-score)                 (Part 2)
  OAI = Spearman rank correlation between S and D across the 12 categories.

Read: OAI near +1, the values a firm puts first on its website are the ones
its proxy gives more attention than other firms do; near 0, no relation;
negative, the proxy emphasises what the website does not. Standardising D
within year removes what every proxy shares (pay-for-performance language,
the market-wide rise of ESG/DEI reporting), so the index compares a firm
with its peers, not with the genre.

Also reported: n_stated (categories on the website) and
n_stated_not_disclosed (stated categories that the proxy emphasises less
than the average firm): a count a non-technical reader can interpret.

Validity check (placebo): if the index captures firm-specific alignment,
a firm's stated values should match its *own* proxy better than the
proxies of other firms in the same year.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from shared import plotstyle as ps  # noqa: E402
from shared.value_codebook import CATEGORY_IDS  # noqa: E402

PROCESSED = REPO / "data" / "intermediate"   # intermediate files
OUTPUTS = REPO / "data" / "outputs"          # final datasets and results
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def stated_scores(p1):
    def score(row):
        present = set(str(row.theme_categories).split(";"))
        primary = set(str(row.primary_themes).split(";"))
        return [2 if c in primary else 1 if c in present else 0 for c in CATEGORY_IDS]
    obs = p1[p1.observation_status == "observed"]
    return pd.DataFrame([score(r) for r in obs.itertuples()], columns=CATEGORY_IDS,
                        index=pd.MultiIndex.from_frame(obs[["ticker", "year"]]))


def disclosed_scores(p2):
    ok = p2[p2.proxy_status == "ok"].set_index(["ticker", "year"])
    share = ok[[f"share_{c}" for c in CATEGORY_IDS]]
    share.columns = CATEGORY_IDS
    # z-score within year: emphasis relative to the other firms that year
    return share.groupby(level="year").transform(lambda s: (s - s.mean()) / s.std(ddof=0))


def spearman(a, b):
    a, b = pd.Series(a).rank(), pd.Series(b).rank()
    if a.nunique() < 2 or b.nunique() < 2:
        return np.nan                     # e.g. a page coded with no value at all
    return float(np.corrcoef(a, b)[0, 1])


def main():
    p1 = pd.read_csv(OUTPUTS / "part1_company_year.csv")
    p2 = pd.read_csv(OUTPUTS / "part2_firm_year.csv")
    S, D = stated_scores(p1), disclosed_scores(p2)
    both = S.index.intersection(D.index)

    rows = []
    for key in both:
        s, d = S.loc[key].values, D.loc[key].values
        # placebo: the same stated profile against other firms' proxies that year
        others = [k for k in D.index if k[1] == key[1] and k[0] != key[0]]
        own = spearman(s, d)
        placebo = np.nanmean([spearman(s, D.loc[k].values) for k in others]) if not np.isnan(own) else np.nan
        rows.append({"ticker": key[0], "year": key[1], "oai": own,
                     "oai_placebo": placebo,
                     "n_stated": int((s > 0).sum()),
                     "n_stated_not_disclosed": int(((s > 0) & (d < 0)).sum())})
    idx = pd.DataFrame(rows).merge(p1[["ticker", "year", "company_name", "sector"]], on=["ticker", "year"])
    idx = idx[["ticker", "company_name", "sector", "year", "oai", "oai_placebo",
               "n_stated", "n_stated_not_disclosed"]].sort_values(["ticker", "year"])
    idx.to_csv(OUTPUTS / "part3_index.csv", index=False)

    v = idx.dropna(subset=["oai"])
    say(f"OAI computed for {len(v)} company-years ({v.ticker.nunique()} firms); "
        f"{len(both) - len(v)} undefined (no stated value variation)")
    say(f"\nDistribution: mean {v.oai.mean():.2f}, sd {v.oai.std():.2f}, "
        f"quartiles {v.oai.quantile(.25):.2f} / {v.oai.median():.2f} / {v.oai.quantile(.75):.2f}, "
        f"min {v.oai.min():.2f}, max {v.oai.max():.2f}")
    between = v.groupby("ticker").oai.transform("mean").var() / v.oai.var()
    say(f"Share of variance between firms: {between:.0%} (the rest is change within firms over time)")
    say("\nBy sector (mean OAI):")
    say(v.groupby("sector").oai.agg(["mean", "std", "count"]).round(2).to_string())
    say("\nBy year (mean OAI):")
    say(v.groupby("year").oai.mean().round(2).to_string())

    d = v.oai - v.oai_placebo
    say(f"\nValidity (placebo): own-proxy OAI {v.oai.mean():.2f} vs other-firm proxies {v.oai_placebo.mean():.2f}; "
        f"own higher in {(d > 0).mean():.0%} of company-years; "
        f"mean difference {d.mean():.2f} (t = {d.mean() / (d.std() / np.sqrt(len(d))):.1f})")
    firm = v.groupby(["ticker", "company_name"]).oai.mean().sort_values()
    say("\nLowest firm averages:\n" + firm.head(5).round(2).to_string())
    say("\nHighest firm averages:\n" + firm.tail(5).round(2).to_string())
    firm_figure(v)
    (OUTPUTS / "part3_results.txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")


def firm_figure(v):
    """Each firm's average OAI (dot) and its range over the years (line)."""
    g = v.groupby(["ticker", "sector"]).oai.agg(["mean", "min", "max"]).reset_index().sort_values("mean")
    sectors = sorted(g.sector.unique())
    fig, ax = ps.figure(7.5, 9)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=ps.GRID, linewidth=0.8)
    for i, r in enumerate(g.itertuples()):
        ax.plot([r.min, r.max], [i, i], color=ps.AXIS, linewidth=1.5, zorder=1)
        ax.scatter(r.mean, i, s=36, color=ps.SERIES[sectors.index(r.sector)],
                   edgecolor=ps.SURFACE, linewidth=1.5, zorder=2)
    ax.axvline(0, color=ps.MUTED, linewidth=1)
    ax.set_yticks(range(len(g)))
    ax.set_yticklabels(g.ticker, fontsize=7.5, color=ps.INK2)
    ax.set_ylim(-1, len(g))
    ax.set_xlabel("OAI: rank correlation of stated and disclosed value priorities", color=ps.MUTED, fontsize=9)
    for k, sec in enumerate(sectors):
        ax.scatter([], [], s=36, color=ps.SERIES[k], label=sec)
    ax.legend(frameon=False, fontsize=8, loc="lower right", labelcolor=ps.INK2)
    ps.title(ax, "Organizational Authenticity Index by firm",
             "Dot: 2016-2024 average; line: lowest to highest year")
    ps.save(fig, Path(__file__).parent / "fig_oai_by_firm.png")


if __name__ == "__main__":
    main()
