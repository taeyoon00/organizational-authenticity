"""
Step 7: validity and reliability checks on the LLM coding.

Inputs : data/outputs/part1_company_year.csv   (step 6)
         data/intermediate/part1_llm_snapshots.csv  (step 5, incl. *_raw coding)
         data/intermediate/part1_change_review.csv  (human labels, filled by hand)
Output : data/outputs/part1_validation.txt     (all figures, quoted in the README)
         data/intermediate/part1_llm_validation.csv (pair-level human vs LLM)

Three checks:
1. Reliability (test-retest). Pages whose text is byte-identical in two
   consecutive years were coded independently by the model (raw coding,
   before the inheritance rule of step 5). Agreement between the two codings
   measures how stable single-pass coding is.
2. Convergent validity against a dictionary coder. For categories with a
   distinctive vocabulary, a transparent keyword list is a second, fully
   reproducible coder. Agreement with the LLM is reported per category with
   Cohen's kappa. The dictionary is cruder (it cannot tell a value from a
   passing mention), so moderate agreement is expected; very low agreement
   would signal a problem with the LLM coding of that category.
3. Change judgements against a human coder, on the 30-pair review sample
   (04b_review_sample.py). Runs once human_label is filled in. LLM labels
   are mapped onto the human vocabulary:
     values_content_changed, wording_only -> values_change
     non_values_content_changed           -> other_content
     no_substantive_change                -> extraction
     different_page                       -> page_switch
"""
import re
import sys

import pandas as pd

from common import OUTPUTS, PROCESSED, REPO

sys.path.insert(0, str(REPO))
from shared.value_codebook import CATEGORY_IDS  # noqa: E402

TO_HUMAN = {
    "values_content_changed": "values_change",
    "wording_only": "values_change",
    "non_values_content_changed": "other_content",
    "no_substantive_change": "extraction",
    "different_page": "page_switch",
}

# second coder for categories with a distinctive vocabulary
LEXICON = {
    "diversity_inclusion": r"\bdivers(e|ity)\b|\binclusi(on|ve|vity)\b|\bbelonging\b|\bequit(y|able)\b(?! (market|investment|fund|capital|stake))",
    "environment_sustainability": r"\bsustainab\w*|\bclimate\b|\bemissions?\b|\bnet[- ]zero\b|\brenewable\b|\benvironment(al)?\b|\bplanet\b|\bcarbon\b",
    "community_social_impact": r"\bcommunit(y|ies)\b|\bphilanthrop\w*|\bvolunteer\w*|\bgiv(e|ing) back\b|\bsocial impact\b",
    "integrity": r"\bintegrity\b|\bethic(s|al)\b|\bhonest\w*|\btransparen\w*|\bdo(ing)? the right thing\b",
    "innovation": r"\binnovat\w*|\binvent\w*|\bpioneer\w*|\bbreakthrough\w*",
    "customer": r"\bcustomers?\b|\bclients?\b|\bpatients?\b|\bguests?\b|\bconsumers?\b",
}

OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def kappa(a, b):
    """Cohen's kappa for two label series of equal length."""
    a, b = pd.Series(list(a)), pd.Series(list(b))
    labels = sorted(set(a) | set(b))
    p_obs = (a.values == b.values).mean()
    p_exp = sum((a == l).mean() * (b == l).mean() for l in labels)
    return (p_obs - p_exp) / (1 - p_exp) if p_exp < 1 else 1.0


def cats(s):
    return set(str(s).split(";")) - {"", "nan"}


def reliability(snap, text):
    t = text.set_index(["ticker", "year"]).page_text_clean
    s = snap.set_index(["ticker", "year"])
    pairs = [(k, (k[0], k[1] - 1)) for k in s.index
             if (k[0], k[1] - 1) in s.index and t.get(k) == t.get((k[0], k[1] - 1))]
    say(f"1. Reliability: {len(pairs)} consecutive-year pairs with byte-identical text, coded independently")
    a = [cats(s.theme_categories_raw[x]) for x, _ in pairs]
    b = [cats(s.theme_categories_raw[y]) for _, y in pairs]
    jac = [len(x & y) / max(1, len(x | y)) for x, y in zip(a, b)]
    say(f"   identical theme sets {sum(x == y for x, y in zip(a, b)) / len(pairs):.0%}, "
        f"mean Jaccard {sum(jac) / len(jac):.2f}")
    for c in CATEGORY_IDS:
        xa, xb = [c in x for x in a], [c in y for y in b]
        say(f"   {c:32s} agreement {sum(p == q for p, q in zip(xa, xb)) / len(pairs):.0%}  kappa {kappa(xa, xb):.2f}")
    say("   -> the final dataset therefore carries a page's coding forward while its text is unchanged (step 5)")


def lexicon_check(final):
    obs = final[final.observation_status == "observed"]
    say(f"\n2. Convergent validity: LLM vs dictionary coder, {len(obs)} observed pages")
    for c, pat in LEXICON.items():
        rx = re.compile(pat, re.I)
        lex = obs.page_text_clean.apply(lambda t: bool(rx.search(str(t))))
        llm = obs.theme_categories.apply(lambda s: c in cats(s))
        say(f"   {c:28s} LLM {llm.mean():.0%}  dictionary {lex.mean():.0%}  "
            f"agreement {(lex == llm).mean():.0%}  kappa {kappa(lex, llm):.2f}  "
            f"LLM-only {(llm & ~lex).sum()}  dictionary-only {(lex & ~llm).sum()}")


def human_check(snap):
    review = pd.read_csv(PROCESSED / "part1_change_review.csv", dtype={"human_label": str, "notes": str})
    review = review[review.human_label.notna() & (review.human_label.str.strip() != "")]
    say("\n3. Change judgements vs human coder")
    if review.empty:
        say("   no human labels yet: fill human_label in part1_change_review.csv")
        return
    df = review.merge(snap[["ticker", "year", "change_vs_prior_llm", "change_summary"]],
                      on=["ticker", "year"], how="left")
    df["human"] = df.human_label.str.strip().str.lower()
    df["llm"] = df.change_vs_prior_llm.map(TO_HUMAN)
    df = df[df.llm.notna()]
    say(f"   {len(df)} pairs with both labels")
    say(pd.crosstab(df.human, df.llm, margins=True).to_string())
    say(f"   4-label agreement {(df.human == df.llm).mean():.0%}, kappa {kappa(df.human, df.llm):.2f}")
    hb, lb = df.human == "values_change", df.llm == "values_change"
    say(f"   'did the stated values change?' agreement {(hb == lb).mean():.0%}, kappa {kappa(hb, lb):.2f}")
    df[["ticker", "year", "similarity", "url_changed", "human", "llm", "change_summary", "notes"]] \
        .to_csv(PROCESSED / "part1_llm_validation.csv", index=False)


def main():
    snap = pd.read_csv(PROCESSED / "part1_llm_snapshots.csv")
    text = pd.read_csv(PROCESSED / "part1_text.csv")
    final = pd.read_csv(OUTPUTS / "part1_company_year.csv")
    reliability(snap, text)
    lexicon_check(final)
    human_check(snap)
    (OUTPUTS / "part1_validation.txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
