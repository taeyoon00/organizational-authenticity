# Organizational Authenticity: do firms disclose what they say they value?

50 large S&P 500 firms (10 in each of five sectors), 2016–2024.

## The study in one page

**Question.** Do the values a company *says* it holds match what its formal disclosures suggest it *prioritises*?

**1. What firms say (Part 1).** We retrieved each firm's archived "About us" or values page for every year from the Wayback Machine. We got **425 of 450 company-years**, and every gap is documented. A local language model coded each page against **12 value themes**: the nine "Culture 500" values plus environment, community and employee wellbeing. Firms lead with performance (63% of pages), innovation (54%) and customers (50%). Stakeholder values (DEI, environment, respect, community) rose to a peak in 2021–23 and fell back in 2024.

**2. What firms disclose (Part 2).** We collected **all 450 annual proxy statements** from SEC EDGAR and counted the same 12 themes. Diversity & inclusion language tripled from 2016 to 2022, then fell 19% by 2024. Environment language rose 3.5× and stayed high. Tone became more committed and less hedged.

**3. The Authenticity Index (Part 3).** For each firm-year, the index measures how well the *ranking* of values on the website matches the ranking of attention in the proxy, relative to other firms that year. It runs from −1 to +1. On average alignment is weak (0.09) but varies widely across firms and years. Healthcare is the most aligned sector. Validity check: a firm's website matches its **own** proxy better than other firms' proxies (0.09 vs 0.00, t = 6.0).

**4. Our extra analysis (Part 4).** Did firms that removed DEI from their website also cut it from their disclosures? Mostly yes, but **so did firms that kept it**. The disclosure retreat was market-wide. Some firms moved the two channels in opposite directions: Schwab dropped DEI from its website while its proxy DEI language rose tenfold. Environment language kept rising in proxies even where websites dropped it. **Websites and disclosures run on different clocks**, so authenticity has to be measured on both.

**Main limitations.** Disclosures are talk, not behaviour. Website coding by a small model is noisy (κ 0.49–0.96 by theme). A keyword count cannot read intent. Details and remedies are in each part's README.

## Where to find things

| Part | Read first | Data produced |
|---|---|---|
| 1. Stated values | [README](part1_stated_values/README.md) (summary at top) | `data/outputs/part1_company_year.csv` |
| 2. Disclosed values | [README](part2_disclosures/README.md) (summary at top) | `data/outputs/part2_firm_year.csv` |
| 3. Authenticity Index | [README](part3_authenticity_index/README.md) (summary at top) | `data/outputs/part3_index.csv` |
| 4. Own proposal | [README](part4_proposal/README.md) (summary at top) | `data/outputs/part4_firm_changes.csv` |
| Every judgement call | [DECISIONS.md](DECISIONS.md) (D-001 – D-014) | |

### Folder map
```
README.md                  this page: start here
DECISIONS.md               every judgement call, with the alternative rejected
data/
  companies.csv            the 50 firms (sector, SEC identifiers)
  outputs/                 FINAL RESULTS: one dataset per part + the figures' numbers
  intermediate/            working files, needed only to re-run the pipeline
part1_stated_values/       code and README for Part 1
part2_disclosures/         code, README and figure for Part 2
part3_authenticity_index/  code, README and figure for Part 3
part4_proposal/            code, README and figure for Part 4
shared/                    the 12-theme codebook and the figure style, used by every part
```

## How to run
```bash
python -m venv .venv && .venv\Scripts\activate        # Windows; source .venv/bin/activate elsewhere
pip install -r requirements.txt
```
- **Part 1:** see its README. Needs [Ollama](https://ollama.com) with `qwen2.5:7b-instruct` (free, local). About 3 hours the first time.
- **Part 2:** `set SEC_USER_AGENT=Your Name you@example.com`, then `python part2_disclosures/01_collect_proxies.py`, `02_measure.py`, `03_analyze.py`. About 40 minutes.
- **Parts 3–4:** `python part3_authenticity_index/01_build_index.py`, `python part4_proposal/01_dei_retreat.py`. Seconds.

All network and model results are cached, so re-runs are fast and interrupted runs resume. Raw HTML and proxy texts are not committed. They are re-downloadable from the URLs and timestamps recorded in the data files.

## Design principles
- **Built to scale from 50 to 500 firms.** Every step is a script driven by two input lists (firms, candidate URLs). Fixes are rules, not hand edits. Everything runs on free sources (Wayback Machine, SEC EDGAR, a local open-weight model).
- **One codebook for both sides.** Stated and disclosed values are measured in the same 12 categories, so they can be compared directly.
- **Every gap and every choice is written down.** Missing data is kept with its reason, and DECISIONS.md records each choice with the alternative rejected.
