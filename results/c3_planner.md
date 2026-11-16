# C3: margins calibrated on P3's own stopped readings (run_log H20)

`configs/exp/c3_planner.yaml` is `v2.yaml` with `calibration_dir: calibration_tables/c3_planner`
(`scripts/analysis/c3_planner_calibration.py`). Both rows of each split are offline P3 replays of the same cached
readings; only the margins differ. Numbers are the rule plus the batch check.

| split | margins | claims | flagged | wrong flags | coverage | missed errors | margin check |
|---|---|---|---|---|---|---|---|
| test | v2 | 201 | 81 | 1 (1.2%) | 74.1% | 0.0% | 98.1% |
| test | C3 | 201 | 82 | 0 (0.0%) | 75.1% | 0.0% | 98.1% |
| dev | v2 | 208 | 71 | 1 (1.4%) | 80.8% | 1.1% | 98.8% |
| dev | C3 | 208 | 71 | 1 (1.4%) | 80.8% | 1.1% | 98.8% |
| holdout | v2 | 186 | 64 | 6 (9.4%) | 78.0% | 0.0% | 90.6% |
| holdout | C3 | 186 | 64 | 6 (9.4%) | 78.5% | 0.0% | 90.6% |
| holdout2 | v2 | 208 | 84 | 1 (1.2%) | 83.7% | 0.9% | 98.8% |
| holdout2 | C3 | 208 | 85 | 2 (2.4%) | 84.1% | 0.9% | 98.2% |
| holdout3 | v2 | 197 | 66 | 1 (1.5%) | 75.6% | 1.1% | 99.3% |
| holdout3 | C3 | 197 | 69 | 1 (1.4%) | 76.1% | 0.0% | 98.7% |
| final | v2 | 205 | 89 | 5 (5.6%) | 84.9% | 1.0% | 98.2% |
| final | C3 | 205 | 90 | 5 (5.6%) | 84.9% | 1.0% | 98.2% |
| **pooled** | v2 | 1205 | 455 | 15 (3.30%) | 79.6% | | |
| **pooled** | C3 | 1205 | 461 | 15 (3.25%) | 80.0% | | |

Rule (H20): keep only if margin coverage on P3 stays >= 95% on every split and pooled wrong flags do not rise.
Pooled wrong flags do not rise (15 and 15), but margin coverage on holdout is 90.6%, below 95%. It was already 90.6%
with the v2 margins (the legend-occlusion bars of U18), so C3 does not cause it, but the rule as written is not met.
The gain is also small: 5 more claims decided out of 1205 (+0.4 points of coverage), one wrong flag fewer on test
and one more on holdout2. **Not kept**: `v3.yaml` keeps the v2 margins. The table stays in
`calibration_tables/c3_planner/` for the record.
