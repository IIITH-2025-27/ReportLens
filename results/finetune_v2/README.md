# Fine-tuning v2 results (run_log C9, report Table 8 and Figure 3)

Copied from the Kaggle notebook outputs (the `kaggle/` folder is not in git).

- `merge_results.json`, `merge_RESULTS.md`: notebook 7 (merge and score). Validation loss on `kaggle/shards/val_200.txt` for
  the base model, the seven adapters and both merges; chart-to-table test on `kaggle/shards/test_300.txt` for base,
  `merged_avg`, `shard_2` and `merged_ties`.
- `val_shard7_A.json`, `test_shard7_A.json`: route A (the laptop adapter's run resumed on 1,050 unused reports).
- `val_shard7_B.json`, `test_shard7_B.json`: route B (restarted from its step-385 checkpoint on 630 other unused reports).

Same 200 validation and 300 test charts for every model. Test measures: `cells_answered` (share of true table cells
returned), `error_median` and `error_p90` (share of the axis range), `within_2pct`, `badly_wrong_over_5pct`.
