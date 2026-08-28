"""The syllabus browser's data source: the Grade 6-9 science curriculum tree.

The tree is parsed out of the textbook contents pages that were transcribed into
`evaluation/probes/textbook_toc.md`. That file is the same artefact the retrieval
evaluation draws its probes from, so what this endpoint shows a learner and what
the retriever is graded against come from one source rather than two.

Shape of the source file (regular throughout):

    ## G6.pdf

    1. Wonders of the Living World — 1
       1.1 Characteristics of Organisms — 6

An unindented `N. Title — page` line opens a chapter; an indented
`N.M Title — page` line is one of its sub-sections. The number after the em dash
(U+2014) is the PRINTED start page, occasionally zero-padded ("01").

Seven book files cover four grades, and a grade split over two parts continues
its chapter numbering across the split (G9P2 opens at chapter 10). Each grade is
therefore presented as one continuous ordered list of chapters, with every
chapter still recording the book file it was printed in.

Page RANGES are derived, never read: a row runs until one before its next
sibling starts. A range is never derived across a book-file boundary, so the
last chapter of a book (and its last sub-section) has no derivable end; those
rows come back with `page_end` equal to `page_start` and `has_range` false, so
the page can print "p. 12" rather than an invented "pp. 12-12".

The file cannot change while the server is running, so the parsed tree is built
once on the first request and then held in a module-level cache.
"""

import re
import threading
from pathlib import Path

from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response

# --- Where the contents pages live ----------------------------------------------

TOC_RELATIVE_PATH = Path("evaluation") / "probes" / "textbook_toc.md"

# Which grade each transcribed book file belongs to. A grade printed in two parts
# lists both, in reading order; chapter numbering runs on from part 1 into part 2.
BOOK_GRADES = {
    "G6.pdf": 6,
    "G7P1.pdf": 7,
    "G7P2.pdf": 7,
    "G8P1.pdf": 8,
    "G8P2.pdf": 8,
    "G9P1.pdf": 9,
    "G9P2.pdf": 9,
}

EM_DASH = "—"

# `## G6.pdf`
_BOOK_RE = re.compile(r"^##\s+(\S+)\s*$")
# `1. Wonders of the Living World — 1`  (unindented: a chapter)
_CHAPTER_RE = re.compile(r"^(\d+)\.\s+(\S.*)$")
# `   1.1 Characteristics of Organisms — 6`  (indented: a sub-section)
_SECTION_RE = re.compile(r"^\s+(\d+\.\d+)\s+(\S.*)$")

# Parsed once, then reused. The lock only guards the first build so two requests
# arriving together cannot each pay for a parse.
_CACHE = None
_CACHE_LOCK = threading.Lock()


# --- Parsing ---------------------------------------------------------------------

def _toc_path():
    """Absolute path to the transcribed contents pages."""
    return Path(settings.BASE_DIR) / TOC_RELATIVE_PATH


def _split_title_and_page(text):
    """Split `Title — 12` into ("Title", 12).

    Splits on the LAST em dash so a title containing one of its own survives, and
    returns a page of None when the tail is not a number (a malformed row is then
    skipped rather than crashing the endpoint).
    """
    if EM_DASH not in text:
        return text.strip(), None
    title, _, page = text.rpartition(EM_DASH)
    page = page.strip()
    if not page.isdigit():
        return text.strip(), None
    # int() handles the zero-padded pages ("01" -> 1).
    return title.strip(), int(page)


def _parse_rows(text):
    """Read the file into a flat ordered list of rows, one per printed line.

    Each row is a dict: kind ("chapter"/"section"), book, number, title,
    page_start. Keeping it flat first makes the page-range pass below a simple
    look-ahead rather than a walk over nested structures.
    """
    rows = []
    book = None
    for line in text.splitlines():
        if not line.strip():
            continue

        book_match = _BOOK_RE.match(line)
        if book_match:
            book = book_match.group(1)
            continue
        if book is None:
            continue  # the document title, before the first book heading

        section_match = _SECTION_RE.match(line)
        if section_match:
            title, page = _split_title_and_page(section_match.group(2))
            if page is None:
                continue
            rows.append({
                "kind": "section",
                "book": book,
                "number": section_match.group(1),
                "title": title,
                "page_start": page,
            })
            continue

        chapter_match = _CHAPTER_RE.match(line)
        if chapter_match:
            title, page = _split_title_and_page(chapter_match.group(2))
            if page is None:
                continue
            rows.append({
                "kind": "chapter",
                "book": book,
                "number": int(chapter_match.group(1)),
                "title": title,
                "page_start": page,
            })
    return rows


def _end_page(row, following):
    """Derive (page_end, has_range) for one row from the rows that follow it.

    A row runs until one page before the next row that opens a new printed span
    at its own level or above:

    * a CHAPTER ends where the next chapter begins — its own sub-sections sit
      inside it and are skipped;
    * a SUB-SECTION ends where the very next row begins, which is either its next
      sibling or, for the last sub-section, the chapter that follows.

    Nothing is derived across a book-file boundary. `has_range` is true only when
    the row genuinely spans more than one page: a row with no next sibling in its
    book, and a row that begins and ends on the same printed page, both come back
    as (page_start, False) so the page prints "p. 161" instead of "pp. 161-161".
    """
    for nxt in following:
        if nxt["book"] != row["book"]:
            break  # never derive a range across book files
        if row["kind"] == "chapter" and nxt["kind"] != "chapter":
            continue  # a chapter's own sub-sections do not end it
        end = nxt["page_start"] - 1
        if end > row["page_start"]:
            return end, True
        return row["page_start"], False
    return row["page_start"], False


def _build_tree(text):
    """Turn the file's text into the grade -> chapter -> section tree."""
    rows = _parse_rows(text)

    # Second pass: attach a derived page range to every row.
    for i, row in enumerate(rows):
        row["page_end"], row["has_range"] = _end_page(row, rows[i + 1:])

    # Third pass: nest sections under their chapter, chapters under their grade.
    grades = {}
    current_chapter = None
    for row in rows:
        grade = BOOK_GRADES.get(row["book"])
        if grade is None:
            continue  # a book file outside the Grade 6-9 programme

        if row["kind"] == "chapter":
            current_chapter = {
                "number": row["number"],
                "title": row["title"],
                "page_start": row["page_start"],
                "page_end": row["page_end"],
                "has_range": row["has_range"],
                "book": row["book"],
                "sections": [],
            }
            bucket = grades.setdefault(grade, {"books": [], "chapters": []})
            if row["book"] not in bucket["books"]:
                bucket["books"].append(row["book"])
            bucket["chapters"].append(current_chapter)
        elif current_chapter is not None:
            current_chapter["sections"].append({
                "number": row["number"],
                "title": row["title"],
                "page_start": row["page_start"],
                "page_end": row["page_end"],
                "has_range": row["has_range"],
            })

    return [
        {
            "grade": grade,
            "books": bucket["books"],
            "chapter_count": len(bucket["chapters"]),
            "section_count": sum(len(c["sections"]) for c in bucket["chapters"]),
            "chapters": bucket["chapters"],
        }
        for grade, bucket in sorted(grades.items())
    ]


def _curriculum_tree():
    """The parsed tree, built on first use and cached for the process's lifetime.

    A missing or unreadable contents file yields an empty tree — the browser then
    shows its empty state instead of the endpoint failing.
    """
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    with _CACHE_LOCK:
        if _CACHE is None:
            try:
                text = _toc_path().read_text(encoding="utf-8")
            except OSError:
                _CACHE = []
            else:
                _CACHE = _build_tree(text)
    return _CACHE


# --- Endpoint --------------------------------------------------------------------

@api_view(["GET"])
def curriculum(request, *args, **kwargs):
    """GET /api/curriculum — the whole Grade 6-9 syllabus tree.

    The whole tree is returned in one response (about 60 KB) because the browser
    filters and expands it entirely on the client; paging it would only add round
    trips to an artefact that never changes.
    """
    grades = _curriculum_tree()
    return Response({
        "source": "Grade 6-9 science textbook contents pages",
        "grades": grades,
        "chapter_count": sum(g["chapter_count"] for g in grades),
        "section_count": sum(g["section_count"] for g in grades),
    })
