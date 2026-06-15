"""Static configuration that the rest of the app reads from.

Keeping the topic list here (rather than in the database) keeps the MVP simple:
the curriculum is small and fixed, so a hardcoded list is enough for the midpoint.
It could later be promoted to a `Topic` model if the curriculum grows.
"""

# The science topics a learner can choose from (Sri Lankan Grade 6-9 syllabus).
# `slug` is the stable id sent by the frontend; `title` is the human-readable name.
TOPICS = [
    {"slug": "water-cycle", "title": "Water Cycle"},
    {"slug": "photosynthesis", "title": "Photosynthesis"},
    {"slug": "states-of-matter", "title": "States of Matter"},
    {"slug": "ecosystems-food-chains", "title": "Ecosystems & Food Chains"},
    {"slug": "energy-electricity", "title": "Energy & Electricity"},
]

# Fast lookup: slug -> title.
_TITLE_BY_SLUG = {t["slug"]: t["title"] for t in TOPICS}


def get_topic_title(slug):
    """Return the display title for a topic slug, or None if the slug is unknown."""
    return _TITLE_BY_SLUG.get(slug)
