"""GET /api/chapters/<id>/provenance — the textbook passages behind a chapter.

Why this endpoint has to do any work at all: a Chapter stores its `sources` as
page REFERENCES only —

    {"source_file": "G9P1.pdf", "page": 52, "page_citation": "pp. 40-41",
     "chapter": "Nature and Properties of Matter", "section": "Elements"}

— and never the passage text. `page` is the PDF page index; `page_citation` is
the printed folio a learner holding the book can actually turn to.

So the text is RE-RETRIEVED read-only at display time from the same index the
chapter was generated against, and matched back to the stored references on
(source_file, page). Two recovery paths, tried in that order:

  1. semantic — one `retrieval.retrieve()` call for the whole chapter, using the
     session topic plus the chapter title as the query. This is the primary path
     and normally returns every reference in one lookup.
  2. exact    — a metadata lookup straight at the collection for any reference
     the semantic query did not happen to return. The stored references came
     from the planner's wider sweep, so a narrower display-time query can miss
     one; this path recovers it.

Each passage reports which path recovered it, so the panel can be honest about
where the text in front of the learner came from. References that neither path
recovers are counted and reported rather than quietly dropped.

Nothing here writes: no migration, no new field, no persistence of the recovered
text. The only state is an in-memory cache, so opening the panel repeatedly
costs one lookup.
"""

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import retrieval
from .models import Chapter

# Resolved passages, keyed by chapter id. The cache is PER PROCESS: it is not
# shared between workers and it is lost on restart, which is exactly what is
# wanted from a display-time convenience. A chapter's sources never change once
# it is generated, so an entry never needs invalidating. Only successful
# resolutions are cached — a run that could not reach the index is not stored,
# so a later request retries rather than serving a permanent failure.
_PASSAGE_CACHE = {}

# How many passages to ask the index for in the semantic pass. Deliberately wide:
# a chapter's stored references came from the planner's own sweep, so the display
# query needs room to return them all before the exact lookup is needed.
SEMANTIC_K = 40

SEMANTIC = "semantic match"
EXACT = "exact lookup"


def _citation(ref, meta):
    """The printed page citation for one reference.

    The stored citation is preferred: it is the record of what the chapter was
    actually built on. The index metadata is only a fallback for an older
    reference saved before citations were stored, and the numeric PDF page is the
    last resort.
    """
    stored = (ref.get("page_citation") or "").strip()
    if stored:
        return stored
    start = (meta.get("page_label_start") or "").strip()
    end = (meta.get("page_label_end") or "").strip()
    if start and end:
        return f"p. {start}" if start == end else f"pp. {start}-{end}"
    page = ref.get("page")
    return f"p. {page}" if page is not None else ""


def _passage(ref, text, meta, recovered_by):
    """One passage as the panel needs it: the textbook prose, where to find it in
    the printed book, and how it was recovered."""
    return {
        "text": text,
        "page_citation": _citation(ref, meta),
        "page": ref.get("page"),
        "chapter": ref.get("chapter") or meta.get("chapter") or "",
        "section": ref.get("section") or meta.get("section") or "",
        "source_file": ref.get("source_file"),
        "recovered_by": recovered_by,
    }


def _semantic_index(grade, query):
    """Map (source_file, page) -> retrieved passage for one semantic sweep.

    `retrieval.retrieve` already returns [] when the index is missing, so a bare
    return of {} here means only "nothing to match against", never an error.
    """
    try:
        passages = retrieval.retrieve(grade, query, k=SEMANTIC_K)
    except Exception:
        return {}
    return {(p.get("source_file"), p.get("page")): p for p in passages if p.get("text")}


def _exact_lookup(collection, ref):
    """Recover one reference by an exact metadata match. Returns (text, meta) or
    (None, None).

    Chroma needs `$and` to combine two conditions. A page can in principle hold
    more than one chunk; the first is used, so the passage shown is stable across
    requests.
    """
    if collection is None or ref.get("source_file") is None or ref.get("page") is None:
        return None, None
    try:
        res = collection.get(where={"$and": [
            {"source_file": ref["source_file"]},
            {"page": ref["page"]},
        ]})
    except Exception:
        return None, None
    documents = res.get("documents") or []
    metadatas = res.get("metadatas") or []
    if not documents:
        return None, None
    return documents[0], (metadatas[0] if metadatas else {}) or {}


def _resolve(chapter):
    """Recover the text behind every stored reference on `chapter`.

    Returns (payload_dict, index_reachable). `index_reachable` is False only when
    the vector index could not be opened at all, which is the case that must
    degrade to an honest message instead of a 500.
    """
    refs = chapter.sources or []
    session = chapter.session

    # Open the collection once. If this fails the index is unavailable in this
    # environment; the semantic sweep will come back empty too, and the response
    # says so rather than pretending the chapter was never grounded.
    try:
        collection = retrieval.get_collection()
    except Exception:
        collection = None

    index = _semantic_index(session.grade, f"{session.topic} {chapter.title}".strip())

    passages = []
    counts = {"semantic": 0, "exact": 0}
    unrecovered = []

    for ref in refs:
        hit = index.get((ref.get("source_file"), ref.get("page")))
        if hit:
            passages.append(_passage(ref, hit["text"], hit, SEMANTIC))
            counts["semantic"] += 1
            continue
        text, meta = _exact_lookup(collection, ref)
        if text:
            passages.append(_passage(ref, text, meta, EXACT))
            counts["exact"] += 1
            continue
        unrecovered.append(ref)

    index_reachable = collection is not None or bool(index)
    return {
        "passages": passages,
        "recovery": counts,
        "recovered_count": len(passages),
        "unrecovered_count": len(unrecovered),
    }, index_reachable


@api_view(["GET"])
def provenance(request, chapter_id):
    """GET /api/chapters/<id>/provenance -> the textbook passages that grounded
    this chapter, with the printed page citation for each.

    404 for a chapter belonging to another learner: ownership is filtered in the
    same query that fetches the chapter, so another learner's chapter is
    indistinguishable from one that does not exist.
    """
    chapter = get_object_or_404(
        Chapter.objects.select_related("session"),
        pk=chapter_id,
        session__learner__user=request.user,
    )
    session = chapter.session
    refs = chapter.sources or []

    base = {
        "chapter_id": chapter.pk,
        "chapter_title": chapter.title,
        "chapter_order": chapter.order,
        "grade": session.grade,
        "topic": session.topic,
        "stored_reference_count": len(refs),
    }

    # A chapter with no stored references is a real, meaningful case: it was not
    # grounded in the textbook (mock mode, an unbuilt index at the time, or a
    # generation that fell back to canned content). Say so plainly.
    if not refs:
        return Response({
            **base,
            "grounded": False,
            "passages": [],
            "recovery": {"semantic": 0, "exact": 0},
            "recovered_count": 0,
            "unrecovered_count": 0,
            "message": (
                "This chapter was not built from the textbook, so there are no "
                "passages to show."
            ),
        })

    cached = _PASSAGE_CACHE.get(chapter.pk)
    if cached is None:
        resolved, index_reachable = _resolve(chapter)
        if index_reachable:
            _PASSAGE_CACHE[chapter.pk] = resolved
        cached = resolved
        if not index_reachable:
            return Response({
                **base,
                "grounded": True,
                "passages": [],
                "recovery": {"semantic": 0, "exact": 0},
                "recovered_count": 0,
                "unrecovered_count": len(refs),
                "message": (
                    "This chapter was built from the Grade "
                    f"{session.grade} textbook, but the passages could not be "
                    "recovered on this server. The page references below the "
                    "chapter still show where to find them in the book."
                ),
            })

    message = ""
    if cached["unrecovered_count"]:
        message = (
            f"{cached['unrecovered_count']} of {len(refs)} textbook references "
            "could not be recovered, so their passages are not shown."
        )

    return Response({**base, "grounded": True, "message": message, **cached})
