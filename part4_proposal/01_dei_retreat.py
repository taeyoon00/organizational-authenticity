"""
Part 4: When firms took DEI off their website, did their disclosures follow?

Inputs : data/outputs/part1_company_year.csv, part2_firm_year.csv
Outputs: data/outputs/part4_results.txt, part4_firm_changes.csv
         part4_proposal/fig_stated_vs_disclosed.png

Motivation. Part 1 found that diversity & inclusion language on corporate
About pages rose to a peak in 2022-23 and fell in 2024. A retreat in
*stated* values can mean two different things for authenticity:
  - the firm changed what it does (website and disclosures both fall), or
  - the firm changed only what it says on its most public page, while its
    formal disclosures keep reporting the same programmes ("quiet keeping"),
    or the reverse.
Comparing the two channels for the same firms separates these readings.

Design. Firms observed in Part 1 in both 2022 and 2024 and with a proxy in
both years are grouped by their *website*:
  dropped  DEI stated in 2022, not in 2024
  kept     DEI stated in both years
  never    DEI stated in neither year
and we compare the change in their *proxy* DEI rate (mentions per 10,000
words) from 2022 to 2024. Environment & sustainability is run the same way
as a comparison category. With ~40 firms this is exploratory: group sizes
are small and no causal claim is made.
"""
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from shared import plotstyle as ps  # noqa: E402

PROCESSED = REPO / "data" / "intermediate"   # intermediate files
OUTPUTS = REPO / "data" / "outputs"          # final datasets and results
HERE = Path(__file__).parent
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def stated(p1, cat):
    obs = p1[p1.observation_status == "observed"]
    return obs.assign(s=obs.theme_categories.fillna("").str.split(";").apply(lambda x: cat in x)) \
        .pivot(index="ticker", columns="year", values="s")


def compare(p1, p2, cat, a=2022, b=2024):
    s = stated(p1, cat)
    d = p2[p2.proxy_status == "ok"].pivot(index="ticker", columns="year", values=f"rate_{cat}")
    firms = s.index[s[a].notna() & s[b].notna()].intersection(d.index[d[a].notna() & d[b].notna()])
    g = pd.DataFrame({"stated_before": s.loc[firms, a].astype(bool), "stated_after": s.loc[firms, b].astype(bool),
                      "proxy_before": d.loc[firms, a], "proxy_after": d.loc[firms, b]})
    g["group"] = ["dropped" if x and not y else "kept" if x and y else "added" if y else "never"
                  for x, y in zip(g.stated_before, g.stated_after)]
    g["proxy_change"] = g.proxy_after - g.proxy_before
    g["proxy_change_pct"] = (g.proxy_change / g.proxy_before.replace(0, pd.NA) * 100).astype(float).round(0)
    say(f"\n{cat}: {len(g)} firms observed on both channels in {a} and {b}")
    say(g.groupby("group").agg(firms=("proxy_change", "size"),
                               proxy_before=("proxy_before", "mean"), proxy_after=("proxy_after", "mean"),
                               mean_change=("proxy_change", "mean"),
                               median_change_pct=("proxy_change_pct", "median"),
                               share_proxy_down=("proxy_change", lambda x: (x < 0).mean())).round(2).to_string())
    for grp in ("dropped", "added"):
        rows = g[g.group == grp]
        if len(rows):
            say(f"   {grp}: " + ", ".join(f"{t} ({r.proxy_before:.1f}->{r.proxy_after:.1f})" for t, r in rows.iterrows()))
    return g.assign(category=cat)


def trend_figure(p1, p2):
    """Website vs proxy DEI over time, each indexed to 2016 = 100 (one axis)."""
    s = stated(p1, "diversity_inclusion")
    s = s[s.notna().all(axis=1)].astype(float)          # firms observed every year
    ok = p2[p2.proxy_status == "ok"]
    d = ok.pivot(index="ticker", columns="year", values="rate_diversity_inclusion").dropna()
    web = s.mean() / s.mean()[2016] * 100
    prx = d.mean() / d.mean()[2016] * 100
    fig, ax = ps.figure()
    for i, (y, lab) in enumerate([(web, f"Website: share of firms stating D&I ({len(s)} firms)"),
                                  (prx, f"Proxy: D&I mentions per 10,000 words ({len(d)} firms)")]):
        ax.plot(y.index, y.values, color=ps.SERIES[i], linewidth=2, marker="o", markersize=4, label=lab)
        ax.text(y.index[-1] + 0.15, y.values[-1], f"{y.values[-1]:.0f}", color=ps.INK2, fontsize=8, va="center")
    ax.axhline(100, color=ps.AXIS, linewidth=1)
    ax.set_xticks(range(2016, 2025))
    ax.set_xlim(2015.6, 2024.8)
    ax.set_ylabel("index, 2016 = 100", color=ps.MUTED, fontsize=9)
    ax.legend(frameon=False, fontsize=8, loc="upper left", labelcolor=ps.INK2)
    ps.title(ax, "Diversity & inclusion: what firms say vs. what they disclose",
             "Both series indexed to their 2016 level")
    ps.save(fig, HERE / "fig_stated_vs_disclosed.png")
    say("\nIndexed trend (2016 = 100): website / proxy")
    say(pd.DataFrame({"website": web.round(0), "proxy": prx.round(0)}).T.to_string())


def main():
    p1 = pd.read_csv(OUTPUTS / "part1_company_year.csv")
    p2 = pd.read_csv(OUTPUTS / "part2_firm_year.csv")
    out = pd.concat([compare(p1, p2, "diversity_inclusion"),
                     compare(p1, p2, "environment_sustainability")])
    out.to_csv(OUTPUTS / "part4_firm_changes.csv")
    trend_figure(p1, p2)
    (OUTPUTS / "part4_results.txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
