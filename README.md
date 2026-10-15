# ReportLens

Uncertainty-aware verification of number-based chart claims in student technical reports.

ReportLens checks whether the numbers written in a report match its own charts. Each chart value is read through four different tools, and the spread of those readings is calibrated against charts with known values. A claim is flagged only when the mismatch is clearly larger than the reading error. Unclear cases go to the TA instead of becoming a wrong accusation.

## How it works

1. **Find the figure.** Match the sentence to the right chart, or return "no matching figure".
2. **Parse the claim.** Turn the sentence into a checkable form: series, point, value, allowed rounding.
3. **Measure.** Read the value with a VLM crop, a VLM chart-to-table pass, DePlot, and OCR with pixel measurement. Take the median.
4. **Calibrate.** Convert tool disagreement into an error margin using conformal calibration on charts with known values.
5. **Decide.** Flag, accept, or send to the TA. Benjamini–Hochberg controls the wrong-flag rate across a batch.

## Outcomes

| Verdict | Meaning |
|---|---|
| Consistent | Claim matches the chart within the error margin |
| Mismatch | Gap is clearly larger than the reading error |
| Not sure | Sent to the TA for review |
| No matching figure | No chart covers the claim |

## Status

Proposal stage. LMA Group Project 2026.

## Team

Harsh Raj, Hritik Ranjan, Karan Thayat, Vikash Kumar
