# ClinOCR-Bench — lab & pathology OCR accuracy

Generated: 2026-10-19 23:17 · Runtime: 11.5s (PaddleOCR, CPU) · no LLM, no network calls during scoring.

Dataset: [ClinOCR-Bench](https://huggingface.co/datasets/ClinOCR-Bench/ClinOCR-Bench) (MIT). Test split only, filtered to laboratory and pathology templates: t2/t6 pathology reports, t11/t12/t15 lab panels. Ground truth is the dataset's human-audited transcription.

## Headline

- **Character accuracy (strict): 80.7%** (CER 19.3%) over 3 documents.
- **Word content F1 (order-free): 95.7%** (precision 96.2%, recall 95.2%).
- **Numeric literals recovered: 87.0%** (100/115, F1 88.5%).
- **Key-level lab rows recovered: n/a** (0/0, precision n/a, F1 n/a) on 0 numeric lab panels.
- **Status agreement (Low/Normal/High): n/a** (0/0).
- OCR failures: 0.

Strict CER/WER compare linear reading order; these scans have two-column
headers, so OCR merges columns and pays an order penalty that the
order-free word-content metric excludes. Both are reported.

## By acquisition condition

| Subset | Docs | Char accuracy | Word content F1 | Number recall | Key-level P / R / F1 | Status agree | Lab-panel docs |
|---|---|---|---|---|---|---|---|
| normal | 3 | 80.7% | 95.7% | 87.0% | n/a / n/a / n/a | n/a | 0 |
| **All** | 3 | 80.7% | 95.7% | 87.0% | n/a / n/a / n/a | n/a | 0 |

## By report type

| Template | Type | Docs | Char accuracy | Word content F1 | Number recall | Key-level P / R / F1 | Status agree | Lab-panel docs |
|---|---|---|---|---|---|---|---|
| t2 — Pathology report (surgical) | 3 | 80.7% | 95.7% | 87.0% | n/a / n/a / n/a | n/a | 0 |

## Per-document results

| doc_id | Subset | Type | Char acc. | Word content F1 | Numbers recalled | Lab rows recovered | Status | OCR s |
|---|---|---|---|---|---|---|---|---|
| normal_t2_s2 | normal | t2 | 74.7% | 94.4% | 29/35 | n/a (narrative) | n/a | 0.0 |
| normal_t2_s3 | normal | t2 | 84.3% | 97.7% | 33/35 | n/a (narrative) | n/a | 0.0 |
| normal_t2_s4 | normal | t2 | 83.2% | 95.2% | 38/45 | n/a (narrative) | n/a | 0.0 |

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
  narrative and would only contribute header-number false positives.
- **Status agreement** is computed among value-matched rows only.
