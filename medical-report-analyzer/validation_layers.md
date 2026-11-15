# MediBridge — Validation Layers for Disease Risk Assessment

How a lab report becomes a risk card: every layer, what it checks, and what
was implemented to keep it reliable. Reference/study document — not a clinical
validation claim (see §11).

Pipeline order: Upload → Extraction → Row parsing → Numeric validation →
Flag reconciliation → Risk engine → (optional) LLM explanation → API →
Frontend. Twelve automated suites (112 tests) pin the behavior.

---

## Layer 1 — File upload & content validation

**Considerations:** wrong file types, fake PDFs, oversized uploads, corrupt images.
**Implemented** (`report_service.py`, `file_utils.py`):
- Extension + MIME allow-list (PDF/JPG/PNG), `%PDF-` magic-byte check, PIL
  image verification, configurable size cap. Rejects fail with 400 before
  anything is stored.

## Layer 2 — Text extraction (PyMuPDF + PaddleOCR)

**Considerations:** digital vs scanned pages, mixed PDFs, blank/unreadable pages,
page-order preservation, never sending empty text to an LLM.
**Implemented** (`text_extraction_service.py`):
- Per-page digital-text threshold (40 chars); scanned pages rendered at
  300 DPI and OCR'd; layout-ordered line reconstruction; page markers kept.
- Blank/unreadable/encrypted/unsupported inputs raise clear errors; short
  extraction (<50 chars) is rejected with 422 downstream.

## Layer 3 — Row parsing & test-name normalization

**Considerations:** single-line rows vs multi-column tables (one field per
line), narrative prose leaking in as parameters, name variants (Hb/FPG/LDL),
junk lines (dates, headers, page footers).
**Implemented** (`offline_analysis_service.py`, `lab_validation.py`):
- Column-table parser (name → value → unit/range in any order) runs first;
  single-line parser fills gaps; sentence-length lines (>90 chars) are skipped.
- Canonical alias table (`normalize_test_name`, specifics-first ordering);
  original names always preserved in output.
- Rows kept only with a recognized unit or parseable bounds; leftover prose
  never shown as a reference range (digit-less ranges become `None`).

## Layer 4 — Deterministic numeric validation (the authority)

**Considerations:** decimals, intervals (`12.0–15.5`), inequalities (`<200`,
`>40`), inverted ranges, unit incompatibility, ambiguous OCR (`?`, `~`,
`ill`, disconnected numbers), boundary inclusivity.
**Implemented** (`lab_validation.py`):
- Below → `Low`; within **including boundaries** → `Normal`; above → `High`;
  anything missing/invalid/ambiguous/incompatible → `Unknown`.
- Units compared via normalized tokens; **no silent cross-unit comparison and
  no unit conversion** (documented limitation).
- OCR-ambiguity heuristic ignores numbers embedded in units (`10^3/uL`).
- The model/report flag is accepted as input but **can never override** a
  validated status (`classify_numerical_status` discards it when numbers rule).

## Layer 5 — Report-flag reconciliation

**Considerations:** the report's own printed flag vs our independent status;
parenthesized annotations (`70 - 99 (HIGH)`); preserving the distinction.
**Implemented** (parser + `risk_assessment.model_flag_to_status`):
- Flag captured separately (`report_flag`); parenthesized flags stripped from
  ranges without losing them; `flag_mismatch` raised on disagreement and
  surfaced in the UI ("Report prints X — independent check differs").

## Layer 6 — Disease-risk engine (deterministic, no LLM)

**Considerations:** one abnormal value ≠ diagnosis; normal single marker ≠
comprehensive assessment; missing fasting context; CKD needs eGFR + albuminuria
+ persistence; cardiovascular needs a validated calculator's full inputs;
no invented thresholds, probabilities, or severity scores.
**Implemented** (`risk_assessment.py` — single source for HF/Gemini/Ollama/offline):
- Explicit states: `assessed` / `insufficient_data` / `not_assessed` /
  `requires_review`. A level appears **only** when `assessed` (else null).
- Abnormal marker → `requires_review` + evidence + missing-inputs list +
  next-step guidance. Lone normal creatinine → `insufficient_data` (never a
  CKD claim). Lone normal Hb → `insufficient_data`. Lipids alone → never an
  overall cardio category (no calculator implemented — stated openly).
- Every item carries `evidence`, `missing`, `method`, `guidance`; invariant
  "level set ⟺ assessed" is test-enforced.

## Layer 7 — LLM explanation layer (isolated, optional)

**Considerations:** hallucinations, format drift, contradiction of validated
findings, quota burn, silent provider switching.
**Implemented** (`hf_space_service.py`, `gemini_service.py`, dispatcher):
- LLM writes narrative only, in a fixed template; three fallback parsers
  tolerate format variants; statuses are always re-derived in Python.
- `ensure_consistent_summary` replaces any summary claiming "all normal"
  while abnormal findings exist.
- `AI_MODE` selects exactly one provider; failures raise (no silent
  fallback); `ENABLE_LLM_SUMMARY=false` disables **all** generation (proven
  by tests asserting zero SDK/HTTP calls); at most one retry (HF) / one call
  (Gemini) per operation; stored results are reused, never regenerated.

## Layer 8 — API contract & storage

**Considerations:** schema drift, old stored reports, cross-patient access.
**Implemented** (`schemas/analysis.py`, `analysis.py` route):
- Extended `DiseaseRiskItem`/`MedicalParameter` with optional fields;
  `legacy_risk_item` maps pre-state reports compatibly.
- Ownership checks on every report/analysis endpoint; doctor access gated by
  accepted connections; no secrets or report text in logs.

## Layer 9 — Frontend presentation

**Considerations:** states must be visually distinct; no decorative risk
badges; mismatch visibility; responsive layout; medical disclaimers.
**Implemented** (`DiseaseRiskCard.tsx`, `ParameterTable.tsx`, types):
- Cards render by state (Low / Needs review / Insufficient data / Not
  assessed) with evidence, missing inputs, method, and decision-support
  footer; `Unknown` stays unclassified, never normal/abnormal; mismatch
  notes inline; disclaimers state non-diagnosis + clinician decides.

## Layer 10 — Tests & evaluation

**Considerations:** pinning behavior without live quota; covering normal,
borderline, abnormal, incomplete, and noisy-OCR cases.
**Implemented** (`backend/tests/`, 112 tests, all mocked):
- Boundary values, missing/invalid ranges, unit mismatches, OCR ambiguity,
  flag override attempts, provider routing + no-fallback + no-LLM proofs,
  legacy compatibility, full HTTP flows, and an 8-case synthetic eval set
  (`test_risk_assessment.py`).

## 11. Known limits (not yet implemented)

- No unit conversions; no validated 10-year risk calculator; age/sex not
  piped into assessment; Ollama statuses not Python-revalidated; PaddleOCR
  confidence scores not plumbed through; frontend has no component-test
  harness (types + build cover the contract).
- **Not clinically validated.** Formal validation needs a
  clinician-adjudicated reference set (de-identified reports × states) with
  measured engine agreement — see README's validation roadmap.
