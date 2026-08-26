"""Management command: derive T3's ground-truth coverage measure from the published
tables of contents.

The question T3 asks is whether the planner scales a session to how much of the
syllabus a topic actually occupies. Answering it needs a measure of curricular
emphasis that owes nothing to the system being evaluated. The contents pages provide
one: they were transcribed from the printed books, so they are independent of the
PDFs' text layer, of the embeddings, of the retrieval thresholds and of the planner.

For each entry, the pages the syllabus devotes to it are

    (start page of the next entry) - (its own start page)

with the final entry of a book running to the page after its last printed page. A
chapter is measured to the start of the NEXT CHAPTER, so a chapter's span covers all
of its sub-sections; a sub-section is measured to whichever entry follows it, which
for the last sub-section in a chapter is the next chapter.

This supersedes the lexical key-term counting originally proposed for T3. Counting
key terms measures how often wording recurs, which is a property of the prose; the
contents pages measure how much of the book the syllabus gives to a topic, which is
the thing T3 is actually about.

Usage:
    python manage.py eval_groundtruth
    python manage.py eval_groundtruth --out evaluation/probes/ground_truth.csv
"""

import csv
import re
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand

from core.management.commands.build_index import PAGE_OFFSETS, TOC_PATH
from evaluation.harness import table

BOOK_RE = re.compile(r"^##\s+(\S+\.pdf)\s*$")
CHAPTER_RE = re.compile(r"^(\d+)\.\s+(.*?)\s+[—-]\s+(\d+)\s*$")
SECTION_RE = re.compile(r"^\s+(\d+\.\d+)\s+(.*?)\s+[—-]\s+(\d+)\s*$")

FIELDNAMES = ["topic", "grade", "gt_pages", "kind", "number", "start_page",
              "end_page", "source_file"]


def parse_grade(source_file):
    match = re.match(r"^G(\d+)", source_file, re.IGNORECASE)
    return int(match.group(1)) if match else None


def last_printed_page(source_file):
    """Last numbered page of a book, from the same table the ingestion uses."""
    entry = PAGE_OFFSETS.get(source_file)
    if not entry:
        return None
    offset, _first, last_valid = entry
    return last_valid - offset


def load_toc(path):
    """Return {source_file: [(start_page, kind, number, title), ...]} sorted by page."""
    books = {}
    book = None
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            match = BOOK_RE.match(line.strip())
            if match:
                book = match.group(1)
                books.setdefault(book, [])
                continue
            if not book or not line.strip():
                continue
            match = SECTION_RE.match(line.rstrip())
            if match:
                books[book].append(
                    (int(match.group(3)), "section", match.group(1), match.group(2).strip()))
                continue
            match = CHAPTER_RE.match(line.strip())
            if match:
                books[book].append(
                    (int(match.group(3)), "chapter", match.group(1), match.group(2).strip()))
    for entries in books.values():
        entries.sort(key=lambda e: e[0])
    return books


def spans_for_book(entries, end_of_book):
    """Attach an end page and a span to every entry.

    A chapter runs to the start of the next CHAPTER, so its span covers all of its
    own sub-sections rather than stopping at the first of them. A sub-section runs to
    the next entry that starts on a LATER page.

    Two short sub-sections sometimes begin on the same printed page - four cases
    occur in this corpus, for example G6 7.1 "Effects of Magnets" and 7.2 "Different
    Type of Magnets" both starting on p.100 with 7.3 on p.101. Measuring to the next
    later start and then dividing the shared pages between them gives each half a
    page, which is closer to the truth than either zero (no coverage at all) or one
    (a full page each).
    """
    rows = []
    for i, (start, kind, number, title) in enumerate(entries):
        if kind == "chapter":
            nxt = next((s for s, k, _n, _t in entries[i + 1:] if k == "chapter"), None)
        else:
            nxt = next((s for s, _k, _n, _t in entries[i + 1:] if s > start), None)
        end = nxt if nxt is not None else end_of_book + 1
        sharing = sum(1 for s, k, _n, _t in entries if s == start and k == kind)
        rows.append((start, kind, number, title, end, round((end - start) / sharing, 2)))
    return rows


class Command(BaseCommand):
    help = ("Derive T3's ground-truth coverage measure (pages per topic) from the "
            "published tables of contents.")

    def add_arguments(self, parser):
        parser.add_argument(
            "--out", default="evaluation/probes/ground_truth.csv",
            help="Destination CSV (default: evaluation/probes/ground_truth.csv).")
        parser.add_argument(
            "--toc", default=str(TOC_PATH),
            help="Table-of-contents source (default: evaluation/probes/textbook_toc.md).")

    def handle(self, *args, **options):
        toc_path = Path(options["toc"])
        if not toc_path.exists():
            self.stderr.write(self.style.ERROR(f"Table of contents not found: {toc_path}"))
            return

        books = load_toc(toc_path)
        if not books:
            self.stderr.write(self.style.ERROR("No entries parsed from the table of contents."))
            return

        rows, anomalies = [], []
        for source_file, entries in sorted(books.items()):
            grade = parse_grade(source_file)
            end_of_book = last_printed_page(source_file)
            if grade is None or end_of_book is None:
                self.stdout.write(self.style.WARNING(
                    f"  Skipping {source_file}: no grade or page range known."))
                continue
            for start, kind, number, title, end, span in spans_for_book(entries, end_of_book):
                row = {
                    "topic": title, "grade": grade, "gt_pages": span, "kind": kind,
                    "number": number, "start_page": start, "end_page": end,
                    "source_file": source_file,
                }
                rows.append(row)
                if span <= 0:
                    anomalies.append(row)

        # --- report ---------------------------------------------------------------
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\nT3 ground truth — pages per topic, from the published contents pages"))
        per_book = []
        for source_file in sorted(books):
            subset = [r for r in rows if r["source_file"] == source_file]
            if not subset:
                continue
            spans = sorted(r["gt_pages"] for r in subset)
            per_book.append({
                "book": source_file,
                "grade": subset[0]["grade"],
                "entries": len(subset),
                "chapters": sum(1 for r in subset if r["kind"] == "chapter"),
                "sections": sum(1 for r in subset if r["kind"] == "section"),
                "min": spans[0],
                "median": spans[len(spans) // 2],
                "max": spans[-1],
            })
        self.stdout.write(table(per_book, ["book", "grade", "entries", "chapters",
                                           "sections", "min", "median", "max"]))

        sections = [r["gt_pages"] for r in rows if r["kind"] == "section"]
        chapters = [r["gt_pages"] for r in rows if r["kind"] == "chapter"]
        self.stdout.write(
            f"\n  {len(rows)} entries total: {len(chapters)} chapters, {len(sections)} sections")
        if sections:
            ordered = sorted(sections)
            self.stdout.write(
                f"  Sub-section spans: min {ordered[0]}, median {ordered[len(ordered)//2]}, "
                f"max {ordered[-1]}, mean {sum(ordered)/len(ordered):.1f} pages")
            self.stdout.write("  Distribution of sub-section spans (pages: count):")
            counts = Counter(sections)
            line = "   " + "  ".join(f"{p}p:{n}" for p, n in sorted(counts.items()))
            self.stdout.write(line)

        if anomalies:
            self.stdout.write(self.style.ERROR(
                f"\n  {len(anomalies)} entries have a zero or negative span — these indicate a "
                f"transcription slip in the contents pages and should be checked:"))
            for row in anomalies:
                self.stdout.write(self.style.ERROR(
                    f"     {row['source_file']} {row['number']:<6} {row['topic'][:46]:<46} "
                    f"p.{row['start_page']} -> p.{row['end_page']} = {row['gt_pages']}"))
        else:
            self.stdout.write(self.style.SUCCESS(
                "\n  No zero or negative spans: every entry starts before the one that follows it."))

        out = Path(options["out"])
        if not out.is_absolute():
            out = Path.cwd() / out
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        self.stdout.write(self.style.SUCCESS(f"\nWrote {out}"))
        self.stdout.write(
            "  Columns beyond topic/grade/gt_pages are for sanity-checking and are ignored\n"
            "  by eval_planner, which matches on (topic, grade).")
