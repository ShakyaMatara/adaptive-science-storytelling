"""The achievements surface: a badge gallery, streaks and lifetime totals.

Read-only over `Badge`, `Session`, `Chapter` and `Question` — nothing here writes.
The badge rules themselves live in `gamification.py` and are read from there
rather than restated, so the criteria a learner is shown cannot drift away from
the criteria actually applied.

Two of the three badges are fixed and can therefore be listed as unearned with
their criteria visible, which is what makes the gallery useful: a learner can see
what is still to aim for. The third, "<Topic> Explorer", is one badge per topic
completed and so has no fixed list; it is presented as a family, with the ones
earned enumerated and the criterion described once.
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import gamification
from .models import Learner, Question


def _learner_for(user):
    """The learner profile for a Django user, created on first use."""
    learner, _ = Learner.objects.get_or_create(user=user, defaults={"name": user.username})
    return learner


def _fixed_badge_catalogue():
    """The two badges with fixed names, and the criterion for each in plain English."""
    return [
        {
            "name": gamification.FIRST_STEPS,
            "icon": "🌱",
            "criterion": "Answer your first question correctly in a story.",
        },
        {
            "name": gamification.ON_FIRE,
            "icon": "🔥",
            "criterion": (
                f"Answer {gamification.STREAK_FOR_ON_FIRE} questions correctly in a row "
                f"without a wrong answer in between."
            ),
        },
    ]


def _best_streak_in(session):
    """The longest run of consecutive correct answers within one session.

    A streak here means what it means everywhere else in the system: consecutive
    CORRECT ANSWERS, reset by a wrong one. `Session.current_streak` holds only the
    run in progress, so the best run has to be recovered by walking the session's
    answered questions in the order they were presented — chapter order first,
    then question order within the chapter.
    """
    answered = (
        Question.objects
        .filter(chapter__session=session, user_answer_index__isnull=False)
        .order_by("chapter__order", "order")
        .values_list("is_correct", flat=True)
    )
    best = run = 0
    for correct in answered:
        run = run + 1 if correct else 0
        best = max(best, run)
    return best


@api_view(["GET"])
def achievements(request):
    """GET /api/me/achievements -> badge gallery, streaks and lifetime totals."""
    learner = _learner_for(request.user)
    sessions = list(
        learner.sessions.prefetch_related("badges", "chapters__questions").order_by("-created_at")
    )

    # --- Badges ---------------------------------------------------------------
    # Every badge row this learner has ever earned, with the session it came from
    # so a topic can be attached to it.
    earned_rows = []
    for session in sessions:
        for badge in session.badges.all():
            earned_rows.append((badge, session))

    def _summarise(name):
        rows = [(b, s) for b, s in earned_rows if b.name == name]
        if not rows:
            return {"earned": False, "first_earned_at": None, "times_earned": 0, "topics": []}
        rows.sort(key=lambda pair: pair[0].awarded_at)
        return {
            "earned": True,
            "first_earned_at": rows[0][0].awarded_at,
            "times_earned": len(rows),
            "topics": sorted({s.topic for _, s in rows}),
        }

    badges = []
    for entry in _fixed_badge_catalogue():
        badges.append({**entry, **_summarise(entry["name"])})

    # The Explorer family: one badge per topic completed, so it is described once
    # and its earned members are listed rather than invented in advance.
    explorer_rows = [
        (b, s) for b, s in earned_rows if b.name.endswith(f" {gamification.EXPLORER_SUFFIX}")
    ]
    explorer_rows.sort(key=lambda pair: pair[0].awarded_at)
    explorer = {
        "icon": "🧭",
        "criterion": "Finish a whole story on a topic. You earn one for every topic you complete.",
        "earned_count": len({b.name for b, _ in explorer_rows}),
        "earned": [
            {"name": b.name, "topic": s.topic, "awarded_at": b.awarded_at}
            for b, s in explorer_rows
        ],
    }

    # --- Streaks --------------------------------------------------------------
    # "Current" is the run in progress on the story last worked on; "best" is the
    # longest run within any single session. Both are per session, because a
    # streak is reset by a wrong answer and does not carry across stories.
    most_recent = sessions[0] if sessions else None
    best_streak, best_streak_topic = 0, None
    for session in sessions:
        streak = _best_streak_in(session)
        if streak > best_streak:
            best_streak, best_streak_topic = streak, session.topic

    # --- Totals ---------------------------------------------------------------
    all_questions = Question.objects.filter(chapter__session__learner=learner)
    answered = all_questions.filter(user_answer_index__isnull=False)
    answered_count = answered.count()
    correct_count = answered.filter(is_correct=True).count()
    completed = [s for s in sessions if s.is_complete]
    chapters_read = sum(s.chapters.count() for s in sessions)

    return Response({
        "badges": badges,
        "explorer": explorer,
        "streaks": {
            "current": most_recent.current_streak if most_recent else 0,
            "current_topic": most_recent.topic if most_recent else None,
            "best": best_streak,
            "best_topic": best_streak_topic,
            "definition": (
                "A streak counts questions answered correctly one after another. "
                "A wrong answer starts it again from zero, and it does not carry "
                "from one story to the next."
            ),
        },
        "totals": {
            "points": sum(s.points for s in sessions),
            "badges_earned": len(earned_rows),
            "stories_started": len(sessions),
            "stories_completed": len(completed),
            "topics_completed": len({s.topic for s in completed}),
            "chapters_read": chapters_read,
            "questions_answered": answered_count,
            "questions_correct": correct_count,
            "accuracy": round(correct_count / answered_count, 2) if answered_count else 0.0,
        },
    })
