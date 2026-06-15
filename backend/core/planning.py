"""Session planning (Phase B): turn "how much textbook content exists for this
topic" into a per-session plan — how many chapters, and each chapter's paragraph
and question ranges — so thin topics yield short stories and rich topics longer ones.

The chapter COUNT scales with how much relevant content there is (not with how the
textbook's section labels happened to come out — those are unreliable, often
"(document)"), and each chapter is grounded in a successive slice of that content.
Reads measured content from retrieval.gather_topic_content(); the generator then
decides exact paragraph/question counts within each chapter's ranges.
"""

import math
from collections import Counter

from . import adaptation
from .retrieval import gather_topic_content

# Richness (from how many relevant passages exist) -> per-chapter ranges.
RICHNESS_RANGES = {
    "thin":     {"min_p": 2, "max_p": 3, "min_q": 0, "max_q": 1},
    "moderate": {"min_p": 3, "max_p": 4, "min_q": 1, "max_q": 2},
    "rich":     {"min_p": 4, "max_p": 6, "min_q": 2, "max_q": 3},
}

# Roughly how many relevant passages ground one chapter — sets how fast the chapter
# count grows with content (e.g. ~14 relevant passages -> 5 chapters).
PASSAGES_PER_CHAPTER = 3


def richness_for(total_relevant):
    """Map the count of relevant passages to a richness level."""
    if total_relevant <= 2:
        return "thin"
    if total_relevant <= 6:
        return "moderate"
    return "rich"


def _split_evenly(items, n):
    """Split `items` into `n` contiguous, near-equal, non-empty slices."""
    n = max(1, min(n, len(items)))
    base, extra = divmod(len(items), n)
    slices, i = [], 0
    for j in range(n):
        size = base + (1 if j < extra else 0)
        slices.append(items[i:i + size])
        i += size
    return slices


def _section_label(passages):
    """Most common section/chapter label across a slice — used for the chapter's
    'Based on:' source line."""
    labels = [p.get("section") or p.get("chapter") or f"p.{p.get('page')}" for p in passages]
    return Counter(labels).most_common(1)[0][0] if labels else ""


def plan_session(grade, topic):
    """Build the per-session plan for a (grade, topic) from real textbook content.

    Returns an ordered list of chapter groups:
        [{section, passages, min_p, max_p, min_q, max_q, level}, ...]
    or [] when the topic isn't covered (caller refuses via the syllabus gate).
    """
    content = gather_topic_content(grade, topic)
    kept = content["passages"]
    total = content["total_relevant"]
    if not kept:
        return []

    level = richness_for(total)
    ranges = RICHNESS_RANGES[level]

    # Chapter count scales with HOW MUCH relevant content there is, clamped [MIN, CAP].
    n_chapters = max(
        adaptation.MIN_CHAPTERS,
        min(math.ceil(total / PASSAGES_PER_CHAPTER), adaptation.MAX_CHAPTERS_CAP),
    )

    # Order by textbook page so the story moves through the material in order, then
    # split into contiguous slices — each chapter gets its own grounding passages.
    ordered = sorted(kept, key=lambda p: ((p.get("page") or 0), p.get("distance") or 0.0))
    plan = [
        {
            "section": _section_label(sl),
            "passages": sl,
            "min_p": ranges["min_p"], "max_p": ranges["max_p"],
            "min_q": ranges["min_q"], "max_q": ranges["max_q"],
            "level": level,
        }
        for sl in _split_evenly(ordered, n_chapters)
    ]

    # Floor: guarantee at least one question across the whole session (so adaptation
    # and mastery always get signal) by forcing the FINAL chapter to carry one.
    plan[-1]["min_q"] = max(plan[-1]["min_q"], 1)
    plan[-1]["max_q"] = max(plan[-1]["max_q"], plan[-1]["min_q"])
    return plan


def mock_plan():
    """A fixed small plan for mock mode (no retrieval / content-scaling)."""
    return [
        {"section": "Mock A", "passages": [], "min_p": 3, "max_p": 4, "min_q": 1, "max_q": 2, "level": "moderate"},
        {"section": "Mock B", "passages": [], "min_p": 3, "max_p": 4, "min_q": 1, "max_q": 2, "level": "moderate"},
    ]
