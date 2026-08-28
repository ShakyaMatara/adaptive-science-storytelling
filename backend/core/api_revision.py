"""Revision mode (read-only): which concepts is this learner weakest at?

This endpoint is a *selector*, not a generator. It answers one question — "what
should I revise?" — by reading the ConceptStat rows that the answer-submission
endpoint already maintains, and it writes nothing at all: no points, no
difficulty, no streak, no ConceptStat. Every query below is a plain SELECT.

Revising a topic then goes through the ordinary story flow. That is deliberate
rather than a shortcut: POST /api/sessions already calls
`personalization.weak_concepts(learner, topic)` and passes the result to the
generator as `revisit_concepts`, so a story started on a topic the learner is
weak at IS a targeted revision story. Adding a second, parallel generation path
would duplicate the adaptation and syllabus-gating rules with no benefit.

Definition of "weak" is the same one the generator uses
(`personalization.weak_concepts`): a concept attempted at least once AND missed
at least once, ranked by lowest mastery, then by most attempts. The difference is
scope — that function is per topic and capped at 3 because it fills a prompt;
this view spans every topic the learner has touched and is uncapped, because it
fills a page.
"""


from rest_framework.decorators import api_view
from rest_framework.response import Response

from django.db.models import Exists, OuterRef

from . import personalization
from .models import Chapter, Learner


def _learner_for(user):
    """The Learner profile for a signed-in user, or None.

    Deliberately a lookup and not a `get_or_create`: this endpoint is read-only,
    and an account with no profile yet has no learning history either, so the
    correct answer for it is an empty revision list — not a new database row.
    """
    return Learner.objects.filter(user=user).first()


def _topic_key(topic):
    """Match topics the way the rest of the app does — case-insensitively.

    `create_session` resumes an unfinished story with `topic__iexact`, so
    "Magnets" and "magnets" are one topic there and must be one topic here too.
    """
    return (topic or "").strip().lower()


def _session_index(learner):
    """One pass over the learner's sessions -> per topic key:

        {"grade": <grade of the most recent session on the topic>,
         "topic": <that session's spelling of the topic>,
         "unfinished": <Session that create_session would resume, or None>}

    Recovering the grade this way is necessary because ConceptStat has no grade
    column: mastery is tracked per (learner, topic, concept) across every grade
    the learner has studied it at. The most recent session is the best available
    evidence of the grade the learner is working at now.
    """
    index = {}
    # Newest first, so the first session seen for a topic is the most recent one.
    # `has_chapters` is annotated rather than tested per session: the resume rule
    # needs it for every candidate, and a query inside the loop would grow with
    # how many stories the learner has.
    sessions = (
        learner.sessions
        .annotate(has_chapters=Exists(Chapter.objects.filter(session=OuterRef("pk"))))
        .order_by("-created_at", "-id")
    )
    for session in sessions:
        key = _topic_key(session.topic)
        entry = index.setdefault(key, {"grade": None, "topic": session.topic, "unfinished": None})
        if entry["grade"] is None:
            entry["grade"] = session.grade
            entry["topic"] = session.topic  # display the most recent spelling
        # Mirror create_session's resume rule exactly: same topic (case-insensitive),
        # same grade, not complete, and it must already have a chapter — an
        # unfinished session with no chapters is NOT resumed, a new one is started.
        if (
            entry["unfinished"] is None
            and not session.is_complete
            and session.grade == entry["grade"]
            and session.has_chapters
        ):
            entry["unfinished"] = session
    return index


@api_view(["GET"])
def weak_concepts(request):
    """GET /api/me/weak-concepts

    Read-only. Returns the learner's weakest concepts across every topic, plus the
    same concepts grouped by topic so the page can offer "revise this topic".

    A learner with nothing weak — everything correct, or nothing attempted yet —
    gets empty lists and a 200. That is not an error state; it is a good result.
    """
    learner = _learner_for(request.user)
    if learner is None:
        return Response({"count": 0, "concepts": [], "topics": [],
                         "revisit_per_story": personalization.REVISIT_LIMIT})

    sessions = _session_index(learner)

    stats = list(learner.concept_stats.filter(attempts__gte=1))
    # Same ordering rule as personalization.weak_concepts: weakest first, and
    # among equally weak concepts the most practised (so best evidenced) first.
    stats.sort(key=lambda s: (s.mastery, -s.attempts))

    concepts = []
    # Topic aggregates are computed over EVERY attempted concept in the topic, not
    # only the weak ones, so "topic mastery" answers "how am I doing on this topic".
    totals = {}
    for stat in stats:
        key = _topic_key(stat.topic)
        session_info = sessions.get(key, {})
        bucket = totals.setdefault(key, {
            "topic": session_info.get("topic") or stat.topic,
            "grade": session_info.get("grade"),
            "attempts": 0,
            "correct": 0,
            "concepts_tracked": 0,
            "weak": [],
            "unfinished": session_info.get("unfinished"),
        })
        bucket["attempts"] += stat.attempts
        bucket["correct"] += stat.correct
        bucket["concepts_tracked"] += 1

        if stat.correct >= stat.attempts:
            continue  # never missed it — not weak

        row = {
            "topic": bucket["topic"],
            "concept": stat.concept,
            "attempts": stat.attempts,
            "correct": stat.correct,
            "mastery": round(stat.mastery, 2),
            "last_seen": stat.last_seen.isoformat(),
            # The grade to revise at; null only if every session on the topic has
            # been deleted, in which case the page must ask for a grade instead.
            "grade": bucket["grade"],
        }
        concepts.append(row)
        bucket["weak"].append(row)

    topics = []
    for bucket in totals.values():
        if not bucket["weak"]:
            continue  # nothing weak in this topic — nothing to offer revision on
        unfinished = bucket["unfinished"]
        topics.append({
            "topic": bucket["topic"],
            "grade": bucket["grade"],
            "weak_count": len(bucket["weak"]),
            "concepts_tracked": bucket["concepts_tracked"],
            "attempts": bucket["attempts"],
            "correct": bucket["correct"],
            "mastery": round(bucket["correct"] / bucket["attempts"], 2) if bucket["attempts"] else 0.0,
            # True when starting revision on this topic would CONTINUE the story the
            # learner already has open rather than begin a new one. The request the
            # page sends is identical either way; this only lets the copy be honest.
            "has_unfinished_session": unfinished is not None,
            "unfinished_session_id": unfinished.id if unfinished else None,
            "concepts": bucket["weak"],
        })
    # Weakest topic first; ties broken by the topic with more weak concepts in it.
    topics.sort(key=lambda t: (t["mastery"], -t["weak_count"]))

    return Response({
        "count": len(concepts),
        "concepts": concepts,
        "topics": topics,
        # How many concepts the generator will be asked to revisit per story, so
        # the page can say so plainly instead of implying every weak concept is
        # covered at once.
        "revisit_per_story": personalization.REVISIT_LIMIT,
    })
