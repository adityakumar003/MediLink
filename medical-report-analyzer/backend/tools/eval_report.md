# Extraction accuracy report

Generated: 2026-10-19 22:54 (local, no network calls)

## Summary

| File | OCR CER | WER | Numbers F1 | Key levels P / R / F1 | Status agree | Gold values |
|---|---|---|---|---|---|---|
| test_report_aditya.pdf | 18.2% | 16.5% | 97.2% | 100.0% / 100.0% / 100.0% | 100% | no labels |
| test_report_anemia_dummy.png | n/a | n/a | n/a | n/a | n/a | 5/5 |
| test_report_lakshya.pdf | 10.0% | 11.1% | 96.6% | 100.0% / 100.0% / 100.0% | 100% | no labels |
| test_report_subhayu.pdf | 0.6% | 6.1% | 100.0% | 100.0% / 100.0% / 100.0% | 100% | no labels |

Pooled over files with references: CER 10.5%, WER 11.7%, key-level P 100.0% / R 100.0% / F1 100.0% (35 of 35 reference rows recovered; 0 spurious).

## Details

### `test_report_aditya.pdf`

- Processed in 61.9s (2 page(s); 1608 reference chars / 1315 OCR chars)
- **OCR:** CER **18.2%** (293 wrong chars / 1608), WER **16.5%** (41 wrong words / 249)
- **Numeric literals:** 53/56 recalled, 53/53 precise (P 100.0% / R 94.6% / F1 97.2%)
- **Key levels (name+value):** 12/12 reference rows recovered (P 100.0% / R 100.0% / F1 100.0%)
  - status agreement: 12/12 (100.0%)

### `test_report_anemia_dummy.png`

- Processed in 2.7s (1 page(s); 0 reference chars / 312 OCR chars)
- **OCR:** no digital text layer (scanned/image-only) -- CER not applicable
- **Gold labels:** 5/5 values correct, 5/5 statuses correct
  - [PASS] Hemoglobin (Hb): got 9.8, expected 9.8; status Low vs Low [PASS]
  - [PASS] MCV: got 74, expected 74; status Low vs Low [PASS]
  - [PASS] Serum Iron: got 38, expected 38; status Low vs Low [PASS]
  - [PASS] Fasting Blood Glucose: got 112, expected 112; status High vs High [PASS]
  - [PASS] Serum Creatinine: got 1.0, expected 1.0; status Normal vs Normal [PASS]

### `test_report_lakshya.pdf`

- Processed in 7.2s (1 page(s); 1168 reference chars / 1053 OCR chars)
- **OCR:** CER **10.0%** (117 wrong chars / 1168), WER **11.1%** (20 wrong words / 180)
- **Numeric literals:** 42/45 recalled, 42/42 precise (P 100.0% / R 93.3% / F1 96.6%)
- **Key levels (name+value):** 11/11 reference rows recovered (P 100.0% / R 100.0% / F1 100.0%)
  - status agreement: 11/11 (100.0%)

### `test_report_subhayu.pdf`

- Processed in 25.0s (1 page(s); 1212 reference chars / 1207 OCR chars)
- **OCR:** CER **0.6%** (7 wrong chars / 1212), WER **6.1%** (12 wrong words / 196)
- **Numeric literals:** 45/45 recalled, 45/45 precise (P 100.0% / R 100.0% / F1 100.0%)
- **Key levels (name+value):** 12/12 reference rows recovered (P 100.0% / R 100.0% / F1 100.0%)
  - status agreement: 12/12 (100.0%)

## How to read these numbers

- **CER/WER** compare OCR against the PDF's own digital text layer;
  the PDF was rendered to a 300-DPI image first, so this is a fair
  simulation of scanning a printed report.
- **Key levels P/R/F1** match test names via the production alias
  normalizer; a value counts only within 0.5% of the reference value.
- **Status agree** checks Low/Normal/High against the status derived
  from the digital text.
- **Gold values** come from hand-checked labels in `tools/eval_truth/`,
  the only valid reference for image-only reports.
