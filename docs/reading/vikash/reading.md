# Vikash · OCR + pixel reader, measurement, calibration, decision rule, evaluation, baselines, safety

You own how a number is read from pixels without a neural model, how readings are combined, how the error margin is
calibrated, the rule that turns all of it into a verdict, and how the system is evaluated. Since the table was made
you also own the model server, the web app and `web_lite`, and the current LoRA data/training scripts.

Read [00_overview.md](../00_overview.md) first. Poster questions for this area: [poster_qa.md](poster_qa.md).

---

## Level 0 · Background

| Idea | Why you need it | Read |
|---|---|---|
| Image basics with NumPy / OpenCV | `ocr_pixel` works on BGR arrays, masks, colour distances | OpenCV-Python tutorials: "Changing colour spaces", "Image thresholding" |
| HSV hue | lines are matched by **hue**, because anti-aliasing and JPEG wash out saturation but keep hue | any HSV explainer |
| Tesseract OCR | tick labels and legends | Tesseract docs, page segmentation modes (`--psm`) |
| Robust line fitting (RANSAC idea) | `fit_y` tries every pair of ticks and keeps the fit most ticks agree with | the RANSAC Wikipedia page is enough |
| Median and MAD | estimate and disagreement | any statistics intro |
| Split conformal prediction | the margin is a conformal quantile of calibration ratios | Angelopoulos & Bates, "A Gentle Introduction to Conformal Prediction" (2021), sections 1–2 |
| Conformal p-values, Benjamini–Hochberg | the batch check controls the wrong-flag rate across a batch | Benjamini & Hochberg (1995); Jin & Candès (2023), "Selection by prediction with conformal p-values" |
| Bootstrap by cluster | intervals resample **reports**, not claims | any bootstrap intro; note why claims in one report are dependent |

---

## Level 1 · Read, in this order

**Reading pixels**
1. **[tools/chart_ocr.py](../../../chart_claim_verifier/tools/chart_ocr.py)** — load and upscale, Tesseract words with
   pixel boxes, group words into lines.
2. **[tools/axis.py](../../../chart_claim_verifier/tools/axis.py)** — `analyse(path) -> Geometry`: plot area
   (`find_plot_area`), tick positions, OCR of tick labels, `fit_x` / `fit_y`, legend (`find_legend` from handles or
   text), `series_colour`. This is the largest file in your area (≈500 lines).
3. **[tools/ocr_pixel.py](../../../chart_claim_verifier/tools/ocr_pixel.py)** — Tool 4: geometry → series colour → x
   position → `read_bar` (longest run of matching columns, middle 60%, median top) or `read_line` (line y at the
   column, continuity check) → `yfit.value(pixel)`. Every failure is a named code.

**Combining and deciding**
4. **[measure/aggregate.py](../../../chart_claim_verifier/measure/aggregate.py)** — `estimate` = median,
   `disagreement` = MAD, `derived_value` per tool, `tool_value` drops tied legs (U10).
5. **[calibration/pvalues.py](../../../chart_claim_verifier/calibration/pvalues.py)** — conformal cut-off
   (⌈(n+1)·level⌉-th smallest), conformal p-value, BH.
6. **[calibration/collect.py](../../../chart_claim_verifier/calibration/collect.py)** — every point of every calibration
   figure × every tool; points and derived quantities become `CalibrationItem`s; signed errors as fractions of the
   true span.
7. **[calibration/fit.py](../../../chart_claim_verifier/calibration/fit.py)** and
   **[calibration/store.py](../../../chart_claim_verifier/calibration/store.py)** — ratio
   `|truth − estimate| / (disagreement + eps·span)`, one subset per item per k, groups and the fallback chain,
   `min_group_size` and `min_group_charts`.
8. **[decide/rule.py](../../../chart_claim_verifier/decide/rule.py)** — the verdict. Read it twice.

**Evaluating**
9. **[evaluation/metrics.py](../../../chart_claim_verifier/evaluation/metrics.py)** — wrong-flag rate, coverage, catch
   rate by planted size, detection limit, attribution of the first wrong step, report-level bootstrap.
10. **[evaluation/sweep.py](../../../chart_claim_verifier/evaluation/sweep.py)** — re-decide stored P0 readings under
    other settings: coverage-vs-wrong-flag curve, coverage at 10% wrong flags, baseline B5 (uncalibrated margin).
11. **[evaluation/correlation.py](../../../chart_claim_verifier/evaluation/correlation.py)** — error correlation,
    joint failures, effective number of independent tools (E4).
12. **[baselines/vlm_baselines.py](../../../chart_claim_verifier/baselines/vlm_baselines.py)** — B1 direct, B2 with
    confidence, B3 majority vote, B4 tools without the rule. All start from your traces so only the decision differs.
13. **[evaluation/safety.py](../../../chart_claim_verifier/evaluation/safety.py)**,
    **[lms/mock_lms.py](../../../chart_claim_verifier/lms/mock_lms.py)**,
    **[lms/guard.py](../../../chart_claim_verifier/lms/guard.py)** — hidden-instruction effect (E8) and the allow-list:
    only `post_flag` may run; `unsafe_executed` must be 0.

**Serving**
14. **[models/remote.py](../../../chart_claim_verifier/models/remote.py)** and
    [web/model_server/README.md](../../../web/model_server/README.md) — same `VLM` interface over HTTP jobs; Kaggle T4 or
    a Hugging Face Space.
15. [web/README.md](../../../web/README.md), [web_lite/README.md](../../../web_lite/README.md) — how a TA and a student use
    the verifier; the backend calls `pipeline.build_agent` / `verify_pdf`.

---

## Level 2 · Run

```bash
pytest tests/test_decision_core.py tests/test_u10_u14.py tests/test_end_to_end.py::test_ocr_pixel_reads_a_bar_chart

# the OCR reader on its own
python scripts/diagnostics/bench_ocr_pixel.py --help
python scripts/diagnostics/diagnose_ocr_pixel.py --help

# calibration and its outputs
chart-claim-verifier calibrate -c configs/exp/smoke_cpu.yaml
ls calibration_tables/            # <tools>.json, .report.json, .errors.json, .profile.json

# evaluation
chart-claim-verifier run   -c configs/exp/smoke_cpu.yaml --split test --policy all_tools
chart-claim-verifier sweep -c configs/exp/smoke_cpu.yaml --run runs/smoke/test_all_tools_rule_ours
python scripts/analysis/intervals.py runs/local/<run>   # 95% intervals, resampling reports (reads data/local)
```

Exercise: open a calibration `.report.json`, pick the group `line|point|k2`, and compute by hand the margin the rule
would use for a claim with two readings 0.81 and 0.83 on an axis of span 1.0.

---

## Level 3 · Full implementation

**The rule, line by line.** With values from k tools: `est = median`, `dis = MAD`,
`scale = dis + eps·span` (the floor stops two identical readings from giving a zero margin). From the table:
`q_flag` at `level_flag` (0.95) and `q_acc` at `level_accept` (0.75) for the group
`chart_type|claim_type|k` (with fallback). Margins `m = q·scale`. `gap` is direction-aware for one-sided claims
("over 80%"). Then:

- `gap > tol + m_flag` → MISMATCH candidate (p-value = conformal p of `(gap − tol)/scale`)
- `gap ≤ tol + m_acc` and `m_acc ≤ max_accept_margin·span` → CONSISTENT
- otherwise NOT_SURE (between margins, or too spread out to accept: a real error would also fit)

Fewer than `min_readings` (2) → NOT_SURE. `batch_check` then runs BH at `alpha` (0.10) over all MISMATCH candidates
of a batch; the losers become NOT_SURE.

**Why the ratio.** Calibration does not learn "the error is ±x". It learns how many disagreements the true value is
away from the estimate. If tools disagree a lot the margin widens automatically; if they share a mistake (agree and are
wrong) the ratio is large and that group's quantile grows (`test_shared_mistakes_widen_margins`).

**One subset per item.** The conformal guarantee assumes one exchangeable ratio per item. `fit_table` therefore takes
one k-subset per item (the first k in `fixed_order`, or seeded random), not all subsets. The tool-set groups (U14)
exist but are off (`by_tool_set: false`): measured, they made wrong flags worse (dev 1.4% → 4.1%) because a pair that
stopped early *because it agreed* is a selected sample.

**Groups rest on charts.** A group with < `min_group_size` ratios or < `min_group_charts` charts falls back:
`line|difference|k2 → line|*|k2 → *|*|k2 → *|*|*`.

**OCR reader details that matter.**
- `fit_y` requires 3 agreeing ticks when 3+ were read (two misreads can agree by chance) and values must grow upwards.
- Colour matching uses `mix_mask`: a pixel is a mix of the series colour and the background, which handles thin
  anti-aliased lines.
- Legend handles share series colours, so the legend box is masked out of the plot.
- Bars whose top is hidden behind the legend raise `occluded_by_legend` instead of reading the legend frame.
- `two_lines_at_x`: another similar-coloured line at the same x; the tool refuses rather than guesses.
- `legend_hint` (from the VLM legend repair) changes the cache key: a hinted reading is a different measurement.

**Cache discipline.** Every reading is cached by (tool, version, image hash, series, x). Bump a tool's `version` when
its behaviour changes, or old readings will be replayed as if they were new.

**Metrics you report.** Wrong-flag rate = share of MISMATCH verdicts whose gold label is not `error` (so a flag on a
SKIPPED sentence counts as wrong); coverage = share of claims with gold `correct` / `error` / `no_figure` that got a
decided verdict (CONSISTENT, MISMATCH or NO_FIGURE); catch rate per planted size; detection limit δ50; margin check
(true value inside the flag margin). All with report-level bootstrap intervals.

**Calibration is hardware-specific.** Tables in `calibration_tables/local` were measured with float16 on Apple
silicon; re-read the calibration charts on a T4 or CPU before trusting the margins there.

**Work by others in your area:** Karan wrote `bench_ocr_pixel.py`, `diagnose_ocr_pixel.py` and the legend pilots;
Hritik wrote `scripts/safety_all.py`, `margin_vs_b5.py`, `lora_wrong_flags.py` and `e4_samples.py`.

---

## Level 4 · Check yourself

1. Two tools read 0.80 and 0.80 on a span of 1.0. What stops the margin from being zero?
2. Why is the cut-off the ⌈(n+1)·level⌉-th ratio and not the plain percentile?
3. A claim says "over 80%" and the estimate is 85%. What is the gap?
4. When does a claim with a tiny gap still come out NOT_SURE?
5. What does BH control, over which set of claims, and why is it run per batch and not per report?
6. Why are bootstrap intervals computed by resampling reports?
7. `ocr_pixel` reads a bar chart with a legend in the top-right corner. Which failure codes can it return and what does
   each mean?
8. You change `read_line`. What else must you change so old readings are not reused?
