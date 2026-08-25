"""Retrieval side of the RAG layer.

At request time we ask the Chroma vector store for the textbook chunks most
relevant to the student's grade + topic. This is the *read* side; the *write*
side (ingestion) is the `build_index` management command.

Chroma is imported lazily inside the functions so that mock mode never needs it.
"""

from django.conf import settings

# Where the persistent index lives, and the collection name. The build_index
# command writes here; retrieve() reads from here. Kept in one place so both
# sides agree.
CHROMA_DIR = settings.BASE_DIR / "chroma_store"
COLLECTION_NAME = "textbooks"

# --- Relevance thresholds (Chroma's default distance is L2 — smaller = closer) ---
# Two SEPARATE jobs, so one cap can't break the other:
#   * GATE_MAX_DISTANCE — is the topic in this grade's book AT ALL? If even the BEST
#     hit is further than this, refuse (don't build a story from unrelated chunks).
#   * the keep window — once a topic IS covered, which of its chunks count as "this
#     topic's content". How many are kept drives how rich/long the story is.
# Tuned against the real books; in-syllabus best hits sit ~0.7-1.05, off-syllabus ~1.4+.
GATE_MAX_DISTANCE = 1.15        # best hit must be at least this close, or the topic is "not covered"
RELEVANCE_REL_MARGIN = 0.65    # then keep hits within +65% of the best hit's distance
RELEVANCE_MAX_DISTANCE = 1.45  # ...and never keep a hit further than this (absolute ceiling)


def get_client():
    """Return a persistent Chroma client (imported lazily)."""
    import chromadb  # local import: mock mode shouldn't require chromadb at all
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_collection():
    """Return the existing textbook collection (raises if the index isn't built)."""
    return get_client().get_collection(COLLECTION_NAME)


def retrieve(grade, query, k=4):
    """Return up to `k` textbook chunks for `grade` most relevant to `query`.

    Each item: {text, page, chapter, section, source_file, distance}. `distance` is
    Chroma's L2 distance (smaller = more relevant). Returns [] if the index hasn't
    been built or nothing matches, so the caller can fall back to plain generation.
    """
    if not query:
        return []
    try:
        collection = get_collection()
    except Exception:
        # Index not built yet (or Chroma unavailable) — let the caller fall back.
        return []

    result = collection.query(
        query_texts=[query],
        n_results=k,
        where={"grade": int(grade)},  # only this grade's textbook chunks
    )

    # Chroma returns parallel lists nested one level deep (one per query).
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    passages = []
    for i, (text, meta) in enumerate(zip(documents, metadatas)):
        meta = meta or {}
        passages.append({
            "text": text,
            "page": meta.get("page"),
            "chapter": meta.get("chapter"),
            "section": meta.get("section"),
            "page_label_start": meta.get("page_label_start"),
            "page_label_end": meta.get("page_label_end"),
            "source_type": meta.get("source_type"),
            "ocr_agreement": meta.get("ocr_agreement"),
            "source_file": meta.get("source_file"),
            "distance": distances[i] if i < len(distances) else None,
        })
    return passages


def gather_topic_content(grade, topic, max_k=40):
    """Measure how much of the grade's textbook actually covers `topic`.

    1. GATE: if the closest hit is further than GATE_MAX_DISTANCE, the topic isn't
       really in this grade's book -> return nothing so the caller refuses.
    2. KEEP: otherwise keep the passages close to the best hit (relative margin) and
       below the absolute ceiling. How many are kept is what makes a story rich/thin.

    Returns {"passages": [...relevant passages, ordered by relevance...],
             "sections": [{section, passages}, ...],   # grouped, for reference/debug
             "total_relevant": int}. Empty `passages` => the topic isn't covered.
    """
    passages = retrieve(grade, topic, k=max_k)
    scored = [p for p in passages if p.get("distance") is not None]
    if not scored:
        return {"passages": [], "sections": [], "total_relevant": 0}

    best = min(p["distance"] for p in scored)
    if best > GATE_MAX_DISTANCE:
        # Even the closest chunk is far away -> topic not covered (syllabus gate).
        return {"passages": [], "sections": [], "total_relevant": 0}

    kept = [
        p for p in scored
        if p["distance"] <= best * (1 + RELEVANCE_REL_MARGIN)
        and p["distance"] <= RELEVANCE_MAX_DISTANCE
    ]

    # Group by section (for reference/debugging), preserving first-seen order.
    groups = []
    by_key = {}
    for p in kept:
        key = p.get("section") or p.get("chapter") or f"p.{p.get('page')}"
        if key not in by_key:
            by_key[key] = {"section": key, "passages": []}
            groups.append(by_key[key])
        by_key[key]["passages"].append(p)

    return {"passages": kept, "sections": groups, "total_relevant": len(kept)}
