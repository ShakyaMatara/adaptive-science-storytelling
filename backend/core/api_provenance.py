"""Placeholder — the real implementation replaces this file wholesale.

The route is wired up front so the page that consumes it can be developed and
checked against a live server rather than against a mock.
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def provenance(request, *args, **kwargs):
    return Response({"placeholder": True})
