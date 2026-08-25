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

import json
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

# Positional slack, in points, when treating two identical glyphs at the same spot
# as a single overprinted impression rather than two characters. See extract_pages.
DEDUPE_TOLERANCE = 1.0

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

# --- Printed page numbers -------------------------------------------------------
# Each PDF page holds exactly ONE printed page. The offset is the front matter that
# precedes printed page 1, so printed = pdf_page - offset, and pages outside the
# valid range (front and back matter) carry no printed number at all.
#
# An earlier implementation parsed the folio out of the running footer instead. That
# was wrong: a page's extracted text frequently captures the FACING page's running
# footer as well, so a footer can read "14 Science | ... Science | ... 15" for a page
# that is printed page 14 or printed page 15 with equal likelihood. Measured across
# the corpus, the correct folio was the left one on 193 such pages and the right one
# on 192 - indistinguishable from a coin toss.
#
# The offset table below is verified two independent ways:
#   * page arithmetic - (PDF pages) - (front matter) - (trailing blanks) equals the
#     last printed page, exactly, in all seven books;
#   * table of contents - all 272 locatable TOC titles appear as a heading on exactly
#     the PDF page this table predicts, in all seven books, with no exceptions.
PAGE_OFFSETS = {
    # source_file: (offset, first valid PDF page, last valid PDF page)
    "G6.pdf":   (14, 15, 189),
    "G7P1.pdf": (12, 13, 160),
    "G7P2.pdf": (12, 13, 139),
    "G8P1.pdf": (10, 11, 137),
    "G8P2.pdf": (10, 11, 152),
    "G9P1.pdf": (12, 13, 121),
    "G9P2.pdf": (12, 13, 180),
}

# The published tables of contents, transcribed from the printed books. This is the
# authoritative source for chapter attribution: being transcribed rather than
# extracted, it inherits none of the PDFs' text-layer defects. Several books render
# their chapter openers as display type split across lines, or as images with no text
# layer at all, so no pattern applied to the extracted text can recover them.
TOC_PATH = settings.BASE_DIR / "evaluation" / "probes" / "textbook_toc.md"
TOC_BOOK_RE = re.compile(r"^##\s+(\S+\.pdf)\s*$")
TOC_CHAPTER_RE = re.compile(r"^(\d+)\.\s+(.*?)\s+[—-]\s+(\d+)\s*$")

# Symbol-font glyphs land in the Unicode Private Use Area, where they carry no
# meaning and render as nothing. The tick and cross marks of comparison tables are
# the damaging case: "Having a mass [tick] / Have not [cross]" reaches the index as
# "Having a mass - Have not -", deleting the distinction the table teaches while the
# surrounding sentence still reads as well-formed English. Each mapping below was
# identified from at least two contexts in the books.
SYMBOL_MAP = {
    0xF0FC: "✓",  # Wingdings check mark - "Having a mass [check]"
    0xF0FB: "✗",  # Wingdings ballot X    - "Have not [X]"
    0xF050: "✓",  # "Mark true ([check]) or false ([X])"
    0xF04F: "✗",
    0xF03D: "•",  # bullet marker in activity lists
    0xF001: "",        # decorative glyph beside a signature in the foreword
}

# Recovered text for pages the PDFs supply only as images. Keyed by PDF page number.
RECOVERED_PATH = settings.BASE_DIR / "evaluation" / "probes" / "g9p1_recovered_pages.json"

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

    # 3) Normalise fancy quote characters, and restore symbol-font glyphs that
    #    would otherwise be invisible Private Use Area codepoints.
    text = text.translate(QUOTE_MAP).translate(SYMBOL_MAP)

    # 4) Collapse runs of spaces/tabs.
    text = re.sub(r"[ \t]+", " ", text)
    return text


def printed_page(source_file, pdf_page):
    """The number printed on the page, or None for front/back matter.

    This is the number a learner holding the book can turn to; the PDF page index is
    not, and appears nowhere in the printed book.
    """
    entry = PAGE_OFFSETS.get(source_file)
    if entry is None:
        return None
    offset, first_valid, last_valid = entry
    if not first_valid <= pdf_page <= last_valid:
        return None
    return pdf_page - offset


_TOC_CACHE = {}


def load_toc(path=TOC_PATH):
    """Parse the tables of contents into {source_file: [(start_page, title), ...]}.

    Only chapter-level entries are read; sub-section labels still come from the
    headings in the text, which are reliable. The list is sorted by start page so a
    chunk can be attributed by a simple scan.
    """
    if path in _TOC_CACHE:
        return _TOC_CACHE[path]
    chapters = {}
    book = None
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            match = TOC_BOOK_RE.match(line.strip())
            if match:
                book = match.group(1)
                chapters.setdefault(book, [])
                continue
            if not book or line.startswith((" ", "\t")):
                continue  # indented lines are sub-sections
            match = TOC_CHAPTER_RE.match(line.strip())
            if match:
                chapters[book].append((int(match.group(3)), match.group(2).strip()))
    for book in chapters:
        chapters[book].sort()
    _TOC_CACHE[path] = chapters
    return chapters


def chapter_for(source_file, printed):
    """The chapter containing a printed page: the last one starting at or before it.

    Returns "" when the page precedes the first chapter (front matter) or the book
    has no table of contents entry.
    """
    if printed is None:
        return ""
    label = ""
    for start, title in load_toc().get(source_file, ()):
        if start <= printed:
            label = title
        else:
            break
    return label


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


def build_chunks_for_file(pages, grade, source_file, recovered_pages=frozenset(),
                          agreement=None):
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
    agreement = agreement or {}
    chunks = []
    chunk_index = 0
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
            length = len(piece.split())
            if length < 8:      # drop tiny leftovers
                continue
            # A chunk routinely runs past the page it starts on, so record the
            # printed page it starts on and the one it ends on; the citation collapses
            # them when they match. Front and back matter have no printed number, so
            # those stay empty and the caller falls back to the PDF page.
            end = min(start + length - 1, len(word_pages) - 1)
            printed_start = printed_page(source_file, word_pages[start])
            printed_end = printed_page(source_file, word_pages[end])
            touched_recovered = recovered_pages.intersection(word_pages[start:end + 1])
            chunks.append({
                "text": piece,
                "grade": grade,
                "source_file": source_file,
                # Chapter comes from the published contents page, by printed page
                # number - never from a pattern applied to the extracted text.
                "chapter": chapter_for(source_file, printed_start) or "(document)",
                "section": current_section or "",
                "page": word_pages[start],
                "page_label_start": "" if printed_start is None else str(printed_start),
                "page_label_end": "" if printed_end is None else str(printed_end),
                # Provenance: "text_layer" for text the PDF supplied, "ocr_vision"
                # for text recovered from an image-only page. A chunk routinely spans
                # several pages, so it counts as recovered when ANY of its words came
                # from a recovered page. Tagging by the starting page alone would leave
                # chunks that DO contain recovered text looking like pure text layer,
                # and they could not then be excluded from an analysis.
                "source_type": ("ocr_vision" if touched_recovered else "text_layer"),
                # Lowest A/B extraction agreement among the recovered pages this chunk
                # draws on; empty for text-layer chunks.
                "ocr_agreement": ("" if not touched_recovered else
                                  str(min(agreement.get(pg, 0.0) for pg in touched_recovered))),
                "chunk_index": chunk_index,
            })
            chunk_index += 1

    # Clean every page once, then pre-scan for the pages that carry a lone chapter
    # heading. Chapter headings no longer supply the chapter LABEL - that comes from
    # the table of contents - but they are still a genuine paragraph boundary, so
    # they continue to flush the buffer exactly as before.
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
                current_section = ""
            elif section_match:
                flush()
                current_section = section_match.group(2).strip()
            else:
                buf.append((page_no, line))
    flush()
    return chunks


def load_recovered(source_file):
    """Recovered text and its verification score for pages supplied only as images.

    Returns ({page_no: text}, {page_no: A/B extraction agreement}).

    G9P1.pdf is distributed with 19 content pages that carry no text layer at all, so
    neither pdfminer nor pdfium can read them and roughly a sixth of that book would
    otherwise be missing from the index. Those pages were rendered at 300 DPI and
    transcribed verbatim. Chunks built from them are flagged source_type="ocr_vision"
    so any analysis can exclude them.
    """
    if not RECOVERED_PATH.exists():
        return {}, {}
    with open(RECOVERED_PATH, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if payload.get("_source_file") != source_file:
        return {}, {}
    pages = {int(k): v for k, v in payload.get("pages", {}).items()}
    agreement = {int(k): float(v) for k, v in payload.get("agreement", {}).items()}
    return pages, agreement


def extract_pages(pdf_path):
    """Return ([(page_no, raw_text), ...], {recovered pages}, {page: A/B agreement}).

    `dedupe_chars` removes overprinted duplicate glyphs. The books render bold type by
    drawing the same glyph twice, which pdfminer faithfully reports twice, so an
    affected run extracts as "TThhrreeee ppeenn ttuubbeess". Deduplication is done on
    the CHARACTER stream using glyph position, not on the flattened string: a regex
    over doubled letters would destroy "letter", "book" and "cell". The tolerance is
    the positional slack allowed when treating two identical glyphs as one
    impression; the recovered text is identical for any value from 0.5 to 3.0, so the
    choice is not delicate, and 1.0 is pdfplumber's own default.
    """
    recovered, agreement = load_recovered(Path(pdf_path).name)
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            page_no = i + 1
            if page_no in recovered:
                pages.append((page_no, recovered[page_no]))
                continue
            pages.append((page_no, page.dedupe_chars(tolerance=DEDUPE_TOLERANCE).extract_text() or ""))
    return pages, set(recovered), agreement


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
            pages, recovered_pages, agreement = extract_pages(pdf_path)
            chunks = build_chunks_for_file(pages, grade, pdf_path.name, recovered_pages,
                                           agreement)

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
                    "page_label_start": c["page_label_start"],
                    "page_label_end": c["page_label_end"],
                    "source_type": c["source_type"],
                    "ocr_agreement": c["ocr_agreement"],
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
