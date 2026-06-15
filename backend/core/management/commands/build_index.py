"""Management command: build the textbook vector index used by RAG.

A one-time (occasional) ingestion. For each textbook PDF in the target folder it:
  1. extracts text page by page (pdfplumber),
  2. cleans each page (strip running header/footer, rejoin hyphen-split words,
     normalise fancy quotes, collapse whitespace),
  3. chunks text along chapter/section headings, splitting long sections into
     ~250-word pieces with ~40-word overlap,
  4. tags every chunk with grade/source_file/chapter/section/page/chunk_index,
  5. stores everything in a persistent Chroma collection (embedded locally).

Re-runnable: the collection is reset each run so a rebuild is clean.

Usage:
    python manage.py build_index                 # uses backend/textbooks/
    python manage.py build_index path\\to\\folder
"""

import re
from pathlib import Path

import pdfplumber
from django.conf import settings
from django.core.management.base import BaseCommand

from core.retrieval import CHROMA_DIR, COLLECTION_NAME, get_client

DEFAULT_TEXTBOOKS_DIR = settings.BASE_DIR / "textbooks"

# Chunking sizes, in words.
CHUNK_WORDS = 250
CHUNK_OVERLAP = 40

# Heading patterns seen in the books:
#   chapter -> "01 Plant Diversity"            (two digits, space, Capitalised title; NO dot)
#   section -> "1.1 Morphological features ..." ("n.m", space, Capitalised title)
# The title must be alphabetic words (spaces / simple punctuation allowed) with NO
# digits. That stops numbered list items ("01. Tap root"), figure/measurement lines
# ("60 N 3 m2") and table-of-contents entries ("1.1 Title 12", which end in a page
# number) from being mistaken for headings.
CHAPTER_RE = re.compile(r"^(\d{2})\s+([A-Z][A-Za-z][A-Za-z &',()\-]{1,58})$")
SECTION_RE = re.compile(r"^(\d{1,2}\.\d{1,2})\s+([A-Z][A-Za-z][A-Za-z &',()\-]{1,68})$")

# Map the "fancy" quote characters found in the books to plain ASCII quotes.
QUOTE_MAP = {
    0x2018: "'", 0x2019: "'", 0x201A: "'", 0x201B: "'",   # ' ' ‚ ‛
    0x02BB: "'", 0x02BC: "'", 0x2032: "'",                 # ʻ ʼ ′
    0x201C: '"', 0x201D: '"', 0x201E: '"', 0x2033: '"',   # " " „ ″
    0x2013: "-", 0x2014: "-",                               # – —  (en/em dash)
}

ROMAN_RE = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)


def parse_grade(filename):
    """Grade from a filename like 'G7P1.pdf' -> 7 (so G7P1 and G7P2 both map to 7).
    Returns None if the name doesn't start with G<number>."""
    match = re.match(r"^G(\d+)", filename, re.IGNORECASE)
    return int(match.group(1)) if match else None


def clean_page_text(raw):
    """Clean one page of extracted text. The four cleanup steps live here."""
    # 1) Drop the running header/footer (always contains 'Science |'), standalone
    #    page numbers, and roman-numeral front-matter page numbers.
    kept = []
    for line in raw.split("\n"):
        s = line.strip()
        if not s or "Science |" in s or s.isdigit() or ROMAN_RE.match(s):
            continue
        kept.append(s)
    text = "\n".join(kept)

    # 2) Rejoin words split by a hyphen at a line break: "non-\nflowering" -> "nonflowering".
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    # 3) Normalise fancy quote characters to plain quotes.
    text = text.translate(QUOTE_MAP)

    # 4) Collapse runs of spaces/tabs.
    text = re.sub(r"[ \t]+", " ", text)
    return text


def split_into_word_chunks(text, size=CHUNK_WORDS, overlap=CHUNK_OVERLAP):
    """Split a long passage into ~`size`-word chunks overlapping by ~`overlap`
    words, so ideas aren't cut mid-thought. Short passages return as one chunk."""
    words = text.split()
    if not words:
        return []
    if len(words) <= size:
        return [text.strip()]
    chunks = []
    start = 0
    while start < len(words):
        chunks.append(" ".join(words[start:start + size]))
        if start + size >= len(words):
            break
        start += size - overlap
    return chunks


def build_chunks_for_file(pages, grade, source_file):
    """Turn (pdf_page_number, raw_text) pairs into tagged chunk dicts.

    We ingest all body text (so no book is ever silently dropped, regardless of how
    its chapters are formatted) and simply update the chapter/section labels
    whenever a heading is detected — the headings are used for metadata, not to
    decide what to keep. The small amount of front matter (foreword/contents) that
    gets included is harmless: a science query won't match it.
    """
    chunks = []
    chunk_index = 0
    current_chapter = "(document)"   # until the first real chapter heading is seen
    current_section = ""
    buf_lines = []
    buf_page = None

    def flush():
        nonlocal buf_lines, chunk_index
        if not buf_lines:
            return
        paragraph = re.sub(r"\s+", " ", " ".join(buf_lines)).strip()
        for piece in split_into_word_chunks(paragraph):
            if len(piece.split()) < 8:      # drop tiny leftovers
                continue
            chunks.append({
                "text": piece,
                "grade": grade,
                "source_file": source_file,
                "chapter": current_chapter or "",
                "section": current_section or "",
                "page": buf_page or 0,
                "chunk_index": chunk_index,
            })
            chunk_index += 1
        buf_lines = []

    for page_no, raw in pages:
        for line in clean_page_text(raw).split("\n"):
            line = line.strip()
            if not line:
                continue
            chapter_match = CHAPTER_RE.match(line)
            section_match = SECTION_RE.match(line)
            if chapter_match:
                flush()
                current_chapter = chapter_match.group(2).strip()
                current_section = ""
                buf_page = page_no
            elif section_match:
                flush()
                current_section = section_match.group(2).strip()
                buf_page = page_no
            else:
                if buf_page is None:
                    buf_page = page_no
                buf_lines.append(line)
    flush()
    return chunks


def extract_pages(pdf_path):
    """Return [(pdf_page_number, raw_text), ...] for a PDF (page numbers 1-based)."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            pages.append((i + 1, page.extract_text() or ""))
    return pages


class Command(BaseCommand):
    help = "Build the textbook vector index (RAG) from the PDFs in backend/textbooks/."

    def add_arguments(self, parser):
        parser.add_argument(
            "folder", nargs="?", default=str(DEFAULT_TEXTBOOKS_DIR),
            help="Folder of textbook PDFs (default: backend/textbooks/).",
        )

    def handle(self, *args, **options):
        folder = Path(options["folder"])
        if not folder.exists():
            self.stderr.write(self.style.ERROR(f"Folder not found: {folder}"))
            return

        pdf_paths = sorted(folder.glob("*.pdf"))
        if not pdf_paths:
            self.stderr.write(self.style.ERROR(f"No PDF files found in {folder}"))
            return

        all_chunks = []
        per_grade = {}
        per_file = []

        for pdf_path in pdf_paths:
            grade = parse_grade(pdf_path.name)
            if grade is None:
                self.stdout.write(self.style.WARNING(
                    f"Skipping {pdf_path.name}: could not read grade from filename."))
                continue

            self.stdout.write(f"Reading {pdf_path.name} (grade {grade}) ...")
            pages = extract_pages(pdf_path)
            chunks = build_chunks_for_file(pages, grade, pdf_path.name)

            if not chunks:
                self.stdout.write(self.style.WARNING(
                    f"  WARNING: {pdf_path.name} produced no text/chunks."))
                continue

            all_chunks.extend(chunks)
            per_grade[grade] = per_grade.get(grade, 0) + len(chunks)
            per_file.append((pdf_path.name, grade, len(pages), len(chunks)))
            self.stdout.write(f"  {len(pages)} pages -> {len(chunks)} chunks")

        if not all_chunks:
            self.stderr.write(self.style.ERROR("No chunks produced; nothing to index."))
            return

        # Reset the collection so a rebuild is clean, then add in batches
        # (Chroma embeds each batch locally with its default model).
        self.stdout.write(f"\nWriting {len(all_chunks)} chunks to Chroma at {CHROMA_DIR} ...")
        client = get_client()
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        collection = client.create_collection(COLLECTION_NAME)

        batch = 200
        for i in range(0, len(all_chunks), batch):
            part = all_chunks[i:i + batch]
            collection.add(
                ids=[f'{c["source_file"]}-{c["chunk_index"]}' for c in part],
                documents=[c["text"] for c in part],
                metadatas=[{
                    "grade": c["grade"],
                    "source_file": c["source_file"],
                    "chapter": c["chapter"],
                    "section": c["section"],
                    "page": c["page"],
                    "chunk_index": c["chunk_index"],
                } for c in part],
            )

        # Summary.
        self.stdout.write(self.style.SUCCESS("\nDone. Index summary:"))
        for name, grade, npages, nchunks in per_file:
            self.stdout.write(f"  {name}: grade {grade}, {npages} pages, {nchunks} chunks")
        self.stdout.write("  ---")
        for grade in sorted(per_grade):
            self.stdout.write(f"  Grade {grade}: {per_grade[grade]} chunks")
        self.stdout.write(self.style.SUCCESS(
            f"  TOTAL: {len(all_chunks)} chunks in collection '{COLLECTION_NAME}'"))
