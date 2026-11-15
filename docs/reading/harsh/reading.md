# Harsh · dataset generator, PDF ingest, retrieval (RAG), claim finding and parsing

You own the system's input side: the synthetic reports with known answers, turning a PDF into figures and sentences,
deciding which sentences are claims and what they say, and finding the figure each claim is about.

Read [00_overview.md](../00_overview.md) first. Poster questions for this area: [poster_qa.md](poster_qa.md).

---

## Level 0 · Background

| Idea | Why you need it | Read |
|---|---|---|
| matplotlib styling | the generator draws charts in many styles, including a held-out one | matplotlib "Customizing Matplotlib with style sheets and rcParams" |
| PDF structure and PyMuPDF | text blocks with positions, embedded images | PyMuPDF docs: "Text extraction", "Extracting images" |
| fpdf2 | the generator writes the PDF | fpdf2 tutorial |
| Regular expressions | rule parser, finder, tolerance | Python `re` docs; regex101.com for testing |
| BM25 | ranking figures by caption + chart text | Robertson & Zaragoza, "The Probabilistic Relevance Framework: BM25 and Beyond" (2009), or any short BM25 explainer; the code uses `rank_bm25.BM25Plus` |
| Fuzzy matching | series / x names that OCR misreads | `rapidfuzz` docs: `fuzz.token_set_ratio` |
| Structured output from an LLM | the LLM parser fills a JSON form validated by pydantic | pydantic docs, "Validation errors" |
| Significant digits and rounding | "82%" means ±0.5, "about 80%" means ±5 | the docstring of `claims/tolerance.py` is the spec |

---

## Level 1 · Read, in this order

**Generating reports with known answers**
1. **[generator/tables.py](../../../chart_claim_verifier/generator/tables.py)** — `ChartTable` (the true values) and
   `make_table`: line tables (epochs, curves; loss or accuracy) and bar / grouped bar tables (models × datasets).
   `hard=True` gives more series and points, like messy student figures.
2. **[generator/plot.py](../../../chart_claim_verifier/generator/plot.py)** — `sample_style` (value labels, grid,
   markers, legend position, font size, figure size, dpi, line width, JPEG quality) and `render`, which records the
   **actual** y limits on the table. `held_out=True` uses a style never seen in calibration or fine-tuning.
3. **[generator/claims.py](../../../chart_claim_verifier/generator/claims.py)** — sentences with known labels:
   correct exact, correct rounded / hedged / one-sided, planted errors of known size (fraction of the axis span),
   mix-ups (wrong series or x), no-figure claims, and setup sentences that are not claims. Labels use **the same
   tolerance function as the checker**.
4. **[generator/injections.py](../../../chart_claim_verifier/generator/injections.py)** — hidden white, tiny text for
   the safety test.
5. **[generator/report_builder.py](../../../chart_claim_verifier/generator/report_builder.py)** — one PDF + `truth.json`
   per report. An injected report and its clean twin differ only in the injection (separate random stream).
6. **[generator/build.py](../../../chart_claim_verifier/generator/build.py)** — splits (`calib`, `dev`, `test`,
   `style_shift`, `phrasing`, `calib_easy`, …); each report has its own seed, so no table is shared between splits.

**Reading a PDF**
7. **[ingest/pdf_parser.py](../../../chart_claim_verifier/ingest/pdf_parser.py)** — text blocks and images; a caption is
   the block just below a figure starting with "Figure N" / "Fig. N"; `merge_continued` joins a sentence cut by a page
   break or a figure; each figure is OCR'd once (legend, ticks, title → `text_lines`) and its axis span measured
   (`y_span`).
8. **[ingest/chart_type.py](../../../chart_claim_verifier/ingest/chart_type.py)** — bar / grouped bar / line from pixels:
   bars are large solid rectangles; several bar hues → grouped bar.

**Claims**
9. **[claims/finder.py](../../../chart_claim_verifier/claims/finder.py)** — a candidate has a number (figure refs
   removed) **and** a result word (`RESULT_WORDS`). Setup sentences are skipped.
10. **[claims/tolerance.py](../../../chart_claim_verifier/claims/tolerance.py)** — allowed rounding from how the number
    is written; hedges ("about", "~") and one-sided words ("over", "above"); `is_within` is the ground-truth check.
11. **[claims/parser.py](../../../chart_claim_verifier/claims/parser.py)** — `RuleParser` (regexes; no model; also the
    "no reasoning" ablation E7) and `LLMParser` (JSON form → pydantic → one retry with the error shown). In both, the
    value, tolerance and direction come from the text, never from the model.

**Finding the figure**
12. **[retrieval/figure_index.py](../../../chart_claim_verifier/retrieval/figure_index.py)** — "Figure N" bonus +
    BM25Plus over caption + OCR text, metric words (accuracy, loss, F1, …), and `covers`: a figure is only accepted if
    the parsed series (and, for category axes, the x value) really appear in it. Otherwise NO_FIGURE. Then
    `cited_figure` (author cites Figure N but OCR misread the legend) and `_covering_with_legend` (ask the VLM for the
    legend names of near-miss figures, U11b).

---

## Level 2 · Run

```bash
chart-claim-verifier generate -c configs/exp/smoke_cpu.yaml
ls data/smoke/generated/test/test_000                     # report.pdf fig*.png truth.json
python -c "import json;t=json.load(open('data/smoke/generated/test/test_000/truth.json'));print(json.dumps(t['claims'][:3],indent=1))"

# ingest one report and look at what the system sees
chart-claim-verifier check -c configs/exp/smoke_cpu.yaml data/smoke/generated/test/test_000

# the parse stage alone (rules, then the LLM)
python scripts/analysis/eval_parse.py -c configs/exp/phrasing.yaml --split phrasing

pytest tests/test_claims_retrieval_safety.py tests/test_generator_phrasing.py
```

Exercise: write five sentences of your own about one generated figure (one rounded, one hedged, one one-sided, one
difference, one with a typo in the series name) and run them through `RuleParser().parse(...)` and
`FigureIndex(...).locate(...)` in a Python shell. Note which ones fail and why.

---

## Level 3 · Full implementation

**The generator is the ground truth, so it must use the checker's own rules.** A sentence's label (correct / error)
is computed with `claims.tolerance` exactly as the checker will read the printed number (`_measured`). If the two ever
differ, "errors" in the dataset are really rounding disagreements and every metric is wrong.

**Planted error sizes** are fractions of the axis span (`generator.planted_deltas: [0.02, 0.05, 0.10, 0.20, 0.50]`),
which is why `render` must record the real `ylim`: the span is what the checker measures errors against.

**Style coverage.** `hard_share` (0.5) controls small, compressed, busy charts. The held-out style (`style_shift`)
is never used for calibration or fine-tuning, so it measures how the system behaves on charts that look different.

**Novel phrasings.** The `phrasing` split uses sentence forms the rule parser does not know, to test escalation to the
LLM parser. `novel_phrasing: 0` must leave the random stream unchanged
(`test_no_novel_phrasing_leaves_the_random_stream_unchanged`) so older splits can be rebuilt exactly.

**Ingest pitfalls.**
- A sentence cut by a page break or a figure must be joined, and a cut comparison must not become a point claim
  (`test_a_sentence_cut_by_a_page_break_is_joined`, `test_a_cut_comparison_is_not_a_point_claim`).
- Hidden injected text is extracted like any other text: everything from the report is **untrusted**
  (`memory.context` marks it so for the parser).

**Parser rules that protect the verdict.**
- The claimed number must occur in the sentence (`test_llm_parser_rejects_number_not_in_sentence`).
- The tolerance comes from the text, not the model (`test_llm_parser_takes_tolerance_from_text_not_model`).
- An epoch written as a JSON number by the model (`"x": 14`) is accepted (`_numbers_as_text`); all 24 LLM failures on
  the `phrasing` split were of this kind.
- `None` means "not a checkable claim", which is different from a parse error.

**Retrieval decisions.**
- `ref_bonus` (10) makes an explicit "Figure N" dominate text similarity.
- `vocab_match` (80) is the fuzzy score for a series / x to count as "in this figure".
- Two close candidates (second ≥ `ambiguity_ratio` × first) are both returned; the agent checks both and never flags.
- `legend_names` recovers OCR misses with one cached VLM call per figure (U11b pilot: 5 of 7 wrong NO_FIGUREs recovered,
  0 of 23 right ones invented).
- Retrieval modes for ablations: `ours`, `nearest` (closest figure above), `oracle` (the truth).

**Known limit.** `RESULT_WORDS` is tuned to ML report wording (accuracy, loss, reached, improved, …). Sentences like
"the value was 2.89 in 2019" are not found. Any change here changes recall and must be measured on `dev`, not `test`.

**Work by others in your area:** small edits by Hritik in retrieval and claims; Hritik's `scripts/analysis/ambiguous_rules.py`
uses your figure candidates.

---

## Level 4 · Check yourself

1. What tolerance and relation does each of these get: "0.82", "82.4%", "about 80%", "about 82%", "over 80%"?
2. Why must the generator label claims with the checker's tolerance function?
3. Why does `render` write the y limits back onto the table?
4. A sentence says "As shown in Figure 2, GRU reaches 71%" but OCR read the legend as "GRY". What happens?
5. When does `locate` return two figures, and what does the agent then do?
6. Which split tests the LLM parser, and how is it built differently?
7. What is the difference between a parser returning `None` and raising `ParseError`?
8. Why are a report and its clean twin built from separate random streams?
