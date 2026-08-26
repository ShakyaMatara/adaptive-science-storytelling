"""T3 — Content-Derived Instructional Scaling (CDIS): validity of the planner.

This is the experiment that substantiates the project's headline novelty claim:
that instructional volume is derived from measured curricular coverage rather
than fixed by the designer or driven only by learner state.

    python manage.py eval_planner                      # correlation study (free)
    python manage.py eval_planner --ground-truth gt.csv
    python manage.py eval_planner --ablate --limit 10  # fixed-length ablation (costs)

Two results are produced.

1. CONVERGENT VALIDITY. For each probe topic the planner's output (chapter count,
   question budget, richness level) is correlated against an independent measure
   of how much the textbook actually covers that topic. Spearman's rho is used
   because the relationship is expected to be monotonic rather than linear and
   the ground-truth counts are ordinal in practice.

   The independent measure can come from two sources:
     * automatic — the number of distinct textbook PAGES the retrieved passages
       span for that topic, which is derived from metadata the planner does not
       itself consume;
     * manual — a CSV you compile by counting pages in the printed textbook, via
       --ground-truth. This is the stronger evidence because it is fully external
       to the system, and it is worth the hour it takes for ~20 topics.

   Reporting both, and reporting their agreement, is what turns "the planner
   varies its output" into "the planner tracks curricular emphasis".

2. DISCRIMINATION. Thin, moderate and rich topics are shown to receive
   significantly different plans, with the spread reported per richness band.

--ablate additionally generates chapters for thin topics under both the CDIS plan
and a fixed 3-chapter plan, so that the padding a fixed-length design forces can
be quantified. This is the argument that CDIS is a safety property, not a
convenience: on a thin topic a fixed-length plan must invent material the
textbook does not support.
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand

from core import planning, retrieval
from evaluation import harness


class Command(BaseCommand):
    help = "T3: validate that instructional scaling tracks measured textbook coverage."

    def add_arguments(self, parser):
        parser.add_argument("--ground-truth", type=str, default=None,
                            help="CSV with columns topic,grade,gt_pages (your manual page counts).")
        parser.add_argument("--ablate", action="store_true",
                            help="Generate CDIS vs fixed-length chapters on thin topics (paid).")
        parser.add_argument("--limit", type=int, default=8, help="Topics used for --ablate.")

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("\nT3 — Content-Derived Instructional Scaling"))

        manual = self._load_ground_truth(options["ground_truth"])
        rows = self._measure(manual)
        if not rows:
            self.stdout.write(self.style.ERROR("No topics planned — is the Chroma index built?"))
            return

        self._correlations(rows, bool(manual))
        self._by_richness(rows)
        self._report_provenance(rows)

        if options["ablate"]:
            self._ablate(rows, options["limit"])

        path = harness.write_csv(
            "t3_planner", rows,
            ["topic", "grade", "total_relevant", "distinct_pages", "page_span", "gt_pages",
             "ocr_relevant", "ocr_share", "richness", "chapters", "min_questions",
             "max_questions", "paragraph_budget"])
        self.stdout.write(self.style.SUCCESS(f"\nPer-topic detail: {path}"))

    def _report_provenance(self, rows):
        """What share of the coverage measure rests on text recovered from images."""
        touched = [r for r in rows if r.get("ocr_relevant")]
        self.stdout.write(self.style.MIGRATE_HEADING("\nProvenance of total_relevant"))
        self.stdout.write(f"  Topics drawing on recovered text: {len(touched)}/{len(rows)}")
        if touched:
            total_rel = sum(r["total_relevant"] for r in rows)
            total_ocr = sum(r["ocr_relevant"] for r in rows)
            self.stdout.write(f"  Recovered passages as a share of all counted passages: "
                              f"{total_ocr}/{total_rel} ({100.0*total_ocr/total_rel:.1f}%)")
            for r in sorted(touched, key=lambda x: -x["ocr_share"])[:8]:
                self.stdout.write(f"     grade {r['grade']} {r['topic'][:44]:<44} "
                                  f"{r['ocr_relevant']}/{r['total_relevant']} "
                                  f"({r['ocr_share']:.0%})")
            self.stdout.write(
                "  Any correlation below can be recomputed with these topics excluded.")

    # --- inputs -------------------------------------------------------------------

    def _load_ground_truth(self, path):
        if not path:
            self.stdout.write(
                "No --ground-truth supplied; using the automatic page-span proxy only.\n"
                "For a stronger result, spend an hour counting textbook pages per topic and re-run with\n"
                "  --ground-truth evaluation/probes/ground_truth.csv   (columns: topic,grade,gt_pages)")
            return {}
        source = Path(path)
        if not source.exists():
            source = harness.EVAL_DIR / path
        if not source.exists():
            self.stdout.write(self.style.ERROR(f"Ground-truth file not found: {path}"))
            return {}
        manual = {}
        with open(source, "r", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    key = (row["topic"].strip().lower(), int(row["grade"]))
                    manual[key] = float(row["gt_pages"])
                except (KeyError, ValueError):
                    continue
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(manual)} manual ground-truth entries."))
        return manual

    # --- measurement ---------------------------------------------------------------

    def _measure(self, manual):
        probes = harness.load_probes("in_syllabus")["probes"]
        rows = []
        for probe in probes:
            grade, topic = probe["grade"], probe["topic"]
            content = retrieval.gather_topic_content(grade, topic)
            if not content["passages"]:
                continue  # refused by the gate; not a planning case

            # PRINTED pages, not PDF page indices: the printed number is the unit a
            # learner and the syllabus both use, and it is what the ground truth counts.
            printed = harness.printed_pages(content["passages"])
            distinct_pages = len(set(printed))
            page_span = harness.printed_span(content["passages"])
            recovered, _total, ocr_share = harness.provenance(content["passages"])

            plan = planning.plan_session(grade, topic)
            if not plan:
                continue

            rows.append({
                "topic": topic,
                "grade": grade,
                "total_relevant": content["total_relevant"],
                "distinct_pages": distinct_pages,
                "page_span": page_span,
                "gt_pages": manual.get((topic.strip().lower(), grade), ""),
                "ocr_relevant": recovered,
                "ocr_share": round(ocr_share, 4),
                "richness": plan[0]["level"],
                "chapters": len(plan),
                "min_questions": sum(c["min_q"] for c in plan),
                "max_questions": sum(c["max_q"] for c in plan),
                "paragraph_budget": sum(c["max_p"] for c in plan),
            })
        self.stdout.write(f"Planned {len(rows)} covered topics.")
        return rows

    # --- correlation ----------------------------------------------------------------

    def _correlations(self, rows, has_manual):
        self.stdout.write(self.style.HTTP_INFO("\nConvergent validity — Spearman's rho"))

        chapters = [r["chapters"] for r in rows]
        questions = [r["max_questions"] for r in rows]
        paragraphs = [r["paragraph_budget"] for r in rows]
        distinct = [r["distinct_pages"] for r in rows]
        span = [r["page_span"] for r in rows]

        pairs = [
            ("distinct textbook pages", "chapter count", distinct, chapters),
            ("distinct textbook pages", "question budget", distinct, questions),
            ("distinct textbook pages", "paragraph budget", distinct, paragraphs),
            ("textbook page span", "chapter count", span, chapters),
        ]

        if has_manual:
            manual_rows = [r for r in rows if r["gt_pages"] != ""]
            if len(manual_rows) >= 3:
                gt = [float(r["gt_pages"]) for r in manual_rows]
                pairs.insert(0, ("manual page count", "chapter count",
                                 gt, [r["chapters"] for r in manual_rows]))
                pairs.insert(1, ("manual page count", "question budget",
                                 gt, [r["max_questions"] for r in manual_rows]))
                pairs.insert(2, ("manual page count", "distinct pages retrieved",
                                 gt, [r["distinct_pages"] for r in manual_rows]))

        table_rows = []
        for x_label, y_label, xs, ys in pairs:
            rho = harness.spearman(xs, ys)
            table_rows.append({
                "coverage measure": x_label,
                "plan measure": y_label,
                "n": len(xs),
                "spearman_rho": rho,
                "strength": self._interpret(rho),
            })
        self.stdout.write(harness.table(
            table_rows, ["coverage measure", "plan measure", "n", "spearman_rho", "strength"]))
        harness.write_csv("t3_planner_correlations", table_rows,
                          ["coverage measure", "plan measure", "n", "spearman_rho", "strength"])

        self.stdout.write(
            "\nInterpretation for Chapter 7: a strong positive rho between an INDEPENDENT measure of textbook\n"
            "coverage and the planner's output is evidence that instructional volume is derived from curricular\n"
            "emphasis. Note honestly that distinct-pages is only quasi-independent (it comes from the same\n"
            "retrieval call, though not from any quantity the planner consumes), which is exactly why the\n"
            "manual page count is worth collecting.")

    @staticmethod
    def _interpret(rho):
        magnitude = abs(rho)
        if magnitude >= 0.8:
            return "very strong"
        if magnitude >= 0.6:
            return "strong"
        if magnitude >= 0.4:
            return "moderate"
        if magnitude >= 0.2:
            return "weak"
        return "negligible"

    # --- discrimination --------------------------------------------------------------

    def _by_richness(self, rows):
        self.stdout.write(self.style.HTTP_INFO("\nDiscrimination by richness band"))
        bands = {}
        for row in rows:
            bands.setdefault(row["richness"], []).append(row)

        table_rows = []
        for level in ("thin", "moderate", "rich"):
            subset = bands.get(level, [])
            if not subset:
                continue
            ch_mean, ch_sd = harness.mean_sd([r["chapters"] for r in subset])
            q_mean, q_sd = harness.mean_sd([r["max_questions"] for r in subset])
            p_mean, _ = harness.mean_sd([r["total_relevant"] for r in subset])
            table_rows.append({
                "richness": level, "topics": len(subset),
                "mean_passages": p_mean,
                "mean_chapters": ch_mean, "sd_chapters": ch_sd,
                "mean_questions": q_mean, "sd_questions": q_sd,
            })
        self.stdout.write(harness.table(
            table_rows, ["richness", "topics", "mean_passages", "mean_chapters",
                         "sd_chapters", "mean_questions", "sd_questions"]))
        harness.write_csv("t3_planner_by_richness", table_rows,
                          ["richness", "topics", "mean_passages", "mean_chapters",
                           "sd_chapters", "mean_questions", "sd_questions"])

        thinnest = min(rows, key=lambda r: r["chapters"])
        richest = max(rows, key=lambda r: r["chapters"])
        self.stdout.write(
            f"\nWorked contrast for the thesis:\n"
            f"  thinnest: G{thinnest['grade']} '{thinnest['topic']}' -> {thinnest['chapters']} chapter(s), "
            f"{thinnest['max_questions']} question(s) from {thinnest['total_relevant']} passages\n"
            f"  richest : G{richest['grade']} '{richest['topic']}' -> {richest['chapters']} chapter(s), "
            f"{richest['max_questions']} question(s) from {richest['total_relevant']} passages")

    # --- ablation (paid) ---------------------------------------------------------------

    def _ablate(self, rows, limit):
        """Generate thin-topic chapters under CDIS vs a fixed 3-chapter plan.

        The measurable consequence of fixed-length planning on a thin topic is
        that the same small evidence base must be stretched across more chapters,
        so grounding density (passages available per chapter) falls. That ratio is
        reported here; run eval_faithfulness on the same topics to show the
        downstream effect on factual groundedness.
        """
        from core import llm, llm_config

        if llm_config.use_mock():
            self.stdout.write(self.style.WARNING(
                "\nUSE_MOCK_LLM is true — ablation skipped. Set USE_MOCK_LLM=false in backend/.env."))
            return

        thin = sorted(rows, key=lambda r: r["total_relevant"])[:limit]
        self.stdout.write(self.style.HTTP_INFO(
            f"\nFixed-length ablation on the {len(thin)} thinnest topics (paid calls)"))

        budget = harness.Budget("t3_ablation")
        model_id = llm_config.get_model()
        out = []

        for row in thin:
            grade, topic = row["grade"], row["topic"]
            content = retrieval.gather_topic_content(grade, topic)
            passages = content["passages"]
            cdis_chapters = row["chapters"]
            fixed_chapters = 3

            for condition, n_chapters in (("cdis", cdis_chapters), ("fixed3", fixed_chapters)):
                per_chapter = max(1, len(passages) // max(1, n_chapters))
                slice_ = passages[:per_chapter]
                try:
                    chapter = llm.generate_chapter(
                        topic, grade, difficulty=3, passages=slice_,
                        min_paragraphs=3, max_paragraphs=4, min_questions=1, max_questions=2)
                    text = " ".join(chapter.get("paragraphs") or [])
                    stats = harness.readability(text)
                    out.append({
                        "topic": topic, "grade": grade, "condition": condition,
                        "planned_chapters": n_chapters,
                        "total_passages": len(passages),
                        "passages_per_chapter": round(len(passages) / max(1, n_chapters), 2),
                        "words": stats["words"],
                        "words_per_grounding_passage": round(stats["words"] / max(1, len(slice_)), 1),
                        "questions": len(chapter.get("questions") or []),
                        "sources_cited": len(chapter.get("sources") or []),
                    })
                    budget.record(model_id, {"prompt_tokens": 0, "completion_tokens": 0})
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f"  {topic} [{condition}]: {exc}"))
                    budget.record(model_id, {"prompt_tokens": 0, "completion_tokens": 0}, failed=True)

        for condition in ("cdis", "fixed3"):
            subset = [r for r in out if r["condition"] == condition]
            if not subset:
                continue
            ppc, _ = harness.mean_sd([r["passages_per_chapter"] for r in subset])
            wpp, _ = harness.mean_sd([r["words_per_grounding_passage"] for r in subset])
            self.stdout.write(
                f"  {condition:7s}  mean passages/chapter={ppc}  mean words per grounding passage={wpp}")

        self.stdout.write(
            "\nA higher words-per-grounding-passage figure under the fixed-length condition means the model was\n"
            "asked to produce more prose from the same evidence — the padding pressure that CDIS removes.\n"
            "Run eval_faithfulness on these same topics to show that this pressure lowers groundedness.")

        path = harness.write_csv(
            "t3_ablation", out,
            ["topic", "grade", "condition", "planned_chapters", "total_passages",
             "passages_per_chapter", "words", "words_per_grounding_passage", "questions", "sources_cited"])
        self.stdout.write(self.style.SUCCESS(f"\n{budget.summary()}\nAblation data: {path}"))
