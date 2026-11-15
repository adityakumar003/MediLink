# ClinOCR-Bench — lab & pathology OCR accuracy benchmark

This folder tests MediBridge's real extraction pipeline (PaddleOCR + the
deterministic offline parser) against an external, third-party benchmark:
[**ClinOCR-Bench**](https://huggingface.co/datasets/ClinOCR-Bench/ClinOCR-Bench)
(MIT license, 2026) — 384 synthetic-but-realistic clinical documents with
**human-audited ground-truth transcriptions**.

Only **laboratory and pathology reports** are used, per project scope.

## Files

| File | Purpose |
|---|---|
| `explore.py` | One-time inspection that maps dataset templates → document types (evidence for the selection below). |
| `run_bench.py` | The benchmark: downloads (cached), OCRs with the production pipeline, scores against ground truth, writes `results.md` / `results.json`. |
| `images/` | Generated: the selected report images (gitignored). |
| `ocr_texts/` | Generated: OCR output cache, one `.txt` per document (gitignored). |
| `results.md` | Generated: full human-readable report. |
| `results.json` | Generated: every raw number. |
| `run.log` | Generated: last run's console log. |

## Selected templates (lab/pathology only)

| Template | Document type |
|---|---|
| t2 | Pathology report (surgical pathology, narrative) |
| t6 | Pathology report (cervical biopsy) |
| t11 | Lab panel — CMP + HbA1c |
| t12 | Lab panel — NMR LipoProfile / lipids |
| t15 | Lab panel — CBC (laboratory services) |

Excluded by inspection: imaging report (t1), endoscopy note (t3), visit notes
(t4/t5/t7), consult fax (t8), medication list (t9), medical-history form (t10),
intake/vitals form (t13), surgical pre-op assessment (t14), behavioral daily
report (t16).

This yields **92 documents** across all six acquisition conditions
(`normal`, `handwriting`, `poor`, `rotated`, `tables`, `mixed`).

## Metrics

- **Character accuracy (strict)** = 1 − CER against the ground truth; sensitive
  to reading-order differences (these forms have two-column headers, so OCR
  merges columns and pays an order penalty).
- **Word content F1 (order-free)** = lowercased alphanumeric token multiset
  overlap; measures how much content was recovered regardless of column order.
- **Number recall** = share of ground-truth numeric literals that appear in the
  OCR output (order-preserving LCS).
- **Key-level P/R/F1** = the real offline parser is run on both ground truth
  and OCR text; a row counts when the canonical test name matches and the value
  is within max(0.01, 0.5%). Scored only on numeric lab panels (t11/t12/t15) —
  pathology narratives would contribute only header-number false positives.
- **Status agreement** = Low/Normal/High agreement among value-matched rows.

## Run it

```powershell
cd backend
python benchmarks/clinocr/run_bench.py                 # full run (reuses OCR cache)
python benchmarks/clinocr/run_bench.py --max-docs 5    # quick smoke test
python benchmarks/clinocr/run_bench.py --force-ocr     # redo OCR
```

- No `datasets` package needed: parquet files are pulled with
  `huggingface_hub` (already a backend dependency) and cached in the user's HF
  cache — the repository only stores the selected images and OCR texts.
- No LLM or network calls during scoring; PaddleOCR runs locally on CPU.
- OCR results are cached per document, so re-scoring is instant.

## Reproduce / cite

```bibtex
@article{clinocrbench2026,
  title={ClinOCR-Bench: A Comprehensive Clinical Scanned Document Dataset for Optical Character Recognition Model Evaluation},
  journal={arXiv preprint arXiv:2607.03650},
  year={2026}
}
```

## Results (92 documents, PaddleOCR on CPU)

| Metric | Result |
|---|---|
| Character accuracy (strict, reading-order sensitive) | **58.8%** (CER 41.2%) |
| Word content F1 (order-free) | **74.9%** (precision 87.2% / recall 65.6%) |
| Numeric literals recovered | **77.2%** (3690/4780, F1 82.1%) |
| Key-level lab rows recovered (30 lab panels) | 24.8% (62/250, P 46.3%, F1 32.3%) |
| Status agreement | not measurable on this dataset (see caveats) |
| OCR failures | 2 / 92 — both severely blurred `mixed` scans |

### By acquisition condition

| Subset | Docs | Char accuracy | Word content F1 | Number recall | Key-level P / R / F1 |
|---|---|---|---|---|---|
| normal | 14 | 83.5% | 95.8% | 91.3% | n/a |
| handwriting | 14 | 36.2% | 34.6% | 58.3% | n/a |
| poor | 14 | 68.0% | 72.7% | 77.6% | n/a |
| rotated | 14 | 47.2% | 81.4% | 67.2% | n/a |
| tables | 21 | 85.2% | 94.3% | 91.5% | 53.0% / 30.3% / 38.5% |
| mixed | 15 | 33.2% | 49.5% | 56.4% | 26.5% / 12.0% / 16.5% |

### By report type

| Template | Docs | Char accuracy | Word content F1 | Number recall | Key-level P / R / F1 |
|---|---|---|---|---|---|
| t2 — pathology (surgical) | 31 | 51.8% | 67.6% | 66.3% | n/a |
| t6 — pathology (biopsy) | 31 | 57.9% | 72.7% | 73.3% | n/a |
| t11 — CMP + HbA1c | 10 | 85.8% | 90.4% | 89.5% | 41.6% / 29.4% / 34.4% |
| t12 — lipid profile | 10 | 75.9% | 83.3% | 80.2% | 75.0% / 37.5% / 50.0% |
| t15 — CBC | 10 | 60.9% | 84.1% | 69.4% | 0.0% / 0.0% / n/a |

### Caveats that matter when quoting these numbers

- **Strict character accuracy is depressed by column reading order.** The
  forms have two-column headers; OCR merges them, while the ground truth is
  column-first. Order-free word F1 isolates actual content recovery
  (e.g. one `normal` pathology scan: 74.7% strict vs 94.4% order-free).
- **Handwriting is out of scope for PaddleOCR's print model.** The 34.6%
  content F1 on the handwriting subset reflects that limitation, not an OCR
  regression on printed reports.
- **Key-level recall is a layout-compatibility finding, not an OCR-quality
  finding.** ClinOCR's tables put value / flag / reference / site on separate
  lines. `_BARE_VALUE_RE` requires a bare `value + unit` line, so merged OCR
  lines (`11.4x10/L H 4.5-11.0 TB`) parse as zero rows, and even perfect
  ground-truth text loses rows whose units contain superscripts (`x10³/µL`
  is not in the unit character class). Fix path: accept inline flag/range/site
  and superscript units in `backend/app/services/offline_analysis_service.py`.
- **Status agreement is n/a on this dataset** because the parser cannot pair
  values with ranges on these layouts even from perfect GT text, so no
  value-matched row has a definite reference status. Statuses are covered by
  the internal gold fixtures (`backend/tools/eval_report.md`).
- The 2 failures are genuinely unreadable heavily-blurred `mixed` scans where
  PaddleOCR detected no text boxes at all.

See [`results.md`](results.md) for the per-document table and
[`results.json`](results.json) for every raw number.

