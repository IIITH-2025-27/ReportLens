# Sample reports: v4.yaml, readers = stub

**Total: 94 ok, 0 WRONG, 0 other, 1 missing** (of 95 sentences)

## 01_latex_ieee_two_column

IEEE two-column LaTeX with matplotlib PDF (vector) figures: hyphenation across lines, ligatures, the LaTeX minus sign, 10^{-4} exponents, 'Fig. N' references and IEEE 'Fig. 1.' captions.

31 sentences, figures: fig1 [vector], fig2 [vector], fig3 [vector]. Result: 12 ok, 0 WRONG, 0 other, 0 missing.

| status | truth | verdict | sentence | why it is expected | system's reason |
|---|---|---|---|---|---|
| ok | setup | SKIPPED | Each model was trained for 20 epochs with a batch size of 128 on a single GPU. | training setup, not a result | not a result claim |
| ok | true | CONSISTENT | ResNet-50 reached 91.2% validation accuracy at epoch 20 (Fig. 1). | past tense; ResNet-50 at epoch 20 is 91.2 | gap <= rounding + accept margin |
| ok | false | MISMATCH | VGG-16 achieved 88.0% validation accuracy at epoch 20. | VGG-16 at epoch 20 is 84.7 | gap > rounding + flag margin |
| ok | true | NOT_SURE | At epoch 10, VGG-16 is 6.7 points lower than ResNet-50. | 'lower than': ResNet-50 84.6 minus VGG-16 77.9 = 6.7 | ambiguous figure: fig1, fig2 |
| ok | true | CONSISTENT | From epoch 2 to epoch 20, the training loss of ResNet-50 decreased by 76%. | a fall: 1.92 -> 0.46 is -76.0% | gap <= rounding + accept margin |
| ok | true | CONSISTENT | The training loss of VGG-16 was 0.63 at epoch 20. | VGG-16 loss at epoch 20 is 0.63 | gap <= rounding + accept margin |
| ok | false | MISMATCH | The training loss of ResNet-50 was 0.30 at epoch 20. | ResNet-50 loss at epoch 20 is 0.46 | gap > rounding + flag margin |
| ok | true | NOT_SURE | On SVHN, ResNet-50 achieves 95.4% test accuracy (Fig. 3). | bar chart, SVHN 95.4 | parser: not a chart claim |
| ok | false | MISMATCH | On STL-10, ResNet-50 is 2.1 points better than VGG-16. | 78.6 - 72.3 = 6.3 | gap > rounding + flag margin |
| ok | true | CONSISTENT | VGG-16 reaches eighty-four point seven percent validation accuracy at epoch twenty. | number words: 84.7 at epoch 20 | gap <= rounding + accept margin |
| ok | true | CONSISTENT | The training loss of ResNet-50 is 4.6 × 10−1 at epoch 20. | exponent as LaTeX prints it: 4.6e-1 = 0.46 | gap <= rounding + accept margin |
| ok | setup | SKIPPED | We used a weight decay of 5 × 10−4 and a learning rate of 10−3. | exponents in a setup sentence: must not become a claim | not a result claim |

## 02_word_excel_charts

A Word-style report: Excel / Google-Sheets-look charts (no frame, the y-axis cannot be read), caption styles 'Figure 1 –', 'Fig 2:' and a caption above its figure, a figure without a caption, past tense, '~' / '>' / '≈', '(see Table 2)' and 'Dr.' in the text.

17 sentences, figures: fig1 (axis unread), fig2 (axis unread), img3, fig3. Result: 11 ok, 0 WRONG, 0 other, 0 missing.

| status | truth | verdict | sentence | why it is expected | system's reason |
|---|---|---|---|---|---|
| ok | setup | SKIPPED | All three models were trained for 8 epochs with a learning rate of 0.001 and a batch size of 32. | training setup | not a result claim |
| ok | true | CONSISTENT | BERT-base achieved 92.5% accuracy at epoch 8. | past tense; 92.5 | gap <= rounding + accept margin |
| ok | true | CONSISTENT | The GRU reached ~85% accuracy at epoch 6. | hedged '~85%': 84.9 | gap <= rounding + accept margin |
| ok | false | NOT_SURE | LSTM obtained 88.0% accuracy at epoch 8. | LSTM at epoch 8 is 84.6 | handed off: the chart's y-axis could not be read, so a mismatch has no scale to be judged against |
| ok | true | CONSISTENT | At epoch 4, BERT-base is 9.5 points higher than LSTM. | 91.4 - 81.9 = 9.5 | gap <= rounding + accept margin |
| ok | false | NOT_SURE | GRU had >85% accuracy at epoch 3. | GRU at epoch 3 is 81.0, not above 85 | handed off: the chart's y-axis could not be read, so a mismatch has no scale to be judged against |
| ok | true | CONSISTENT | On SST-2, BERT-base reached an F1 score of 94.1% (see Table 2). | 94.1; a table reference | gap <= rounding + accept margin |
| ok | true | CONSISTENT | On IMDB, the GRU scored ≈81% F1. | '≈81%': 81.0 | gap <= rounding + accept margin |
| ok | false | NOT_SURE | On AG News, LSTM obtained an F1 score of 90.0%. | LSTM on AG News is 83.4 | handed off: the chart's y-axis could not be read, so a mismatch has no scale to be judged against |
| ok | true | CONSISTENT | The training loss of the LSTM was 0.43 at epoch 8 (Figure 3). | 0.43, caption above the chart | gap <= rounding + accept margin |
| ok | true | CONSISTENT | From epoch 1 to epoch 8, the training loss of the LSTM fell by 53%. | a fall: 0.92 -> 0.43 = -53.3% | gap <= rounding + accept margin |

## 03_tricky_language

Ordinary matplotlib charts with sentences that are hard to read: negations, decreases, 'lower than' / 'trails', 'improves by 8.2%' (points or relative?), hedges on large numbers ('about 1000'), ranges '84-86%' and 'between', '±', number words, 'after 5 epochs', "X's accuracy".

23 sentences, figures: fig1, fig2, fig3. Result: 21 ok, 0 WRONG, 0 other, 0 missing.

| status | truth | verdict | sentence | why it is expected | system's reason |
|---|---|---|---|---|---|
| ok | setup | SKIPPED | We trained each network for 10 epochs and repeated every run 3 times. | setup | not a result claim |
| ok | negated | NOT_SURE | ResNet-50 does not exceed 92% accuracy at epoch 10. | negated (true, but not checked) | parser: not a chart claim |
| ok | negated | NOT_SURE | ViT-S never reaches 90% accuracy at epoch 10. | negated | handed off: the sentence is negated ('never'): the checker only verifies positive statements |
| ok | true | CONSISTENT | At epoch 10, ViT-S trails ResNet-50 by 4.0 points. | 91.2 - 87.2 = 4.0 | gap <= rounding + accept margin |
| ok | false | MISMATCH | At epoch 10, ViT-S trails ResNet-50 by 9.0 points. | the gap is 4.0 | gap > rounding + flag margin |
| ok | true | NOT_SURE | From epoch 5 to epoch 10, the accuracy of ResNet-50 improves by 8.2%. | ambiguous %: 8.2 points (true) but 9.9% relative; never a flag | handed off: the % is ambiguous: wrong as a relative change, but it matches as percentage points (estimate 8.2) |
| ok | true | CONSISTENT | From epoch 5 to epoch 10, the accuracy of ResNet-50 improves by a relative 9.9%. | explicitly relative | gap <= rounding + accept margin |
| ok | true | CONSISTENT | ResNet-50 reaches 83.0% accuracy after 5 epochs. | 'after 5 epochs' = epoch 5 | gap <= rounding + accept margin |
| ok | true | CONSISTENT | VGG-16's accuracy is 70.0% at epoch 3. | possessive phrasing | gap <= rounding + accept margin |
| ok | true | CONSISTENT | At epoch 10, VGG-16 reaches 84-86% accuracy. | range with a dash: 84.7 | gap <= rounding + accept margin |
| ok | true | CONSISTENT | At epoch 10, ResNet-50 reaches between 90% and 92% accuracy. | range: 91.2 | gap <= rounding + accept margin |
| ok | true | CONSISTENT | ResNet-50 reaches 91.2 ± 0.4% accuracy at epoch 10. | mean ± sd | gap <= rounding + accept margin |
| ok | true | CONSISTENT | ViT-S reaches eighty-seven point two percent accuracy at epoch ten. | number words: 87.2 | gap <= rounding + accept margin |
| ok | true | CONSISTENT | From epoch 1 to epoch 10, the loss of VGG-16 drops by 65%. | a fall: 2.20 -> 0.77 = -65.0% | gap <= rounding + accept margin |
| ok | false | MISMATCH | From epoch 1 to epoch 10, the loss of ResNet-50 drops by 30%. | it drops by 70% | gap > rounding + flag margin |
| ok | true | CONSISTENT | From epoch 1 to epoch 10, the loss of ResNet-50 improves by 70%. | 'improves' on a loss means it falls by 70% | gap <= rounding + accept margin |
| ok | true | CONSISTENT | The loss of VGG-16 is 0.77 at epoch 10. | 0.77 | gap <= rounding + accept margin |
| ok | true | CONSISTENT | On GPU, ResNet-50 reaches about 1000 images per second. | hedged large number: 1040 is within 5% of 'about 1000' (the old rule allowed only ±5) | gap <= rounding + accept margin |
| ok | true | CONSISTENT | On CPU, VGG-16 reaches ~35 images per second. | 35 | gap <= rounding + accept margin |
| ok | true | CONSISTENT | On GPU, ViT-S reaches >700 images per second. | 760 > 700 | gap <= rounding + accept margin |
| ok | false | MISMATCH | On GPU, VGG-16 reaches about 600 images per second. | 870 is far from 600 | gap > rounding + flag margin |

## 04_similar_names_and_splits

Model and dataset names that differ by a number (ResNet-18 / ResNet-34 / ResNet-50 / ResNet-101, CIFAR-10 / CIFAR-100, VGG-16 / VGG-19) and separate training, validation and test charts.

13 sentences, figures: fig1, fig2, fig3. Result: 10 ok, 0 WRONG, 0 other, 0 missing.

| status | truth | verdict | sentence | why it is expected | system's reason |
|---|---|---|---|---|---|
| ok | true | CONSISTENT | ResNet-18 reaches 94.1% training accuracy at epoch 10. | Figure 1, not Figure 2 | gap <= rounding + accept margin |
| ok | true | CONSISTENT | ResNet-18 reaches 84.0% validation accuracy at epoch 10. | Figure 2, not Figure 1 | gap <= rounding + accept margin |
| ok | false | MISMATCH | ResNet-50 reaches 96.4% validation accuracy at epoch 10. | 96.4 is the TRAINING value; validation is 88.5 | gap > rounding + flag margin |
| ok | no_figure | NOT_SURE | ResNet-34 reaches 86.0% validation accuracy at epoch 10. | ResNet-34 is not plotted (the old matching read ResNet-18 or ResNet-50 instead) | handed off: no trustworthy pair among the tools still available on this figure |
| ok | no_figure | NOT_SURE | VGG-19 reaches 79.5% validation accuracy at epoch 10. | VGG-19 is not plotted, only VGG-16 (whose value is 79.5) | handed off: no trustworthy pair among the tools still available on this figure |
| ok | no_figure | NO_FIGURE | ResNet-50 reaches 89.0% test accuracy at epoch 10. | no test curve: the curves are training and validation | no figure shows this series / x |
| ok | true | CONSISTENT | On CIFAR-100, ResNet-50 achieves 78.2% test accuracy. | CIFAR-100 bar | gap <= rounding + accept margin |
| ok | false | MISMATCH | On CIFAR-100, ResNet-18 achieves 92.1% test accuracy. | 92.1 is CIFAR-10; CIFAR-100 is 70.3 (the old matching read the CIFAR-10 bar) | gap > rounding + flag margin |
| ok | true | CONSISTENT | On CIFAR-10, ResNet-101 is 0.7 points better than ResNet-50. | 95.3 - 94.6 = 0.7 | gap <= rounding + accept margin |
| ok | no_figure | NOT_SURE | On CIFAR-10, ResNet-152 achieves 96.0% test accuracy. | ResNet-152 is not plotted | handed off: no trustworthy pair among the tools still available on this figure |

## 05_hard_charts

Chart kinds the reading tools cannot judge safely: two y-axes, an axis multiplier (1e-5), a log scale, a seaborn style, horizontal bars, and a two-panel figure. Claims here should be handed to the TA (NOT_SURE) unless they can be measured properly; none may be flagged wrongly.

10 sentences, figures: fig1 [dual_y], fig2 [axis_multiplier], fig3 [log_y], fig4 (axis unread), fig5 (axis unread), fig6a, fig6b. Result: 9 ok, 0 WRONG, 0 other, 0 missing.

| status | truth | verdict | sentence | why it is expected | system's reason |
|---|---|---|---|---|---|
| ok | true | NOT_SURE | ResNet-50 reaches 91.2% accuracy at epoch 10 (Figure 1). | two y-axes: hand to the TA | handed off: the chart has two y-axes, and which series belongs to which axis is not known |
| ok | false | NOT_SURE | ResNet-50 reaches 70.0% accuracy at epoch 10 (Figure 1). | 91.2; two y-axes | handed off: the chart has two y-axes, and which series belongs to which axis is not known |
| ok | true | NOT_SURE | ResNet-50 has a gradient norm of 0.00056 at epoch 10 (Figure 2). | the axis shows 5.6 with '1e-4' above it: readers report 5.6 | handed off: the y-axis has a multiplier above it (like 1e-5 or +1e3) that the reading tools ignore |
| ok | true | CONSISTENT | ResNet-50 has a training loss of 0.005 at epoch 10 (Figure 3). | log scale | gap <= rounding + accept margin |
| ok | true | CONSISTENT | VGG-16 reaches 84.7% validation accuracy at epoch 10 (Figure 4). | seaborn style | gap <= rounding + accept margin |
| ok | false | NOT_SURE | VGG-16 reaches 89.0% validation accuracy at epoch 10 (Figure 4). | 84.7; the axis cannot be read, so this must not be flagged by guesswork | handed off: the chart's y-axis could not be read, so a mismatch has no scale to be judged against |
| ok | true | CONSISTENT | On SVHN, VGG-16 achieves 93.1% test accuracy (Figure 5). | horizontal bars | gap <= rounding + accept margin |
| ok | true | CONSISTENT | In Figure 6(b), the loss of ResNet-50 is 0.60 at epoch 10. | panel b | gap <= rounding + accept margin |
| ok | false | MISMATCH | In Figure 6(a), ResNet-50 reaches 80.0% accuracy at epoch 10. | 91.2 in panel a | gap > rounding + flag margin |

## 06_scanned_copy

Report 03 printed and scanned: every page is one greyscale image, slightly rotated and JPEG compressed, with no text layer. The old web config found 0 sentences and showed an empty, clean-looking result. OCR errors may change words, so sentences are matched loosely.

24 sentences, figures: fig1 (axis unread) [scanned], fig2 (axis unread) [scanned], fig3 (axis unread) [scanned]. Result: 20 ok, 0 WRONG, 0 other, 1 missing.

| status | truth | verdict | sentence | why it is expected | system's reason |
|---|---|---|---|---|---|
| missing | setup | - | We trained each network for 10 epochs and repeated every run 3 times. | setup |  |
| ok | negated | NOT_SURE | ResNet-50 does not exceed 92% accuracy at epoch 10. | negated (true, but not checked) | parser: not a chart claim |
| ok | negated | NOT_SURE | ViT-S never reaches 90% accuracy at epoch 10. | negated | handed off: the sentence is negated ('never'): the checker only verifies positive statements |
| ok | true | NOT_SURE | At epoch 10, ViT-S trails ResNet-50 by 4.0 points. | 91.2 - 87.2 = 4.0 | handed off: the chart comes from a scanned page and its y-axis could not be read, so the reading error has no  |
| ok | false | NOT_SURE | At epoch 10, ViT-S trails ResNet-50 by 9.0 points. | the gap is 4.0 | handed off: the chart comes from a scanned page and its y-axis could not be read, so the reading error has no  |
| ok | true | NOT_SURE | From epoch 5 to epoch 10, the accuracy of ResNet-50 improves by 8.2%. | ambiguous %: 8.2 points (true) but 9.9% relative; never a flag | handed off: the chart comes from a scanned page and its y-axis could not be read, so the reading error has no  |
| ok | true | NOT_SURE | From epoch 5 to epoch 10, the accuracy of ResNet-50 improves by a relative 9.9%. | explicitly relative | handed off: the chart comes from a scanned page and its y-axis could not be read, so the reading error has no  |
| ok | true | NOT_SURE | ResNet-50 reaches 83.0% accuracy after 5 epochs. | 'after 5 epochs' = epoch 5 | handed off: the chart comes from a scanned page and its y-axis could not be read, so the reading error has no  |
| ok | true | NOT_SURE | VGG-16's accuracy is 70.0% at epoch 3. | possessive phrasing | handed off: the chart comes from a scanned page and its y-axis could not be read, so the reading error has no  |
| ok | true | NOT_SURE | At epoch 10, VGG-16 reaches 84-86% accuracy. | range with a dash: 84.7 | handed off: the chart comes from a scanned page and its y-axis could not be read, so the reading error has no  |
| ok | true | NOT_SURE | At epoch 10, ResNet-50 reaches between 90% and 92% accuracy. | range: 91.2 | handed off: the chart comes from a scanned page and its y-axis could not be read, so the reading error has no  |
| ok | true | NOT_SURE | ResNet-50 reaches 91.2 ± 0.4% accuracy at epoch 10. | mean ± sd | parser: not a chart claim |
| ok | true | NOT_SURE | ViT-S reaches eighty-seven point two percent accuracy at epoch ten. | number words: 87.2 | handed off: the chart comes from a scanned page and its y-axis could not be read, so the reading error has no  |
| ok | true | NOT_SURE | From epoch 1 to epoch 10, the loss of VGG-16 drops by 65%. | a fall: 2.20 -> 0.77 = -65.0% | handed off: the chart comes from a scanned page and its y-axis could not be read, so the reading error has no  |
| ok | false | NOT_SURE | From epoch 1 to epoch 10, the loss of ResNet-50 drops by 30%. | it drops by 70% | handed off: the chart comes from a scanned page and its y-axis could not be read, so the reading error has no  |
| ok | true | NOT_SURE | From epoch 1 to epoch 10, the loss of ResNet-50 improves by 70%. | 'improves' on a loss means it falls by 70% | handed off: the chart comes from a scanned page and its y-axis could not be read, so the reading error has no  |
| ok | true | NOT_SURE | The loss of VGG-16 is 0.77 at epoch 10. | 0.77 | handed off: the chart comes from a scanned page and its y-axis could not be read, so the reading error has no  |
| ok | true | NOT_SURE | On GPU, ResNet-50 reaches about 1000 images per second. | hedged large number: 1040 is within 5% of 'about 1000' (the old rule allowed only ±5) | handed off: the chart comes from a scanned page and its y-axis could not be read, so the reading error has no  |
| ok | true | NOT_SURE | On CPU, VGG-16 reaches ~35 images per second. | 35 | handed off: the chart comes from a scanned page and its y-axis could not be read, so the reading error has no  |
| ok | true | NOT_SURE | On GPU, ViT-S reaches >700 images per second. | 760 > 700 | handed off: the chart comes from a scanned page and its y-axis could not be read, so the reading error has no  |
| ok | false | NOT_SURE | On GPU, VGG-16 reaches about 600 images per second. | 870 is far from 600 | handed off: the chart comes from a scanned page and its y-axis could not be read, so the reading error has no  |

## 07_latex_pgfplots_full_report

A three-page LaTeX article whose charts are drawn by pgfplots (vector graphics with real text labels), with setup numbers that must be skipped, 'Figs. 1 and 2' citations, a repeated sentence, claims in captions and a mix of true and false statements.

22 sentences, figures: fig1 [vector], fig2 [vector], fig3 (axis unread) [vector]. Result: 11 ok, 0 WRONG, 0 other, 0 missing.

| status | truth | verdict | sentence | why it is expected | system's reason |
|---|---|---|---|---|---|
| ok | setup | SKIPPED | All models were trained for 20 epochs on 4 GPUs with a batch size of 256. | setup | not a result claim |
| ok | setup | SKIPPED | The learning rate was reduced by 10% every 5 epochs. | setup with 'reduced by 10%': not a chart claim | not a result claim |
| ok | true | CONSISTENT | ResNet-50 achieved 91.2% validation accuracy at epoch 20. | 91.2 | gap <= rounding + accept margin |
| ok | false | MISMATCH | ViT-S reached 90.0% validation accuracy at epoch 20. | 87.4 | gap > rounding + flag margin |
| ok | true | NOT_SURE | At epoch 10, ViT-S is 4.3 points lower than ResNet-50. | 84.6 - 80.3 = 4.3 | ambiguous figure: fig1, fig2 |
| ok | true | CONSISTENT | From epoch 2 to epoch 20, the training loss of ViT-S fell by 71%. | 2.20 -> 0.64 = -70.9% | gap <= rounding + accept margin |
| ok | true | CONSISTENT | The training loss of ResNet-50 is 0.46 at epoch 20. | 0.46 | gap <= rounding + accept margin |
| ok | true | CONSISTENT | On SVHN, ViT-S achieves 93.8% test accuracy. | 93.8 | gap <= rounding + accept margin |
| ok | false | NOT_SURE | On CIFAR-10, ResNet-50 is 6.0 points better than ViT-S. | 91.2 - 87.4 = 3.8 | handed off: the chart's y-axis could not be read, so a mismatch has no scale to be judged against |
| ok | negated | NOT_SURE | ViT-S does not reach the accuracy of ResNet-50 at any epoch, staying below 88%. | negated | parser: not a chart claim |
| ok | true | CONSISTENT | ResNet-50 reaches 91.2% at epoch 20. | a claim inside a caption (v3 A4) | gap <= rounding + accept margin |
