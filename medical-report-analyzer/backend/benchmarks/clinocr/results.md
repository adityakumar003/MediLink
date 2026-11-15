# ClinOCR-Bench — lab & pathology OCR accuracy

Generated: 2026-10-20 00:59 · Runtime: 1747.8s (PaddleOCR, CPU) · no LLM, no network calls during scoring.

Dataset: [ClinOCR-Bench](https://huggingface.co/datasets/ClinOCR-Bench/ClinOCR-Bench) (MIT). Test split only, filtered to laboratory and pathology templates: t2/t6 pathology reports, t11/t12/t15 lab panels. Ground truth is the dataset's human-audited transcription.

## Headline

- **Character accuracy (strict): 61.4%** (CER 38.6%) over 92 documents.
- **Word content F1 (order-free): 73.5%** (precision 83.7%, recall 65.5%).
- **Numeric literals recovered: 75.7%** (3619/4780, F1 79.6%).
- **Print-only accuracy (handwriting excluded): 80.4%** word content F1 / 65.8% strict / 77.4% of numbers (78 documents).
- **Key-level lab rows recovered: 51.4%** (144/280, precision 83.7%, F1 63.7%) on 30 numeric lab panels.
- **Status agreement (Low/Normal/High): 100.0%** (50/50).
- OCR failures: 1.

Strict CER/WER compare linear reading order; these scans have two-column
headers, so OCR merges columns and pays an order penalty that the
order-free word-content metric excludes. Both are reported.

Status agreement is n/a here: these column tables keep value / flag /
site on separate lines, so the deterministic parser (built for
single-line lab rows) cannot pair a value with its range even in the
ground-truth text, leaving no value-matched row with a definite
reference status. Status handling is covered by the internal gold
fixtures instead (see backend/tools/eval_report.md).

## By acquisition condition

| Subset | Docs | Char accuracy | Word content F1 | Number recall | Key-level P / R / F1 | Status agree | Lab-panel docs |
|---|---|---|---|---|---|---|---|
| normal | 14 | 82.6% | 92.8% | 90.9% | n/a / n/a / n/a | n/a | 0 |
| handwriting | 14 | 42.1% | 31.7% | 60.0% | n/a / n/a / n/a | n/a | 0 |
| poor | 14 | 71.3% | 70.9% | 75.9% | n/a / n/a / n/a | n/a | 0 |
| rotated | 14 | 53.6% | 90.5% | 71.5% | n/a / n/a / n/a | n/a | 0 |
| tables | 21 | 85.0% | 91.9% | 91.0% | 89.8% / 67.3% / 77.0% | 100.0% | 21 |
| mixed | 15 | 33.1% | 41.0% | 48.4% | 48.0% / 14.3% / 22.0% | 100.0% | 9 |
| **Print-only (no handwriting)** | 78 | 65.8% | 80.4% | 77.4% | 83.7% / 51.4% / 63.7% | 100.0% | 30 |
| **All** | 92 | 61.4% | 73.5% | 75.7% | 83.7% / 51.4% / 63.7% | 100.0% | 30 |

## By report type

| Template | Type | Docs | Char accuracy | Word content F1 | Number recall | Key-level P / R / F1 | Status agree | Lab-panel docs |
|---|---|---|---|---|---|---|---|
| t2 — Pathology report (surgical) | 31 | 55.7% | 68.0% | 66.5% | n/a / n/a / n/a | n/a | 0 |
| t6 — Pathology report (biopsy) | 31 | 60.8% | 72.2% | 75.6% | n/a / n/a / n/a | n/a | 0 |
| t11 — Lab panel (CMP + HbA1c) | 10 | 85.1% | 86.9% | 85.3% | 74.3% / 48.8% / 58.9% | n/a | 10 |
| t12 — Lab panel (lipid profile) | 10 | 74.5% | 77.3% | 77.9% | 94.1% / 40.0% / 56.1% | n/a | 10 |
| t15 — Lab panel (CBC) | 10 | 61.1% | 79.4% | 66.7% | 100.0% / 62.5% / 76.9% | 100.0% | 10 |

## Per-document results

| doc_id | Subset | Type | Char acc. | Word content F1 | Numbers recalled | Lab rows recovered | Status | OCR s |
|---|---|---|---|---|---|---|---|---|
| normal_t2_s2 | normal | t2 | 72.4% | 89.0% | 29/35 | n/a (narrative) | n/a | 34.6 |
| normal_t2_s3 | normal | t2 | 81.8% | 92.4% | 27/35 | n/a (narrative) | n/a | 7.3 |
| normal_t2_s4 | normal | t2 | 73.4% | 87.1% | 41/45 | n/a (narrative) | n/a | 7.6 |
| normal_t2_s5 | normal | t2 | 82.3% | 93.4% | 32/36 | n/a (narrative) | n/a | 8.4 |
| normal_t2_s6 | normal | t2 | 80.6% | 91.1% | 37/43 | n/a (narrative) | n/a | 6.6 |
| normal_t2_s7 | normal | t2 | 79.1% | 93.8% | 26/32 | n/a (narrative) | n/a | 6.8 |
| normal_t2_s8 | normal | t2 | 81.3% | 91.1% | 45/49 | n/a (narrative) | n/a | 6.9 |
| normal_t6_s2 | normal | t6 | 87.7% | 92.7% | 24/24 | n/a (narrative) | n/a | 5.5 |
| normal_t6_s3 | normal | t6 | 85.7% | 97.2% | 19/19 | n/a (narrative) | n/a | 5.1 |
| normal_t6_s4 | normal | t6 | 85.0% | 92.7% | 37/39 | n/a (narrative) | n/a | 22.9 |
| normal_t6_s5 | normal | t6 | 90.8% | 96.1% | 27/29 | n/a (narrative) | n/a | 23.9 |
| normal_t6_s6 | normal | t6 | 89.3% | 94.7% | 31/31 | n/a (narrative) | n/a | 25.1 |
| normal_t6_s7 | normal | t6 | 81.7% | 96.6% | 19/19 | n/a (narrative) | n/a | 18.7 |
| normal_t6_s8 | normal | t6 | 88.0% | 95.3% | 24/24 | n/a (narrative) | n/a | 22.4 |
| handwriting_t2_s2 | handwriting | t2 | 35.1% | 31.8% | 24/35 | n/a (narrative) | n/a | 18.0 |
| handwriting_t2_s3 | handwriting | t2 | 51.3% | 32.4% | 14/35 | n/a (narrative) | n/a | 21.6 |
| handwriting_t2_s4 | handwriting | t2 | 30.2% | 26.4% | 12/45 | n/a (narrative) | n/a | 21.0 |
| handwriting_t2_s5 | handwriting | t2 | 40.6% | 30.1% | 27/36 | n/a (narrative) | n/a | 16.3 |
| handwriting_t2_s6 | handwriting | t2 | 55.6% | 45.2% | 31/43 | n/a (narrative) | n/a | 27.6 |
| handwriting_t2_s7 | handwriting | t2 | 35.4% | 35.7% | 18/32 | n/a (narrative) | n/a | 16.2 |
| handwriting_t2_s8 | handwriting | t2 | 43.4% | 24.6% | 17/49 | n/a (narrative) | n/a | 28.0 |
| handwriting_t6_s2 | handwriting | t6 | 24.8% | 23.7% | 19/24 | n/a (narrative) | n/a | 13.0 |
| handwriting_t6_s3 | handwriting | t6 | 66.1% | 34.5% | 17/19 | n/a (narrative) | n/a | 13.6 |
| handwriting_t6_s4 | handwriting | t6 | 51.9% | 29.6% | 28/39 | n/a (narrative) | n/a | 16.5 |
| handwriting_t6_s5 | handwriting | t6 | 40.8% | 24.7% | 28/29 | n/a (narrative) | n/a | 16.0 |
| handwriting_t6_s6 | handwriting | t6 | 32.2% | 16.0% | 15/31 | n/a (narrative) | n/a | 15.3 |
| handwriting_t6_s7 | handwriting | t6 | 77.7% | 68.3% | 19/19 | n/a (narrative) | n/a | 20.1 |
| handwriting_t6_s8 | handwriting | t6 | 15.2% | 20.1% | 7/24 | n/a (narrative) | n/a | 8.3 |
| poor_t2_s2 | poor | t2 | 56.9% | 90.9% | 35/35 | n/a (narrative) | n/a | 26.8 |
| poor_t2_s3 | poor | t2 | 80.5% | 93.4% | 32/35 | n/a (narrative) | n/a | 25.5 |
| poor_t2_s4 | poor | t2 | 66.6% | 40.6% | 30/45 | n/a (narrative) | n/a | 29.1 |
| poor_t2_s5 | poor | t2 | 51.4% | 19.1% | 14/36 | n/a (narrative) | n/a | 23.6 |
| poor_t2_s6 | poor | t2 | 79.5% | 86.6% | 39/43 | n/a (narrative) | n/a | 23.9 |
| poor_t2_s7 | poor | t2 | 59.2% | 17.5% | 6/32 | n/a (narrative) | n/a | 22.3 |
| poor_t2_s8 | poor | t2 | 70.5% | 78.0% | 42/49 | n/a (narrative) | n/a | 25.7 |
| poor_t6_s2 | poor | t6 | 86.5% | 97.1% | 22/24 | n/a (narrative) | n/a | 20.1 |
| poor_t6_s3 | poor | t6 | 82.7% | 91.8% | 19/19 | n/a (narrative) | n/a | 20.0 |
| poor_t6_s4 | poor | t6 | 71.6% | 45.5% | 17/39 | n/a (narrative) | n/a | 20.8 |
| poor_t6_s5 | poor | t6 | 90.8% | 97.1% | 29/29 | n/a (narrative) | n/a | 24.8 |
| poor_t6_s6 | poor | t6 | 57.5% | 91.1% | 30/31 | n/a (narrative) | n/a | 24.4 |
| poor_t6_s7 | poor | t6 | 65.4% | 24.8% | 11/19 | n/a (narrative) | n/a | 19.0 |
| poor_t6_s8 | poor | t6 | 86.2% | 85.5% | 23/24 | n/a (narrative) | n/a | 23.0 |
| rotated_t2_s2 | rotated | t2 | 57.7% | 92.8% | 32/35 | n/a (narrative) | n/a | 29.7 |
| rotated_t2_s3 | rotated | t2 | 46.2% | 83.0% | 17/35 | n/a (narrative) | n/a | 21.0 |
| rotated_t2_s4 | rotated | t2 | 30.3% | 89.4% | 17/45 | n/a (narrative) | n/a | 24.4 |
| rotated_t2_s5 | rotated | t2 | 47.3% | 93.9% | 24/36 | n/a (narrative) | n/a | 26.9 |
| rotated_t2_s6 | rotated | t2 | 49.1% | 91.4% | 30/43 | n/a (narrative) | n/a | 22.7 |
| rotated_t2_s7 | rotated | t2 | 72.7% | 88.6% | 24/32 | n/a (narrative) | n/a | 22.9 |
| rotated_t2_s8 | rotated | t2 | 57.1% | 91.6% | 42/49 | n/a (narrative) | n/a | 25.8 |
| rotated_t6_s2 | rotated | t6 | 43.6% | 96.4% | 18/24 | n/a (narrative) | n/a | 20.2 |
| rotated_t6_s3 | rotated | t6 | 45.8% | 91.4% | 14/19 | n/a (narrative) | n/a | 18.7 |
| rotated_t6_s4 | rotated | t6 | 50.0% | 92.9% | 26/39 | n/a (narrative) | n/a | 19.2 |
| rotated_t6_s5 | rotated | t6 | 87.2% | 96.5% | 27/29 | n/a (narrative) | n/a | 24.4 |
| rotated_t6_s6 | rotated | t6 | 62.2% | 93.4% | 31/31 | n/a (narrative) | n/a | 24.1 |
| rotated_t6_s7 | rotated | t6 | 77.3% | 97.9% | 19/19 | n/a (narrative) | n/a | 19.6 |
| rotated_t6_s8 | rotated | t6 | 27.5% | 64.4% | 8/24 | n/a (narrative) | n/a | 21.4 |
| tables_t11_s2 | tables | t11 | 90.6% | 95.5% | 141/149 | 10/16 | n/a | 25.1 |
| tables_t11_s3 | tables | t11 | 91.1% | 96.2% | 142/149 | 9/16 | n/a | 17.6 |
| tables_t11_s4 | tables | t11 | 91.1% | 94.6% | 142/149 | 9/16 | n/a | 8.4 |
| tables_t11_s5 | tables | t11 | 91.5% | 97.3% | 142/149 | 10/16 | n/a | 16.4 |
| tables_t11_s6 | tables | t11 | 91.1% | 95.2% | 142/149 | 10/16 | n/a | 24.2 |
| tables_t11_s7 | tables | t11 | 90.3% | 95.9% | 142/149 | 10/16 | n/a | 25.1 |
| tables_t11_s8 | tables | t11 | 91.3% | 96.2% | 142/149 | 11/16 | n/a | 21.0 |
| tables_t12_s2 | tables | t12 | 88.4% | 77.0% | 67/74 | 2/4 | n/a | 17.3 |
| tables_t12_s3 | tables | t12 | 89.1% | 91.6% | 68/75 | 2/4 | n/a | 17.1 |
| tables_t12_s4 | tables | t12 | 88.5% | 85.7% | 70/75 | 2/4 | n/a | 17.9 |
| tables_t12_s5 | tables | t12 | 89.6% | 91.4% | 67/74 | 2/4 | n/a | 8.4 |
| tables_t12_s6 | tables | t12 | 89.1% | 89.5% | 70/75 | 2/4 | n/a | 17.6 |
| tables_t12_s7 | tables | t12 | 89.1% | 93.5% | 68/75 | 2/4 | n/a | 7.9 |
| tables_t12_s8 | tables | t12 | 88.7% | 85.2% | 68/75 | 2/4 | n/a | 9.8 |
| tables_t15_s2 | tables | t15 | 69.0% | 91.5% | 40/51 | 8/8 | 8/8 | 13.5 |
| tables_t15_s3 | tables | t15 | 69.2% | 89.3% | 48/60 | 8/8 | 8/8 | 14.4 |
| tables_t15_s4 | tables | t15 | 67.9% | 88.9% | 40/51 | 5/8 | 5/5 | 12.5 |
| tables_t15_s5 | tables | t15 | 68.5% | 88.9% | 40/51 | 7/8 | 7/7 | 12.8 |
| tables_t15_s6 | tables | t15 | 68.0% | 89.9% | 40/51 | 7/8 | 7/7 | 12.9 |
| tables_t15_s7 | tables | t15 | 67.1% | 89.0% | 40/51 | 8/8 | 8/8 | 12.3 |
| tables_t15_s8 | tables | t15 | 67.4% | 86.0% | 40/51 | 6/8 | 6/6 | 12.5 |
| mixed_t11_s5 | mixed | t11 | 85.5% | 96.8% | 142/149 | 8/16 | n/a | 26.5 |
| mixed_t11_s6 | mixed | t11 | 53.6% | 33.9% | 45/149 | 0/16 | n/a | 23.1 |
| mixed_t11_s8 | mixed | t11 | 75.3% | 52.8% | 91/149 | 1/16 | n/a | 23.9 |
| mixed_t12_s2 | mixed | t12 | 3.1% | 2.0% | 1/74 | 0/4 | n/a | 2.5 |
| mixed_t12_s3 | mixed | t12 | 52.1% | 41.8% | 38/75 | 0/4 | n/a | 10.4 |
| mixed_t12_s8 | mixed | t12 | 70.8% | 80.4% | 65/75 | 2/4 | n/a | 15.9 |
| mixed_t15_s6 | mixed | t15 | 52.0% | 84.1% | 33/51 | 1/8 | 1/1 | 13.2 |
| mixed_t15_s7 | mixed | t15 | 23.5% | 17.8% | 7/51 | 0/8 | n/a | 9.1 |
| mixed_t15_s8 | mixed | t15 | 56.8% | 42.1% | 18/51 | 0/8 | n/a | 12.6 |
| mixed_t2_s2 | mixed | t2 | 28.1% | 31.0% | 22/35 | n/a (narrative) | n/a | 17.7 |
| mixed_t2_s4 | mixed | t2 | 14.8% | 16.9% | 12/45 | n/a (narrative) | n/a | 14.3 |
| mixed_t2_s7 | mixed | t2 | 21.6% | 15.9% | 8/32 | n/a (narrative) | n/a | 14.7 |
| mixed_t6_s2 | mixed | t6 | 0.0% | 0.0% | 0/24 | n/a (narrative) | n/a | 4.1 |
| mixed_t6_s3 | mixed | t6 | 22.9% | 11.5% | 3/19 | n/a (narrative) | n/a | 14.7 |
| mixed_t6_s5 | mixed | t6 | 11.6% | 5.3% | 3/29 | n/a (narrative) | n/a | 8.1 |

## Definitions

- **Character accuracy (strict)** = 1 − normalized edit distance against
  the human-audited ground truth; it penalizes reading-order differences.
- **Word content F1 (order-free)** = token multiset overlap (lowercased
  alphanumerics), insensitive to column reading order.
- **Number recall**: share of numeric literals in the ground truth that
  also appear in the OCR output (order-preserving LCS).
- **Key-level**: the real offline parser is run on both the ground truth
  and the OCR text; a row counts only when the canonical test name matches
  and the value is within max(0.01, 0.5%) of the reference value.
  Scored only on numeric lab panels (t11/t12/t15); pathology reports are
  narrative. Note: these synthetic tables place value / flag / previous
  result / site in separate columns, a layout the offline parser (built
  for single-line Indian lab rows) misreads even on perfect ground-truth
  text -- so this is an end-to-end pipeline figure, not pure OCR quality.
- **Status agreement** is computed among value-matched rows whose ground
  truth status is Low/Normal/High/Critical (Unknown is excluded).


Wrote C:\Coding\major_project\medical-report-analyzer\backend\benchmarks\clinocr\results.md and C:\Coding\major_project\medical-report-analyzer\backend\benchmarks\clinocr\results.jso