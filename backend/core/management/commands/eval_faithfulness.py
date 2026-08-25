"""T4 — Groundedness ablation: does retrieval actually constrain the generation?

The central safety claim of the system is that stories are grounded in the
prescribed textbooks. This experiment tests that claim by ablation: the same
model writes the same chapter with and without the retrieved passages, and the
factual content of both is scored against the textbook evidence.

    python manage.py eval_faithfulness --dry-run
    python manage.py eval_faithfulness --limit 12
    python manage.py eval_faithfulness --limit 12 --judge-model "<cheap-model-id>"

Measures per chapter:
  * FAITHFULNESS — the proportion of atomic scientific claims in the chapter that
    are supported by the retrieved passages, scored by an LLM judge following the
    definition used in the RAG evaluation literature (supported claims divided by
    total claims). The judge sees the passages and the chapter and nothing else.
  * UNSUPPORTED CLAIM COUNT — the absolute number of claims the judge could not
    trace to the evidence, which is the quantity that matters pedagogically
    because each one is a potential misconception delivered in narrative form.
  * CITATION VALIDITY — whether the page numbers the system attached as sources
    correspond to passages that were actually supplied to the model. This is
    checked deterministically, not by the judge.

VALIDATE THE JUDGE. Hand-score a subset yourself (the command writes a
ready-to-fill template) and report the agreement between your scores and the
judge's. An LLM judge with unreported agreement is not evidence; an LLM judge
with reported agreement against a human subset is a recognised method.

Cost: 2 generations + 2 judgements per topic. --limit 12 is about 48 calls.
"""

import json
import time

from django.core.management.base import BaseCommand

from core import llm, llm_config, retrieval
from evaluation import harness

JUDGE_SYSTEM = (
    "You are a strict scientific fact-checker evaluating educational text for school children. "
    "You judge ONLY whether each claim is supported by the supplied textbook excerpts. "
    "General world knowledge does NOT count as support. "
    "You always reply with a single valid JSON object and nothing else."
)

# The judge returns a short JSON verdict, but several current models spend a large,
# invisible reasoning budget before emitting it. At max_tokens=1400 deepseek-v4-flash
# returned an EMPTY visible response on 17 of 24 judgements - the parse error was
# "Expecting value: line 1 column 1", i.e. nothing to parse rather than bad JSON. The
# cap must therefore cover hidden reasoning as well as the verdict. Unused headroom
# costs nothing, since billing is per token actually generated.
JUDGE_MAX_TOKENS = 3000

JUDGE_TEMPLATE = """Below are textbook excerpts and a story chapter written for a school student.

Extract every distinct scientific claim made in the chapter (ignore narrative details such as
character names, places, dialogue and feelings — judge only statements about science).

For each claim decide:
  "supported"   - the excerpts directly state or clearly entail it
  "unsupported" - the excerpts do not establish it, even if it is true in general
  "contradicted"- the excerpts state something incompatible with it

Respond with ONLY this JSON:
{{"claims": [{{"claim": "<short quote or paraphrase>", "verdict": "supported|unsupported|contradicted"}}],
  "total_claims": <int>, "supported": <int>, "unsupported": <int>, "contradicted": <int>}}

TEXTBOOK EXCERPTS:
{passages}

CHAPTER:
{chapter}
"""


class Command(BaseCommand):
    help = "T4: ablate retrieval grounding and measure faithfulness and citation validity."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10, help="Number of topics.")
        parser.add_argument("--difficulty", type=int, default=3)
        parser.add_argument("--judge-model", type=str, default="",
                            help="Model id for judging. Defaults to the configured MODEL.")
        parser.add_argument("--max-usd", type=float, default=0.0, help="Abort above this estimated spend.")
        parser.add_argument(
            "--second-judge-model", type=str, default="",
            help="Judge the first N chapters with a SECOND model as well and report "
                 "inter-judge agreement. A single unvalidated judge is an assertion.")
        parser.add_argument("--second-judge-limit", type=int, default=6,
                            help="How many chapters the second judge also scores.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        limit = options["limit"]
        topics = self._pick_topics(limit)

        self.stdout.write(self.style.MIGRATE_HEADING("\nT4 — Groundedness ablation (RAG on vs RAG off)"))
        self.stdout.write(f"Topics ({len(topics)}): {', '.join(f'G{g} {t}' for t, g in topics)}")
        self.stdout.write(f"Planned calls: {len(topics)} x (2 generations + 2 judgements) = {len(topics) * 4}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("\n--dry-run: no calls made."))
            return
        if llm_config.use_mock():
            self.stdout.write(self.style.ERROR(
                "USE_MOCK_LLM is true — set USE_MOCK_LLM=false in backend/.env to run T4."))
            return

        judge_model = options["judge_model"] or llm_config.get_model()
        self.stdout.write(f"Judge model: {judge_model}")

        second_judge = options["second_judge_model"]
        if second_judge:
            self.stdout.write(f"Second judge: {second_judge} "
                              f"(first {options['second_judge_limit']} chapters)")
        rows = self._run(topics, options["difficulty"], judge_model, options["max_usd"],
                         second_judge, options["second_judge_limit"])
        if not rows:
            self.stdout.write(self.style.ERROR("No results collected."))
            return

        self._report(rows)
        self._report_provenance(rows)
        self._write_human_template(rows)

        path = harness.write_csv(
            "t4_faithfulness", rows,
            ["topic", "grade", "condition", "total_claims", "supported", "unsupported",
             "contradicted", "faithfulness", "sources_attached", "citations_valid",
             "ocr_passages", "ocr_share", "ocr_agreement", "faithfulness2",
             "total_claims2", "supported2", "judge2_model", "words", "fkgl", "judge_error"])
        self.stdout.write(self.style.SUCCESS(f"\nPer-chapter detail: {path}"))

    def _pick_topics(self, n):
        probes = harness.load_probes("in_syllabus")["probes"]
        scored = []
        for probe in probes:
            content = retrieval.gather_topic_content(probe["grade"], probe["topic"])
            if content["total_relevant"] >= 2:
                scored.append((content["total_relevant"], probe["topic"], probe["grade"]))
        # Mix thin and rich topics so the ablation covers both regimes.
        scored.sort()
        thin = [(t, g) for _, t, g in scored[:max(1, n // 2)]]
        rich = [(t, g) for _, t, g in scored[-(n - len(thin)):]] if n > len(thin) else []
        return (thin + rich)[:n] or [("The water cycle", 7)]

    def _run(self, topics, difficulty, judge_model, max_usd,
             second_judge="", second_judge_limit=0):
        budget = harness.Budget("t4_faithfulness")
        gen_model = llm_config.get_model()
        rows = []
        done, total = 0, len(topics) * 2

        for topic, grade in topics:
            content = retrieval.gather_topic_content(grade, topic)
            passages = content["passages"][:4]
            if not passages:
                continue
            evidence = self._format_passages(passages)

            for condition in ("rag_on", "rag_off"):
                done += 1
                supplied = passages if condition == "rag_on" else []
                ocr_n, _tot, ocr_share = harness.provenance(passages)
                row = {"topic": topic, "grade": grade, "condition": condition,
                       "total_claims": 0, "supported": 0, "unsupported": 0, "contradicted": 0,
                       "faithfulness": 0.0, "sources_attached": 0, "citations_valid": "",
                       "ocr_passages": ocr_n, "ocr_share": round(ocr_share, 4),
                       "faithfulness2": "", "total_claims2": "", "supported2": "",
                       "judge2_model": "",
                       "ocr_agreement": harness.min_agreement(passages),
                       "words": 0, "fkgl": 0.0, "judge_error": ""}
                try:
                    chapter = llm.generate_chapter(
                        topic, grade, difficulty, passages=supplied,
                        min_paragraphs=3, max_paragraphs=4, min_questions=1, max_questions=2)
                    budget.record(gen_model, {"prompt_tokens": 0, "completion_tokens": 0})

                    body = " ".join(chapter.get("paragraphs") or [])
                    stats = harness.readability(body)
                    row["words"], row["fkgl"] = stats["words"], stats["fkgl"]

                    sources = chapter.get("sources") or []
                    row["sources_attached"] = len(sources)
                    row["citations_valid"] = self._check_citations(sources, passages)

                    verdict, usage, error = self._judge(evidence, body, judge_model)
                    budget.record(judge_model, usage, failed=bool(error))
                    if error:
                        row["judge_error"] = error[:120]
                    else:
                        total_claims = int(verdict.get("total_claims") or 0)
                        supported = int(verdict.get("supported") or 0)
                        row["total_claims"] = total_claims
                        row["supported"] = supported
                        row["unsupported"] = int(verdict.get("unsupported") or 0)
                        row["contradicted"] = int(verdict.get("contradicted") or 0)
                        row["faithfulness"] = round(supported / total_claims, 4) if total_claims else 0.0

                        # A second, independent judge on the same chapter text. Both
                        # see identical evidence and identical prose, so any
                        # disagreement is the judges' and not the generator's.
                        if second_judge and len([r for r in rows if r.get("faithfulness2") != ""]) < second_judge_limit:
                            v2, u2, e2 = self._judge(evidence, body, second_judge)
                            budget.record(second_judge, u2, failed=bool(e2))
                            if not e2:
                                tc2 = int(v2.get("total_claims") or 0)
                                sup2 = int(v2.get("supported") or 0)
                                row["total_claims2"] = tc2
                                row["supported2"] = sup2
                                row["faithfulness2"] = round(sup2 / tc2, 4) if tc2 else 0.0
                                row["judge2_model"] = second_judge
                except Exception as exc:
                    row["judge_error"] = f"{type(exc).__name__}: {exc}"[:120]
                    budget.record(gen_model, {"prompt_tokens": 0, "completion_tokens": 0}, failed=True)

                rows.append(row)
                self.stdout.write(
                    f"  [{done}/{total}] {condition:8s} {topic[:30]:30s} "
                    f"faithfulness={row['faithfulness']} claims={row['total_claims']}")

                if max_usd and budget.cost > max_usd:
                    self.stdout.write(self.style.WARNING(f"\nSpend cap ${max_usd} reached — stopping."))
                    self.stdout.write(self.style.SUCCESS("\n" + budget.summary()))
                    return rows
                time.sleep(0.5)

        self.stdout.write(self.style.SUCCESS("\n" + budget.summary()))
        return rows

    @staticmethod
    def _format_passages(passages):
        parts = []
        for i, p in enumerate(passages, start=1):
            ref = f"p.{p.get('page_label_start') or p.get('page')}"
            parts.append(f"[{i}] ({ref}) {p['text']}")
        return "\n\n".join(parts)

    @staticmethod
    def _check_citations(sources, passages):
        """Deterministic check that cited pages were actually supplied to the model."""
        if not sources:
            return "no_sources"
        supplied = {str(p.get("page_label_start")) for p in passages
                    if p.get("page_label_start")}
        supplied |= {str(p.get("page")) for p in passages}   # tolerate unnumbered pages
        cited = set()
        for src in sources:
            if isinstance(src, dict):
                cited.add(str(src.get("page_label_start") or src.get("page")))
            else:
                cited.add(str(src))
        if not cited:
            return "no_pages"
        valid = len(cited & supplied)
        return f"{valid}/{len(cited)}"

    def _judge(self, evidence, chapter_text, judge_model):
        if not chapter_text.strip():
            return {}, {"prompt_tokens": 0, "completion_tokens": 0}, "empty chapter"
        messages = [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": JUDGE_TEMPLATE.format(
                passages=evidence[:9000], chapter=chapter_text[:6000])},
        ]
        try:
            with harness.use_model(judge_model):
                text, usage, _ = harness.raw_call(
                    messages, max_tokens=JUDGE_MAX_TOKENS, temperature=0.0, model=judge_model)
        except Exception as exc:
            return {}, {"prompt_tokens": 0, "completion_tokens": 0}, f"{type(exc).__name__}: {exc}"
        parsed, error = harness.parse_json(text)
        if parsed is None:
            return {}, usage, f"judge JSON invalid: {error}"
        return parsed, usage, ""

    def _report_provenance(self, rows):
        """Faithfulness split by whether the grounding passages were recovered text.

        This is the most consequential provenance report in the programme. When a
        chapter is grounded on recovered text, the "textbook evidence" the judge
        scores against is itself a transcription produced by a model, so the judge is
        comparing one model's output against another's rather than against the book.
        A faithfulness score computed over such chapters measures internal
        consistency, not fidelity to the textbook, and must not be quoted as the
        latter.
        """
        scored = [r for r in rows if not r["judge_error"] and r["total_claims"]]
        if not scored:
            return
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\nFaithfulness by provenance of the grounding passages"))
        table_rows = []
        for label, subset in (
            ("text layer only", [r for r in scored if not r.get("ocr_passages")]),
            ("includes recovered", [r for r in scored if r.get("ocr_passages")]),
        ):
            if not subset:
                continue
            faith_m, faith_sd = harness.mean_sd([r["faithfulness"] for r in subset])
            unsup_m, _ = harness.mean_sd([r["unsupported"] for r in subset])
            table_rows.append({
                "grounding": label, "n": len(subset),
                "mean_faithfulness": faith_m, "sd": faith_sd,
                "mean_unsupported": unsup_m,
            })
        self.stdout.write(harness.table(
            table_rows, ["grounding", "n", "mean_faithfulness", "sd", "mean_unsupported"]))
        harness.write_csv("t4_faithfulness_by_provenance", table_rows,
                          ["grounding", "n", "mean_faithfulness", "sd", "mean_unsupported"])
        recovered = [r for r in scored if r.get("ocr_passages")]
        if recovered:
            self.stdout.write(self.style.WARNING(
                "  CAVEAT: for the rows above that include recovered text, the evidence the"))
            self.stdout.write(self.style.WARNING(
                "  judge scores against is a model transcription of a page image, not the"))
            self.stdout.write(self.style.WARNING(
                "  text layer of the book. Their faithfulness measures consistency with that"))
            self.stdout.write(self.style.WARNING(
                "  transcription. State this wherever the T4 figure is quoted."))
        else:
            self.stdout.write(
                "  No chapter in this run was grounded on recovered text, so the T4 figure"
                " rests entirely on the text layer.")

    def _report(self, rows):
        self.stdout.write(self.style.HTTP_INFO("\nAblation results"))
        table_rows = []
        for condition in ("rag_on", "rag_off"):
            subset = [r for r in rows if r["condition"] == condition and not r["judge_error"]]
            if not subset:
                continue
            faith_m, faith_sd = harness.mean_sd([r["faithfulness"] for r in subset])
            unsup_m, _ = harness.mean_sd([r["unsupported"] for r in subset])
            contra_m, _ = harness.mean_sd([r["contradicted"] for r in subset])
            claims_m, _ = harness.mean_sd([r["total_claims"] for r in subset])
            table_rows.append({
                "condition": condition, "n": len(subset),
                "mean_faithfulness": faith_m, "sd": faith_sd,
                "mean_claims": claims_m,
                "mean_unsupported": unsup_m, "mean_contradicted": contra_m,
            })
        self.stdout.write(harness.table(
            table_rows, ["condition", "n", "mean_faithfulness", "sd", "mean_claims",
                         "mean_unsupported", "mean_contradicted"]))
        harness.write_csv("t4_faithfulness_summary", table_rows,
                          ["condition", "n", "mean_faithfulness", "sd", "mean_claims",
                           "mean_unsupported", "mean_contradicted"])

        on = next((r for r in table_rows if r["condition"] == "rag_on"), None)
        off = next((r for r in table_rows if r["condition"] == "rag_off"), None)
        if on and off:
            delta = round(on["mean_faithfulness"] - off["mean_faithfulness"], 4)
            self.stdout.write(self.style.SUCCESS(
                f"\nGrounding effect: faithfulness rises by {delta} "
                f"({off['mean_faithfulness']} -> {on['mean_faithfulness']}) when retrieval is enabled."))
            self.stdout.write(
                f"Unsupported claims per chapter fall from {off['mean_unsupported']} to "
                f"{on['mean_unsupported']}. In a narrative science tool each unsupported claim is a candidate\n"
                "misconception delivered in a memorable form, so this is the safety argument for the RAG layer,\n"
                "not merely an accuracy improvement.")

        errors = [r for r in rows if r["judge_error"]]
        if errors:
            self.stdout.write(self.style.WARNING(
                f"\n{len(errors)} judgements failed — exclude them from the means and report the exclusion."))

    def _write_human_template(self, rows):
        """Emit a blank template so the judge can be validated against your own scoring."""
        sample = [r for r in rows if not r["judge_error"]][:12]
        template = [{
            "topic": r["topic"], "grade": r["grade"], "condition": r["condition"],
            "judge_faithfulness": r["faithfulness"],
            "human_faithfulness": "", "human_notes": "",
        } for r in sample]
        path = harness.write_csv(
            "t4_judge_validation_TEMPLATE", template,
            ["topic", "grade", "condition", "judge_faithfulness", "human_faithfulness", "human_notes"])
        self.stdout.write(self.style.HTTP_INFO(
            f"\nJudge-validation template: {path}\n"
            "Fill in human_faithfulness for these chapters yourself, then report the agreement between your\n"
            "scores and the judge's in Chapter 7. Roughly 12 chapters is enough for a defensible statement,\n"
            "and it converts the automated score from an assertion into a validated instrument."))
