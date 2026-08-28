"""Gamification: award badges based on session state.

Badges are simple, motivating milestones, earned at most once per LEARNER. They
are awarded at chapter boundaries (when the learner moves to the next chapter or
finishes), so the caller passes in whether the just-finished chapter had any
correct answer and whether the session is now complete.

Two rules are worth stating because they were originally absent. A badge is
checked against every session the learner has ever run, not just the current one,
so returning to a topic does not hand out its explorer badge a second time. And
completing a story only earns its explorer badge if the learner answered at least
one question in it, so ending a story the moment it starts earns nothing.
"""

from .models import Badge, Question

# Badge names (kept as constants so the rules below read clearly).
FIRST_STEPS = "First Steps"      # first correct answer in the session
ON_FIRE = "On Fire"              # reached a 3-in-a-row correct streak
STREAK_FOR_ON_FIRE = 3
EXPLORER_SUFFIX = "Explorer"     # e.g. "Water Cycle Explorer" on completion


def _already_earned(learner_id, name):
    """Has this LEARNER earned a badge of this name before, in any session?

    Badge rows are attached to a session, but a badge means something about the
    learner, not about the run in which it happened: "First Steps" is the first
    correct answer they ever gave, and a topic is explored once. Scoping this
    check to the current session — as it originally was — awarded every badge
    again on every run, so a learner who returned to the water cycle three times
    collected three "Water Cycle Explorer" badges.

    The comparison is case-insensitive because a topic is free text, and
    `create_session` already treats "water cycle" and "Water Cycle" as one topic
    when deciding whether to resume. Matching that rule here keeps a learner from
    earning the same explorer badge twice by capitalising differently.
    """
    return Badge.objects.filter(
        session__learner_id=learner_id, name__iexact=name
    ).exists()


def _has_answered_anything(session):
    """Did the learner answer at least one question in this session?

    A story can be ended at any point from the reader, so completion on its own
    is no evidence that the learner engaged with the topic: starting a story and
    immediately finishing it used to be enough to earn its explorer badge.
    """
    return Question.objects.filter(
        chapter__session=session, user_answer_index__isnull=False
    ).exists()


def award_badges(session, had_correct, is_complete):
    """Create Badge rows for any milestones newly reached, and return their names.

    `had_correct` = did the chapter just finished contain at least one correct
    answer (used for "First Steps"). `session.current_streak` must be up to date.

    Each badge is earned once per learner. Re-earning one adds nothing — the
    gallery shows it as earned either way — and awarding it repeatedly made the
    achievement meaningless.
    """
    learner_id = session.learner_id
    newly_awarded = []

    # "First Steps": the learner's first correct answer, ever.
    if had_correct and not _already_earned(learner_id, FIRST_STEPS):
        newly_awarded.append(FIRST_STEPS)

    # "On Fire": a streak of 3 correct answers in a row.
    if session.current_streak >= STREAK_FOR_ON_FIRE and not _already_earned(learner_id, ON_FIRE):
        newly_awarded.append(ON_FIRE)

    # "<Topic> Explorer": finished a story on this topic, having actually answered
    # something in it. The topic keeps the spelling the learner typed; only the
    # duplicate check ignores case.
    if is_complete and _has_answered_anything(session):
        explorer = f"{session.topic.strip()} {EXPLORER_SUFFIX}"
        if not _already_earned(learner_id, explorer):
            newly_awarded.append(explorer)

    for name in newly_awarded:
        Badge.objects.create(session=session, name=name)

    return newly_awarded
