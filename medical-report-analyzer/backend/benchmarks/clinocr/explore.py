"""
benchmarks/clinocr/explore.py
=============================
One-time inspection of ClinOCR-Bench: maps subset/template -> document type so
the benchmark can select only laboratory / pathology reports.

Run from the backend directory:
    python benchmarks/clinocr/explore.py
"""

from __future__ import annotations

from collections import defaultdict

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download

REPO = "ClinOCR-Bench/ClinOCR-Bench"
SUBSETS = ["normal", "handwriting", "poor", "rotated", "tables", "mixed"]


def main() -> None:
    for subset in SUBSETS:
        path = hf_hub_download(REPO, f"{subset}/test-00000-of-00001.parquet", repo_type="dataset")
        table = pq.read_table(path)
        rows = table.to_pylist()
        grouped: dict[int, list[dict]] = defaultdict(list)
        for row in rows:
            grouped[row["template"]].append(row)

        print(f"\n=== {subset} ({table.num_rows} rows, columns={table.column_names}) ===")
        for template, items in sorted(grouped.items()):
            snippet = " | ".join(items[0]["ground_truth"].splitlines()[:4])[:220]
            print(f"  t{template:>2} n={len(items):<2} :: {snippet}")

    # Show the schema of the image column once.
    path = hf_hub_download(REPO, "normal/test-00000-of-00001.parquet", repo_type="dataset")
    print("\nSchema:", pq.read_table(path).schema)


if __name__ == "__main__":
    main()
