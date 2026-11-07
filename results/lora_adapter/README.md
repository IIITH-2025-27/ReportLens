# What is in this folder

- `summary.md`: accuracy, coverage, wrong flags and missed errors per method and split, with intervals; a table of truth against verdict; breakdowns; accuracy of every report.
- `all_claims_<split>.csv`: every claim of the split, one row each, with the truth, the verdict and the evidence.
- `examples/<report>/`: a few reports with their PDF and a per-claim results file. They are chosen by fixed rules, so failures are shown as well as successes:

  - `test_002`: the report with the most claims (test)
  - `holdout_018`: a wrongly flagged claim
  - `holdout_019`: a figure that exists was reported as NO_FIGURE
  - `holdout3_019`: a sentence that fits two figures
  - `test_004`: every decided claim is right (test)

Made by `python scripts/export_results.py` from the saved runs; no model is called.

These are the E6 runs: `vlm_table` uses the LoRA adapter in `checkpoints/lora_chart2table` (918 charts, one epoch), the margins come from `calibration_tables/local_lora`, everything else is as in the main results (`configs/exp/local_lora.yaml`). Model times are estimated with the base tool profile. Why the LoRA tool raises wrong flags pooled although it reads better: `results/run_log.md`, rows E4 and E9.
