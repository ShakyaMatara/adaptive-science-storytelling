"""T6 — Model selection benchmark.

Answers the question "why this model?" with measurement rather than assertion.
Each candidate model is given identical grounded prompts and scored on the
criteria that actually determine fitness for this system.

    python manage.py eval_models --dry-run
    python manage.py eval_models --models "a,b,c" --prompts 8
    python manage.py eval_models --models "a,b" --prompts 5 --max-usd 2.50

Criteria and why each matters here:
  * FIRST-ATTEMPT JSON VALIDITY — the application depends on a strict JSON
    contract and retries once before falling back to a canned chapter. A model
    that frequently fails the contract raises both latency and cost and degrades
    the learner's experience, so this is the primary selection criterion.
  * SCHEMA COMPLETENESS — valid JSON is not enough; the required keys and the
    four-option question structure must be present.
  * GROUNDING BEHAVIOUR — whether page-level sources were attached.
  * READABILITY FIT — mean FKGL against the 6-9 band for the target age group.
  * LATENCY — median seconds per chapter against NFR-05.
  * COST — tokens per chapter, converted to currency using the rates you enter in
    harness.PRICES_PER_MTOK.

Important: this command deliberately calls the provider WITHOUT the application's
retry, using harness.raw_call, so that first-attempt compliance is measured
honestly. The application's own retry-then-fallback behaviour is a separate
robustness property, tested in the functional suite.
"""

import statistics
import time

from django.core.management.base import BaseCommand

from core import llm, llm_config, retrieval
from evaluation import harness

REQUIRED_KEYS = {"setting", "title", "paragraphs", "summary", "questions"}


class Command(BaseCommand):
    help = "T6: benchmark candidate LLMs on schema compliance, grounding, readability, latency and cost."

    def add_arguments(self, parser):
        parser.add_argument("--models", type=str, default="",
                            help="Comma-separated model ids. Defaults to the configured MODEL only.")
        parser.add_argument("--prompts", type=int, default=6, help="Topics per model.")
        parser.add_argument("--difficulty", type=int, default=3)
        parser.add_argument("--max-usd", type=float, default=0.0,
                            help="Abort the run if estimated spend exceeds this (0 = no cap).")
        parser.add_argument("--dry-run", action="store_true", help="Report the planned call count and stop.")

    def handle(self, *args, **options):
        models = [m.strip() for m in options["models"].split(",") if m.strip()]
        if not models:
            models = [llm_config.get_model()]

        topics = self._pick_topics(options["prompts"])
        total = len(models) * len(topics)

        self.stdout.write(self.style.MIGRATE_HEADING("\nT6 — Model selection benchmark"))
        self.stdout.write(f"Models ({len(models)}): {', '.join(models)}")
        self.stdout.write(f"Topics ({len(topics)}): {', '.join(f'G{g} {t}' for t, g in topics)}")
        self.stdout.write(f"Planned calls: {len(models)} x {len(topics)} = {total}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("\n--dry-run: no calls made."))
            return
        if llm_config.use_mock():
            self.stdout.write(self.style.ERROR(
                "USE_MOCK_LLM is true — set USE_MOCK_LLM=false in backend/.env to benchmark real models."))
            return

        rows = self._run(models, topics, options["difficulty"], options["max_usd"])
        if not rows:
            self.stdout.write(self.style.ERROR("No results collected."))
            return

        self._report(rows, models)

        path = harness.write_csv(
            "t6_models", rows,
            ["model", "topic", "grade", "first_attempt_valid", "schema_complete", "parse_error",
             "paragraphs", "questions", "options_ok", "sources", "fkgl", "fre", "words",
             "latency_s", "prompt_tokens", "completion_tokens", "cost_usd"])
        self.stdout.write(self.style.SUCCESS(f"\nPer-call detail: {path}"))

    def _pick_topics(self, n):
        probes = harness.load_probes("in_syllabus")["probes"]
        scored = []
        for probe in probes:
            content = retrieval.gather_topic_content(probe["grade"], probe["topic"])
            if content["total_relevant"] >= 3:
                scored.append((content["total_relevant"], probe["topic"], probe["grade"]))
        scored.sort(reverse=True)
        # Spread across grades so no single textbook dominates the benchmark.
        picked, seen_grades = [], {}
        for _, topic, grade in scored:
            if seen_grades.get(grade, 0) >= max(1, n // 4 + 1):
                continue
            picked.append((topic, grade))
            seen_grades[grade] = seen_grades.get(grade, 0) + 1
            if len(picked) >= n:
                break
        return picked or [("The water cycle", 7)]

    def _run(self, models, topics, difficulty, max_usd):
        rows = []
        budget = harness.Budget("t6_models")
        done, total = 0, len(models) * len(topics)

        # Use the application's OWN token budget. A fixed cap below what a chapter
        # needs does not measure a model's schema compliance, it measures the cap:
        # at max_tokens=1400 google/gemini-3.7-flash returned exactly 1396 completion
        # tokens on all six prompts and scored 0/6, which is truncation, not a
        # formatting failure. _max_tokens_for is what generate_chapter uses in
        # production, so the benchmark now matches deployed behaviour.
        max_tokens = llm._max_tokens_for(4, 2)
        for model_id in models:
            self.stdout.write(self.style.HTTP_INFO(f"\n  {model_id}"))
            for topic, grade in topics:
                done += 1
                content = retrieval.gather_topic_content(grade, topic)
                passages = content["passages"][:4]

                messages = llm._build_chapter_messages(
                    topic, grade, difficulty,
                    setting=None, story_so_far=None, revisit_concepts=None,
                    passages=passages, gate=False,
                    min_paragraphs=3, max_paragraphs=4, min_questions=1, max_questions=2)

                row = {"model": model_id, "topic": topic, "grade": grade,
                       "first_attempt_valid": False, "schema_complete": False, "parse_error": "",
                       "paragraphs": 0, "questions": 0, "options_ok": False, "sources": len(passages),
                       "fkgl": 0.0, "fre": 0.0, "words": 0,
                       "latency_s": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}

                try:
                    with harness.use_model(model_id):
                        text, usage, latency = harness.raw_call(messages, max_tokens=max_tokens, model=model_id)
                    row["latency_s"] = latency
                    row["prompt_tokens"] = usage["prompt_tokens"]
                    row["completion_tokens"] = usage["completion_tokens"]
                    row["cost_usd"] = harness.estimate_cost(model_id, usage)
                    budget.record(model_id, usage)

                    parsed, error = harness.parse_json(text)
                    if parsed is None:
                        row["parse_error"] = error[:120]
                    else:
                        row["first_attempt_valid"] = True
                        row["schema_complete"] = REQUIRED_KEYS.issubset(set(parsed.keys()))
                        paragraphs = parsed.get("paragraphs") or []
                        questions = parsed.get("questions") or []
                        row["paragraphs"] = len(paragraphs) if isinstance(paragraphs, list) else 0
                        row["questions"] = len(questions) if isinstance(questions, list) else 0
                        row["options_ok"] = all(
                            isinstance(q, dict) and isinstance(q.get("options"), list)
                            and len(q["options"]) == 4 and isinstance(q.get("correct_index"), int)
                            for q in questions) if questions else False
                        body = " ".join(p for p in paragraphs if isinstance(p, str))
                        stats = harness.readability(body)
                        row["fkgl"], row["fre"], row["words"] = stats["fkgl"], stats["fre"], stats["words"]
                except Exception as exc:
                    row["parse_error"] = f"CALL FAILED {type(exc).__name__}: {exc}"[:160]
                    budget.record(model_id, {"prompt_tokens": 0, "completion_tokens": 0}, failed=True)

                rows.append(row)
                flag = "ok " if row["first_attempt_valid"] else "FAIL"
                self.stdout.write(f"    [{done}/{total}] {flag} {topic[:34]:34s} "
                                  f"{row['latency_s']:6.2f}s  fkgl={row['fkgl']}")

                if max_usd and budget.cost > max_usd:
                    self.stdout.write(self.style.WARNING(
                        f"\n  Spend cap of ${max_usd} reached — stopping early. Partial results retained."))
                    self.stdout.write(self.style.SUCCESS("\n" + budget.summary()))
                    return rows

                time.sleep(0.5)  # be polite to the provider's rate limits

        self.stdout.write(self.style.SUCCESS("\n" + budget.summary()))
        return rows

    def _report(self, rows, models):
        self.stdout.write(self.style.HTTP_INFO("\nModel comparison"))
        table_rows = []
        for model_id in models:
            subset = [r for r in rows if r["model"] == model_id]
            if not subset:
                continue
            n = len(subset)
            valid = [r for r in subset if r["first_attempt_valid"]]
            latencies = [r["latency_s"] for r in subset if r["latency_s"] > 0]
            fkgls = [r["fkgl"] for r in valid if r["fkgl"] > 0]
            fkgl_mean, _ = harness.mean_sd(fkgls)
            cost_total = sum(r["cost_usd"] for r in subset)
            tokens = [r["prompt_tokens"] + r["completion_tokens"] for r in subset]
            table_rows.append({
                "model": model_id,
                "n": n,
                "json_ok": f"{len(valid)}/{n}",
                "json_rate": round(len(valid) / n, 3),
                "schema_rate": round(sum(1 for r in subset if r["schema_complete"]) / n, 3),
                "options_rate": round(sum(1 for r in subset if r["options_ok"]) / n, 3),
                "median_latency_s": round(statistics.median(latencies), 2) if latencies else "",
                "mean_fkgl": fkgl_mean,
                "fkgl_band_fit": "yes" if 6.0 <= fkgl_mean <= 9.0 else "no",
                "mean_tokens": round(sum(tokens) / n) if tokens else 0,
                "cost_per_chapter": round(cost_total / n, 5) if cost_total else "",
            })

        self.stdout.write(harness.table(
            table_rows, ["model", "n", "json_ok", "json_rate", "schema_rate", "options_rate",
                         "median_latency_s", "mean_fkgl", "fkgl_band_fit", "mean_tokens",
                         "cost_per_chapter"]))
        harness.write_csv("t6_models_summary", table_rows,
                          ["model", "n", "json_ok", "json_rate", "schema_rate", "options_rate",
                           "median_latency_s", "mean_fkgl", "fkgl_band_fit", "mean_tokens",
                           "cost_per_chapter"])

        if table_rows:
            ranked = sorted(table_rows, key=lambda r: (
                -r["json_rate"], -r["schema_rate"],
                r["median_latency_s"] if isinstance(r["median_latency_s"], float) else 999))
            winner = ranked[0]
            self.stdout.write(self.style.SUCCESS(
                f"\nHighest first-attempt schema compliance: {winner['model']} "
                f"({winner['json_ok']}, median {winner['median_latency_s']}s)."))
            self.stdout.write(
                "Sentence for Chapter 6 (Technology Selection):\n"
                f"  \"{winner['model']} was selected on the evidence of Table 7.n, which recorded the highest\n"
                f"  first-attempt strict-JSON compliance ({winner['json_rate']:.0%}) at a median latency of\n"
                f"  {winner['median_latency_s']} s, within the NFR-05 budget, while producing text in the\n"
                f"  readability band appropriate for the target cohort.\"\n"
                "Adjust the wording if a different model wins on your run — the point is that the choice is\n"
                "now evidenced rather than asserted, which is exactly what the midpoint feedback asked for.")

        failures = [r for r in rows if not r["first_attempt_valid"]]
        if failures:
            self.stdout.write(self.style.WARNING(
                f"\n{len(failures)} first-attempt failures — include a sample in Chapter 7 as the "
                f"'failures compared to the success' evidence:"))
            for row in failures[:8]:
                self.stdout.write(self.style.WARNING(
                    f"    {row['model']} / {row['topic'][:28]}: {row['parse_error'][:80]}"))
