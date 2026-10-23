"""
Part 2, step 3: trends, sector differences and event windows in the proxies.

Input : data/outputs/part2_firm_year.csv
Output: data/outputs/part2_results.txt
        part2_disclosures/fig_stakeholder_trends.png

Three questions from the brief:
  1. Change within companies over time: yearly means on a balanced panel
     (firms with a proxy in every year), and how many firms moved up or down.
  2. Cross-company and cross-sector variation: sector means; share of
     variance between firms.
  3. Shifts around external events, by proxy filing year (a proxy filed in
     year t reports on year t-1):
       2016-2020  baseline
       2021-2023  after 2020 (racial-justice protests, COVID-19, the SEC's
                  human-capital disclosure rule of Nov 2020, investor
                  pressure on climate and board diversity)
       2024       after the Supreme Court's June 2023 affirmative-action
                  ruling (SFFA) and the wider pushback on DEI
"""
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from shared import plotstyle as ps  # noqa: E402
from shared.value_codebook import CATEGORY_IDS, CODEBOOK  # noqa: E402

PROCESSED = REPO / "data" / "intermediate"   # intermediate files
OUTPUTS = REPO / "data" / "outputs"          # final datasets and results
HERE = Path(__file__).parent
STAKEHOLDER = ["diversity_inclusion", "environment_sustainability",
               "employee_wellbeing_development", "community_social_impact"]
TONE = ["tone_commitment", "tone_hedging", "tone_numbers"]
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def period(y):
    return "2016-20 baseline" if y <= 2020 else "2021-23 post-2020" if y <= 2023 else "2024 post-SFFA"


def main():
    df = pd.read_csv(OUTPUTS / "part2_firm_year.csv")
    ok = df[df.proxy_status == "ok"].copy()
    rates = [f"rate_{c}" for c in CATEGORY_IDS]
    say(f"{len(ok)} proxies from {ok.ticker.nunique()} firms; median {int(ok.n_words.median()):,} words")
    say("Rates are mentions per 10,000 words.")

    n_years = ok.groupby("ticker").year.nunique()
    bal = ok[ok.ticker.isin(n_years[n_years == 9].index)]
    say(f"\n1. Over time (balanced panel, {bal.ticker.nunique()} firms with all 9 proxies)")
    say(bal.groupby("year")[rates + TONE].mean().round(1).T.to_string())

    piv = bal.pivot(index="ticker", columns="year", values="rate_diversity_inclusion")
    say(f"\n   DEI language, firm by firm: up 2016->2022 in {(piv[2022] > piv[2016]).mean():.0%} of firms; "
        f"down 2022->2024 in {(piv[2024] < piv[2022]).mean():.0%}")

    say("\n2. By sector (all proxies)")
    say(ok.groupby("sector")[rates + TONE].mean().round(1).T.to_string())
    for c in STAKEHOLDER:
        col = f"rate_{c}"
        between = ok.groupby("ticker")[col].transform("mean").var() / ok[col].var()
        say(f"   {c}: {between:.0%} of variance is between firms")

    ok["period"] = ok.year.map(period)
    say("\n3. Event windows (mean per period, balanced panel)")
    bal = bal.assign(period=bal.year.map(period))
    say(bal.groupby("period")[[f"rate_{c}" for c in STAKEHOLDER] + TONE].mean().round(1).T.to_string())

    # figure: stakeholder language over time
    fig, ax = ps.figure()
    means = bal.groupby("year")[[f"rate_{c}" for c in STAKEHOLDER]].mean()
    for i, c in enumerate(STAKEHOLDER):
        y = means[f"rate_{c}"]
        ax.plot(y.index, y.values, color=ps.SERIES[i], linewidth=2, marker="o", markersize=4,
                label=CODEBOOK[c]["label"])
    ps.end_labels(ax, 2024.15, [(means[f"rate_{c}"].iloc[-1], CODEBOOK[c]["label"]) for c in STAKEHOLDER],
                  min_gap=1.3)
    ax.axvspan(2020.5, 2023.5, color=ps.GRID, alpha=0.5, linewidth=0)
    ax.set_xlim(2015.6, 2026.6)
    ax.set_xticks(range(2016, 2025))
    ax.set_ylabel("mentions per 10,000 words", color=ps.MUTED, fontsize=9)
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=8, loc="upper left", labelcolor=ps.INK2)
    ps.title(ax, "Stakeholder language in proxy statements, 2016-2024",
             f"{bal.ticker.nunique()} firms with a proxy every year; shaded: proxies filed 2021-23 (reporting on 2020-22)")
    ps.save(fig, HERE / "fig_stakeholder_trends.png")
    (OUTPUTS / "part2_results.txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
