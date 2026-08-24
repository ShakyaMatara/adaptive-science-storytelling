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
from collections import Counter
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
#
# The title is additionally capped at SIX words and may not contain a comma. Numbered
# TABLE rows are typographically indistinguishable from a chapter heading once the
# layout is flattened to text, and in this corpus they are the dominant source of
# false headings: the materials-properties table on G6 p.44 yielded rows such as
# "01 Hardness The property of resistance to Diamond , Iron", which a heading pattern
# with no length bound accepted and then applied to the remaining 124 chunks of the
# book. Every genuine chapter title in the corpus is one to six words long (the
# longest is "The Correct Use of the Microscope"), so the bound separates the two
# cleanly. Single-word table rows that survive this test are rejected structurally
# instead - see _chapter_heading_pages().
CHAPTER_RE = re.compile(
    r"^(\d{2})\s+([A-Z][A-Za-z][A-Za-z&'()\-]*(?:\s+[A-Za-z][A-Za-z&'()\-]*){0,5})$"
)
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
    words, so ideas aren't cut mid-thought. Short passages return as one chunk.

    Returns [(chunk_text, start_word_index), ...]. The start index lets the caller
    map a chunk back to the page its OWN first word came from, which is what the
    chunk's `page` metadata has to record.
    """
    words = text.split()
    if not words:
        return []
    if len(words) <= size:
        return [(text.strip(), 0)]
    chunks = []
    start = 0
    while start < len(words):
        chunks.append((" ".join(words[start:start + size]), start))
        if start + size >= len(words):
            break
        start += size - overlap
    return chunks


def _chapter_heading_pages(cleaned_pages):
    """Return the set of pages carrying exactly ONE chapter-heading candidate.

    A genuine chapter heading is the only one on its page, because a chapter runs
    for many pages. A numbered TABLE row is typographically identical to a heading
    once the layout is flattened ("01 Talc"), but such rows always appear several
    to a page. This corpus contains two of them - the Mohs hardness scale on G9P2
    p.171 (ten rows, "Talc" ... "Diamond") and the materials-properties table on
    G6 p.44 (five rows) - and both are rejected by requiring uniqueness, while
    every genuine heading in the corpus sits alone on its page and survives.
    """
    per_page = Counter()
    for page_no, text in cleaned_pages:
        for line in text.splitlines():
            if CHAPTER_RE.match(line.strip()):
                per_page[page_no] += 1
    return {page_no for page_no, count in per_page.items() if count == 1}


def build_chunks_for_file(pages, grade, source_file):
    """Turn (pdf_page_number, raw_text) pairs into tagged chunk dicts.

    We ingest all body text (so no book is ever silently dropped, regardless of how
    its chapters are formatted) and simply update the chapter/section labels
    whenever a heading is detected — the headings are used for metadata, not to
    decide what to keep. The small amount of front matter (foreword/contents) that
    gets included is harmless: a science query won't match it.

    Page attribution: body text is buffered across page boundaries until the next
    heading flushes it, so a buffer routinely spans several pages. The page each
    LINE came from is therefore carried alongside the line, and every emitted chunk
    is stamped with the page its own first word sits on. Recording the page of the
    most recent heading instead would collapse whole books onto a handful of page
    numbers and make the learner-facing citations wrong.
    """
    chunks = []
    chunk_index = 0
    current_chapter = "(document)"   # until the first real chapter heading is seen
    current_section = ""
    buf = []                         # [(page_no, line), ...] awaiting the next flush

    def flush():
        nonlocal buf, chunk_index
        if not buf:
            return
        # Flatten the buffer to a word list, keeping a parallel list of the page
        # each word came from so a chunk can be traced back to its own page.
        words, word_pages = [], []
        for page_no, line in buf:
            line_words = line.split()
            words.extend(line_words)
            word_pages.extend([page_no] * len(line_words))
        buf = []
        if not words:
            return
        paragraph = " ".join(words)
        for piece, start in split_into_word_chunks(paragraph):
            if len(piece.split()) < 8:      # drop tiny leftovers
                continue
            chunks.append({
                "text": piece,
                "grade": grade,
                "source_file": source_file,
                "chapter": current_chapter or "",
                "section": current_section or "",
                "page": word_pages[start],
                "chunk_index": chunk_index,
            })
            chunk_index += 1

    # Clean every page once, then pre-scan for the pages that carry a lone chapter
    # heading; candidates on any other page are numbered table rows and stay body text.
    cleaned = [(page_no, clean_page_text(raw)) for page_no, raw in pages]
    solo_heading_pages = _chapter_heading_pages(cleaned)

    for page_no, text in cleaned:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            chapter_match = CHAPTER_RE.match(line)
            section_match = SECTION_RE.match(line)
            if chapter_match and page_no in solo_heading_pages:
                flush()
                current_chapter = chapter_match.group(2).strip()
                current_section = ""
            elif section_match:
                flush()
                current_section = section_match.group(2).strip()
            else:
                buf.append((page_no, line))
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
