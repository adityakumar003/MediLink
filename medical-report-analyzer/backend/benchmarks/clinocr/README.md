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

## Results

See [`results.md`](results.md) for the full tables (headline numbers, per
acquisition condition, per report type, per document).
