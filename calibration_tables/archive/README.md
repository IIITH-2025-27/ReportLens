# Archived calibration tables

Old tables kept for the record. Nothing in the code or the configs reads this folder;
the live tables are in `../local/` (base model) and `../local_lora/` (LoRA chart-to-table adapter).
See `results/run_log.md` for the experiments these belong to.

| Folder | What it is |
|---|---|
| `_pre_calib_easy_backup/` | Table before the extra easy calibration charts (`calib_easy`, U5) were added |
| `_before_u14/` | Table before U14 (margins fitted per tool set; rejected) |
| `_before_min_charts/` | Table before the chart-count rule (`min_group_charts`, run-log entry B2) |
| `_before_u17/` | Table before U17 (extra grouped-bar calibration charts, `calib_grouped`) |
| `_u17_rejected/` | The U17 table itself; it made wrong flags worse and was rejected (run-log entry B6) |

Each folder also holds a nested `_backup_before_u2/` with the tool profile and error file from before U2.
