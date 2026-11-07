# Chart Claim Verifier

Uncertainty-aware verification of number-based chart claims in student technical reports.

Chart Claim Verifier checks whether the numbers written in a report match its own charts. Each chart value is read through four different tools, and the spread of those readings is calibrated against charts with known values. A claim is flagged only when the mismatch is clearly larger than the reading error. Unclear cases go to the TA instead of becoming a wrong accusation.

## How it works

1. **Find the figure.** Match the sentence to the right chart, or return "no matching figure".
2. **Parse the claim.** Turn the sentence into a checkable form: series, point, value, allowed rounding.
3. **Measure.** Read the value with a VLM crop, a VLM chart-to-table pass, DePlot, and OCR with pixel measurement. Take the median.
4. **Calibrate.** Convert tool disagreement into an error margin using conformal calibration on charts with known values.
5. **Decide.** Flag, accept, or send to the TA. Benjamini–Hochberg controls the wrong-flag rate across a batch.

The language model parses sentences and picks the next tool; it never decides a verdict. That is a few lines of tested Python (`chart_claim_verifier/decide/rule.py`).

## How the agent decides

Measure first, then decide. `chart-claim-verifier calibrate` reads every data point of the calibration charts with every tool and writes a **tool profile**: for each kind of chart (`line|easy`, `line|hard`, `bar|easy`, `bar|hard`), each tool's measured success rate, typical error, rate of silent big errors, time per call, and for every pair of tools how often they agree on a wrong value (`chart-claim-verifier profile` prints it; `chart-claim-verifier profile --rebuild` recomputes it from the cached calibration readings).

Every number comes with the number of *charts* behind it (`chart-claim-verifier profile` shows both): points on one chart share their mistakes, so a situation measured on fewer than 5 charts falls back to the pooled numbers. The profile also records how far each failure reaches (`failure_scope`: does `y_fit_failed` repeat on every point of the figure, `series_not_found` on every point of the series, `two_lines_at_x` only on its own point?), which is what report memory uses to decide what not to retry.

The pair numbers matter more than the single-tool ones: the rule only accepts or flags when readings agree, so a wrong verdict needs two tools that make the *same* mistake. On hard line charts the VLM crop reader alone is badly wrong 34% of the time, yet when it agrees with the pixel reader both are wrong only 1.3% of the time; the two VLM tools (same model) agree on a wrong value 5.1% of the time, just above the planner's 5% limit, so it does not pair them there (51 calibration charts, `calib` + `calib_easy`).

At run time the agent looks before it acts, at every stage, and logs why (`stages` in each trace):

| Stage | Looks at | Decides |
|---|---|---|
| Plan (per report) | each figure's situation: chart type, image size, legend size, printed labels, readable axis | which tools are worth using on that figure |
| Parse | did the rule parser recognise the phrasing? do the parsed names exist in a figure? | keep the rule result, or escalate to the LLM parser |
| Figure | explicit "Figure N", text-match scores | one figure, check two, or no matching figure |
| Measure | will the tool answer for this x (labelled or not)? are its answers right? would its agreement with the tools already read be trustworthy? cost (a table tool's one-off cost is shared by the claims waiting on that figure) | plan a trustworthy *pair* first and read the member most likely to fail per second first, so a failure shows up before the expensive tool is paid for; don't call tools that would refuse; don't use a tool as a cross-check if it shares the first tool's mistakes |
| Remember | which tool failed on which figure/series, with which code, and how far that code reaches | don't retry a failure that repeats; do retry one that doesn't |
| Repair | the code of the last failure | if a repair was measured to work (`read_legend` for `ocr_pixel`'s `series_not_found`) and would complete a trustworthy pair, run it, then read again |
| Stop / hand off | gap vs. margins, calls left, any trustworthy cross-check left? | stop, measure again, or hand to the TA early (no model time spent when no pair can cross-check) |
| Decide | gap, rounding, calibrated margin | fixed rule (never the LLM) |

Policies to compare (ablation E5): `all_tools` (P0), `fixed_order` (P1), `calibration_informed` (P1b), `llm` (P2, the LLM picks with the same evidence), `informed` (P3, decides from the measured profile). Parser modes: `rule`, `llm`, `agent` (rules first, LLM only when needed).

## Outcomes

| Verdict | Meaning |
|---|---|
| Consistent | Claim matches the chart within the error margin |
| Mismatch | Gap is clearly larger than the reading error |
| Not sure | Sent to the TA for review |
| No matching figure | No chart covers the claim |

## Status (final submission, 13 Nov 2026)

Everything in the plan is built and has run on real tools (Qwen3-VL-4B, DePlot, Tesseract) on an Apple M4 laptop. The method was frozen on 9 Nov (`configs/exp/local_real.yaml`) and then run once on a new, untouched split (`final`). Results: [`results/summary.md`](results/summary.md); every run and decision, kept or rejected: [`results/run_log.md`](results/run_log.md); write-up: [`report/final_report/report.pdf`](report/final_report/report.pdf).

| Part | State |
|---|---|
| Data generator (charts, PDF reports, labelled claims, hidden injections, clean twins) | working; 6 evaluation splits of 20 reports, 17 calibration reports, 1,088 fine-tuning charts |
| Ingest, retrieval (Figure N + BM25 + series check + VLM legend names), rule and LLM parsers, tolerance rules | working |
| Four tools (OCR + pixel, DePlot, VLM table, VLM crop), reading cache, offline replay | working |
| Calibration, decision rule, BH batch check | working (BH cannot change a verdict at level 0.95 with alpha 0.10; see `scripts/margin_vs_b5.py`) |
| Agent: measured tool profile, informed planner (P3), failure-aware memory, early hand-off; P0 / P1 / P2 for comparison | working |
| Mock LMS + allow-list guard, injection test (E8) | working; 0 unsafe actions in every run; hidden instructions change 0 of 210 verdicts with the rule parser, and made the LLM parser drop 8 claims (`results/safety.md`); since G1 such sentences go to the TA instead |
| After the final run (`configs/exp/v2.yaml`, development results) | rejected candidates go to the TA (G1), cited figure wins (G2): wrong flags 3.5 -> 3.3% pooled; LLM parser rejections 40 -> 2 of 247 claims (G4); reduced E4 (`results/e4_samples.md`); look-alike figure check rejected (G3). See run log section G |
| Baselines B1-B5 | run (B1-B4 on `final`; B5 by replay) |
| LoRA fine-tuning of the VLM table tool | one run (918 charts, 1 epoch); better reading, not fewer wrong flags (diagnosed in the run log, E4/E9) |
| Simulated tools (truth + noise) | for pipeline tests only; never report their numbers |

## Final results

On the untouched `final` split (20 reports, 205 claims, run once after the freeze), with the same Qwen3-VL-4B everywhere:

| Method | Coverage | Right when decided | Wrong flags | Missed errors | Model time |
|---|---|---|---|---|---|
| B1: the VLM sees chart + sentence and answers | 100% | 64.9% | 23.3% | 55.8% | 15.0 min |
| B3: five samples, abstain unless unanimous | 88.3% | 66.3% | 19.1% | 50.0% | ~28 min |
| B4: the same four tool readings, the VLM judges | 99.5% | 82.4% | 25.9% | 0.0% | – |
| P0: all tools + rule | 81.0% | 97.0% | 5.7% | 0.0% | 44.7 min |
| **P3: planner + rule (main)** | **84.9%** | **96.6%** | **5.6%** | **1.0%** | **16.2 min** |

All six evaluation splits pooled (1,205 claims): P3 decides 79.7% of claims, is right on 96.8% of them, 3.5% of its flags are wrong [2.0, 5.2], 0.7% of real errors are missed, and no planted error was accepted. Negative findings, reported as such: an uncalibrated margin (B5) does as well as the calibrated one; the BH batch check cannot change a verdict at level 0.95 with alpha 0.10; LoRA improves chart reading but not wrong flags. Details: [`results/summary.md`](results/summary.md), [`results/margin_vs_b5.md`](results/margin_vs_b5.md), [`results/safety.md`](results/safety.md), [`results/run_log.md`](results/run_log.md).

## Quick start

Needs Python >= 3.10 and Tesseract (`brew install tesseract` / `apt install tesseract-ocr`).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # add ",gpu" for the real models (torch, transformers, peft)
pytest                             # 90 tests, CPU only

# check one report (any PDF); prints each claim's verdict and the TA's evidence card. v2 = the frozen method plus the two
# changes kept after the final run (a rejected-looking claim goes to the TA; a cited figure wins), see results/run_log.md G
chart-claim-verifier check -c configs/exp/v2.yaml path/to/report.pdf
```

CPU-only smoke run with simulated tools:

```bash
chart-claim-verifier generate  -c configs/exp/smoke_cpu.yaml        # 12 calibration + 12 test reports
chart-claim-verifier calibrate -c configs/exp/smoke_cpu.yaml
chart-claim-verifier run       -c configs/exp/smoke_cpu.yaml --split test --policy all_tools
```

## Reproduce the final numbers

Every reading is cached (`cache/local.sqlite`), so all policies replay without a model; `offline_misses` in `metrics.json` counts readings the cache lacked. The cache, the split lists and the generated calibration and evaluation reports are tracked in git (see `.gitignore`), so this works from a clone; run folders and the LoRA weights are not.

```bash
# frozen configuration, every split, every policy (no model is loaded)
for s in test dev holdout holdout2 holdout3 final; do for p in informed fixed_order all_tools; do
  chart-claim-verifier run -c configs/exp/local_real.yaml --split $s --policy $p --offline --name fin_${s}_${p}; done; done
python scripts/export_results.py --run test=fin_test dev=fin_dev holdout=fin_holdout holdout2=fin_holdout2 \
    holdout3=fin_holdout3 final=fin_final --out results
python scripts/margin_vs_b5.py --choose test=fin_test dev=fin_dev \
    --evaluate holdout=fin_holdout holdout2=fin_holdout2 holdout3=fin_holdout3 final=fin_final
python scripts/lora_wrong_flags.py                        # why LoRA raised wrong flags
python scripts/safety_all.py                              # E8 from the e8_* runs (made live with --parser llm)
PYTHONPATH=. python report/final_report/make_figures.py   # the report's figures and numbers.json
```

Live runs (need the models): `run ... --split final --policy all_tools` fills the cache for a split; `baselines --run runs/local/<all_tools run> --which b1,b2,b3,b4`; the safety experiment is `run --split S --reports @S_clean --parser llm` against `run --split S_clean --parser llm`, compared with `safety --run ... --clean-run ...`.

If the `chart-claim-verifier` command stops working after the folder is moved, run `pip install -e .` again or use `python -m chart_claim_verifier.cli ...`.

## Layout

```
configs/            default.yaml + one file per experiment
chart_claim_verifier/
  schemas.py        the data contract every module uses
  generator/        synthetic tables, charts, reports, claims, injections
  ingest/           PDF -> Report; chart-type detection
  retrieval/        which figure a sentence is about (BM25 + coverage check)
  claims/           finder, rule / LLM parser, tolerance rules
  tools/            OCR+pixel, VLM crop, VLM table, DePlot, simulated tools, disk cache
  measure/          median, disagreement, per-tool derived values
  calibration/      collect readings, fit conformal tables, p-values, BH
  decide/           the decision rule and the batch check
  agent/            memory, policies, the informed policy (planner.py), claim loop, report planner
  lms/              mock LMS and allow-list guard
  baselines/        B1–B4 (B5 is in evaluation/sweep.py)
  evaluation/       metrics, sweeps, tool correlation, safety
finetune/           LoRA data (make_sft_data.py); scripts/finetune_lora.py trained the adapter
scripts/            export_results, margin_vs_b5, lora_wrong_flags, safety_all, e4_samples, compare_runs, ambiguous_rules,
                    eval_parse, pilot_legend
results/            summary, per-claim CSVs, example reports, run log (every action, kept or rejected)
report/             mid_report/ and final_report/ (LaTeX; figures drawn from the saved runs)
tests/
```

