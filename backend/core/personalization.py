"""Cross-session personalisation: use a learner's concept-mastery history to
revisit their weak spots and to choose an adaptive starting difficulty.

Reads from ConceptStat (updated whenever a question is answered). Kept small and
rule-based so it is easy to explain and defend.
"""

from . import adaptation
from .models import ConceptStat


def record_answer(learner, topic, concept, is_correct):
    """Update the learner's mastery of (topic, concept) after one answer."""
    if not concept:
        return  # nothing to track for an unlabelled question
    stat, _ = ConceptStat.objects.get_or_create(learner=learner, topic=topic, concept=concept)
    stat.attempts += 1
    if is_correct:
        stat.correct += 1
    stat.save()  # last_seen auto-updates


def weak_concepts(learner, topic, limit=3):
    """Return up to `limit` concepts in this topic the learner is weakest at.

    "Weak" = attempted at least once and missed at least once, ranked by lowest
    mastery (then by most attempts). These are fed to the story generator so the
    next chapter gently revisits them.
    """
    stats = ConceptStat.objects.filter(learner=learner, topic=topic, attempts__gte=1)
    ranked = sorted(stats, key=lambda s: (s.mastery, -s.attempts))
    weak = [s.concept for s in ranked if s.correct < s.attempts]  # missed at least once
    return weak[:limit]


def starting_difficulty(learner, topic):
    """Choose a starting difficulty for a returning learner from their mastery of
    this topic (mapped into the 2-4 band); brand-new topics use the default (3).
    """
    stats = list(ConceptStat.objects.filter(learner=learner, topic=topic, attempts__gte=1))
    if not stats:
        return adaptation.START_DIFFICULTY  # 3 — no history yet

    total_attempts = sum(s.attempts for s in stats)
    total_correct = sum(s.correct for s in stats)
    mastery = (total_correct / total_attempts) if total_attempts else 0.0

    if mastery >= 0.75:
        return 4   # doing well -> start a bit harder
    if mastery <= 0.4:
        return 2   # struggling -> start a bit easier
    return 3       # middling -> start in the middle
