"""Verify and curate the evaluation probe sets against the real textbook index.

The positive probe sets shipped with the harness are CANDIDATES. Before any T1
result is reported they must be checked against the corpus that is actually
indexed, because a "positive" topic the textbooks do not cover would be counted
as a false negative and would understate the gate's accuracy.

    python manage.py eval_probes --verify          # check every probe set
    python manage.py eval_probes --suggest         # mine real headings from the index
    python manage.py eval_probes --suggest --grade 8 --limit 60

--verify reports the best retrieval distance for every probe and flags:
  * positives whose best distance exceeds GATE_MAX_DISTANCE (would be refused)
  * negatives whose best distance falls below it (would be accepted)

--suggest lists the distinct section/chapter labels held in the index per grade,
which is the fastest way to build a positive probe set that is guaranteed to be
drawn from the prescribed textbooks rather than from assumption.

No model calls are made by this command; it costs nothing to run.
"""

from django.core.management.base import BaseCommand

from core import retrieval
from evaluation import harness


class Command(BaseCommand):
    help = "Verify evaluation probe sets against the built Chroma index, or mine candidate topics from it."

    def add_arguments(self, parser):
        parser.add_argument("--verify", action="store_true", help="Check all probe sets against the index.")
        parser.add_argument("--suggest", action="store_true", help="List section labels held in the index.")
        parser.add_argument("--grade", type=int, default=None, help="Restrict --suggest to one grade.")
        parser.add_argument("--limit", type=int, default=40, help="Max labels per grade for --suggest.")
        parser.add_argument(
            "--positives", default="in_syllabus",
            help="Positive probe set to verify: in_syllabus (contents-page wording) or "
                 "in_syllabus_paraphrased (learner phrasing).")

    def handle(self, *args, **options):
        if not options["verify"] and not options["suggest"]:
            self.stdout.write(self.style.WARNING("Nothing to do. Pass --verify and/or --suggest."))
            return
        if options["suggest"]:
            self._suggest(options["grade"], options["limit"])
        if options["verify"]:
            self._verify(options["positives"])

    # --- mining candidate topics from the index --------------------------------

    def _suggest(self, only_grade, limit):
        self.stdout.write(self.style.MIGRATE_HEADING("\nSection labels present in the index"))
        try:
            collection = retrieval.get_collection()
        except Exception as exc:
            self.stdout.write(self.style.ERROR(
                f"Could not open the Chroma collection ({exc}). Run `python manage.py build_index` first."))
            return

        grades = [only_grade] if only_grade else [6, 7, 8, 9]
        rows = []
        for grade in grades:
            try:
                data = collection.get(where={"grade": int(grade)}, include=["metadatas", "documents"])
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  grade {grade}: {exc}"))
                continue
            metadatas = data.get("metadatas") or []
            documents = data.get("documents") or []

            seen = {}
            for i, meta in enumerate(metadatas):
                meta = meta or {}
                label = (meta.get("section") or meta.get("chapter") or "").strip()
                # Section labels can be missing or degenerate (e.g. "(document)");
                # fall back to the opening line of the chunk, which is usually the
                # heading the chunker split on.
                if not label or label.lower() in {"(document)", "document", "none"}:
                    text = documents[i] if i < len(documents) else ""
                    first_line = (text or "").strip().split("\n")[0][:70].strip()
                    label = first_line or ""
                if label and label not in seen:
                    # The PRINTED page is the unit the syllabus and the learner use.
                    seen[label] = meta.get("page_label_start") or meta.get("page")
                if len(seen) >= limit:
                    break

            self.stdout.write(self.style.HTTP_INFO(f"\n  Grade {grade} — {len(seen)} distinct labels shown"))
            for label, page in seen.items():
                self.stdout.write(f"    p.{page}  {label}")
                rows.append({"grade": grade, "label": label, "page": page})

        if rows:
            path = harness.write_csv("probe_candidates", rows, ["grade", "label", "page"])
            self.stdout.write(self.style.SUCCESS(f"\nCandidates written to {path}"))
            self.stdout.write(
                "Copy the good ones into evaluation/probes/in_syllabus.json as {\"topic\": ..., \"grade\": ...}.")

    # --- verifying the probe sets ----------------------------------------------

    def _probe_distance(self, grade, topic):
        """Best (smallest) retrieval distance for a topic at a grade, or None."""
        passages = retrieval.retrieve(grade, topic, k=10)
        scored = [p["distance"] for p in passages if p.get("distance") is not None]
        return min(scored) if scored else None

    def _verify(self, positives="in_syllabus"):
        gate = retrieval.GATE_MAX_DISTANCE
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nVerifying probe sets against GATE_MAX_DISTANCE = {gate}"))

        self.stdout.write(f"Positive set: {positives}")

        rows, problems = [], []

        # Positives: should be ACCEPTED, i.e. best distance <= gate.
        for probe in harness.load_probes(positives)["probes"]:
            grade, topic = probe["grade"], probe["topic"]
            best = self._probe_distance(grade, topic)
            ok = best is not None and best <= gate
            rows.append({"set": positives, "grade": grade, "topic": topic,
                         "best_distance": round(best, 4) if best is not None else "",
                         "expected": "accept", "would": "accept" if ok else "REFUSE", "ok": ok})
            if not ok:
                problems.append(f"  [positive would be refused] G{grade} '{topic}' "
                                f"(best={best if best is None else round(best, 4)})")

        # Negatives: should be REFUSED, i.e. best distance > gate.
        for probe in harness.load_probes("off_syllabus")["probes"]:
            topic = probe["topic"]
            for grade in (6, 7, 8, 9):
                best = self._probe_distance(grade, topic)
                bad = best is not None and best <= gate
                rows.append({"set": "off_syllabus", "grade": grade, "topic": topic,
                             "best_distance": round(best, 4) if best is not None else "",
                             "expected": "refuse", "would": "ACCEPT" if bad else "refuse", "ok": not bad})
                if bad:
                    problems.append(f"  [negative would be accepted] G{grade} '{topic}' "
                                    f"(best={round(best, 4)})")

        # Grade-boundary: should be REFUSED at the stated (wrong) grade.
        for probe in harness.load_probes("grade_boundary")["probes"]:
            grade, topic = probe["grade"], probe["topic"]
            best = self._probe_distance(grade, topic)
            bad = best is not None and best <= gate
            rows.append({"set": "grade_boundary", "grade": grade, "topic": topic,
                         "best_distance": round(best, 4) if best is not None else "",
                         "expected": "refuse", "would": "ACCEPT" if bad else "refuse", "ok": not bad})
            if bad:
                problems.append(f"  [grade-boundary leak] '{topic}' accepted at G{grade} "
                                f"(correct grade {probe.get('correct_grade')}, best={round(best, 4)})")

        path = harness.write_csv("probe_verification", rows,
                                 ["set", "grade", "topic", "best_distance", "expected", "would", "ok"])

        self.stdout.write(f"\nChecked {len(rows)} probe/grade combinations.")
        if problems:
            self.stdout.write(self.style.WARNING(f"\n{len(problems)} probes need attention:"))
            for line in problems[:60]:
                self.stdout.write(self.style.WARNING(line))
            if len(problems) > 60:
                self.stdout.write(self.style.WARNING(f"  ... and {len(problems) - 60} more (see the CSV)."))
            self.stdout.write(
                "\nPositives that would be refused are usually wording mismatches — replace them with the "
                "textbook's own heading (use --suggest). Negatives that would be accepted are genuine gate "
                "false positives and SHOULD be kept: they are the interesting failures for Chapter 7.")
        else:
            self.stdout.write(self.style.SUCCESS("\nAll probes behave as expected at the current threshold."))
        self.stdout.write(self.style.SUCCESS(f"Detail written to {path}"))
