"""
tools/eval_extraction.py
========================
Accuracy harness for the offline report pipeline (OCR + key-level parsing).

What it measures
----------------
1. OCR accuracy on PDFs that have a digital text layer.
   The digital text is treated as ground truth; every page is rendered to a
   300-DPI image (exactly like the production scanned-PDF path) and OCR'd.
   Reported as Character Error Rate (CER) and Word Error Rate (WER) -- lower
   is better.

2. Key-level extraction accuracy.
   - Self-supervised: parameters parsed from the OCR text are compared with
     parameters parsed from the digital text (name, value, status).
   - Gold labels: if `tools/eval_truth/<file stem>.json` exists, the OCR
     text is scored against hand-checked values instead (this is the only
     reference available for image-only reports).

3. Numeric-literal precision/recall/F1 between digital and OCR text.

Matching rules (kept deliberately honest)
-----------------------------------------
- Test names are matched with the production normalizer (`normalize_test_name`).
- A value counts as correct only when it is within max(0.01, 0.5%) of the
  reference value -- a wrong digit is a miss, not a rounding difference.
- Status counts as correct only on exact strings (Low/Normal/High/Critical).

Usage
-----
    cd backend
    python tools/eval_extraction.py                  # ../test_report* files
    python tools/eval_extraction.py path/to/file.pdf
    python tools/eval_extraction.py --out my_report.md

Gold-label JSON format (`tools/eval_truth/<stem>.json`):
    {
      "source": "test_report_anemia_dummy.png",
      "tests": [
        {"name": "Hemoglobin", "value": 9.8, "unit": "g/dL", "status": "Low"}
      ]
    }
`unit` and `status` are optional; `value` is required.

No network calls: OCR runs locally on CPU, parsing is the deterministic
offline pipeline, so results are reproducible.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# PaddleOCR (paddlepaddle 2.x) needs protobuf's pure-Python implementation.
# Must be set before any protobuf import -- same workaround as app/main.py.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
TOOLS_DIR = Path(__file__).resolve().parent
TRUTH_DIR = TOOLS_DIR / "eval_truth"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.lab_validation import normalize_test_name  # noqa: E402
from app.services.offline_analysis_service import (  # noqa: E402
    analyse_report_text_offline,
)
from app.services.text_extraction_service import extract_text  # noqa: E402

RENDER_DPI = 300  # must match app/services/text_extraction_service.py
PAGE_MARKER_RE = re.compile(r"^--- Page \d+ ---$", re.MULTILINE)
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


# ── Text helpers ────────────────────────────────────────────────────────────

def strip_page_markers(text: str) -> str:
    return PAGE_MARKER_RE.sub(" ", text or "")


def norm_chars(text: str) -> str:
    return re.sub(r"\s+", " ", strip_page_markers(text).lower()).strip()


def norm_words(text: str) -> List[str]:
    return norm_chars(text).split(" ")


def edit_distance(a: Sequence[Any], b: Sequence[Any]) -> int:
    """Levenshtein distance for two sequences (str chars or word lists)."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(
                min(
                    previous[j] + 1,          # deletion
                    current[j - 1] + 1,       # insertion
                    previous[j - 1] + (ca != cb),  # substitution
                )
            )
        previous = current
    return previous[-1]


def error_rate(reference: Sequence[Any], hypothesis: Sequence[Any]) -> Tuple[int, int]:
    if not reference:
        return 0, 0
    return edit_distance(reference, hypothesis), len(reference)


def num_equal(a: float, b: float) -> bool:
    return abs(a - b) <= max(1e-9, 1e-6 * max(abs(a), abs(b)))


def lcs_length(a: Sequence[Any], b: Sequence[Any], eq) -> int:
    if not a or not b:
        return 0
    previous = [0] * (len(b) + 1)
    for ca in a:
        current = [0]
        for j, cb in enumerate(b):
            if eq(ca, cb):
                current.append(previous[j] + 1)
            else:
                current.append(max(current[j], previous[j + 1]))
        previous = current
    return previous[-1]


def value_close(ocr_value: Any, ref_value: Any) -> bool:
    if not isinstance(ocr_value, (int, float)) or isinstance(ocr_value, bool):
        return False
    if not isinstance(ref_value, (int, float)) or isinstance(ref_value, bool):
        return False
    return abs(float(ocr_value) - float(ref_value)) <= max(0.01, 0.005 * abs(float(ref_value)))


def param_map(parameters: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Map canonical test name -> first parsed parameter with that name."""
    mapped: Dict[str, Dict[str, Any]] = {}
    for param in parameters:
        key = normalize_test_name(str(param.get("name", "")))
        if key and key not in mapped:
            mapped[key] = param
    return mapped


def status_of(param: Optional[Dict[str, Any]]) -> str:
    return str((param or {}).get("status") or "").lower()


# ── OCR extraction ──────────────────────────────────────────────────────────

async def ocr_pdf_with_reference(path: Path) -> Tuple[str, str, int]:
    """Render every PDF page to 300 DPI and OCR it.

    Returns (digital_reference_text, ocr_text, page_count). The digital text
    is the ground truth; pages without a text layer contribute nothing to it.
    """
    import fitz

    ref_parts: List[str] = []
    ocr_parts: List[str] = []
    zoom = RENDER_DPI / 72.0

    with tempfile.TemporaryDirectory(prefix="medbridge_eval_") as tmp:
        with fitz.open(str(path)) as doc:
            page_count = doc.page_count
            for index, page in enumerate(doc, start=1):
                digital = (page.get_text("text") or "").strip()
                pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                png_path = Path(tmp) / f"page_{index:02d}.png"
                pixmap.save(str(png_path))
                ocr_text = strip_page_markers(await extract_text(png_path)).strip()
                ref_parts.append(f"--- Page {index} ---\n{digital}")
                ocr_parts.append(f"--- Page {index} ---\n{ocr_text}")

    return "\n".join(ref_parts), "\n".join(ocr_parts), page_count


async def ocr_image(path: Path) -> str:
    return strip_page_markers(await extract_text(path)).strip()


# ── Scoring ─────────────────────────────────────────────────────────────────

def score_parameters(
    ref_params: List[Dict[str, Any]],
    ocr_params: List[Dict[str, Any]],
) -> Dict[str, Any]:
    ref_map = param_map(ref_params)
    ocr_map = param_map(ocr_params)

    common = [key for key in ocr_map if key in ref_map]
    value_ok = [key for key in common if value_close(ocr_map[key].get("value"), ref_map[key].get("value"))]
    status_ok = [
        key for key in value_ok
        if status_of(ocr_map[key]) == status_of(ref_map[key]) and status_of(ref_map[key])
    ]

    missing = [key for key in ref_map if key not in ocr_map]
    extra = [key for key in ocr_map if key not in ref_map]
    value_bad = [key for key in common if key not in value_ok]
    status_bad = [
        key for key in value_ok
        if status_of(ref_map[key]) and status_of(ocr_map[key]) != status_of(ref_map[key])
    ]

    precision = len(value_ok) / len(ocr_map) if ocr_map else 0.0
    recall = len(value_ok) / len(ref_map) if ref_map else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "copies": len(ocr_map),
        "reference_count": len(ref_map),
        "value_matched": value_ok,
        "status_matched": status_ok,
        "missing": missing,
        "extra": extra,
        "value_bad": value_bad,
        "status_bad": status_bad,
        "value_bad_details": [
            {
                "name": ref_map[key].get("name"),
                "expected": ref_map[key].get("value"),
                "got": ocr_map[key].get("value"),
            }
            for key in value_bad
        ],
        "status_bad_details": [
            {
                "name": ref_map[key].get("name"),
                "expected": ref_map[key].get("status"),
                "got": ocr_map[key].get("status"),
            }
            for key in status_bad
        ],
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "trues": len(value_ok),
    }


def score_numbers(ref_text: str, ocr_text: str) -> Dict[str, Any]:
    ref_nums = [float(x) for x in NUMBER_RE.findall(strip_page_markers(ref_text))]
    ocr_nums = [float(x) for x in NUMBER_RE.findall(strip_page_markers(ocr_text))]
    matched = lcs_length(ref_nums, ocr_nums, num_equal)
    precision = matched / len(ocr_nums) if ocr_nums else 0.0
    recall = matched / len(ref_nums) if ref_nums else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "reference_count": len(ref_nums),
        "extracted_count": len(ocr_nums),
        "matched": matched,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def score_gold(
    truth: Dict[str, Any],
    ocr_params: List[Dict[str, Any]],
) -> Dict[str, Any]:
    ocr_map = param_map(ocr_params)
    rows: List[Dict[str, Any]] = []
    value_hits = 0
    status_hits = 0
    status_total = 0

    for item in truth.get("tests", []):
        key = normalize_test_name(str(item.get("name", "")))
        expected = item.get("value")
        got = ocr_map.get(key)
        value_ok = got is not None and value_close(got.get("value"), expected)
        if value_ok:
            value_hits += 1
        status_expected = item.get("status")
        status_ok: Optional[bool] = None
        if status_expected:
            status_total += 1
            status_ok = bool(value_ok and status_of(got) == str(status_expected).lower())
            if status_ok:
                status_hits += 1
        rows.append(
            {
                "name": item.get("name"),
                "expected": expected,
                "got": None if got is None else got.get("value"),
                "value_ok": value_ok,
                "status_expected": status_expected,
                "status_got": None if got is None else got.get("status"),
                "status_ok": status_ok,
            }
        )

    return {
        "rows": rows,
        "total": len(rows),
        "value_hits": value_hits,
        "status_hits": status_hits,
        "status_total": status_total,
    }


# ── Per-file evaluation ─────────────────────────────────────────────────────

def load_truth(filename: str) -> Optional[Dict[str, Any]]:
    """Load hand-checked labels; accepts `<stem>.json` or `<filename>.json`."""
    stem = Path(filename).stem
    for candidate in (TRUTH_DIR / f"{stem}.json", TRUTH_DIR / f"{filename}.json"):
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    return None


async def evaluate_file(path: Path) -> Dict[str, Any]:
    started = time.perf_counter()
    result: Dict[str, Any] = {"file": path.name, "errors": []}

    ref_text = ""
    if path.suffix.lower() == ".pdf":
        ref_text, ocr_text, pages = await ocr_pdf_with_reference(path)
        result["pages"] = pages
    else:
        ocr_text = await ocr_image(path)
        result["pages"] = 1

    result["duration_s"] = time.perf_counter() - started
    result["ref_chars"] = len(norm_chars(ref_text))
    result["ocr_chars"] = len(norm_chars(ocr_text))

    # --- OCR error rates (only where a digital reference exists) ---
    if norm_chars(ref_text):
        char_dist, char_ref = error_rate(norm_chars(ref_text), norm_chars(ocr_text))
        word_dist, word_ref = error_rate(norm_words(ref_text), norm_words(ocr_text))
        result["cer"] = char_dist / char_ref
        result["wer"] = word_dist / word_ref
        result["char_dist"] = char_dist
        result["char_ref"] = char_ref
        result["word_dist"] = word_dist
        result["word_ref"] = word_ref
        result["numbers"] = score_numbers(ref_text, ocr_text)
    else:
        result["cer"] = result["wer"] = None
        result["numbers"] = None

    # --- Key-level extraction ---
    ocr_params = analyse_report_text_offline(ocr_text)["parameters"]
    result["ocr_parameters"] = len(ocr_params)
    if norm_chars(ref_text):
        ref_params = analyse_report_text_offline(ref_text)["parameters"]
        result["reference_parameters"] = len(ref_params)
        result["parameters"] = score_parameters(ref_params, ocr_params)
    else:
        result["reference_parameters"] = None
        result["parameters"] = None

    # --- Gold labels (hand-checked) ---
    truth = load_truth(path.name)
    if truth:
        result["gold"] = score_gold(truth, ocr_params)
        if not norm_chars(ref_text):
            # Image-only report: show the OCR text around each finding.
            result["ocr_text"] = ocr_text
    else:
        result["gold"] = None

    return result


# ── Reporting ───────────────────────────────────────────────────────────────

def fmt_pct(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def fmt_ratio(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def file_section_markdown(result: Dict[str, Any]) -> str:
    lines: List[str] = [f"### `{result['file']}`", ""]
    lines.append(f"- Processed in {result['duration_s']:.1f}s"
                 f" ({result['pages']} page(s); "
                 f"{result['ref_chars']} reference chars / {result['ocr_chars']} OCR chars)")

    if result["cer"] is not None:
        lines.append(
            f"- **OCR:** CER **{fmt_pct(result['cer'])}** "
            f"({result['char_dist']} wrong chars / {result['char_ref']}), "
            f"WER **{fmt_pct(result['wer'])}** "
            f"({result['word_dist']} wrong words / {result['word_ref']})"
        )
        numbers = result["numbers"]
        if numbers:
            lines.append(
                f"- **Numeric literals:** {numbers['matched']}/{numbers['reference_count']} "
                f"recalled, {numbers['matched']}/{numbers['extracted_count']} precise "
                f"(P {fmt_pct(numbers['precision'])} / R {fmt_pct(numbers['recall'])} / "
                f"F1 {fmt_pct(numbers['f1'])})"
            )
        params = result["parameters"]
        if params:
            lines.append(
                f"- **Key levels (name+value):** {len(params['value_matched'])}/"
                f"{params['reference_count']} reference rows recovered "
                f"(P {fmt_pct(params['precision'])} / R {fmt_pct(params['recall'])} / "
                f"F1 {fmt_pct(params['f1'])})"
            )
            if params["missing"]:
                lines.append(f"  - missed: {', '.join(params['missing'][:10])}")
            if params["extra"]:
                lines.append(f"  - unexpected extra: {', '.join(params['extra'][:10])}")
            if params["value_bad_details"]:
                details = "; ".join(
                    f"{item['name']} expected {item['expected']}, got {item['got']}"
                    for item in params["value_bad_details"][:10]
                )
                lines.append(f"  - value off: {details}")
            if params["status_bad_details"]:
                details = "; ".join(
                    f"{item['name']} expected {item['expected']}, got {item['got']}"
                    for item in params["status_bad_details"][:10]
                )
                lines.append(f"  - status disagreements: {details}")
            status_rate = (
                len(params["status_matched"]) / len(params["value_matched"])
                if params["value_matched"] else 0.0
            )
            lines.append(
                f"  - status agreement: {len(params['status_matched'])}/"
                f"{len(params['value_matched'])} ({fmt_pct(status_rate)})"
            )
    else:
        lines.append("- **OCR:** no digital text layer (scanned/image-only) -- CER not applicable")

    if result["gold"]:
        gold = result["gold"]
        lines.append(
            f"- **Gold labels:** {gold['value_hits']}/{gold['total']} values correct"
            + (
                f", {gold['status_hits']}/{gold['status_total']} statuses correct"
                if gold["status_total"] else ""
            )
        )
        for row in gold["rows"]:
            mark = "PASS" if row["value_ok"] else "FAIL"
            status_part = ""
            if row["status_expected"]:
                status_mark = "PASS" if row["status_ok"] else "FAIL"
                status_part = f"; status {row['status_got']} vs {row['status_expected']} [{status_mark}]"
            lines.append(
                f"  - [{mark}] {row['name']}: got {row['got']}, expected {row['expected']}{status_part}"
            )

    if result["gold"] is None and result["reference_parameters"] == 0 and result["ocr_parameters"] == 0:
        lines.append("- No gold labels found and no rows parsed -- add "
                     f"`tools/eval_truth/{Path(result['file']).stem}.json` to score this file.")

    lines.append("")
    return "\n".join(lines)


def summary_table(results: Sequence[Dict[str, Any]]) -> str:
    header = ("| File | OCR CER | WER | Numbers F1 | Key levels P / R / F1 | "
              "Status agree | Gold values |")
    lines = [header, "|" + "---|" * 7]
    for result in results:
        params = result["parameters"]
        if params and params["reference_count"]:
            key_col = (
                f"{fmt_pct(params['precision'])} / {fmt_pct(params['recall'])} / "
                f"{fmt_pct(params['f1'])}"
            )
            status_rate = (
                len(params["status_matched"]) / len(params["value_matched"]) * 100
                if params["value_matched"] else 0.0
            )
            status_col = f"{status_rate:.0f}%" if params["value_matched"] else "n/a"
        else:
            key_col = "n/a"
            status_col = "n/a"
        numbers = result["numbers"]
        num_col = fmt_pct(numbers["f1"]) if numbers else "n/a"
        gold = result["gold"]
        gold_col = f"{gold['value_hits']}/{gold['total']}" if gold else "no labels"
        lines.append(
            f"| {result['file']} | {fmt_pct(result['cer'])} | {fmt_pct(result['wer'])} "
            f"| {num_col} | {key_col} | {status_col} | {gold_col} |"
        )
    return "\n".join(lines)


def pooled_line(results: Sequence[Dict[str, Any]]) -> str:
    char_dist = sum(r.get("char_dist") or 0 for r in results)
    char_ref = sum(r.get("char_ref") or 0 for r in results)
    word_dist = sum(r.get("word_dist") or 0 for r in results)
    word_ref = sum(r.get("word_ref") or 0 for r in results)
    trues = sum(r["parameters"]["trues"] for r in results if r["parameters"])
    extracted = sum(r["parameters"]["copies"] for r in results if r["parameters"])
    reference = sum(r["parameters"]["reference_count"] for r in results if r["parameters"])
    pooled_p = trues / extracted if extracted else 0
    pooled_r = trues / reference if reference else 0
    pooled_f1 = 2 * pooled_p * pooled_r / (pooled_p + pooled_r) if (pooled_p + pooled_r) else 0
    return (
        f"Pooled over files with references: CER "
        f"{(char_dist / char_ref * 100 if char_ref else 0):.1f}%, WER "
        f"{(word_dist / word_ref * 100 if word_ref else 0):.1f}%, key-level "
        f"P {pooled_p * 100:.1f}% / R {pooled_r * 100:.1f}% / F1 {pooled_f1 * 100:.1f}% "
        f"({trues} of {reference} reference rows recovered; {extracted - trues} spurious)."
    )


def build_report(results: Sequence[Dict[str, Any]]) -> str:
    generated = time.strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Extraction accuracy report",
        "",
        f"Generated: {generated} (local, no network calls)",
        "",
        "## Summary",
        "",
        summary_table(results),
        "",
        pooled_line(results),
        "",
        "## Details",
        "",
    ]
    for result in results:
        lines.append(file_section_markdown(result))
    lines.extend([
        "## How to read these numbers",
        "",
        "- **CER/WER** compare OCR against the PDF's own digital text layer;",
        "  the PDF was rendered to a 300-DPI image first, so this is a fair",
        "  simulation of scanning a printed report.",
        "- **Key levels P/R/F1** match test names via the production alias",
        "  normalizer; a value counts only within 0.5% of the reference value.",
        "- **Status agree** checks Low/Normal/High against the status derived",
        "  from the digital text.",
        "- **Gold values** come from hand-checked labels in `tools/eval_truth/`,",
        "  the only valid reference for image-only reports.",
        "",
    ])
    return "\n".join(lines)


# ── Entry point ─────────────────────────────────────────────────────────────

def default_files() -> List[Path]:
    return sorted(REPO_DIR.glob("test_report*"))


async def run(files: Sequence[Path]) -> List[Dict[str, Any]]:
    results = []
    for path in files:
        print(f"Evaluating {path.name} ...", file=sys.stderr)
        try:
            results.append(await evaluate_file(path))
        except Exception as exc:  # keep going; report the failure
            results.append({"file": path.name, "errors": [str(exc)],
                            "cer": None, "wer": None, "numbers": None,
                            "parameters": None, "gold": None, "errors_note": str(exc)})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="PDF/image files (default: repo test_report*)")
    parser.add_argument("--out", default=str(TOOLS_DIR / "eval_report.md"),
                        help="Markdown output path")
    args = parser.parse_args()

    files = [Path(p) for p in args.files] if args.files else default_files()
    if not files:
        print("No input files found.", file=sys.stderr)
        raise SystemExit(2)

    results = asyncio.run(run(files))

    failed = [r for r in results if r.get("errors")]
    for failure in failed:
        print(f"ERROR {failure['file']}: {failure['errors']}", file=sys.stderr)

    report = build_report([r for r in results if not r.get("errors")])
    out_path = Path(args.out)
    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nMarkdown report written to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
