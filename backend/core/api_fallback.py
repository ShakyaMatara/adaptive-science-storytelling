"""Placeholder — the real implementation replaces this file wholesale."""

from rest_framework.decorators import api_view
from rest_framework.response import Response


def record_fallback_if_needed(session, chapter):
    """Called from the view layer after a chapter is persisted."""
    return None


@api_view(["GET"])
def generation_status(request, chapter_id):
    return Response({"placeholder": True})


@api_view(["POST"])
def retry_chapter(request, session_id, chapter_id):
    return Response({"placeholder": True})
