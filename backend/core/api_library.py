"""My Stories: every story this learner has started, summarised for the library.

One row per session, carrying enough to draw a card without a second request —
how far through the story the learner is, how they scored, what they earned, and
when they last worked on it — with the newest activity first.

Read-only throughout: nothing here writes to the database.
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Learner, Session


def _learner_for(user):
    """Return (creating if needed) the Learner profile for a Django user.

    Deliberately the same shape as the helper in views.py rather than an import
    of it, so this module stands on its own.
    """
    learner, _ = Learner.objects.get_or_create(user=user, defaults={"name": user.username})
    return learner


def _chapter_is_complete(chapter):
    """A chapter counts as complete once every one of its questions is answered.

    A chapter that carries no questions at all counts as complete: there is
    nothing left in it for the learner to do.
    """
    return all(q.user_answer_index is not None for q in chapter.questions.all())


def _summarise(session):
    """Collapse one session and its prefetched chapters/questions into a card."""
    chapters = list(session.chapters.all())

    chapters_completed = 0
    question_count = 0
    questions_answered = 0
    correct_count = 0
    # The newest timestamp anywhere in the story, falling back to when it started.
    last_activity = session.created_at

    for chapter in chapters:
        if chapter.created_at > last_activity:
            last_activity = chapter.created_at
        if _chapter_is_complete(chapter):
            chapters_completed += 1
        for question in chapter.questions.all():
            question_count += 1
            if question.created_at > last_activity:
                last_activity = question.created_at
            if question.user_answer_index is not None:
                questions_answered += 1
                if question.is_correct:
                    correct_count += 1

    return {
        "id": session.pk,
        "topic": session.topic,
        "grade": session.grade,
        # Chapters actually generated so far, and how many are fully answered.
        "chapter_count": len(chapters),
        "chapters_completed": chapters_completed,
        # How many chapters the content plan intends the story to run to. 0 when
        # the story predates planning or was never planned; the page then falls
        # back to the generated count.
        "planned_chapters": len(session.plan or []),
        "content_level": session.content_level or "",
        "question_count": question_count,
        "questions_answered": questions_answered,
        "correct_count": correct_count,
        "points": session.points,
        "badges": [badge.name for badge in session.badges.all()],
        "is_complete": session.is_complete,
        "created_at": session.created_at,
        "last_activity": last_activity,
    }


@api_view(["GET"])
def library(request, *args, **kwargs):
    """GET /api/me/library — this learner's own stories, newest activity first.

    Ownership is enforced by filtering on the signed-in user, exactly as the rest
    of the API does; a learner can never see another learner's stories.
    """
    learner = _learner_for(request.user)

    # One query for the sessions and one each for the chapters, questions and
    # badges — the per-story counting below then touches no database at all.
    sessions = (
        Session.objects.filter(learner=learner, learner__user=request.user)
        .prefetch_related("chapters__questions", "badges")
    )

    stories = [_summarise(session) for session in sessions]
    # `last_activity` is derived per story rather than stored, so the ordering has
    # to happen here rather than in the query.
    stories.sort(key=lambda s: s["last_activity"], reverse=True)

    return Response({
        "stories": stories,
        "count": len(stories),
        "in_progress": sum(1 for s in stories if not s["is_complete"]),
        "completed": sum(1 for s in stories if s["is_complete"]),
    })
