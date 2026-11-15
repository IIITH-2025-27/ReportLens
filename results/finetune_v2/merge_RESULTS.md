# Six-shard LoRA: results

Shards merged: 7 (shard_1, shard_2, shard_3, shard_4, shard_5, shard_6, shard_7); reports 5819; charts 21167.

Chosen by validation loss (200 validation charts): **merged_avg**.

| model | validation loss |
|---|---|
| merged_avg | 0.2437 |
| shard_2 | 0.2467 |
| shard_7 | 0.2471 |
| shard_1 | 0.2475 |
| shard_4 | 0.2478 |
| shard_5 | 0.2481 |
| shard_3 | 0.2497 |
| shard_6 | 0.2503 |
| merged_ties | 0.2786 |
| base | 0.6051 |

## Test: the same 300 charts (one per test report, all 21 templates)

| measure | base | merged_avg | shard_2 | merged_ties |
|---|---|---|---|---|
| charts scored | 300 | 300 | 300 | 300 |
| answers that parse | 0.993 | 0.993 | 0.993 | 0.947 |
| cells answered | 0.675 | 0.851 | 0.839 | 0.691 |
| median error (share of axis) | 0.014068466537147415 | 0.006771626883358734 | 0.006850253459377997 | 0.011655011655011819 |
| 90th percentile error | 0.2594670406732118 | 0.26350461133069836 | 0.22722029988465975 | 0.42635658914728686 |
| badly wrong (> 5% of axis) | 0.288 | 0.247 | 0.238 | 0.326 |
| within 2% of axis | 0.561 | 0.65 | 0.651 | 0.581 |
