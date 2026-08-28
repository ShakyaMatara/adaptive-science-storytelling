"""GET /api/me/progress — the learner's whole progress picture (FR-17).

This started life as a small view in views.py that returned concept mastery
grouped by topic. That response is preserved here byte-for-byte under the
`progress` key — same query ordering, same rounding, same field names — because
several things already read it and the existing test asserts on it. Everything
this module adds is a NEW key alongside it, so the extension cannot have changed
what was there before.

What is added:
  * `summary`  — headline counters across every session the learner has run;
  * `topics`   — the same per-concept mastery, but enriched: each topic carries
                 its own aggregate mastery, the grade(s) it was studied at, the
                 chapter to open to see the textbook behind it, and each concept
                 carries when it was last seen;
  * `strongest` / `weakest` — the concepts worth celebrating and the concepts
                 worth revising, each carrying the grade to revise them at;
  * `definitions` — the rules used to pick those two lists, returned with the
                 data so a reader never has to guess what "weakest" means.

Read-only: this module runs queries and nothing else. It does not create the
Learner profile if one is missing (an account with no profile simply has no
progress yet), so a GET can never write a row.
"""

from django.db.models import Count, Q
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .api_curriculum import place_sources
from .models import Badge, Chapter, Learner, Question

# How many concepts each of the two highlight lists may contain.
HIGHLIGHT_LIMIT = 5

# Returned to the client verbatim so the panel can explain itself, and so the
# definition lives next to the numbers rather than only in a document.
DEFINITIONS = {
    "strongest": (
        "Concepts with at least one attempt and at least one correct answer, "
        "ranked by highest mastery first and then by the most attempts, so a "
        "concept proved right repeatedly outranks one answered right once."
    ),
    "weakest": (
        "Concepts with at least one attempt that have been answered wrongly at "
        "least once, ranked by lowest mastery first and then by the most "
        "attempts. A concept answered correctly every time is never weak, no "
        "matter how few attempts it has."
    ),
    "topic_mastery": "A topic's correct answers divided by its attempts, across every session.",
    "accuracy": "Questions answered correctly divided by questions attempted.",
    "revision_grade": "The grade of the learner's most recent session on that topic.",
}


def _iso(value):
    """Timestamp as an ISO-8601 string, or None. Kept in one place so every
    timestamp in the response is formatted the same way."""
    return value.isoformat() if value else None


def _session_facts(learner):
    """One pass over the learner's sessions, returning what the rest of the view
    needs from them: the grades each topic was studied at, the grade to revise
    each topic at, and the session-level counters.

    Sessions are read newest-first, so the FIRST one seen for a topic is the most
    recent — that is the grade a revision link should use.
    """
    grades_by_topic = {}
    revision_grade = {}
    total_points = 0
    completed = 0
    in_progress = 0

    for session in learner.sessions.all().order_by("-created_at", "-id"):
        topic = session.topic
        revision_grade.setdefault(topic, session.grade)
        grades_by_topic.setdefault(topic, set()).add(session.grade)
        total_points += session.points or 0
        if session.is_complete:
            completed += 1
        else:
            in_progress += 1

    return {
        "grades_by_topic": {t: sorted(g) for t, g in grades_by_topic.items()},
        "syllabus_placement":
            "Where a topic sits in the printed syllabus, found by looking the "
            "pages its story was grounded on up in the textbook contents pages. "
            "Voted by chapter first, then by sub-section within it; `matched` of "
            "`total` says how many of the stored references agreed.",
        "revision_grade": revision_grade,
        "total_points": total_points,
        "stories_completed": completed,
        "stories_in_progress": in_progress,
        "topics_studied": len(grades_by_topic),
    }


def _chapter_facts(learner):
    """One pass over the learner's chapters: how many there are, and which chapter
    to open when they ask to see the textbook behind a topic.

    Chapters are read newest-first. A chapter that carries stored textbook
    references is always preferred, because that is the one with passages to
    show; a topic whose chapters were never grounded still gets an entry, flagged
    as ungrounded so the panel can say so plainly instead of showing nothing.
    """
    chapters_read = 0
    by_topic = {}
    sources_by_topic = {}   # every stored reference for a topic, for placing it

    # `paragraphs` and `summary` hold the whole story text and nothing here reads
    # them, so they are deferred: this loop only needs the citation refs and the
    # session's topic and grade.
    for chapter in (Chapter.objects
                    .filter(session__learner=learner)
                    .select_related("session")
                    .defer("paragraphs", "summary")
                    .order_by("-created_at", "-id")):
        chapters_read += 1
        topic = chapter.session.topic
        grounded = bool(chapter.sources)
        sources_by_topic.setdefault(topic, []).extend(chapter.sources or [])
        current = by_topic.get(topic)
        if current is None or (grounded and not current["grounded"]):
            by_topic[topic] = {
                "chapter_id": chapter.pk,
                "title": chapter.title,
                "grade": chapter.session.grade,
                "grounded": grounded,
            }

    # Where each topic sits in the printed syllabus. A learner types a topic
    # freely — "Light emitting diode" is nobody's chapter heading — but the pages
    # the story was grounded on belong to a numbered section, so the placement is
    # a lookup against the contents pages rather than a guess about the wording.
    syllabus_by_topic = {
        topic: place_sources(refs) for topic, refs in sources_by_topic.items()
    }

    return {"chapters_read": chapters_read, "source_chapter_by_topic": by_topic,
            "syllabus_by_topic": syllabus_by_topic}


def _highlights(stats, revision_grade):
    """Split the concept stats into the strongest and the weakest few.

    `stats` is a list of already-serialised concept dicts each carrying its topic.
    Both lists require at least one attempt. The weakest list additionally
    excludes anything with perfect mastery — a concept answered correctly every
    time is not a weakness even when it has only been seen once — and the
    strongest list requires at least one correct answer, so a concept never yet
    answered right cannot be presented as a strength.

    Ties are broken by attempts (more attempts = stronger evidence) and then by
    topic and concept name, so the ordering is deterministic for a given dataset.
    """
    attempted = [s for s in stats if s["attempts"] > 0]

    strongest = sorted(
        (s for s in attempted if s["correct"] > 0),
        key=lambda s: (-s["mastery"], -s["attempts"], s["topic"], s["concept"]),
    )[:HIGHLIGHT_LIMIT]

    weakest = sorted(
        (s for s in attempted if s["mastery"] < 1.0),
        key=lambda s: (s["mastery"], -s["attempts"], s["topic"], s["concept"]),
    )[:HIGHLIGHT_LIMIT]

    def shape(s):
        return {
            "topic": s["topic"],
            "concept": s["concept"],
            "attempts": s["attempts"],
            "correct": s["correct"],
            "mastery": s["mastery"],
            "grade": revision_grade.get(s["topic"]),
        }

    return [shape(s) for s in strongest], [shape(s) for s in weakest]


def _empty_payload():
    """The response for an account with no learner profile yet. Deliberately the
    same shape as a real one — the page renders its empty state from the numbers,
    not from a missing key."""
    return {
        "progress": [],
        "summary": {
            "topics_studied": 0,
            "chapters_read": 0,
            "questions_attempted": 0,
            "questions_correct": 0,
            "accuracy": 0.0,
            "total_points": 0,
            "badges_earned": 0,
            "stories_completed": 0,
            "stories_in_progress": 0,
        },
        "topics": [],
        "strongest": [],
        "weakest": [],
        "definitions": DEFINITIONS,
    }


@api_view(["GET"])
def me_progress(request):
    """GET /api/me/progress -> concept mastery, headline counters, and the
    concepts worth celebrating or revising.

    The `progress` key is the original response and is unchanged.
    """
    learner = Learner.objects.filter(user=request.user).first()
    if learner is None:
        return Response(_empty_payload())

    # --- The original response, unchanged ------------------------------------
    # Same ordering and same rounding as the view this replaced; `by_topic` is
    # also reused below so the enriched view cannot drift from this one.
    by_topic = {}
    stats_by_topic = {}
    for s in learner.concept_stats.all().order_by("topic", "concept"):
        by_topic.setdefault(s.topic, []).append({
            "concept": s.concept,
            "attempts": s.attempts,
            "correct": s.correct,
            "mastery": round(s.mastery, 2),
        })
        stats_by_topic.setdefault(s.topic, []).append(s)
    progress = [{"topic": topic, "concepts": concepts} for topic, concepts in by_topic.items()]

    # --- Everything below is new ---------------------------------------------
    facts = _session_facts(learner)
    chapter_facts = _chapter_facts(learner)

    answered = Question.objects.filter(
        chapter__session__learner=learner, user_answer_index__isnull=False
    )
    # One pass rather than two counts over the same three-table join.
    tally = answered.aggregate(
        attempted=Count("id"), correct=Count("id", filter=Q(is_correct=True)))
    questions_attempted = tally["attempted"]
    questions_correct = tally["correct"]

    summary = {
        "topics_studied": facts["topics_studied"],
        "chapters_read": chapter_facts["chapters_read"],
        "questions_attempted": questions_attempted,
        "questions_correct": questions_correct,
        "accuracy": round(questions_correct / questions_attempted, 2) if questions_attempted else 0.0,
        "total_points": facts["total_points"],
        "badges_earned": Badge.objects.filter(session__learner=learner).count(),
        "stories_completed": facts["stories_completed"],
        "stories_in_progress": facts["stories_in_progress"],
    }

    topics = []
    flat = []  # every concept, with its topic, for the highlight lists
    for topic, concepts in by_topic.items():
        raw = stats_by_topic[topic]
        attempts = sum(c["attempts"] for c in concepts)
        correct = sum(c["correct"] for c in concepts)
        enriched = [
            dict(c, last_seen=_iso(stat.last_seen))
            for c, stat in zip(concepts, raw)
        ]
        topics.append({
            "topic": topic,
            "mastery": round(correct / attempts, 2) if attempts else 0.0,
            "attempts": attempts,
            "correct": correct,
            "concept_count": len(concepts),
            "grades": facts["grades_by_topic"].get(topic, []),
            "grade": facts["revision_grade"].get(topic),
            # The chapter to open to see the textbook passages behind this topic.
            "source_chapter": chapter_facts["source_chapter_by_topic"].get(topic),
            # Where the topic sits in the printed syllabus; null when the story
            # was not textbook-grounded, or its citations could not be resolved.
            "syllabus": chapter_facts["syllabus_by_topic"].get(topic),
            "concepts": enriched,
        })
        flat.extend(dict(c, topic=topic) for c in concepts)

    strongest, weakest = _highlights(flat, facts["revision_grade"])

    return Response({
        "progress": progress,
        "summary": summary,
        "topics": topics,
        "strongest": strongest,
        "weakest": weakest,
        "definitions": DEFINITIONS,
    })
