"""
benchmarks/clinocr/run_bench.py
===============================
End-to-end OCR accuracy benchmark on ClinOCR-Bench (MIT, 2026), restricted to
laboratory / pathology reports.

Dataset: https://huggingface.co/datasets/ClinOCR-Bench/ClinOCR-Bench
Loaded from the released parquet files with huggingface_hub (the `datasets`
package is NOT required, so the backend environment is untouched).

Lab/pathology templates (verified against the ground-truth text):
    t2  pathology report (surgical pathology, narrative)
    t6  pathology report (cervical biopsy)
    t11 laboratory panel (CMP + HbA1c)
    t12 laboratory panel (NMR LipoProfile / lipids)
    t15 laboratory panel (CBC, laboratory services)
Everything else (imaging, visit notes, faxes, medication lists, intake forms,
pre-op assessment, behavioral report) is excluded.

What is measured per document, against the human-audited ground truth:
    - CER / WER (strict, reading-order sensitive) + order-free word content F1
    - numeric-literal precision / recall / F1
    - key-level rows parsed by the real offline pipeline (name + value,
      value within 0.5%) + Low/Normal/High status agreement — scored only on
      the numeric lab-panel templates (t11/t12/t15); pathology reports are
      narrative text evaluated on the metrics above.

Usage (from the backend directory):
    python benchmarks/clinocr/run_bench.py
    python benchmarks/clinocr/run_bench.py --max-docs 5      # quick smoke test
    python benchmarks/clinocr/run_bench.py --force-ocr       # ignore OCR cache

Generated artifacts in this folder:
    images/<subset>/<doc_id>.png   selected report images
    ocr_texts/<doc_id>.txt         OCR output cache
    results.json                   all raw numbers
    results.md                     human-readable report

No network calls at scoring time; images + ground truth come from the cached
ClinOCR-Bench parquet files. PaddleOCR runs locally on CPU.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Must be set before importing PaddleOCR/protobuf (same workaround as app/main.py).
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

BENCH_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BENCH_DIR.parents[1]
TOOLS_DIR = BACKEND_DIR / "tools"

for extra_path in (str(BACKEND_DIR), str(TOOLS_DIR)):
    if extra_path not in sys.path:
        sys.path.insert(0, extra_path)

import pyarrow.parquet as pq  # noqa: E402
from huggingface_hub import hf_hub_download  # noqa: E402

import eval_extraction as ev  # noqa: E402
from app.services.offline_analysis_service import analyse_report_text_offline  # noqa: E402
from app.services.text_extraction_service import extract_text  # noqa: E402

REPO = "ClinOCR-Bench/ClinOCR-Bench"
SUBSETS = ["normal", "handwriting", "poor", "rotated", "tables", "mixed"]

LAB_TEMPLATES: Dict[int, str] = {
    2: "Pathology report (surgical)",
    6: "Pathology report (biopsy)",
    11: "Lab panel (CMP + HbA1c)",
    12: "Lab panel (lipid profile)",
    15: "Lab panel (CBC)",
}

# Key-level (name -> value) scoring only makes sense for numeric lab panels.
# Pathology reports are narrative; the table parser finds only header numbers
# (accession numbers, fax numbers) there, so they are scored on text only.
LAB_PANEL_TEMPLATES = {11, 12, 15}

_WORD_RE = re.compile(r"[a-z0-9]+")

IMAGES_DIR = BENCH_DIR / "images"
OCR_DIR = BENCH_DIR / "ocr_texts"
RESULTS_MD = BENCH_DIR / "results.md"
RESULTS_JSON = BENCH_DIR / "results.json"


# ── Dataset loading ─────────────────────────────────────────────────────────

def load_lab_documents() -> List[Dict[str, Any]]:
    """Download (cached) the six test parquet files and keep lab/pathology rows."""
    docs: List[Dict[str, Any]] = []
    for subset in SUBSETS:
        parquet_path = hf_hub_download(
            REPO, f"{subset}/test-00000-of-00001.parquet", repo_type="dataset"
        )
        for row in pq.read_table(parquet_path).to_pylist():
            if row["template"] not in LAB_TEMPLATES:
                continue
            docs.append(row)
    docs.sort(key=lambda r: (SUBSETS.index(r["subset"]), r["template"], r["doc_id"]))
    return docs


def materialize_image(row: Dict[str, Any]) -> Path:
    """Write the parquet image bytes to disk once, as PNG."""
    target = IMAGES_DIR / row["subset"] / f"{row['doc_id']}.png"
    if target.exists():
        return target

    from PIL import Image

    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (row.get("image") or {}).get("bytes")
    if not payload:
        raise ValueError(f"{row['doc_id']}: parquet image has no bytes")
    with Image.open(BytesIO(payload)) as image:
        image.convert("RGB").save(target, "PNG")
    return target


# ── OCR ─────────────────────────────────────────────────────────────────────

async def ocr_document(row: Dict[str, Any], force: bool) -> Tuple[str, float, Optional[str]]:
    """Return (ocr_text, seconds, error). Reuses the per-doc OCR cache.

    Only successful, non-empty results are cached; failures are retried on the
    next run so the error is recorded every time (never masked as a success).
    """
    cache_path = OCR_DIR / f"{row['doc_id']}.txt"
    if cache_path.exists() and not force:
        cached = cache_path.read_text(encoding="utf-8")
        if cached.strip():
            return cached, 0.0, None
        cache_path.unlink()  # stale empty cache from an earlier failed run

    started = time.perf_counter()
    error: Optional[str] = None
    try:
        image_path = materialize_image(row)
        text = ev.strip_page_markers(await extract_text(image_path)).strip()
    except Exception as exc:  # keep the benchmark moving; score the doc as a miss
        text, error = "", f"{type(exc).__name__}: {exc}"

    elapsed = time.perf_counter() - started
    if text.strip():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding="utf-8")
    return text, elapsed, error


# ── Scoring ─────────────────────────────────────────────────────────────────

def word_content_scores(reference: str, hypothesis: str) -> Dict[str, Any]:
    """Order-free token overlap.

    Column layouts are read left-to-right by OCR but laid out column-first in
    the source template, so strict edit distance penalizes reading order.
    This metric measures how much of the actual content was recovered.
    """
    ref_tokens = _WORD_RE.findall(ev.norm_chars(reference))
    hyp_tokens = _WORD_RE.findall(ev.norm_chars(hypothesis))
    ref_counts = Counter(ref_tokens)
    hyp_counts = Counter(hyp_tokens)
    matched = sum((ref_counts & hyp_counts).values())
    precision = matched / len(hyp_tokens) if hyp_tokens else 0.0
    recall = matched / len(ref_tokens) if ref_tokens else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "matched": matched,
        "reference": len(ref_tokens),
        "extracted": len(hyp_tokens),
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def score_document(
    row: Dict[str, Any],
    ocr_text: str,
    ocr_seconds: float,
    error: Optional[str],
) -> Dict[str, Any]:
    reference = row["ground_truth"]
    char_dist, char_ref = ev.error_rate(ev.norm_chars(reference), ev.norm_chars(ocr_text))
    word_dist, word_ref = ev.error_rate(ev.norm_words(reference), ev.norm_words(ocr_text))
    numbers = ev.score_numbers(reference, ocr_text)
    content = word_content_scores(reference, ocr_text)
    analytical = row["template"] in LAB_PANEL_TEMPLATES

    if analytical:
        ref_params = analyse_report_text_offline(reference)["parameters"]
        ocr_params = analyse_report_text_offline(ocr_text)["parameters"]
        params = ev.score_parameters(ref_params, ocr_params)
        rows_matched = len(params["value_matched"])
        rows_extracted = params["copies"]
        rows_reference = params["reference_count"]
        ref_map = ev.param_map(ref_params)
        ocr_map = ev.param_map(ocr_params)
        # Status agreement only where the ground truth has a definite status;
        # "Unknown" (a column-alignment artifact) must not count as a
        # disagreement.
        status_matched = status_denominator = 0
        for key in params["value_matched"]:
            reference_status = ev.status_of(ref_map.get(key))
            if reference_status in {"low", "normal", "high", "critical"}:
                status_denominator += 1
                if ev.status_of(ocr_map.get(key)) == reference_status:
                    status_matched += 1
        missing_rows = params["missing"][:5]
        value_mismatches = params["value_bad_details"][:5]
    else:
        rows_matched = rows_extracted = rows_reference = None
        status_matched = status_denominator = None
        missing_rows, value_mismatches = [], []

    return {
        "doc_id": row["doc_id"],
        "subset": row["subset"],
        "template": row["template"],
        "doc_type": LAB_TEMPLATES[row["template"]],
        "analytical": analytical,
        "reference_chars": char_ref,
        "ocr_chars": len(ev.norm_chars(ocr_text)),
        "char_distance": char_dist,
        "char_reference": char_ref,
        "word_distance": word_dist,
        "word_reference": word_ref,
        "cer": char_dist / char_ref if char_ref else None,
        "wer": word_dist / word_ref if word_ref else None,
        "word_content_matched": content["matched"],
        "word_content_reference": content["reference"],
        "word_content_extracted": content["extracted"],
        "word_content_precision": content["precision"],
        "word_content_recall": content["recall"],
        "word_content_f1": content["f1"],
        "numbers_matched": numbers["matched"],
        "numbers_reference": numbers["reference_count"],
        "numbers_extracted": numbers["extracted_count"],
        "rows_matched": rows_matched,
        "rows_extracted": rows_extracted,
        "rows_reference": rows_reference,
        "status_matched": status_matched,
        "status_denominator": status_denominator,
        "missing_rows": missing_rows,
        "value_mismatches": value_mismatches,
        "ocr_seconds": round(ocr_seconds, 2),
        "error": error,
    }


def aggregate(docs: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    docs = list(docs)
    char_dist = sum(d["char_distance"] for d in docs)
    char_ref = sum(d["char_reference"] for d in docs)
    word_dist = sum(d["word_distance"] for d in docs)
    word_ref = sum(d["word_reference"] for d in docs)

    content_matched = sum(d["word_content_matched"] for d in docs)
    content_ref = sum(d["word_content_reference"] for d in docs)
    content_extracted = sum(d["word_content_extracted"] for d in docs)

    numbers_matched = sum(d["numbers_matched"] for d in docs)
    numbers_ref = sum(d["numbers_reference"] for d in docs)
    numbers_extracted = sum(d["numbers_extracted"] for d in docs)

    lab_panels = [d for d in docs if d["analytical"]]
    rows_matched = sum(d["rows_matched"] or 0 for d in lab_panels)
    rows_ref = sum(d["rows_reference"] or 0 for d in lab_panels)
    rows_extracted = sum(d["rows_extracted"] or 0 for d in lab_panels)
    status_matched = sum(d["status_matched"] or 0 for d in lab_panels)
    status_denominator = sum(d["status_denominator"] or 0 for d in lab_panels)

    def ratio(numerator: int, denominator: int) -> Optional[float]:
        return numerator / denominator if denominator else None

    def f1_score(precision: Optional[float], recall: Optional[float]) -> Optional[float]:
        if precision is None or recall is None or not (precision + recall):
            return None
        return 2 * precision * recall / (precision + recall)

    precision = ratio(rows_matched, rows_extracted)
    recall = ratio(rows_matched, rows_ref)

    num_precision = ratio(numbers_matched, numbers_extracted)
    num_recall = ratio(numbers_matched, numbers_ref)

    content_precision = ratio(content_matched, content_extracted)
    content_recall = ratio(content_matched, content_ref)

    return {
        "documents": len(docs),
        "lab_panel_documents": len(lab_panels),
        "documents_with_rows": sum(1 for d in lab_panels if (d["rows_reference"] or 0) > 0),
        "failures": sum(1 for d in docs if d["error"]),
        "char_distance": char_dist,
        "char_reference": char_ref,
        "cer": ratio(char_dist, char_ref),
        "character_accuracy": 1 - ratio(char_dist, char_ref) if char_ref else None,
        "word_distance": word_dist,
        "word_reference": word_ref,
        "wer": ratio(word_dist, word_ref),
        "word_accuracy": 1 - ratio(word_dist, word_ref) if word_ref else None,
        "word_content_matched": content_matched,
        "word_content_reference": content_ref,
        "word_content_extracted": content_extracted,
        "word_content_precision": content_precision,
        "word_content_recall": content_recall,
        "word_content_f1": f1_score(content_precision, content_recall),
        "numbers_matched": numbers_matched,
        "numbers_reference": numbers_ref,
        "numbers_extracted": numbers_extracted,
        "numbers_precision": num_precision,
        "numbers_recall": num_recall,
        "numbers_f1": f1_score(num_precision, num_recall),
        "rows_matched": rows_matched,
        "rows_reference": rows_ref,
        "rows_extracted": rows_extracted,
        "rows_precision": precision,
        "rows_recall": recall,
        "rows_f1": f1_score(precision, recall),
        "status_matched": status_matched,
        "status_denominator": status_denominator,
        "status_accuracy": ratio(status_matched, status_denominator),
        "ocr_seconds": round(sum(d["ocr_seconds"] for d in docs), 1),
    }


# ── Reporting ───────────────────────────────────────────────────────────────

def pct(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def ratio_col(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def summary_row(label: str, stats: Dict[str, Any]) -> str:
    return (
        f"| {label} | {stats['documents']} | {pct(stats['character_accuracy'])} "
        f"| {pct(stats['word_content_f1'])} | {pct(stats['numbers_recall'])} "
        f"| {ratio_col(stats['rows_precision'])} / {ratio_col(stats['rows_recall'])} / "
        f"{ratio_col(stats['rows_f1'])} | {ratio_col(stats['status_accuracy'])} "
        f"| {stats['lab_panel_documents']} |"
    )


def build_markdown(
    documents: List[Dict[str, Any]],
    by_subset: Dict[str, Dict[str, Any]],
    by_template: Dict[int, Dict[str, Any]],
    overall: Dict[str, Any],
    print_only_stats: Dict[str, Any],
    elapsed: float,
) -> str:
    generated = time.strftime("%Y-%m-%d %H:%M")
    lines: List[str] = [
        "# ClinOCR-Bench — lab & pathology OCR accuracy",
        "",
        f"Generated: {generated} · Runtime: {elapsed:.1f}s (PaddleOCR, CPU) · "
        "no LLM, no network calls during scoring.",
        "",
        "Dataset: [ClinOCR-Bench](https://huggingface.co/datasets/ClinOCR-Bench/ClinOCR-Bench) "
        "(MIT). Test split only, filtered to laboratory and pathology templates: "
        "t2/t6 pathology reports, t11/t12/t15 lab panels. "
        "Ground truth is the dataset's human-audited transcription.",
        "",
        "## Headline",
        "",
        f"- **Character accuracy (strict): {pct(overall['character_accuracy'])}** "
        f"(CER {pct(overall['cer'])}) over {overall['documents']} documents.",
        f"- **Word content F1 (order-free): {pct(overall['word_content_f1'])}** "
        f"(precision {pct(overall['word_content_precision'])}, "
        f"recall {pct(overall['word_content_recall'])}).",
        f"- **Numeric literals recovered: {pct(overall['numbers_recall'])}** "
        f"({overall['numbers_matched']}/{overall['numbers_reference']}, "
        f"F1 {pct(overall['numbers_f1'])}).",
        f"- **Print-only accuracy (handwriting excluded): "
        f"{pct(print_only_stats['word_content_f1'])}** word content F1 / "
        f"{pct(print_only_stats['character_accuracy'])} strict / "
        f"{pct(print_only_stats['numbers_recall'])} of numbers "
        f"({print_only_stats['documents']} documents).",
        f"- **Key-level lab rows recovered: {pct(overall['rows_recall'])}** "
        f"({overall['rows_matched']}/{overall['rows_reference']}, "
        f"precision {pct(overall['rows_precision'])}, F1 {pct(overall['rows_f1'])}) "
        f"on {overall['lab_panel_documents']} numeric lab panels.",
        f"- **Status agreement (Low/Normal/High): {pct(overall['status_accuracy'])}** "
        f"({overall['status_matched']}/{overall['status_denominator']}).",
        f"- OCR failures: {overall['failures']}.",
        "",
        "Strict CER/WER compare linear reading order; these scans have two-column",
        "headers, so OCR merges columns and pays an order penalty that the",
        "order-free word-content metric excludes. Both are reported.",
        "",
        "Status agreement is n/a here: these column tables keep value / flag /",
        "site on separate lines, so the deterministic parser (built for",
        "single-line lab rows) cannot pair a value with its range even in the",
        "ground-truth text, leaving no value-matched row with a definite",
        "reference status. Status handling is covered by the internal gold",
        "fixtures instead (see backend/tools/eval_report.md).",
        "",
        "## By acquisition condition",
        "",
        "| Subset | Docs | Char accuracy | Word content F1 | Number recall | "
        "Key-level P / R / F1 | Status agree | Lab-panel docs |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for subset in SUBSETS:
        if subset in by_subset:
            lines.append(summary_row(subset, by_subset[subset]))
    lines.append(summary_row("**Print-only (no handwriting)**", print_only_stats))
    lines.append(summary_row("**All**", overall))

    lines.extend([
        "",
        "## By report type",
        "",
        "| Template | Type | Docs | Char accuracy | Word content F1 | Number recall | "
        "Key-level P / R / F1 | Status agree | Lab-panel docs |",
        "|---|---|---|---|---|---|---|---|",
    ])
    for template in sorted(by_template):
        lines.append(
            summary_row(f"t{template} — {LAB_TEMPLATES[template]}", by_template[template])
        )

    lines.extend([
        "",
        "## Per-document results",
        "",
        "| doc_id | Subset | Type | Char acc. | Word content F1 | Numbers recalled | "
        "Lab rows recovered | Status | OCR s |",
        "|---|---|---|---|---|---|---|---|---|",
    ])
    for doc in sorted(documents, key=lambda d: (SUBSETS.index(d["subset"]), d["doc_id"])):
        char_acc = 1 - doc["cer"] if doc["cer"] is not None else None
        status = "n/a"
        if doc["status_denominator"]:
            status = f"{doc['status_matched']}/{doc['status_denominator']}"
        lab_rows = (
            f"{doc['rows_matched']}/{doc['rows_reference']}"
            if doc["analytical"] else "n/a (narrative)"
        )
        lines.append(
            f"| {doc['doc_id']} | {doc['subset']} | t{doc['template']} "
            f"| {pct(char_acc)} | {pct(doc['word_content_f1'])} "
            f"| {doc['numbers_matched']}/{doc['numbers_reference']} "
            f"| {lab_rows} "
            f"| {status} | {doc['ocr_seconds']:.1f} |"
        )

    lines.extend([
        "",
        "## Definitions",
        "",
        "- **Character accuracy (strict)** = 1 − normalized edit distance against",
        "  the human-audited ground truth; it penalizes reading-order differences.",
        "- **Word content F1 (order-free)** = token multiset overlap (lowercased",
        "  alphanumerics), insensitive to column reading order.",
        "- **Number recall**: share of numeric literals in the ground truth that",
        "  also appear in the OCR output (order-preserving LCS).",
        "- **Key-level**: the real offline parser is run on both the ground truth",
        "  and the OCR text; a row counts only when the canonical test name matches",
        "  and the value is within max(0.01, 0.5%) of the reference value.",
        "  Scored only on numeric lab panels (t11/t12/t15); pathology reports are",
        "  narrative. Note: these synthetic tables place value / flag / previous",
        "  result / site in separate columns, a layout the offline parser (built",
        "  for single-line Indian lab rows) misreads even on perfect ground-truth",
        "  text -- so this is an end-to-end pipeline figure, not pure OCR quality.",
        "- **Status agreement** is computed among value-matched rows whose ground",
        "  truth status is Low/Normal/High/Critical (Unknown is excluded).",
        "",
    ])
    return "\n".join(lines)


# ── Entry point ─────────────────────────────────────────────────────────────

async def run(documents: List[Dict[str, Any]], force: bool) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for index, row in enumerate(documents, 1):
        print(f"[{index}/{len(documents)}] {row['doc_id']}", file=sys.stderr, flush=True)
        text, seconds, error = await ocr_document(row, force)
        results.append(score_document(row, text, seconds, error))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-docs", type=int, default=None,
                        help="Limit the number of documents (deterministic order).")
    parser.add_argument("--force-ocr", action="store_true",
                        help="Re-run OCR even when a cached text file exists.")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    started = time.perf_counter()
    documents = load_lab_documents()
    if args.max_docs:
        documents = documents[: args.max_docs]
    if not documents:
        raise SystemExit("No lab/pathology documents found.")

    results = asyncio.run(run(documents, args.force_ocr))
    elapsed = time.perf_counter() - started

    by_subset = {subset: aggregate(d for d in results if d["subset"] == subset)
                 for subset in SUBSETS if any(d["subset"] == subset for d in results)}
    by_template_groups: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for doc in results:
        by_template_groups[doc["template"]].append(doc)
    by_template = {template: aggregate(docs) for template, docs in by_template_groups.items()}
    overall = aggregate(results)
    print_only_stats = aggregate(
        doc for doc in results if doc["subset"] != "handwriting"
    )

    markdown = build_markdown(
        results, by_subset, by_template, overall, print_only_stats, elapsed
    )
    RESULTS_MD.write_text(markdown, encoding="utf-8")
    RESULTS_JSON.write_text(
        json.dumps(
            {
                "dataset": REPO,
                "subsets": SUBSETS,
                "lab_templates": LAB_TEMPLATES,
                "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "runtime_seconds": round(elapsed, 1),
                "overall": overall,
                "print_only": print_only_stats,
                "by_subset": by_subset,
                "by_template": by_template,
                "documents": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(markdown)
    print(f"\nWrote {RESULTS_MD} and {RESULTS_JSON}", file=sys.stderr)


if __name__ == "__main__":
    main()
