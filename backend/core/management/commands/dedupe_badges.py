"""Remove duplicate badge rows left behind by the original awarding rule.

Badges were once checked against the current session only, so a learner who
returned to a topic earned its badge again on every run. The rule is now scoped
to the learner, but rows created before that change remain in any database that
ran the old code. The gallery already collapses them for display; this command
removes them from the data.

Duplicates are matched the same way the awarder matches them — by name, ignoring
case — and the EARLIEST row of each group is kept, so the date a badge shows is
the date it was genuinely first earned.

    python manage.py dedupe_badges              # report only, changes nothing
    python manage.py dedupe_badges --apply      # delete the duplicates
"""

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Badge


class Command(BaseCommand):
    help = "Report, and optionally remove, duplicate badges earned under the old rule."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually delete the duplicates. Without this the command only reports.",
        )

    def handle(self, *args, **options):
        # Oldest first, so the row kept for each group is the one earned first.
        badges = list(
            Badge.objects.select_related("session__learner").order_by("awarded_at", "id")
        )

        groups = defaultdict(list)
        for badge in badges:
            groups[(badge.session.learner_id, badge.name.casefold())].append(badge)

        duplicates = {key: rows for key, rows in groups.items() if len(rows) > 1}

        if not duplicates:
            self.stdout.write(self.style.SUCCESS(
                f"No duplicate badges. {len(badges)} rows, all distinct per learner."))
            return

        doomed = []
        self.stdout.write(f"{len(duplicates)} duplicated badge(s):\n")
        for rows in sorted(duplicates.values(), key=lambda r: r[0].name.lower()):
            keep, extra = rows[0], rows[1:]
            learner = keep.session.learner.name
            self.stdout.write(
                f'  {learner}: "{keep.name}" x{len(rows)}\n'
                f"      keep   id={keep.id}  earned {keep.awarded_at:%Y-%m-%d %H:%M}"
                f"  (session {keep.session_id})"
            )
            for badge in extra:
                spelling = "" if badge.name == keep.name else f'  [spelt "{badge.name}"]'
                self.stdout.write(
                    f"      delete id={badge.id}  earned {badge.awarded_at:%Y-%m-%d %H:%M}"
                    f"  (session {badge.session_id}){spelling}"
                )
            doomed.extend(extra)

        if not options["apply"]:
            self.stdout.write(self.style.WARNING(
                f"\nDry run: {len(doomed)} row(s) would be deleted. "
                f"Re-run with --apply to make the change."))
            return

        with transaction.atomic():
            Badge.objects.filter(id__in=[b.id for b in doomed]).delete()

        self.stdout.write(self.style.SUCCESS(
            f"\nDeleted {len(doomed)} duplicate badge row(s). "
            f"{Badge.objects.count()} remain."))
