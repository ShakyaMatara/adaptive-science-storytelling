"""Management command: measure the METADATA QUALITY of the built Chroma index.

Part of the evaluation harness, not the running application. It reads the index
and writes one row per grade describing how well the ingestion pipeline attributed
each chunk to a page, a section and a chapter. It creates no application rows and
makes no provider calls, so it is free and non-invasive.

Used to evidence the ingestion defect-and-repair reported in Chapter 7: run it once
before the build_index fix and once after, and compare the two CSVs.

Usage:
    python manage.py eval_index_quality --out evaluation/results/index_quality_before.csv
"""

from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand

from evaluation.harness import table

FIELDNAMES = [
    "grade",
    "chunks",
    "distinct_pages",
    "distinct_sections",
    "distinct_chapters",
    "max_chunks_per_page",
]


def measure(metadatas):
    """Return one metadata-quality row per grade, ordered by grade."""
    chunks = Counter()
    pages = defaultdict(Counter)
    sections = defaultdict(set)
    chapters = defaultdict(set)

    for meta in metadatas:
        grade = meta.get("grade")
        chunks[grade] += 1
        pages[grade][meta.get("page")] += 1
        if meta.get("section"):
            sections[grade].add(meta.get("section"))
        if meta.get("chapter"):
            chapters[grade].add(meta.get("chapter"))

    rows = []
    for grade in sorted(chunks, key=lambda g: (g is None, g)):
        counts = pages[grade]
        rows.append({
            "grade": grade,
            "chunks": chunks[grade],
            "distinct_pages": len(counts),
            "distinct_sections": len(sections[grade]),
            "distinct_chapters": len(chapters[grade]),
            "max_chunks_per_page": max(counts.values()) if counts else 0,
        })
    return rows


class Command(BaseCommand):
    help = "Measure per-grade metadata quality of the Chroma index and write it to a CSV."

    def add_arguments(self, parser):
        parser.add_argument(
            "--out", required=True,
            help="Destination CSV path (relative to backend/, or absolute).",
        )

    def handle(self, *args, **options):
        import csv

        from core.retrieval import get_collection

        try:
            collection = get_collection()
        except Exception as exc:
            self.stderr.write(self.style.ERROR(
                f"Could not open the Chroma collection: {type(exc).__name__}: {exc}"))
            return

        metadatas = collection.get(include=["metadatas"]).get("metadatas") or []
        if not metadatas:
            self.stderr.write(self.style.ERROR("The collection returned no metadata; nothing to measure."))
            return

        rows = measure(metadatas)

        out = Path(options["out"])
        if not out.is_absolute():
            out = Path.cwd() / out
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)

        self.stdout.write(table(rows, FIELDNAMES))
        self.stdout.write(f"\nTotal chunks: {sum(r['chunks'] for r in rows)}")
        self.stdout.write(self.style.SUCCESS(f"Wrote {out}"))
