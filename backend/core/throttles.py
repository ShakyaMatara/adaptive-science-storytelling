"""Per-user rate limits (DRF's built-in throttling — no new dependency).

These cap how often one user can hit the endpoints that trigger PAID LLM calls
(create_session / next_chapter / ask), so a runaway loop, rapid repeated clicks,
or a stolen token can't burn through API credits. The `answer` endpoint is
deliberately NOT throttled — it only records an answer and makes no LLM call.

Rates live in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], keyed by `scope`.
Each class is one named budget; stacking a per-minute and a per-day class on the
same endpoint gives both a burst limit and a daily ceiling. A throttled request
gets HTTP 429 with a "try again in N seconds" detail the frontend already shows.

Note: the real spending ceiling is the credit/spend limit set on the provider's
dashboard (e.g. OpenRouter) — throttling lowers the risk; the spend cap bounds
the worst case.
"""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class StoryGenThrottle(UserRateThrottle):
    """Burst cap on chapter generation (create_session / next_chapter)."""
    scope = "story_gen"


class StoryGenDailyThrottle(UserRateThrottle):
    """Daily ceiling on chapter generation."""
    scope = "story_gen_day"


class AskThrottle(UserRateThrottle):
    """Burst cap on the grounded Q&A panel."""
    scope = "ask"


class AskDailyThrottle(UserRateThrottle):
    """Daily ceiling on the grounded Q&A panel."""
    scope = "ask_day"


class AuthThrottle(AnonRateThrottle):
    """Slows brute-force attempts on login/register (keyed by client IP)."""
    scope = "anon_auth"
