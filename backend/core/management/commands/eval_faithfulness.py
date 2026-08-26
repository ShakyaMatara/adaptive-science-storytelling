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
  * EVIDENCE BASE SIZE — `total_relevant`, the richness band derived from it, the
    number of passages actually supplied, and the size of the evidence block in
    characters. A faithfulness of 1.000 scored against two short, overlapping,
    activity-heavy passages is a weaker result than the same score against a
    large evidence base, and the two cannot be told apart from the score alone.

EVIDENCE PERSISTENCE (FINDING-10). Earlier versions of this command wrote the
metrics and discarded everything they were computed from: the generated prose,
the evidence block the judge saw, and the judge's per-claim verdicts all existed
only inside the process. Generation runs at temperature 0.7, so a re-run produces
a DIFFERENT chapter — the scored text was unrecoverable and the human validation
the command itself asks for was impossible to start. Every run now writes:

    t4_chapters_<stamp>.json               full audit record, one entry per chapter
    t4_judge_validation_TEMPLATE_*.csv     human columns first, judge columns after
    t4_judge_validation_BLIND_*.csv        identical, judge's scores omitted entirely
    t4_chapter_dossier_BLIND_*.md          readable scoring surface, no judge output

VALIDATE THE JUDGE. Score the BLIND copy by hand — it carries the chapter text and
the evidence and no judge output, so it cannot anchor you — then merge on `row_id`
and report the agreement. An LLM judge with unreported agreement is not evidence;
an LLM judge with reported agreement against a human subset is a recognised method.

Cost: 2 generations + 2 judgements per topic. --limit 12 is about 48 calls.
"""

import json
import time

from django.core.management.base import BaseCommand

from core import llm, llm_config, planning, retrieval
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

# What the judge is shown. Named rather than inlined so the persisted record can
# state exactly how much of the evidence and the chapter reached the judge, and
# flag the rows where something was cut off.
JUDGE_EVIDENCE_CHARS = 9000
JUDGE_CHAPTER_CHARS = 6000

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

# Columns of the per-chapter metrics CSV. Heavy text (chapter prose, evidence
# block, per-claim verdicts) is carried on the same row dicts but deliberately
# left out of this list, so the metrics file stays readable; write_csv projects
# onto these fields and the full record goes to the JSON audit file instead.
METRIC_FIELDS = [
    "row_id", "topic", "grade", "condition", "total_relevant", "richness",
    "passages_used", "evidence_chars",
    "total_claims", "supported", "unsupported", "contradicted", "faithfulness",
    "claims_listed", "claims_consistent",
    "sources_attached", "citations_valid",
    "ocr_passages", "ocr_share", "ocr_agreement",
    "faithfulness2", "total_claims2", "supported2", "judge2_model",
    "words", "fkgl", "chapter_truncated", "evidence_truncated", "judge_error",
]


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
        parser.add_argument("--validation-rows", type=int, default=12,
                            help="How many chapters to put in the human-validation template.")
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
        self._report_evidence_base(rows)
        self._report_fallbacks(rows)
        self._report_provenance(rows)

        # Persist the evidence BEFORE the metrics, so an interrupted run still
        # leaves the material an audit needs rather than only the numbers.
        self._write_audit_record(rows, judge_model, second_judge)
        self._write_human_template(rows, options["validation_rows"])

        path = harness.write_csv("t4_faithfulness", rows, METRIC_FIELDS)
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
            total_relevant = content["total_relevant"]
            evidence = self._format_passages(passages)
            evidence_shown = evidence[:JUDGE_EVIDENCE_CHARS]

            for condition in ("rag_on", "rag_off"):
                done += 1
                supplied = passages if condition == "rag_on" else []
                ocr_n, _tot, ocr_share = harness.provenance(passages)
                row = {"row_id": done, "topic": topic, "grade": grade, "condition": condition,
                       "total_relevant": total_relevant,
                       "richness": planning.richness_for(total_relevant),
                       "passages_used": len(passages),
                       "evidence_chars": len(evidence_shown),
                       "total_claims": 0, "supported": 0, "unsupported": 0, "contradicted": 0,
                       "faithfulness": 0.0, "claims_listed": "", "claims_consistent": "",
                       "sources_attached": 0, "citations_valid": "",
                       "ocr_passages": ocr_n, "ocr_share": round(ocr_share, 4),
                       "faithfulness2": "", "total_claims2": "", "supported2": "",
                       "judge2_model": "",
                       "ocr_agreement": harness.min_agreement(passages),
                       "words": 0, "fkgl": 0.0,
                       "chapter_truncated": "", "evidence_truncated": len(evidence) > len(evidence_shown),
                       "judge_error": "",
                       # --- persisted evidence, projected out of the metrics CSV ---
                       "chapter_text": "", "chapter_text_shown": "",
                       "evidence_block": evidence_shown,
                       "evidence_block_full": evidence,
                       "chapter_title": "", "chapter_summary": "",
                       "chapter_questions": [], "chapter_sources": [],
                       "judge_claims": [], "judge2_claims": [],
                       "passage_refs": self._passage_refs(passages)}
                try:
                    chapter = llm.generate_chapter(
                        topic, grade, difficulty, passages=supplied,
                        min_paragraphs=3, max_paragraphs=4, min_questions=1, max_questions=2)
                    budget.record(gen_model, {"prompt_tokens": 0, "completion_tokens": 0})

                    body = " ".join(chapter.get("paragraphs") or [])
                    stats = harness.readability(body)
                    row["words"], row["fkgl"] = stats["words"], stats["fkgl"]

                    # The prose the judge scored, kept verbatim. Without this the
                    # score cannot be checked by anyone, including its author.
                    row["chapter_text"] = body
                    row["chapter_text_shown"] = body[:JUDGE_CHAPTER_CHARS]
                    row["chapter_truncated"] = len(body) > JUDGE_CHAPTER_CHARS
                    row["chapter_title"] = chapter.get("title") or ""
                    row["chapter_summary"] = chapter.get("summary") or ""
                    row["chapter_questions"] = chapter.get("questions") or []
                    row["chapter_sources"] = chapter.get("sources") or []

                    sources = chapter.get("sources") or []
                    row["sources_attached"] = len(sources)
                    row["citations_valid"] = self._check_citations(sources, passages)

                    verdict, usage, error = self._judge(evidence_shown, body, judge_model)
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

                        # The itemised verdicts. Totals alone make a human/judge
                        # disagreement visible but not diagnosable; the claim list
                        # shows WHICH claim the two of you scored differently.
                        claims = verdict.get("claims")
                        row["judge_claims"] = claims if isinstance(claims, list) else []
                        row["claims_listed"] = len(row["judge_claims"])
                        row["claims_consistent"] = (row["claims_listed"] == total_claims)

                        # A second, independent judge on the same chapter text. Both
                        # see identical evidence and identical prose, so any
                        # disagreement is the judges' and not the generator's.
                        if second_judge and len([r for r in rows if r.get("faithfulness2") != ""]) < second_judge_limit:
                            v2, u2, e2 = self._judge(evidence_shown, body, second_judge)
                            budget.record(second_judge, u2, failed=bool(e2))
                            if not e2:
                                tc2 = int(v2.get("total_claims") or 0)
                                sup2 = int(v2.get("supported") or 0)
                                row["total_claims2"] = tc2
                                row["supported2"] = sup2
                                row["faithfulness2"] = round(sup2 / tc2, 4) if tc2 else 0.0
                                row["judge2_model"] = second_judge
                                c2 = v2.get("claims")
                                row["judge2_claims"] = c2 if isinstance(c2, list) else []
                except Exception as exc:
                    row["judge_error"] = f"{type(exc).__name__}: {exc}"[:120]
                    budget.record(gen_model, {"prompt_tokens": 0, "completion_tokens": 0}, failed=True)

                rows.append(row)
                self.stdout.write(
                    f"  [{done}/{total}] {condition:8s} {topic[:30]:30s} "
                    f"faithfulness={row['faithfulness']} claims={row['total_claims']} "
                    f"rel={total_relevant}")

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
    def _passage_refs(passages):
        """Where each supplied passage came from, for the audit record."""
        refs = []
        for i, p in enumerate(passages, start=1):
            refs.append({
                "n": i,
                "source_file": p.get("source_file"),
                "chapter": p.get("chapter"),
                "section": p.get("section"),
                "page": p.get("page"),
                "page_label_start": p.get("page_label_start"),
                "page_label_end": p.get("page_label_end"),
                "distance": p.get("distance"),
                "source_type": p.get("source_type"),
                "ocr_agreement": p.get("ocr_agreement"),
                "chars": len(p.get("text") or ""),
            })
        return refs

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
                passages=evidence[:JUDGE_EVIDENCE_CHARS],
                chapter=chapter_text[:JUDGE_CHAPTER_CHARS])},
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

    # --- evidence persistence --------------------------------------------------

    def _write_audit_record(self, rows, judge_model, second_judge):
        """Write the complete record: prose, evidence, per-claim verdicts, metrics.

        This is the file that makes every T4 number checkable after the fact. It is
        JSON rather than CSV because the judge's verdict is a LIST of claims, and
        flattening it into a cell loses exactly the structure an audit needs.
        """
        record = {
            "experiment": "T4 groundedness ablation",
            "generated_at": harness.datetime.now().isoformat(timespec="seconds"),
            "generation_model": llm_config.get_model(),
            "generation_temperature": "provider default (0.7) — generations are NOT reproducible; "
                                      "this file is the only record of the scored prose",
            "primary_judge": judge_model,
            "second_judge": second_judge or None,
            "judge_max_tokens": JUDGE_MAX_TOKENS,
            "judge_evidence_char_limit": JUDGE_EVIDENCE_CHARS,
            "judge_chapter_char_limit": JUDGE_CHAPTER_CHARS,
            "note": "In BOTH conditions the judge is shown the same textbook evidence. "
                    "rag_off means the evidence was withheld from the GENERATOR, not from "
                    "the judge.",
            "chapters": rows,
        }
        path = harness.write_json("t4_chapters", record)
        self.stdout.write(self.style.SUCCESS(
            f"\nFull audit record (prose + evidence + per-claim verdicts): {path}"))

    def _write_human_template(self, rows, n_rows=12):
        """Emit the human-validation surface: a blind copy to score from, a merge
        target that carries the judge's output, and a readable dossier.

        The blind copy exists because scoring next to the judge's number is not an
        independent measurement — it is an invitation to anchor. Score BLIND, then
        merge on row_id.
        """
        sample = [r for r in rows if not r["judge_error"] and r["chapter_text"]][:n_rows]
        if not sample:
            self.stdout.write(self.style.WARNING(
                "\nNo scorable chapters — validation template not written."))
            return

        common = []
        for r in sample:
            common.append({
                "row_id": r["row_id"], "topic": r["topic"], "grade": r["grade"],
                "condition": r["condition"], "total_relevant": r["total_relevant"],
                "richness": r["richness"], "passages_used": r["passages_used"],
                "evidence_chars": r["evidence_chars"], "words": r["words"],
                "human_total_claims": "", "human_supported": "",
                "human_faithfulness": "", "human_notes": "",
                "chapter_text": r["chapter_text_shown"],
                "evidence_block": r["evidence_block"],
            })

        blind_fields = ["row_id", "topic", "grade", "condition", "total_relevant",
                        "richness", "passages_used", "evidence_chars", "words",
                        "human_total_claims", "human_supported", "human_faithfulness",
                        "human_notes", "chapter_text", "evidence_block"]
        blind_path = harness.write_csv("t4_judge_validation_BLIND", common, blind_fields)

        by_id = {r["row_id"]: r for r in sample}
        full = []
        for row in common:
            r = by_id[row["row_id"]]
            entry = dict(row)
            entry["judge_faithfulness"] = r["faithfulness"]
            entry["judge_total_claims"] = r["total_claims"]
            entry["judge_supported"] = r["supported"]
            entry["judge_claims"] = json.dumps(r["judge_claims"], ensure_ascii=False)
            full.append(entry)

        # Human columns deliberately precede the judge's, so the eye reaches the
        # blank cell before it reaches the number that would fill it in for you.
        full_fields = blind_fields[:blind_fields.index("chapter_text")] + [
            "judge_faithfulness", "judge_total_claims", "judge_supported", "judge_claims",
            "chapter_text", "evidence_block"]
        template_path = harness.write_csv("t4_judge_validation_TEMPLATE", full, full_fields)

        dossier_path = self._write_dossier(sample)

        self.stdout.write(self.style.HTTP_INFO(
            f"\nJudge validation, {len(sample)} chapters:"
            f"\n  SCORE FROM THIS (no judge output):  {blind_path}"
            f"\n  readable version of the same:       {dossier_path}"
            f"\n  merge target (judge's scores):      {template_path}"
            "\nFill human_total_claims / human_supported / human_faithfulness in the BLIND file,"
            "\nthen merge on row_id and report the agreement in Chapter 7. Scoring beside the"
            "\njudge's number is not an independent measurement."))

    def _write_dossier(self, sample):
        """A readable per-chapter scoring surface. Nobody hand-scores from a CSV cell."""
        out = [
            "# T4 judge validation — blind scoring dossier",
            "",
            "Each entry below is one generated chapter and the textbook evidence the judge",
            "was shown, verbatim. The judge's own scores are NOT in this file. Read the",
            "chapter, count the distinct scientific claims, count how many the evidence",
            "supports, and record both in the BLIND csv against the same `row_id`.",
            "",
            "Note on conditions: in `rag_off` the evidence below was withheld from the",
            "GENERATOR but still shown to the judge. Score it against the same evidence.",
            "",
            "Only the chapter body was judged — titles, summaries and quiz questions were",
            "not shown to the judge and must not be scored.",
            "",
        ]
        for r in sample:
            out += [
                "---",
                "",
                f"## row_id {r['row_id']} — {r['topic']} (Grade {r['grade']}, {r['condition']})",
                "",
                f"Evidence base: total_relevant = {r['total_relevant']} ({r['richness']}), "
                f"passages supplied = {r['passages_used']}, "
                f"evidence block = {r['evidence_chars']} characters. "
                f"Chapter length = {r['words']} words.",
                "",
                "### Chapter, exactly as the judge received it",
                "",
                r["chapter_text_shown"],
                "",
                "### Textbook evidence, exactly as the judge received it",
                "",
                "```",
                r["evidence_block"],
                "```",
                "",
                "### Your scoring",
                "",
                "| | |",
                "|---|---|",
                "| distinct scientific claims | |",
                "| of those, supported by the evidence | |",
                "| faithfulness (supported / total) | |",
                "| notes | |",
                "",
            ]
        path = harness.write_text("t4_chapter_dossier_BLIND", "\n".join(out), ".md")
        return path

    # --- reporting -------------------------------------------------------------

    def _report_evidence_base(self, rows):
        """Faithfulness against the SIZE of the evidence it was scored on.

        A score is a ratio, and a ratio over a small denominator is cheap. Two short
        overlapping passages give the generator little to be unfaithful TO, so a
        perfect score there is a weaker result than the same score against a large
        evidence base. Reporting faithfulness without the size of the evidence base
        hides that difference.
        """
        scored = [r for r in rows if not r["judge_error"] and r["total_claims"]]
        if not scored:
            return
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\nFaithfulness against the size of the evidence base"))

        per_topic = []
        for r in sorted(scored, key=lambda x: (x["total_relevant"], x["topic"], x["condition"])):
            per_topic.append({
                "topic": r["topic"][:28], "grade": r["grade"], "condition": r["condition"],
                "total_relevant": r["total_relevant"], "richness": r["richness"],
                "passages_used": r["passages_used"], "evidence_chars": r["evidence_chars"],
                "claims": r["total_claims"], "faithfulness": r["faithfulness"],
            })
        self.stdout.write(harness.table(
            per_topic, ["topic", "grade", "condition", "total_relevant", "richness",
                        "passages_used", "evidence_chars", "claims", "faithfulness"]))
        harness.write_csv("t4_faithfulness_by_evidence_base", per_topic,
                          ["topic", "grade", "condition", "total_relevant", "richness",
                           "passages_used", "evidence_chars", "claims", "faithfulness"])

        band_rows = []
        for band in ("thin", "moderate", "rich"):
            for condition in ("rag_on", "rag_off"):
                subset = [r for r in scored
                          if r["richness"] == band and r["condition"] == condition]
                if not subset:
                    continue
                faith_m, faith_sd = harness.mean_sd([r["faithfulness"] for r in subset])
                chars_m, _ = harness.mean_sd([r["evidence_chars"] for r in subset])
                band_rows.append({
                    "richness": band, "condition": condition, "n": len(subset),
                    "mean_total_relevant": harness.mean_sd([r["total_relevant"] for r in subset])[0],
                    "mean_evidence_chars": chars_m,
                    "mean_faithfulness": faith_m, "sd": faith_sd,
                })
        if band_rows:
            self.stdout.write("")
            self.stdout.write(harness.table(
                band_rows, ["richness", "condition", "n", "mean_total_relevant",
                            "mean_evidence_chars", "mean_faithfulness", "sd"]))
            harness.write_csv("t4_faithfulness_by_richness", band_rows,
                              ["richness", "condition", "n", "mean_total_relevant",
                               "mean_evidence_chars", "mean_faithfulness", "sd"])

        on = [r for r in scored if r["condition"] == "rag_on"]
        if len(on) >= 3:
            rho_rel = harness.spearman([r["total_relevant"] for r in on],
                                       [r["faithfulness"] for r in on])
            rho_chars = harness.spearman([r["evidence_chars"] for r in on],
                                         [r["faithfulness"] for r in on])
            self.stdout.write(
                f"\nWithin rag_on (n={len(on)}): "
                f"rho(total_relevant, faithfulness) = {rho_rel}, "
                f"rho(evidence_chars, faithfulness) = {rho_chars}.")
            if rho_chars < -0.2:
                self.stdout.write(
                    "  The correlation is NEGATIVE: the highest scores sit on the smallest\n"
                    "  evidence bases, so the headline figure is carried by the topics where\n"
                    "  there was least to contradict.")
            elif rho_chars > 0.2:
                self.stdout.write(
                    "  The correlation is POSITIVE: the highest scores sit on the LARGEST\n"
                    "  evidence bases. A thin topic still has to fill the same paragraph\n"
                    "  budget, so the model must go beyond its evidence to do it, and the\n"
                    "  claims it adds are unsupported even when they are true.")
            else:
                self.stdout.write(
                    "  The correlation is near zero: on this sample the score does not track\n"
                    "  the size of the evidence base in either direction.")
            self.stdout.write(
                "  State the sign wherever the T4 figure is quoted; a ratio over a small\n"
                "  denominator is not the same measurement as a ratio over a large one.")

    def _report_fallbacks(self, rows):
        """Flag rag_on chapters that were not grounded generations at all.

        `generate_chapter` retries once on unparseable output and then returns the
        canned chapter from `mock_content`, with `sources` set to []. That is correct
        application behaviour - a learner gets a readable page instead of an error -
        but it is NOT a grounded generation, and averaging it into the rag_on mean
        measures the fallback path while reporting it as the grounding path.

        The check is deterministic: in rag_on the application always attaches source
        refs for the supplied passages, so zero sources means the fallback fired.
        """
        on = [r for r in rows if r["condition"] == "rag_on" and not r["judge_error"]]
        fell_back = [r for r in on if not r["sources_attached"]]
        if not on:
            return
        if not fell_back:
            self.stdout.write(
                "\nNo rag_on chapter came from the canned fallback path: every grounded"
                " generation parsed.")
            return
        self.stdout.write(self.style.ERROR(
            f"\n{len(fell_back)} of {len(on)} rag_on chapters came from the CANNED FALLBACK"
            " path, not from grounded generation:"))
        for r in fell_back:
            self.stdout.write(self.style.ERROR(
                f"    row_id {r['row_id']}  {r['topic']}  faithfulness={r['faithfulness']}"
                f"  claims={r['total_claims']}  words={r['words']}"))
        clean = [r for r in on if r["sources_attached"]]
        off = [r for r in rows if r["condition"] == "rag_off" and not r["judge_error"]]
        if clean and off:
            cm, csd = harness.mean_sd([r["faithfulness"] for r in clean])
            am, asd = harness.mean_sd([r["faithfulness"] for r in on])
            om, _ = harness.mean_sd([r["faithfulness"] for r in off])
            self.stdout.write(
                f"    rag_on mean AS MEASURED       {am} (sd {asd}, n={len(on)})"
                f"  -> effect {round(am - om, 4)}")
            self.stdout.write(
                f"    rag_on mean EXCLUDING fallback {cm} (sd {csd}, n={len(clean)})"
                f"  -> effect {round(cm - om, 4)}")
            self.stdout.write(
                "    Report BOTH. The first is what the pipeline produced end to end; the\n"
                "    second is what the grounding mechanism produced when it ran at all.")

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

        inconsistent = [r for r in rows
                        if r.get("claims_consistent") is False and not r["judge_error"]]
        if inconsistent:
            self.stdout.write(self.style.WARNING(
                f"\n{len(inconsistent)} judgements reported a total_claims that does not match the"
                "\nlength of the claim list they returned. The faithfulness ratio uses the reported"
                "\ntotals; the discrepancy is recorded per row as claims_listed / claims_consistent."))

        errors = [r for r in rows if r["judge_error"]]
        if errors:
            self.stdout.write(self.style.WARNING(
                f"\n{len(errors)} judgements failed — exclude them from the means and report the exclusion."))
