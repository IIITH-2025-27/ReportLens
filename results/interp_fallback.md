# DePlot interpolated at x values with no tick label (run_log K1)

Calibration charts only: 279 points at an unlabelled x on 11 hard line charts, where DePlot's table has no row for that x. Errors are fractions of the y-axis range.

| | value |
|---|---|
| a straight line between the two labelled neighbours gives a value | 169 of 279 (61%) |
| ... badly wrong (> 5% of the axis) | 32 (19%) |
| vlm_crop badly wrong at the same points (for comparison) | 151 of 279 (54%) |
| interpolated value and vlm_crop agree (within 3%) | 45 of 169 |
| ... and both badly wrong | 3 (6.7%) on 1 of 5 charts |
| no value: series not found or x outside the labelled range 85 | |

Curve-bend error alone (the straight line drawn through the TRUE values at the same neighbours):

| percentile | 50 | 90 | 95 | 99 |
|---|---|---|---|---|
| error | 1.5% | 3.9% | 4.8% | 6.8% |

Most badly wrong interpolations come from DePlot misreading the labelled neighbours (a few charts), not from
the bend. The pair still agrees on a wrong value more often than the planner's 5% bar, so the interpolated
value is not a profile tool: it is used only as a last step before a hand-off, with the flag margin widened
by the bend error's 95th percentile (4.8% of the axis, halved in the estimate because the
estimate averages the interpolated value with vlm_crop's direct reading). Accepts are not widened.
