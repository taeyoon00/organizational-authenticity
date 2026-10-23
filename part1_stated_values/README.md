# Part 1 — Stated values from archived "About Us" pages

**Question.** What values do 50 large S&P 500 firms *say* they hold on their corporate About / mission / values page, and how did that self-description change from 2016 to 2024?

**Output.** [`data/outputs/part1_company_year.csv`](../data/outputs/part1_company_year.csv): one row per company-year (50 × 9 = 450 rows), including the years with no usable page, each with the reason.
Every judgment call, with the alternatives rejected, is in [`../DECISIONS.md`](../DECISIONS.md) (D-001 to D-011).

## Summary (non-technical)

### What we did
For 50 of the largest S&P 500 companies (ten each in technology, financials, healthcare, consumer discretionary and energy), we retrieved the archived version of each firm's "About us" or values page for every year from 2016 to 2024 from the Internet Archive. Where a firm had a dedicated values page (Johnson & Johnson's *Credo*, *The Chevron Way*, Amazon's *Leadership Principles*), we used it. A language model then recorded which of twelve values each page expresses, and whether the values content changed from the previous year.

We recovered a usable page for **425 of the 450 company-years (94%)**. Every missing year has a recorded reason. Most are recent site redesigns whose text is loaded by the browser and was never archived (Broadcom, Eli Lilly, Nike), or pages a firm had taken down.

### What we found

**1. Firms lead with performance, innovation and customers.** Across all pages, the most common stated values are performance and growth (63% of pages), innovation (54%) and customer focus (50%). Stakeholder values appear less often: environment (43%), employee wellbeing and development (33%), diversity and inclusion (29%), integrity (28%), community (26%).

**2. Sectors talk about different things.** Technology firms stress innovation (80% of their pages) and diversity and inclusion (51%). Healthcare firms put patients and customers first (79%). Energy firms rarely mention customers (17%) but emphasise integrity (38%) and the environment (51%). Financial firms mention innovation least (22%).

**3. Stakeholder language rose to a peak in 2021–2023 and fell back in 2024.** Among the 40 firms observed in every year:

| Share of firms whose page states… | 2016 | 2022 | 2024 |
|---|---|---|---|
| Diversity & inclusion | 20% | 42% | 32% |
| Environment & sustainability | 38% | 57% | 48% |
| Respect for people | 22% | 35% | 18% |
| Community & social impact (peak 2021: 35%) | 25% | 32% | 22% |

The rise follows the period after 2020, when calls for corporate action on racial equity and climate were strongest. The fall coincides with the political and legal pushback on DEI after 2023.

**4. Stated values are revised often.** When a page's text changed from one year to the next, the model judged that the *values* themselves changed in 129 of 372 year-on-year comparisons (35%). 43 of the 50 firms changed their stated values at least once. Revisions are most frequent in technology (46% of comparisons) and healthcare (45%), and least frequent in consumer discretionary (21%).

### What this means
- **Stated values are not fixed.** Any measure built on them, including the authenticity index in Part 3, has to treat them as changing year by year, not as a single snapshot.
- **Compare firms within their sector.** "Low on environment" means something different for a bank than for an oil company, so stated values should be judged against sector norms.
- **The 2024 pullback is the most useful signal for this study.** If a firm dropped diversity or community language from its website, did its disclosures (Part 2) also drop the substance, or only the words? A gap between the two is what an authenticity measure should pick up.

### How far to trust this
- **Coverage is good, but not complete or random.** The missing years cluster in recent technology and consumer redesigns.
- **The coding model is small and free to run, so we checked it.** Coding the same page twice gave the same result for each value 89–98% of the time. Where a page's text did not change, we kept last year's coding, so this noise does not appear as change.
- **Agreement with a simple keyword count is moderate (κ 0.30–0.57).** The model is stricter: it ignores passing mentions such as "communities" in a business description.
- **A human check of the change judgements is in progress.** The 35% revision rate should be read as provisional until it is done.
- **The model's free-text notes contain occasional factual errors.** Treat them as pointers to the archived pages (linked for every row), not as evidence.

---

## Technical notes

## 1. What was done

| Step | Script | What it does | Main output |
|---|---|---|---|
| 1 | `01_find_snapshots.py` | Queries the Wayback Machine **CDX API** for each candidate URL; picks, per year, the capture closest to 1 July (live pages before redirects, candidates in priority order) | `part1_snapshot_index.csv`, `part1_coverage_matrix.csv` |
| 2 | `02_download_snapshots.py` | Downloads the raw archived HTML (`id_` URLs, no Wayback toolbar); follows and logs redirect chains; flags dead pages, homepage redirects and redirects into other years | raw HTML (not committed), `part1_download_log.csv` |
| 3 | `03_extract_text.py` | Extracts visible body text (trafilatura, BeautifulSoup fallback), strips site-search widgets; flags error pages, JavaScript shells and menu-only pages | `part1_text.csv` |
| — | `run_part1.py` | Runs 1–3 in a loop: any snapshot rejected by step 2 or 3 makes step 1 fall back to the next capture or the next candidate URL, until nothing new is rejected | `part1_excluded_snapshots.csv` |
| 4 | `04_detect_change.py` | Deterministic year-over-year text similarity (word-level difflib) | `part1_change.csv` |
| 4b | `04b_review_sample.py` | Draws 30 changed pairs for human validation | `part1_change_review.csv` |
| 4c | `04c_gap_report.py` | Lists every missing company-year, with the reason and the snapshots tried | `part1_gaps.csv` |
| 5 | `05_llm_code_snapshots.py` | **LLM** (a) judges whether the *values content* changed, on the sentences removed/added; (b) codes value themes against a 12-category codebook, with verbatim evidence | `part1_llm_snapshots.csv` |
| 5b | `05b_llm_firm_trajectory.py` | **LLM** (c) reads each firm's nine-year series and dates linguistic shifts; writes one analyst note per year | `part1_llm_firms.csv`, `part1_llm_notes.csv` |
| 6 | `06_build_dataset.py` | Assembles the final company-year dataset | `part1_company_year.csv` |
| 7 | `07_validate_llm.py` | Reliability, convergent-validity and human-agreement checks | `part1_validation.txt` |

Shared code: `common.py` (paths, polite HTTP with back-off, rejection log), `llm.py` (model backend, cache, usage log), `../shared/value_codebook.py` (categories, also used in Part 2).

### How to run
```bash
python -m venv .venv && .venv\Scripts\activate          # Windows (source .venv/bin/activate elsewhere)
pip install -r requirements.txt
# local LLM (free): install Ollama, then
ollama pull qwen2.5:7b-instruct
cd part1_stated_values
python run_part1.py                  # steps 1-4c (network; ~1 h first time, minutes when cached)
python 05_llm_code_snapshots.py      # ~2.5 h on a 6 GB laptop GPU, cached afterwards
python 05b_llm_firm_trajectory.py    # ~30 min
python 06_build_dataset.py
python 07_validate_llm.py
```
Every network and LLM result is cached on disk, so an interrupted run resumes where it stopped and a re-run costs nothing. To use the Claude API instead of the local model: `set LLM_BACKEND=anthropic` (estimated $21 for Part 1).

---

## 2. Key decisions (details in DECISIONS.md)

- **Which page (D-003).** The firm's primary self-description of purpose / mission / values / culture. Priority, applied per year: dedicated values page (e.g. J&J *Our Credo*, *The Chevron Way*, Amazon *Leadership Principles*) > mission page > general About page. Investor-relations, careers, press and product pages excluded. Values-first means a firm can alternate between a values page and a general page across years; those years are flagged `url_changed`.
- **One snapshot per year (D-004).** Capture closest to 1 July; HTTP 200 captures before redirects. A year with no usable page stays missing: snapshots are **never borrowed from another year**.
- **Redirects (D-005).** Up to 10 hops, chain logged. Redirects to the site's homepage or into a capture from another year are rejected.
- **Rejection loop (D-010).** Dead pages, archived error pages ("soft 404"), JavaScript shells (text loaded in the browser, absent from the archive) and menu-only pages are recorded and step 1 falls back automatically; fixes are rules, not hand edits, so the pipeline scales to 500 firms.
- **Candidate URLs (D-009).** 111 candidates, found by hand and by CDX prefix searches over each firm's site; every candidate that was tried and rejected is logged.
- **Change (D-007).** Two layers: `text_change` (similarity ≥ 0.95 → unchanged; reproducible, no LLM) and `changed_from_prior` (LLM judgement on the sentences that changed: values / wording / other content / no substantive change / different page).
- **Categories (D-008).** The MIT Sloan / Glassdoor *Culture 500* "Big Nine" (agility, collaboration, customer, diversity & inclusion, execution, innovation, integrity, performance, respect) plus environment & sustainability, community & social impact, and employee wellbeing & development, which ESG / DEI disclosures report on. **The same codebook is used in Part 2**, so Part 3 compares stated and disclosed values in one space. Value language outside the codebook is captured in `other_themes`.
- **LLM (D-011).** A local open-weight model, Qwen2.5-7B-Instruct via Ollama: no cost, no data leaves the machine, weights pinned for reproducibility. JSON-schema constrained output, temperature 0. Its weaker accuracy is handled by narrow tasks (one task per call), short inputs (only changed sentences), and the validation in section 5.

---

## 3. Coverage: 425 of 450 company-years (94.4%)

| Status | Company-years | Cases |
|---|---|---|
| Observed, usable text | **425** | |
| JavaScript shell (no archived text) | 10 | AVGO 2020–24, LLY 2021–23, NKE 2023–24 |
| Not archived | 5 | LOW 2016–19, NVDA 2017 |
| Page gone (404 / homepage redirect) | 5 | ORCL 2016, MCD 2023–24, PSX 2023–24 |
| Menu / figures only | 3 | NVDA 2022, TGT 2022–23 |
| Archived error page | 1 | SBUX 2016 |
| Text too short (128 characters) | 1 | NVDA 2016 |

All 50 firms have at least four observed years; 40 firms are observed in all nine. Each gap, with the URLs and snapshots tried, is in `part1_gaps.csv`.

Of the 425 pages, the LLM classes 249 as values statements, 167 as general About pages, and 9 as not an About page: Berkshire Hathaway 2016–23, whose minimal homepage is its only candidate (kept, since it is how the firm presents itself), and Intel 2016, which on inspection is a real company overview (a model error).

---

## 4. Data dictionary — `part1_company_year.csv`

| Column | Meaning |
|---|---|
| `ticker`, `company_name` | From the assignment list |
| `sector` | Sector as given in the assignment (used for all comparisons) |
| `gics_sector_actual` | True GICS sector in Jan 2024 (GOOGL, META → Communication Services; TGT → Consumer Staples), for robustness checks (D-001) |
| `year` | 2016–2024 |
| `observation_status` | `observed`, or why not: `no_snapshot_in_year`, `all_snapshots_rejected`, `too_short` |
| `gap_explanation` | Plain-language reason for a gap |
| `source_url` | Candidate URL the snapshot came from |
| `page_type` | `values` or `about` (from the candidate list, D-003) |
| `wayback_timestamp`, `wayback_url` | The capture used; the link opens it in the Wayback Machine |
| `page_content_type` | LLM: `values_statement` / `general_about` / `mixed` / `not_an_about_page` |
| `page_text_clean` | Extracted body text (empty for gaps) |
| `n_chars` | Length of the text |
| `changed_from_prior` | **Final change label**: `unchanged`, `changed_values`, `changed_wording`, `changed_other_content`, `no_substantive_change`, `page_switch`, `no_prior` (first observed year or prior year missing) |
| `text_change` | Deterministic layer: `unchanged` (similarity ≥ 0.95), `minor_change`, `major_change`, `no_prior`, `not_comparable` |
| `text_similarity_to_prior` | Word-level similarity with the prior year, 0–1 |
| `url_changed` | Prior year came from a different URL (a change may be a page switch) |
| `change_summary` | LLM: one sentence on what changed |
| `theme_categories` | **Value categories present** (codebook ids, `;`-separated) |
| `primary_themes` | Subset that is a named value, headline or repeated emphasis |
| `themes_from_year` | Year whose coding the row carries (earlier if the text was unchanged; see 5.1) |
| `theme_evidence` | Verbatim quote supporting each category |
| `other_themes` | Value language outside the 12 categories |
| `analyst_notes` | LLM note on the year in the context of the firm's series; `[auto]` = built from the year's coding where the model gave no note |

Intermediate files, all in `data/intermediate/`, are documented in the docstring of the script that writes them.

---

## 5. Validation (`part1_validation.txt`)

**5.1 Reliability.** 96 pairs of consecutive years had byte-identical text and were coded independently. The model gave the same theme set in 61% of pairs (mean Jaccard 0.85); per category, agreement 89–98% and Cohen's κ 0.49 (agility) to 0.96 (customer). The variation comes from coding the same text twice, not from the page, so the final dataset **carries a page's coding forward while its text is unchanged** (`themes_from_year`); otherwise the noise would appear as year-to-year shifts in stated values. The raw codings are kept (`*_raw` columns in `part1_llm_snapshots.csv`).

**5.2 Convergent validity against a dictionary coder.** A transparent keyword list per category acts as a second coder:

| Category | LLM | Dictionary | Agreement | κ |
|---|---|---|---|---|
| Diversity & inclusion | 29% | 41% | 80% | 0.57 |
| Innovation | 54% | 58% | 78% | 0.56 |
| Environment & sustainability | 43% | 51% | 76% | 0.52 |
| Integrity | 28% | 44% | 75% | 0.47 |
| Customer | 50% | 68% | 70% | 0.40 |
| Community & social impact | 26% | 59% | 62% | 0.30 |

Disagreements are mostly words the dictionary counts and the LLM does not (e.g. "communities" in a business description, "clients" in a product list), which is the distinction between a value and a passing mention that the LLM is there to make.

**5.3 Change judgements against a human coder.** 30 changed pairs (`part1_change_review.csv`, with Wayback links to both years) are labelled by hand; `07_validate_llm.py` reports agreement and κ once the labels are in. *Status: human labels pending.*

**Spot checks.** The LLM recognised Amazon's 2021 addition of "Strive to be Earth's Best Employer" and "Success and Scale Bring Broad Responsibility" as a values change. Its `not_an_about_page` labels led to the menu-only check in step 3. It also produced errors that are documented rather than hidden: a J&J Credo sentence on employee health coded as *execution*, and a firm-level note claiming Amazon cut its Leadership Principles "from 16 to four" (it added two). Free-text LLM fields (`analyst_notes`, `linguistic_shifts`) should be read as leads to check against the text, not as findings.

---

## 6. Assumptions

- The page chosen by the D-003 hierarchy is the firm's stated values. Firms state values in other places too (annual reports, codes of conduct, careers pages); this measure captures the public-facing web self-description only.
- The capture nearest 1 July represents the year. Mid-year changes are dated to the year in which the July capture shows them.
- A page whose text is unchanged (similarity ≥ 0.95) states the same values.
- The assignment's sector labels are used as given (D-001); `gics_sector_actual` allows regrouping.

## 7. Known limitations

1. **Small-model coding.** A 7B model makes coding errors; reliability is acceptable for most categories (κ ≥ 0.68 for 10 of 12) but weak for agility (0.49). Category shares are more trustworthy aggregated over firms than for a single firm-year.
2. **Hallucination in free text.** Firm-level narratives can contain claims not supported by the text (see 5).
3. **Page comparability.** Values-first page choice means some firms switch between a values page and a general page; theme counts then change because the page changed (`url_changed` flags 55 such years). A general About page will list fewer values than a Credo.
4. **Archive limits.** JavaScript-rendered sites (Broadcom, Lilly, Nike in recent years) are not recoverable from archived HTML; their absence is not random (they are recent, tech-heavy redesigns).
5. **Candidate discovery is partly manual.** Prefix searches were run per firm and judged by hand; the judgement rules are documented, but the search itself is not yet a single script.
6. **One capture per year** misses changes that were reverted within the year.

## 8. With more time

- Turn candidate discovery into a script: crawl each firm's archived homepage for links matching values/culture/purpose/about, query CDX for each, score by keyword and prose share; humans review only the ranking. This is the main step needed to scale to 500 firms.
- Render JavaScript pages in a headless browser against the archive to recover the 10 shell years.
- Self-consistency coding (three runs, majority vote) or a larger model on the hard categories (agility, respect, employee wellbeing), and compare with the Claude API backend on the validation sample.
- Complete and extend the human validation (two coders, inter-coder κ) and use it to tune the change prompt.
- Segment long pages into value statements vs. other content before coding, so mixed pages (values plus news) are coded on their values part.
