"""T5 — Difficulty adaptation validity: is the difficulty ladder real?

The pedagogical engine claims to move a learner between five difficulty levels.
That claim is only meaningful if the levels produce measurably different text.
This experiment tests it objectively, with no human raters, using established
readability formulae.

    python manage.py eval_difficulty                       # 5 levels x 4 reps
    python manage.py eval_difficulty --reps 6 --topics 3
    python manage.py eval_difficulty --dry-run             # show the call count first

Measures per generated chapter:
  * Flesch-Kincaid Grade Level (Kincaid et al., 1975)
  * Flesch Reading Ease (Flesch, 1948)
  * mean words per sentence, mean syllables per word
  * type-token ratio (lexical diversity)

Two findings are reported:
  1. MONOTONICITY — does FKGL rise as the configured difficulty rises? Reported as
     Spearman's rho between configured difficulty and measured FKGL across all
     generations. This is the direct test of whether adaptation is real or
     cosmetic.
  2. TARGET-BAND FIT — does the mid-difficulty setting land in the reading band
     appropriate for learners aged 11-14 (roughly FKGL 6-9)? This is the test of
     whether the ladder is centred correctly for the intended cohort, which is a
     separate question from whether it moves.

Note in the thesis that readability formulae measure surface linguistic
complexity, not conceptual difficulty; they are a necessary but not sufficient
indicator, and the honest claim is that the levels are linguistically
distinguishable in the intended direction.
"""

from django.core.management.base import BaseCommand

from core import llm, llm_config, retrieval
from evaluation import harness


class Command(BaseCommand):
    help = "T5: verify that the 1-5 difficulty ladder produces measurably different text."

    def add_arguments(self, parser):
        parser.add_argument("--reps", type=int, default=4, help="Generations per difficulty level per topic.")
        parser.add_argument("--topics", type=int, default=2, help="Number of topics to test across.")
        parser.add_argument("--dry-run", action="store_true", help="Report the planned call count and stop.")

    def handle(self, *args, **options):
        reps, n_topics = options["reps"], options["topics"]
        self.stdout.write(self.style.MIGRATE_HEADING("\nT5 — Difficulty adaptation validity"))

        topics = self._pick_topics(n_topics)
        total_calls = len(topics) * 5 * reps
        self.stdout.write(f"Topics: {', '.join(f'G{g} {t}' for t, g in topics)}")
        self.stdout.write(f"Planned generations: {len(topics)} topics x 5 levels x {reps} reps = {total_calls}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("\n--dry-run: no calls made."))
            return
        if llm_config.use_mock():
            self.stdout.write(self.style.ERROR(
                "USE_MOCK_LLM is true — mock chapters are canned and will not vary by difficulty.\n"
                "Set USE_MOCK_LLM=false in backend/.env before running T5."))
            return

        rows = self._generate(topics, reps)
        if not rows:
            self.stdout.write(self.style.ERROR("No successful generations."))
            return

        self._report(rows)

        path = harness.write_csv(
            "t5_difficulty", rows,
            ["topic", "grade", "difficulty", "rep", "fkgl", "fre", "words", "sentences",
             "words_per_sentence", "type_token_ratio", "questions", "latency_s"])
        self.stdout.write(self.style.SUCCESS(f"\nPer-generation detail: {path}"))

    def _pick_topics(self, n):
        """Choose rich topics so every difficulty level has enough grounding material."""
        probes = harness.load_probes("in_syllabus")["probes"]
        scored = []
        for probe in probes:
            content = retrieval.gather_topic_content(probe["grade"], probe["topic"])
            if content["total_relevant"] >= 4:
                scored.append((content["total_relevant"], probe["topic"], probe["grade"]))
        scored.sort(reverse=True)
        return [(topic, grade) for _, topic, grade in scored[:n]] or [("The water cycle", 7)]

    def _generate(self, topics, reps):
        budget = harness.Budget("t5_difficulty")
        model_id = llm_config.get_model()
        rows = []
        done = 0
        total = len(topics) * 5 * reps

        for topic, grade in topics:
            content = retrieval.gather_topic_content(grade, topic)
            passages = content["passages"][:4]
            for difficulty in (1, 2, 3, 4, 5):
                for rep in range(1, reps + 1):
                    done += 1
                    try:
                        import time
                        started = time.time()
                        chapter = llm.generate_chapter(
                            topic, grade, difficulty, passages=passages,
                            min_paragraphs=3, max_paragraphs=4,
                            min_questions=1, max_questions=2)
                        latency = round(time.time() - started, 2)
                        text = " ".join(chapter.get("paragraphs") or [])
                        stats = harness.readability(text)
                        rows.append({
                            "topic": topic, "grade": grade, "difficulty": difficulty, "rep": rep,
                            "fkgl": stats["fkgl"], "fre": stats["fre"],
                            "words": stats["words"], "sentences": stats["sentences"],
                            "words_per_sentence": stats["words_per_sentence"],
                            "type_token_ratio": stats["type_token_ratio"],
                            "questions": len(chapter.get("questions") or []),
                            "latency_s": latency,
                        })
                        budget.record(model_id, {"prompt_tokens": 0, "completion_tokens": 0})
                    except Exception as exc:
                        self.stdout.write(self.style.ERROR(
                            f"  [{done}/{total}] D{difficulty} rep{rep}: {type(exc).__name__}: {exc}"))
                        budget.record(model_id, {"prompt_tokens": 0, "completion_tokens": 0}, failed=True)
                    if done % 5 == 0:
                        self.stdout.write(f"  ... {done}/{total}")

        self.stdout.write(self.style.SUCCESS("\n" + budget.summary()))
        return rows

    def _report(self, rows):
        self.stdout.write(self.style.HTTP_INFO("\nReadability by configured difficulty"))
        table_rows = []
        for difficulty in (1, 2, 3, 4, 5):
            subset = [r for r in rows if r["difficulty"] == difficulty]
            if not subset:
                continue
            fkgl_m, fkgl_sd = harness.mean_sd([r["fkgl"] for r in subset])
            fre_m, _ = harness.mean_sd([r["fre"] for r in subset])
            wps_m, _ = harness.mean_sd([r["words_per_sentence"] for r in subset])
            ttr_m, _ = harness.mean_sd([r["type_token_ratio"] for r in subset])
            words_m, _ = harness.mean_sd([r["words"] for r in subset])
            table_rows.append({
                "difficulty": difficulty, "n": len(subset),
                "mean_fkgl": fkgl_m, "sd_fkgl": fkgl_sd,
                "mean_fre": fre_m, "mean_words_per_sentence": wps_m,
                "mean_ttr": ttr_m, "mean_words": words_m,
            })
        self.stdout.write(harness.table(
            table_rows, ["difficulty", "n", "mean_fkgl", "sd_fkgl", "mean_fre",
                         "mean_words_per_sentence", "mean_ttr", "mean_words"]))
        harness.write_csv("t5_difficulty_summary", table_rows,
                          ["difficulty", "n", "mean_fkgl", "sd_fkgl", "mean_fre",
                           "mean_words_per_sentence", "mean_ttr", "mean_words"])

        rho_fkgl = harness.spearman([r["difficulty"] for r in rows], [r["fkgl"] for r in rows])
        rho_fre = harness.spearman([r["difficulty"] for r in rows], [r["fre"] for r in rows])
        rho_wps = harness.spearman([r["difficulty"] for r in rows], [r["words_per_sentence"] for r in rows])
        rho_ttr = harness.spearman([r["difficulty"] for r in rows], [r["type_token_ratio"] for r in rows])

        self.stdout.write(self.style.HTTP_INFO("\nMonotonicity — Spearman's rho against configured difficulty"))
        self.stdout.write(f"  FKGL (expect POSITIVE)              rho = {rho_fkgl}")
        self.stdout.write(f"  Flesch Reading Ease (expect NEGATIVE) rho = {rho_fre}")
        self.stdout.write(f"  words per sentence (expect POSITIVE) rho = {rho_wps}")
        self.stdout.write(f"  type-token ratio (expect POSITIVE)   rho = {rho_ttr}")

        if rho_fkgl >= 0.4 and rho_fre <= -0.3:
            self.stdout.write(self.style.SUCCESS(
                "\nThe ladder moves in the intended direction: higher configured difficulty produces "
                "linguistically more complex text. Report this as evidence that difficulty adaptation is "
                "operationally real rather than a label."))
        else:
            self.stdout.write(self.style.WARNING(
                "\nThe ladder does not separate cleanly. This is a genuine finding, not a failure to hide — "
                "report it, and discuss it as evidence that prompt-level difficulty control is weaker than "
                "the design assumes. Consider whether levels 1-2 and 4-5 collapse into each other, which "
                "would argue for a three-level ladder in future work."))

        mid = [r["fkgl"] for r in rows if r["difficulty"] == 3]
        if mid:
            mid_mean, _ = harness.mean_sd(mid)
            fit = "within" if 6.0 <= mid_mean <= 9.0 else "OUTSIDE"
            self.stdout.write(
                f"\nTarget-band fit: mean FKGL at difficulty 3 is {mid_mean}, which is {fit} the "
                f"6.0-9.0 band appropriate for learners aged 11-14.")
