"""API endpoints (the orchestration layer).

Auth (register/login/me) + the story loop. A session is a continuous, multi-chapter
story: create a session (first chapter), answer each chapter's questions, then ask
for the next chapter (which is where difficulty adapts and badges are awarded).
"""

import difflib
import re

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from . import adaptation, gamification, llm_config, personalization, planning
from .constants import TOPICS
from .llm import LLMError, answer_question, generate_chapter
from .models import Chapter, Learner, Question, Session
from .serializers import PresentedChapterSerializer, SessionSerializer
from .throttles import (
    AskDailyThrottle,
    AskThrottle,
    AuthThrottle,
    StoryGenDailyThrottle,
    StoryGenThrottle,
)


# --- Helpers --------------------------------------------------------------------

def _persist_chapter(session, data):
    """Create a Chapter (+ its Questions) from generated content and advance the
    session's chapter counter. `data` is the dict from generate_chapter."""
    session.chapter_count += 1
    chapter = Chapter.objects.create(
        session=session,
        order=session.chapter_count,
        title=data["title"],
        paragraphs=data["paragraphs"],
        summary=data.get("summary", ""),
        difficulty_at_time=session.difficulty,
        sources=data.get("sources") or [],
    )
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
    session.save()
    return chapter


def _question_feedback(question, is_correct, points_awarded):
    """Human-friendly message after answering one question."""
    if is_correct:
        return f"Correct! You earned {points_awarded} points."
    correct_text = question.options[question.correct_index]
    feedback = f'Not quite. The correct answer was "{correct_text}".'
    if question.hint:
        feedback += f" Hint: {question.hint}"
    return feedback


def _chapter_is_answered(chapter):
    """True once every question in the chapter has been answered.
    (A chapter with zero questions counts as already answered.)"""
    return not chapter.questions.filter(user_answer_index__isnull=True).exists()


def _chapter_kwargs(group):
    """Translate a plan group (Phase B) into generate_chapter kwargs: the grounding
    passages and this chapter's paragraph/question ranges. Empty for no group."""
    if not group:
        return {}
    return {
        "passages": group.get("passages"),
        "min_paragraphs": group["min_p"],
        "max_paragraphs": group["max_p"],
        "min_questions": group["min_q"],
        "max_questions": group["max_q"],
    }


# --- Q&A anti-cheat (deterministic similarity gate) -------------------------------

# How similar (0..1) a typed question must be to a still-unanswered quiz question
# before we refuse to answer it. May need light tuning: a heavy paraphrase can slip
# under it, and a long unrelated question could occasionally trip it.
SIMILARITY_THRESHOLD = 0.7


def _normalise_text(text):
    """Lowercase, keep only letters/digits/spaces, collapse whitespace — so casing
    or punctuation tweaks can't dodge the similarity check."""
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _matches_active_question(question_text, active_questions):
    """True if `question_text` is suspiciously similar to any of the given
    still-unanswered quiz Question rows."""
    asked = _normalise_text(question_text)
    if not asked:
        return False
    for q in active_questions:
        ratio = difflib.SequenceMatcher(None, asked, _normalise_text(q.question_text)).ratio()
        if ratio >= SIMILARITY_THRESHOLD:
            return True
    return False


def _answered_state(chapter):
    """Frontend-ready answer state for the already-answered questions in a chapter.
    Used when RESUMING a story so prior answers show correctly (Phase C). Keyed by
    question id; only answered questions appear, so unanswered answer keys never leak.
    """
    state = {}
    for q in chapter.questions.all():
        if q.user_answer_index is not None:
            points = adaptation.points_for_correct(chapter.difficulty_at_time) if q.is_correct else 0
            state[q.id] = {
                "selectedIndex": q.user_answer_index,
                "isCorrect": q.is_correct,
                "correctIndex": q.correct_index,
                "feedback": _question_feedback(q, q.is_correct, points),
            }
    return state


# --- Authentication -------------------------------------------------------------

def _profile(learner):
    """The small profile object returned to the frontend after auth."""
    return {
        "id": learner.id,
        "username": learner.user.username if learner.user else None,
        "display_name": learner.name,
    }


def _learner_for(user):
    """Return (creating if needed) the Learner profile for a Django user."""
    learner, _ = Learner.objects.get_or_create(user=user, defaults={"name": user.username})
    return learner


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthThrottle])
def register(request):
    """POST /api/auth/register  body: {username, password, display_name?}

    Creates a User (securely hashed password) + a linked Learner, returns a token.
    """
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""
    display_name = (request.data.get("display_name") or "").strip()
    if not username or not password:
        return Response({"error": "Username and password are required."},
                        status=status.HTTP_400_BAD_REQUEST)
    if User.objects.filter(username=username).exists():
        return Response({"error": "That username is already taken."},
                        status=status.HTTP_400_BAD_REQUEST)
    user = User.objects.create_user(username=username, password=password)  # hashes the password
    learner = Learner.objects.create(user=user, name=display_name or username)
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "profile": _profile(learner)},
                    status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthThrottle])
def login(request):
    """POST /api/auth/login  body: {username, password} -> token + profile."""
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""
    user = authenticate(username=username, password=password)
    if user is None:
        return Response({"error": "Invalid username or password."},
                        status=status.HTTP_400_BAD_REQUEST)
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "profile": _profile(_learner_for(user))})


@api_view(["GET"])
def me(request):
    """GET /api/auth/me -> the current user's profile (requires a valid token)."""
    return Response(_profile(_learner_for(request.user)))


@api_view(["GET"])
def me_progress(request):
    """GET /api/me/progress -> the learner's concept mastery, grouped by topic.
    Useful for showing strengths/weaknesses (and for the report)."""
    learner = _learner_for(request.user)
    by_topic = {}
    for s in learner.concept_stats.all().order_by("topic", "concept"):
        by_topic.setdefault(s.topic, []).append({
            "concept": s.concept,
            "attempts": s.attempts,
            "correct": s.correct,
            "mastery": round(s.mastery, 2),
        })
    progress = [{"topic": topic, "concepts": concepts} for topic, concepts in by_topic.items()]
    return Response({"progress": progress})


# --- Endpoints ------------------------------------------------------------------

@api_view(["GET"])
def topics(request):
    """GET /api/topics -> the fixed list of {slug, title} topics."""
    return Response(TOPICS)


@api_view(["POST"])
@throttle_classes([StoryGenThrottle, StoryGenDailyThrottle])  # paid LLM call
def create_session(request):
    """POST /api/sessions  body: {topic, grade}

    The learner is the logged-in user; `topic` is free text. The first chapter is
    syllabus-gated: if the grade's textbook doesn't cover the topic, no session is
    created and we return {in_syllabus: false, reason}.
    """
    learner = _learner_for(request.user)
    topic = (request.data.get("topic") or "").strip()
    if not topic:
        return Response({"error": "Please enter a topic."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        grade = int(request.data.get("grade"))
    except (TypeError, ValueError):
        return Response({"error": "Please choose a grade (6-9)."}, status=status.HTTP_400_BAD_REQUEST)
    if grade not in (6, 7, 8, 9):
        return Response({"error": "Grade must be 6, 7, 8 or 9."}, status=status.HTTP_400_BAD_REQUEST)

    # Cross-session story memory (Phase C): if there's an unfinished story for this
    # learner + topic + grade, resume it (same setting/characters, preserved points/
    # difficulty/plan) instead of starting a new one.
    existing = (
        Session.objects.filter(learner=learner, topic__iexact=topic, grade=grade, is_complete=False)
        .order_by("-created_at")
        .first()
    )
    if existing:
        current = existing.chapters.order_by("-order").first()
        if current:
            return Response({
                "session_id": existing.id,
                "in_syllabus": True,
                "resumed": True,
                "chapter": PresentedChapterSerializer(current).data,
                "answers": _answered_state(current),       # rehydrate any prior answers
                "difficulty": existing.difficulty,
                "points": existing.points,
                "badges": list(existing.badges.values_list("name", flat=True)),
                "sources": current.sources or [],
                "chapter_complete": _chapter_is_answered(current),
                "total_chapters": len(existing.plan or []),
                "is_complete": False,
            }, status=status.HTTP_200_OK)

    # Personalise for a returning learner: an adaptive starting difficulty and a
    # list of weak concepts to revisit on this topic (Phase 4).
    start_difficulty = personalization.starting_difficulty(learner, topic)
    revisit = personalization.weak_concepts(learner, topic)

    # Build the content-driven plan (Phase B): how many chapters, and how many
    # paragraphs/questions each, from how much textbook content exists. Mock mode
    # has no retrieval, so it uses a fixed small plan.
    if llm_config.use_mock():
        plan = planning.mock_plan()
    else:
        plan = planning.plan_session(grade, topic)
        if not plan:
            # No relevant textbook content -> off-syllabus. Refuse, create nothing.
            return Response(
                {"in_syllabus": False,
                 "reason": f"We couldn't find \"{topic}\" in the Grade {grade} science textbook."},
                status=status.HTTP_200_OK,
            )
    first = plan[0]

    # Generate the first chapter BEFORE writing to the DB. gate=True lets the model
    # also refuse if the retrieved sections don't actually cover the topic.
    try:
        data = generate_chapter(
            topic, grade, start_difficulty,
            revisit_concepts=revisit, gate=True, **_chapter_kwargs(first),
        )
    except LLMError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    # Syllabus gate: topic not covered -> refuse politely, create nothing.
    if data.get("in_syllabus") is False:
        return Response(
            {"in_syllabus": False,
             "reason": data.get("reason") or f"\"{topic}\" isn't in the Grade {grade} syllabus."},
            status=status.HTTP_200_OK,
        )

    session = Session.objects.create(
        learner=learner,
        topic=topic,
        grade=grade,
        difficulty=start_difficulty,
        setting=data.get("setting") or "",
        content_level=first.get("level", ""),
        plan=plan,
    )
    chapter = _persist_chapter(session, data)

    return Response(
        {
            "session_id": session.id,
            "in_syllabus": True,
            "chapter": PresentedChapterSerializer(chapter).data,
            "difficulty": session.difficulty,
            "points": session.points,
            "badges": [],
            "sources": data.get("sources", []),
            "chapter_complete": chapter.questions.count() == 0,
            "total_chapters": len(plan),
            "is_complete": session.is_complete,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
def answer(request, session_id):
    """POST /api/sessions/<id>/answer  body: {question_id, answer_index, response_time_ms?}

    Records one answer and awards points. Difficulty/badges are handled per-chapter
    by /next. Returns whether the chapter is now fully answered.
    """
    session = get_object_or_404(Session, pk=session_id, learner__user=request.user)
    if session.is_complete:
        return Response({"error": "This session is already complete."}, status=status.HTTP_400_BAD_REQUEST)

    question = get_object_or_404(
        Question, pk=request.data.get("question_id"), chapter__session=session
    )
    if question.user_answer_index is not None:
        return Response({"error": "This question has already been answered."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        answer_index = int(request.data.get("answer_index"))
    except (TypeError, ValueError):
        return Response({"error": "answer_index must be an integer 0-3."}, status=status.HTTP_400_BAD_REQUEST)
    if not 0 <= answer_index <= 3:
        return Response({"error": "answer_index must be between 0 and 3."}, status=status.HTTP_400_BAD_REQUEST)

    response_time_ms = request.data.get("response_time_ms")
    response_time_ms = int(response_time_ms) if response_time_ms is not None else None

    # Record the answer.
    is_correct = (answer_index == question.correct_index)
    question.user_answer_index = answer_index
    question.is_correct = is_correct
    question.response_time_ms = response_time_ms
    question.save()

    # Per-question scoring (points + streak). Difficulty changes per chapter only.
    points_awarded = adaptation.score_question(session, is_correct)
    session.save()

    # Update cross-session concept mastery (Phase 4).
    personalization.record_answer(session.learner, session.topic, question.concept, is_correct)

    return Response({
        "is_correct": is_correct,
        "correct_index": question.correct_index,
        "feedback": _question_feedback(question, is_correct, points_awarded),
        "points": session.points,
        "chapter_complete": _chapter_is_answered(question.chapter),
    })


@api_view(["POST"])
@throttle_classes([StoryGenThrottle, StoryGenDailyThrottle])  # paid LLM call
def next_chapter(request, session_id):
    """POST /api/sessions/<id>/next

    Only valid once the current chapter is fully answered. Runs chapter-level
    adaptation, awards badges, then generates the next chapter or finishes.
    """
    session = get_object_or_404(Session, pk=session_id, learner__user=request.user)
    if session.is_complete:
        return Response({"error": "This session is already complete."}, status=status.HTTP_400_BAD_REQUEST)

    current = session.chapters.order_by("-order").first()
    if current is None or not _chapter_is_answered(current):
        return Response({"error": "Answer all questions in this chapter first."},
                        status=status.HTTP_400_BAD_REQUEST)

    # Chapter-level adaptation from the score (changes session.difficulty in memory).
    # A 0-question chapter gives no signal, so difficulty is left unchanged there.
    total = current.questions.count()
    correct = current.questions.filter(is_correct=True).count()
    adaptation.adjust_difficulty_for_chapter(session, correct, total)
    had_correct = correct > 0

    # Finished once the planned chapters are covered (Phase B), capped for safety.
    plan = session.plan or []
    planned = min(len(plan), adaptation.MAX_CHAPTERS_CAP) if plan else adaptation.MAX_CHAPTERS_CAP
    session.is_complete = session.chapter_count >= max(planned, adaptation.MIN_CHAPTERS)
    if session.is_complete:
        new_badges = gamification.award_badges(session, had_correct, is_complete=True)
        session.save()
        return Response({
            "is_complete": True,
            "chapter": None,
            "points": session.points,
            "difficulty": session.difficulty,
            "badges": list(session.badges.values_list("name", flat=True)),
            "badges_awarded": new_badges,
        })

    # Otherwise generate the next chapter, revisiting any missed concepts and
    # continuing from this chapter's summary. Generate BEFORE persisting the
    # difficulty change / badges, so an LLM failure leaves the session retryable.
    # Revisit the learner's weak concepts on this topic (cross-session; already
    # includes this chapter's mistakes, since stats update on every answer).
    revisit = personalization.weak_concepts(session.learner, session.topic)
    # The next chapter's grounding + length come from the plan (Phase B).
    group = plan[session.chapter_count] if session.chapter_count < len(plan) else None
    try:
        data = generate_chapter(
            session.topic, session.grade, session.difficulty,
            setting=session.setting, story_so_far=current.summary, revisit_concepts=revisit,
            **_chapter_kwargs(group),
        )
    except LLMError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    new_badges = gamification.award_badges(session, had_correct, is_complete=False)
    next_ch = _persist_chapter(session, data)  # saves the session (difficulty + count)

    return Response({
        "is_complete": False,
        "chapter": PresentedChapterSerializer(next_ch).data,
        "difficulty": session.difficulty,
        "points": session.points,
        "badges": list(session.badges.values_list("name", flat=True)),
        "badges_awarded": new_badges,
        "sources": data.get("sources", []),
        "chapter_complete": next_ch.questions.count() == 0,
        "total_chapters": len(plan),
    })


@api_view(["POST"])
def finish_session(request, session_id):
    """POST /api/sessions/<id>/finish

    End the session early (before the planned last chapter) and go to the results.
    Marks it complete and awards the completion badges. Makes no LLM call, so it is
    free and deliberately not throttled.
    """
    session = get_object_or_404(Session, pk=session_id, learner__user=request.user)
    if session.is_complete:
        return Response({"error": "This session is already complete."}, status=status.HTTP_400_BAD_REQUEST)

    session.is_complete = True
    had_correct = Question.objects.filter(chapter__session=session, is_correct=True).exists()
    new_badges = gamification.award_badges(session, had_correct, is_complete=True)
    session.save()

    return Response({
        "is_complete": True,
        "points": session.points,
        "difficulty": session.difficulty,
        "badges": list(session.badges.values_list("name", flat=True)),
        "badges_awarded": new_badges,
    })


@api_view(["GET"])
def get_session(request, session_id):
    """GET /api/sessions/<id> -> full session state with all chapters, questions
    and badges. Serves as evidence that every interaction is logged."""
    session = get_object_or_404(Session, pk=session_id, learner__user=request.user)
    return Response(SessionSerializer(session).data)


@api_view(["POST"])
@throttle_classes([AskThrottle, AskDailyThrottle])  # paid LLM call
def ask(request, session_id):
    """POST /api/sessions/<id>/ask  body: {question}

    Grounded Q&A: answer a free question using ONLY the grade's textbook. This is
    deliberately separate from grading — it never changes difficulty, points,
    streak or concept mastery.
    """
    session = get_object_or_404(Session, pk=session_id, learner__user=request.user)
    question = (request.data.get("question") or "").strip()
    if not question:
        return Response({"error": "Please enter a question."}, status=status.HTTP_400_BAD_REQUEST)

    # Anti-cheat, layer 1 (deterministic — no LLM call): refuse questions too
    # similar to one of the CURRENT chapter's still-unanswered quiz questions.
    # Questions the learner has already answered stay fair game to discuss.
    current = session.chapters.order_by("-order").first()
    active = list(current.questions.filter(user_answer_index__isnull=True)) if current else []
    if _matches_active_question(question, active):
        return Response({
            "answer": "I can't answer the quiz question for you — give it your best try first, "
                      "and I'm happy to explain the idea behind it.",
            "in_syllabus": True,
            "sources": [],
            "blocked": True,  # lets the frontend style the refusal
        })

    try:
        # Anti-cheat, layer 2: even when the wording doesn't match, tell the model
        # not to answer the active quiz questions (catches paraphrases).
        result = answer_question(
            session.topic, session.grade, question,
            avoid_questions=[q.question_text for q in active],
        )
    except LLMError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response(result)  # {answer, in_syllabus, sources}
