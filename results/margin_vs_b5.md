# Calibrated margin against B5, and the BH batch check

Made by `python scripts/margin_vs_b5.py`; settings chosen on test, dev, measured on holdout, holdout2, holdout3, final. All-tools readings re-decided offline; the two-figure rule is not applied.

## Every setting

| Setting | Coverage (choose) | Wrong flags (choose) | Coverage (evaluate) | Wrong flags (evaluate) |
|---|---|---|---|---|
| ours, level 0.8 | 84.4% | 12.4% | 85.8% | 14.5% |
| ours, level 0.85 | 82.4% | 8.4% | 84.9% | 12.8% |
| ours, level 0.9 | 80.2% | 5.9% | 83.3% | 10.4% |
| ours, level 0.925 | 79.5% | 5.4% | 82.0% | 8.3% |
| ours, level 0.95 | 76.5% | 3.9% | 79.6% | 5.7% |
| ours, level 0.975 | 73.1% | 2.1% | 77.1% | 4.7% |
| B5, factor 0.5 | 81.7% | 17.9% | 83.2% | 18.3% |
| B5, factor 1 | 79.0% | 6.4% | 82.0% | 9.8% |
| B5, factor 1.5 | 80.2% | 4.8% | 81.8% | 6.5% |
| B5, factor 2 | 80.2% | 3.2% | 81.8% | 5.7% |
| B5, factor 3 | 73.8% | 1.5% | 78.0% | 4.9% |
| B5, factor 5 | 63.1% | 1.7% | 71.1% | 5.1% |

## Setting chosen on the first splits, measured on the others

| Target | Chosen (ours / B5) | Ours: coverage, wrong flags | B5: coverage, wrong flags | Coverage ours - B5 |
|---|---|---|---|---|
| 5% | ours, level 0.95 / B5, factor 2 | 79.6% [75.9%, 83.2%], 5.7% [3.1%, 8.8%] | 81.8% [77.9%, 85.4%], 5.7% [3.1%, 8.4%] | -2.1 points [-3.8, -0.5] |
| 10% | ours, level 0.85 / B5, factor 2 | 84.9% [81.2%, 88.4%], 12.8% [9.3%, 16.4%] | 81.8% [77.9%, 85.4%], 5.7% [3.1%, 8.4%] | +3.1 points [+1.4, +5.0] |

## The BH batch check (alpha 0.1) on all splits

| Per-claim flag level | Rule alone: coverage, wrong flags | Rule + BH: coverage, wrong flags | Verdicts BH changed |
|---|---|---|---|
| 0.6 | 86.8%, 19.7% | 79.0%, 8.3% | 94 |
| 0.7 | 86.4%, 16.8% | 80.8%, 8.2% | 67 |
| 0.8 | 85.3%, 13.8% | 82.1%, 8.8% | 39 |
| 0.9 | 82.2%, 8.9% | 82.2%, 8.9% | 0 |
| 0.95 | 78.6%, 5.1% | 78.6%, 5.1% | 0 |
