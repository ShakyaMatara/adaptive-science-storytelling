"""Disclosure of chapters that fell back to canned content.

When the model's reply fails schema validation twice, `llm.generate_chapter`
returns a canned chapter instead of raising. That is deliberate — a learner is
never left staring at an error — and it stays. What was missing is that the
learner was told nothing: the chapter simply arrived with generic content, no
textbook page references, and no way to ask for another attempt. The evaluation
programme measured this at 2.8% of chapters.

The detection lives here rather than in the generator, which is unchanged. The
deterministic signal is a chapter with no attached sources: every chapter that
came from the textbook carries page references, and only the canned fallback
carries none.

ONE IMPORTANT QUALIFICATION. In mock mode every chapter is created with no
sources by design — retrieval does not run at all — so "no sources" means
"fallback" only when the system is generating for real. Every check below is
therefore guarded by `llm_config.use_mock()`, without which the notice would
appear on every chapter of every offline demonstration and throughout the test
suite.
"""

from django.db import DatabaseError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response

from . import llm_config, personalization
from .llm import LLMError, generate_chapter
from .models import Chapter, GenerationEvent, Question, Session
from .serializers import PresentedChapterSerializer
from .throttles import StoryGenDailyThrottle, StoryGenThrottle


# --- Detection ------------------------------------------------------------------

def chapter_used_fallback(chapter):
    """True when this chapter is the canned fallback rather than a generated one.

    False in mock mode regardless of sources: canned content is the *expected*
    output there, not a failure worth reporting.
    """
    if llm_config.use_mock():
        return False
    return not (chapter.sources or [])


def record_fallback_if_needed(session, chapter):
    """Record that a chapter fell back, once and only once.

    Called from the view layer immediately after a chapter is persisted. It must
    never disturb the request it is called from: a learner receiving a chapter
    should not see an error because the bookkeeping around it failed, so every
    database problem is swallowed. Returns the event when one was created,
    otherwise None.
    """
    try:
        if not chapter_used_fallback(chapter):
            return None
        event, created = GenerationEvent.objects.get_or_create(
            chapter=chapter,
            kind=GenerationEvent.FALLBACK_SERVED,
            defaults={
                "session": session,
                "detail": f"Chapter {chapter.order} of \"{session.topic}\" was served from "
                          f"standby material; no textbook passages were attached.",
            },
        )
        return event if created else None
    except DatabaseError:
        return None


def _retry_is_possible(chapter):
    """Whether a retry would be accepted for this chapter, and why not if it wouldn't.

    Returns (bool, reason). Kept next to the endpoint that enforces the same
    conditions so the two cannot drift apart.
    """
    if not chapter_used_fallback(chapter):
        return False, "This chapter was written from the textbook, so there is nothing to retry."
    if chapter.session.is_complete:
        return False, "This story has already finished."
    if chapter.questions.filter(user_answer_index__isnull=False).exists():
        return False, "You have already answered a question in this chapter."
    return True, ""


# --- Endpoints ------------------------------------------------------------------

@api_view(["GET"])
def generation_status(request, chapter_id):
    """GET /api/chapters/<id>/generation-status

    Read-only. Tells the reader whether this chapter came from the textbook or
    from standby material, and whether another attempt can be made.
    """
    chapter = get_object_or_404(
        Chapter, pk=chapter_id, session__learner__user=request.user
    )
    used_fallback = chapter_used_fallback(chapter)
    can_retry, reason = _retry_is_possible(chapter)
    return Response({
        "chapter_id": chapter.id,
        "session_id": chapter.session_id,
        "used_fallback": used_fallback,
        "source_count": len(chapter.sources or []),
        "recorded": GenerationEvent.objects.filter(
            chapter=chapter, kind=GenerationEvent.FALLBACK_SERVED).exists(),
        "can_retry": can_retry,
        "retry_blocked_reason": reason,
    })


@api_view(["POST"])
@throttle_classes([StoryGenThrottle, StoryGenDailyThrottle])  # paid call, like any generation
def retry_chapter(request, session_id, chapter_id):
    """POST /api/sessions/<id>/chapters/<id>/retry

    Ask for one more attempt at a chapter that fell back. This calls the ordinary
    generation path with the arguments the original call used; it does not change
    how generation works.

    It rewrites only the chapter's own content — title, paragraphs, summary,
    sources and questions. Points, difficulty, the streak, the chapter count, the
    session plan, the chapter's position and the difficulty it was written at are
    all left exactly as they were, and concept mastery is untouched. A chapter
    with any answered question is refused outright, so no recorded answer can be
    discarded.
    """
    # Imported here rather than at module scope: views.py calls
    # record_fallback_if_needed above, so a module-level import either way round
    # would be circular.
    from . import views

    session = get_object_or_404(Session, pk=session_id, learner__user=request.user)
    chapter = get_object_or_404(Chapter, pk=chapter_id, session=session)

    allowed, reason = _retry_is_possible(chapter)
    if not allowed:
        return Response({"error": reason}, status=status.HTTP_400_BAD_REQUEST)

    # Rebuild the arguments the original generation used. The difficulty is the
    # one the chapter was WRITTEN at, not the session's current difficulty: this
    # replaces a chapter in place, so it must stay consistent with the
    # `difficulty_at_time` already stored on it.
    previous = session.chapters.filter(order=chapter.order - 1).first()
    group = None
    plan = session.plan or []
    if 0 <= chapter.order - 1 < len(plan):
        group = plan[chapter.order - 1]

    try:
        data = generate_chapter(
            session.topic,
            session.grade,
            chapter.difficulty_at_time,
            setting=session.setting or None,
            story_so_far=previous.summary if previous else None,
            revisit_concepts=personalization.weak_concepts(session.learner, session.topic),
            **views._chapter_kwargs(group),
        )
    except LLMError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    # Still no textbook passages: the second attempt fell back as well. Keep the
    # chapter the learner already has rather than swapping one canned chapter for
    # another, and say so plainly.
    if not (data.get("sources") or []):
        GenerationEvent.objects.create(
            session=session, chapter=chapter, kind=GenerationEvent.RETRY_FAILED,
            detail=f"Retry of chapter {chapter.order} fell back again; the original was kept.",
        )
        return Response({
            "retried": True,
            "succeeded": False,
            "message": "That attempt did not work either, so your chapter has been left as it "
                       "is. You can carry on reading — the science in it is still correct.",
            "chapter": PresentedChapterSerializer(chapter).data,
            "sources": [],
        })

    # Replace the chapter's content in place. Nothing outside the chapter and its
    # questions is written.
    chapter.title = data["title"]
    chapter.paragraphs = data["paragraphs"]
    chapter.summary = data.get("summary", "")
    chapter.sources = data.get("sources") or []
    chapter.save(update_fields=["title", "paragraphs", "summary", "sources"])

    chapter.questions.all().delete()
    for i, q in enumerate(data["questions"], start=1):
        Question.objects.create(
            chapter=chapter,
            order=i,
            question_text=q["question"],
            options=q["options"],
            correct_index=q["correct_index"],
            hint=q.get("hint", ""),
            concept=q.get("concept", ""),
        )

    GenerationEvent.objects.create(
        session=session, chapter=chapter, kind=GenerationEvent.RETRY_SUCCEEDED,
        detail=f"Retry of chapter {chapter.order} produced a textbook-grounded chapter.",
    )

    chapter.refresh_from_db()
    return Response({
        "retried": True,
        "succeeded": True,
        "message": "Here is your chapter, rewritten from the textbook.",
        "chapter": PresentedChapterSerializer(chapter).data,
        "sources": chapter.sources,
        "chapter_complete": chapter.questions.count() == 0,
    })
