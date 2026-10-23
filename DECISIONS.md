# Decision log

Each entry: what was decided, why, and what alternative was rejected.
The assignment is deliberately under-specified; this file is where those gaps are closed.

## D-001 Use the provided 50-firm list, and record where it departs from GICS
The brief says "the 10 largest by market cap in each of five GICS sectors, S&P 500 as of January 2024" **and** gives a fixed list "required for all parts". These do not fully agree:
- GOOGL and META have been GICS **Communication Services** since the September 2018 GICS restructuring, not Information Technology.
- TGT moved to GICS **Consumer Staples** in the March 2023 GICS update.
- "Healthcare" corresponds to GICS "Health Care"; "Technology" to "Information Technology".
- The Technology top 10 by January 2024 market cap would likely include firms such as ADBE, AMD, CSCO or ACN ahead of INTC/IBM (to be verified against a January 2024 market-cap snapshot).

**Decision:** keep the provided list, because it is explicitly required and keeps results comparable with other applicants. `data/companies.csv` stores both `sector_assignment` (the brief's label, used for all sector comparisons) and `gics_sector_actual`, so a robustness check can regroup firms by true GICS sector.

## D-002 Repository and reproducibility
One script per pipeline step, numbered in run order; each step reads the previous step's output from `data/intermediate/` and caches network results, so the pipeline is resumable and scales from 50 to 500 firms without code changes (only the two input CSVs grow).

## D-003 Which page counts as the "About Us" page
A page qualifies if it is the firm's primary corporate self-description of **purpose, mission, values or culture**. Priority when several exist:
1. a dedicated values / culture / credo / principles page (e.g. J&J "Our Credo", Chevron "The Chevron Way");
2. a mission / purpose page;
3. the general "About us" / "Company" page.

This hierarchy is applied **per year**, even when it makes a firm alternate between a values page and a general About page: the target construct is *stated values*, so a year in which the values page was archived should use it. The alternative (one fixed page per firm for a consistent series) was rejected because it would drop values text in years where only the general page fits the series. Page switches are flagged in step 4 (`url_changed`) and handled in analysis. *(Confirmed with Taeyoon, 2026-10-16.)*

Excluded: investor-relations pages, careers pages (except where they are the firm's canonical values statement, e.g. Amazon Leadership Principles, flagged `page_type=values`), press releases, and product pages.
Candidate URLs, with priority and notes, live in `part1_stated_values/url_candidates.csv`. Firms restructure their sites, so several historical URLs may be listed for one firm.
*Status: candidate URLs were compiled from knowledge of the sites and must be confirmed against the CDX results before the full download.*

## D-004 One snapshot per year, and missing years
- Target date: the capture closest to **1 July** of each year (mid-year avoids picking a January capture that really reflects the prior year's site).
- HTTP 200 captures preferred; redirect captures used only when no 200 exists.
- Candidate URLs are tried in priority order **per year**, so a firm may switch URL when its site was reorganised; the URL used is recorded in every row.
- Two passes per year: first the highest-priority candidate with an HTTP 200 capture; only if no candidate has one, the highest-priority candidate with a redirect capture. Without this, a dead URL that left only redirect captures (e.g. Phillips 66's old values page after 2018) blocked a live lower-priority page and produced 404s.
- If no candidate has a capture in a year, the row is kept with `missing_reason = no_snapshot_in_year`. Snapshots are **never borrowed from another year**, so each row is a genuine observation of that year.
- The CDX query is collapsed to one capture per day (`collapse=timestamp:8`): busy pages have tens of thousands of captures, which made queries slow and triggered rate limiting. Day resolution is all the "closest to 1 July" rule needs. Trade-off: if a day's first capture is a redirect, a later 200 capture on the same day is not seen; redirects are followed in step 2, so this changes which capture is fetched, not whether the year is observed.
- Politeness: requests are spaced 1.5 s apart; after an HTTP 429 the scraper waits 60 s x attempt, because short retries against the Internet Archive can escalate to a temporary IP block.

## D-005 Redirect chains
Follow up to 10 redirects; log the full chain. If the chain ends on the site's homepage, flag `redirected_to_homepage` (the About page had disappeared) and treat the row as missing unless the homepage itself carries the values text. Candidates that are themselves a site root (`about.nike.com`, `aboutschwab.com`, `berkshirehathaway.com`) are never flagged; an http->https hop to their own root is not a lost page.
If the chain lands on a capture from **another year** (the Archive redirects to the nearest capture in time, which can be years away), the row is flagged `redirect_out_of_year` and not used, per D-004.

## D-006 Text extraction
`trafilatura` main-content extraction (drops navigation, footer, cookie banners), with a BeautifulSoup fallback that removes `nav/header/footer/script/style/form/aside`. Pages with fewer than 200 characters are flagged `too_short` for manual review, not dropped.
Short pages built by a JavaScript framework (React/Next.js/Nuxt markers in the HTML) are flagged `js_rendered_shell`: their text was fetched by the browser at view time, so the archived HTML holds only a title or "Loading..." (seen for Broadcom 2019-24, Lilly 2021-23, Nike 2023-24). For such firm-years an alternative URL with server-rendered text is sought (D-009); if none exists the year is treated as unobserved. Rows failing the extraction check are labelled `not_comparable` in step 4 rather than compared, since two empty shells would otherwise score as "unchanged". HTML is read as bytes so the parsers detect the page encoding (reading as text used the Windows default code page, cp949, and corrupted characters).
Pages whose extracted text is almost entirely menus, link lists, contact blocks or stat boxes are flagged `no_prose`: fewer than 20% of their words stand in lines of eight or more words (real About/values pages score 0.86-1.0 on this share, interquartile range). The check was added after the LLM labelled some pages `not_an_about_page` (D-011): EOG's `/company` hub page, an Apple contacts page, Target's figures block, and an NVIDIA page where the fallback extractor returned the full mega-menu. Like other rejections it triggers the fallback to the next candidate (D-010); for EOG the hub page's own "Culture" link was added as a values-page candidate.
*With more time:* render these pages in a headless browser against the Wayback capture, which would recover text where the archived API responses were also captured.

## D-007 "Changed from prior year"
Deterministic first: difflib similarity between consecutive years' clean text. >= 0.95 unchanged, < 0.60 major change, otherwise minor change. Only changed pages go to the LLM for a qualitative description. Keeps the core variable reproducible and LLM cost low.
Similarity is computed on **lower-cased word sequences with `autojunk=False`**. The first implementation compared raw characters with difflib's default `autojunk=True`, which on inputs over 200 elements discards frequent elements as noise; near-identical TJX pages (2019 vs 2020, only figures updated) scored 0.09. Word-level without autojunk scores the same pair 0.65. This cut "major change" from 161 to 126 of 387 comparisons.
Remaining caveat: where the "About" page is a microsite homepage with a news feed (e.g. `aboutschwab.com`), similarity tracks news churn, not values. Such firms need a narrower page or a values-sentence filter before the change variable is interpreted.

**Revision after manual validation (supersedes the thresholds as the final label).** A 30-pair sample (`part1_change_review.csv`, drawn by `04b_review_sample.py`) showed that similarity alone does not answer "did the stated values change": Amazon's 2021 addition of two Leadership Principles scored 0.85 ("minor"), while many "major" changes were product promotions, news feeds, or extraction differences. The brief also asks for an LLM-based judgement. The final design therefore has two layers:
1. `text_change` (deterministic, step 4): unchanged / minor / major by similarity. It is reproducible and free, and acts as a filter: pairs with similarity >= 0.95 are labelled `unchanged` without an LLM call.
2. `changed_from_prior` (step 5, LLM): for every pair whose text changed, the model sees both years' texts and decides whether the **values content** changed (`changed_values`), was only reworded, whether only other content changed, or whether the two years are different pages.
The LLM labels are validated against the human labels on the 30-pair sample (agreement reported in the Part 1 README).

## D-008 Value categories (one codebook for Parts 1 and 2)
Start from the MIT Sloan / Glassdoor **Culture 500 "Big Nine"** values (Sull, Turconi & Sull 2019), which were derived empirically from how employees and firms describe culture:
Agility, Collaboration, Customer, Diversity & Inclusion, Execution, Innovation, Integrity, Performance, Respect.
Add three categories needed to connect with Part 2 disclosures:
Environment & Sustainability, Community & Social Impact, Employee Wellbeing & Development.
The **same 12 categories will be used in Part 2**, so Part 3 can compare stated and disclosed emphasis in one space. The codebook lives in `shared/value_codebook.py`, with a definition, examples that count, and examples that belong to a neighbouring category for each entry, so the boundaries the LLM applies are written down and reviewable.
Why this scheme rather than alternatives:
- *Empirical grounding*: the Big Nine come from a large-scale study of how culture is described, not from our intuition, and they are widely cited in management research.
- *Comparable granularity*: 12 categories are coarse enough for 50 firms x 9 years to give stable shares, and fine enough to separate shareholder-oriented (performance, execution) from stakeholder-oriented (community, environment, employees) language, the contrast the authenticity question turns on.
- *Bridging Part 2*: environment, community and employee categories are what ESG/DEI/proxy disclosures report on; without them the stated-vs-disclosed comparison would have no common terms.
*Rejected:* an inductive scheme (topic model or LLM-generated categories per firm) would fit the pages more closely but would differ between Parts 1 and 2 and between runs, which breaks the comparison Part 3 needs. To keep the codebook from forcing a fit, the LLM also returns `other_themes` for value language outside the 12 categories; frequent other-themes are a signal to revise the codebook.
**LLM setup:** see D-011 (local open-weight model). JSON-schema structured output; every answer cached on disk (`data/intermediate/llm_cache/`) with token usage logged (`llm_usage.csv`). Item (c), linguistic shifts, is coded per firm over the full nine-year series (step 5b), because a shift is a property of a sequence, not of one snapshot.

## D-009 Filling coverage gaps in candidate URLs
The first CDX pass (83 hand-compiled URLs) found snapshots for 407 / 450 company-years. Five candidate URLs had zero captures (wrong paths), and gaps clustered in early years when firms ran older site structures (e.g. Occidental's SharePoint site `oxy.com/aboutoccidental/...`, Phillips 66 `.../pages/visionandvalues.aspx`).
**Decision:** for each gap, run a CDX *prefix* search over the firm's site for the gap years, filtered to HTTP 200 HTML pages whose path contains about / company / values / mission / principles etc., and add the page that matches the D-003 hierarchy. Values pages found this way (BAC, COP, OXY, PSX, UNH, XOM) are given top priority, consistent with D-003. Zero-capture URLs were removed. Discovered URLs are marked `found via CDX prefix search` in `url_candidates.csv`.
**Consequence:** a firm can switch between a values page and a general About page across years when only one of them was archived in a given year. Step 4 flags these cases (`url_changed = True`) so that a page switch is not misread as a change in stated values.
A second pass targeted firms whose page was an About-microsite homepage with a news feed (SCHW, GOOGL, AXP, NKE) or a JavaScript shell (AVGO, LLY, NKE). Found and kept: Google "Ten things we know to be true" (all nine years, three URLs over time), Schwab `who-we-are` (2019-23), Amex `who-we-are` (2022), Nike `topics/purpose` (2024). Found and **rejected after inspecting the text**: `aboutschwab.com/culture` (a rotating feed of employee stories, not a values statement), `about.nike.com/en/company` and Broadcom `citizenship/corporate-culture` (JavaScript shells with no archived text).
Note on search mechanics: a path keyword filter must exclude the host name, otherwise every URL on `about.*` domains matches and the 500-row limit is filled alphabetically.
*Rejected:* borrowing a neighbouring year's snapshot to fill the gap (violates D-004), or using the homepage (rarely carries values text).

## D-010 Rejected snapshots trigger an automatic fallback
A capture can pass the CDX check yet be unusable: the redirect ends in a 404, on the homepage, or in another year; the archive stored an error page with HTTP 200 ("soft 404"); or the page is a JavaScript shell with no archived text. Rather than leaving these as gaps or fixing them by hand, steps 2 and 3 record them in `part1_excluded_snapshots.csv`, and step 1 skips them on the next run:
- `capture` scope (soft 404, out-of-year redirect): try the next-closest capture of the same URL in that year;
- `url_year` scope (404, homepage redirect, JavaScript shell, or a second bad capture of the same URL-year): move to the next candidate URL.
`run_part1.py` repeats steps 1-3 until a round rejects nothing new (converged in two rounds). This keeps every fix rule-based and logged, which is what lets the pipeline scale to 500 firms without manual patching.
Examples it resolved: Starbucks 2016 (three archived error pages, then the next candidate), IBM 2018 and BofA 2019 (redirects into other years), Broadcom 2019 (the about-us shell, then `broadcom.com/company` with text).
Result: 429 of 450 company-years have usable text (95.3%). The 21 gaps, each with its reason and the snapshots tried, are listed in `data/outputs/part1_gaps.csv`: JavaScript shells 9 (AVGO 2020-24, LLY 2021-23, NKE 2023), not archived 5 (LOW 2016-19, NVDA 2017), dead page 5 (ORCL 2016, MCD 2023-24, PSX 2023-24), archived error page 1 (SBUX 2016), too short 1 (NVDA 2016).
Site-search widget lines that trafilatura keeps as body text (e.g. Oracle's "No results found / Use synonyms...") are removed line by line before comparison.

## D-011 A local open-weight LLM instead of a paid API
The brief asks for "an LLM-based pipeline of your choice" and provides no API budget. **Decision:** run a local open-weight model, **Qwen2.5-7B-Instruct** (Apache-2.0) served by **Ollama**, on a consumer laptop GPU (RTX 3060, 6 GB).
Why: zero marginal cost, so the pipeline can be rerun or scaled to 500 firms without a budget decision; no page text leaves the machine; the model weights are pinned (`qwen2.5:7b-instruct`, digest `845dbda0ea48`), so the coding is reproducible, which a hosted model that is updated or retired is not. Decoding is deterministic (temperature 0, fixed seed).
Cost of the choice: a 7B model makes more coding errors than a frontier model (e.g. it coded a Credo sentence on employee health as *execution* rather than *employee wellbeing*). This is handled by (1) a tightly defined codebook with explicit boundaries (D-008), (2) asking about change only on the sentences that changed, which keeps inputs short and focused, and (3) measuring agreement with human labels on the review sample (step 7) and reporting it.
Engineering needed for a small local model, all in `llm.py`: JSON-schema constrained decoding with length limits and an output cap (without them the model looped inside a JSON array for 8,000+ tokens); a few fixed context sizes (8k/16k/32k) with requests grouped by size, because the server reloads the model whenever the context size changes; one retry after a crashed model runner; removal of stray CJK characters that Qwen emits when a string hits its length limit.
Throughput: median 14 seconds per snapshot, about 2 hours for all 429 (plus ~30 minutes for the change judgements).
One task per call: the first run asked for themes and the change judgement in a single call. The 7B model then invented change labels for 26 snapshots that had no prior-year comparison and skipped the judgement for 20 that had one. The change judgement was moved to a dedicated call that sees only the removed and added sentences and must choose one of five labels (no "not assessed" option); the theme call's own change field is ignored.
Cache validity: each cached answer stores a fingerprint of the exact input (system prompt, page text, schema). An answer is reused only for the same input, so when an upstream fix changes a company-year's text (e.g. a new candidate URL), only that company-year is coded again.
*Alternative kept:* the same code runs on the Claude API (`LLM_BACKEND=anthropic`, Claude Opus 5.5, est. $21 for Part 1); answers are cached per model, so the two can be compared on the review sample if credits become available.
*Rejected:* free tiers of hosted APIs (rate limits, and terms that often allow training on submitted data); having the coding assistant hand-label the pages (not a reproducible pipeline).

## D-012 Part 2 document: annual proxy statements (DEF 14A), coded with a dictionary
**Document.** The proxy statement each firm files with the SEC before its annual meeting. Every US-listed firm must file one every year, so all 50 firms are covered for all nine years from one free, permanent source (SEC EDGAR); since the late 2010s proxies also report board diversity, human capital, ESG oversight and culture. One proxy per filing year: if a year has several DEF 14A filings, the first whose opening text mentions an "annual meeting" (special-meeting proxies, e.g. merger votes, are skipped). Broadcom's 2016-17 proxies were filed by its predecessor registrant (redomiciled in 2018); `companies.csv` records a predecessor CIK for such cases.
*Rejected:* ESG / sustainability / DEI reports. They are voluntary, start in different years per firm, change format and title, and have no common location, so coverage would be partial and collection manual; that conflicts with the brief's emphasis on scaling to 500 firms.
**Measure.** Each of the 12 codebook categories (D-008) is counted with a keyword pattern (`LEXICON` in `shared/value_codebook.py`) and expressed per 10,000 words. Tone uses three simple rates: commitment words, hedging words, and percentages (quantification). A dictionary rather than an LLM: proxies are 30,000-100,000 words, the categories have distinctive vocabularies, and a count is transparent, reproducible and takes seconds. Patterns avoid common proxy phrases ("equity awards", "with respect to", "execution of the agreement").
*Limitation acknowledged:* a count measures how much a document talks about a value, not whether the firm acts on it, and proxies are partly boilerplate (pay-for-performance language inflates "performance"). Part 3 handles the second issue by comparing each firm with other firms in the same year.

## D-013 Operationalising authenticity as rank alignment
**Definition.** For each company-year, the Organizational Authenticity Index (OAI) is the Spearman rank correlation, across the 12 categories, between the *stated* profile (website: 2 = primary value, 1 = mentioned, 0 = absent) and the *disclosed* profile (proxy: each category's share of the firm's value language, z-scored against all firms filing that year).
**Reasoning.** "Alignment" here means: the values a firm puts first in public are the ones its formal disclosure gives *more attention than its peers do*. Three choices follow:
- *Rank, not level:* the two sources are on different scales (a 0-2 coding vs. word rates); only the ordering of priorities is comparable.
- *Within-year standardisation of the proxy:* every proxy talks about performance and every proxy added ESG language after 2020; without standardising, all firms would look "aligned on performance" and drift together. The index compares a firm with its peers.
- *A profile, not a single value:* authenticity is about priorities as a whole, so the index uses all 12 categories at once; a per-category view (`n_stated_not_disclosed`, stated values the proxy gives below-average attention) is kept for interpretation.
*Rejected:* cosine similarity of raw profiles (dominated by the categories every proxy is full of); an LLM judgement of "authenticity" per firm (not reproducible, and it would hide the definition inside a prompt).
**Validity check.** A placebo: the same stated profile is correlated with the proxies of all *other* firms in the same year. If the index measures firm-specific alignment, own-proxy correlations must exceed the placebo.

## D-014 Part 4 question: did website DEI retreats reach the disclosures?
Part 1's most distinctive pattern is the 2024 fall in diversity & inclusion language on websites. Part 4 asks whether firms that removed it from their website also reduced it in their proxy, comparing firms that dropped, kept or never had DEI on their website (2022 vs 2024), with environment as a comparison category. Chosen because it tests the authenticity idea directly on a real, recent event, with data already collected, and its answer is informative either way.

## Open items
- [x] Network: collection runs locally (the drafting sandbox could not reach web.archive.org).
- [x] CIKs verified against EDGAR (all 50 resolve; Broadcom needs its predecessor CIK for 2016-17).
- [x] Part 2 document type: proxy statements (D-012).
