"""T1 — Curricular boundary enforcement: accuracy and threshold calibration.

Measures whether the syllabus gate correctly accepts topics the learner's grade
textbook covers and refuses everything else, and calibrates GATE_MAX_DISTANCE
empirically instead of by assertion.

    python manage.py eval_gate                     # layer 1 only (free)
    python manage.py eval_gate --sweep             # + threshold sweep (free)
    python manage.py eval_gate --layer2 --limit 30 # + model adjudication (costs)

Method
------
Retrieval runs ONCE per probe and the best (smallest) embedding distance is
recorded. Because the layer-1 decision is exactly `best_distance <=
GATE_MAX_DISTANCE`, the entire threshold sweep can then be recomputed offline
over the recorded distances at zero additional cost. This is why the sweep is
free and why it is reproducible from the CSV alone.

Polarity: the positive class is "accepted as in-syllabus".
  TP = in-syllabus topic accepted        FN = in-syllabus topic wrongly refused
  TN = off-syllabus topic refused        FP = off-syllabus topic wrongly accepted

For a children's education tool a false positive (generating a story about a
topic the syllabus does not cover) is the more damaging error, so specificity is
reported alongside recall and the sweep reports both.
"""

from django.core.management.base import BaseCommand

from core import retrieval
from evaluation import harness


class Command(BaseCommand):
    help = "T1: evaluate and calibrate the syllabus gate (curricular boundary enforcement)."

    def add_arguments(self, parser):
        parser.add_argument("--sweep", action="store_true",
                            help="Recompute metrics across a range of thresholds (free).")
        parser.add_argument("--sweep-min", type=float, default=0.80)
        parser.add_argument("--sweep-max", type=float, default=1.60)
        parser.add_argument("--sweep-step", type=float, default=0.05)
        parser.add_argument("--layer2", action="store_true",
                            help="Also run the model adjudication layer (makes paid calls).")
        parser.add_argument("--limit", type=int, default=0,
                            help="Cap the number of probes sent to layer 2.")

    def handle(self, *args, **options):
        gate = retrieval.GATE_MAX_DISTANCE
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nT1 — Syllabus gate evaluation (current GATE_MAX_DISTANCE = {gate})"))

        rows = self._measure()
        if not rows:
            self.stdout.write(self.style.ERROR("No probes measured — is the Chroma index built?"))
            return

        metrics = self._score(rows, gate)
        self._report_headline(metrics, rows, gate)
        self._report_provenance(rows)
        self._report_by_family(rows, gate)

        if options["sweep"]:
            self._sweep(rows, options["sweep_min"], options["sweep_max"], options["sweep_step"], gate)

        if options["layer2"]:
            self._layer2(rows, options["limit"])

        path = harness.write_csv(
            "t1_gate", rows,
            ["set", "family", "topic", "grade", "correct_grade", "expected",
             "best_distance", "kept_passages", "ocr_passages", "ocr_share",
             "layer1_accept", "layer2_in_syllabus", "layer2_reason", "correct"])
        self.stdout.write(self.style.SUCCESS(f"\nPer-probe detail: {path}"))

    def _report_provenance(self, rows):
        """How much of the accepted evidence is text recovered from page images."""
        accepted = [r for r in rows if r.get("kept_passages")]
        touched = [r for r in accepted if r.get("ocr_passages")]
        if not accepted:
            return
        self.stdout.write(self.style.MIGRATE_HEADING("\nProvenance of the retrieved evidence"))
        self.stdout.write(
            f"  Topics whose kept passages include recovered text: {len(touched)}/{len(accepted)}")
        if touched:
            wholly = [r for r in touched if r["ocr_share"] >= 0.999]
            self.stdout.write(f"  ...of which wholly recovered: {len(wholly)}")
            mean_share = sum(r["ocr_share"] for r in touched) / len(touched)
            self.stdout.write(f"  Mean recovered share among those topics: {mean_share:.1%}")
            for r in sorted(touched, key=lambda x: -x["ocr_share"])[:8]:
                self.stdout.write(f"     grade {r['grade']} {r['topic'][:44]:<44} "
                                  f"{r['ocr_passages']}/{r['kept_passages']} passages "
                                  f"({r['ocr_share']:.0%})")
        self.stdout.write(
            "  Recovered text was transcribed from page images and verified against a second\n"
            "  extraction (see results/g9p1_coverage_gap.md); results resting on it should be\n"
            "  read with that in mind.")

    # --- measurement ------------------------------------------------------------

    def _best_distance(self, grade, topic):
        passages = retrieval.retrieve(grade, topic, k=10)
        scored = [p["distance"] for p in passages if p.get("distance") is not None]
        return min(scored) if scored else None

    def _measure(self):
        """One retrieval per probe; record the raw distance for offline sweeping."""
        rows = []

        for probe in harness.load_probes("in_syllabus")["probes"]:
            grade, topic = probe["grade"], probe["topic"]
            content = retrieval.gather_topic_content(grade, topic)
            recovered, total, share = harness.provenance(content["passages"])
            rows.append({
                "set": "in_syllabus", "family": "positive", "topic": topic, "grade": grade,
                "correct_grade": grade, "expected": "accept",
                "best_distance": self._best_distance(grade, topic),
                "kept_passages": content["total_relevant"],
                "ocr_passages": recovered,
                "ocr_share": round(share, 4),
            })

        for probe in harness.load_probes("off_syllabus")["probes"]:
            topic, family = probe["topic"], probe.get("family", "other")
            for grade in (6, 7, 8, 9):
                content = retrieval.gather_topic_content(grade, topic)
                rows.append({
                    "set": "off_syllabus", "family": family, "topic": topic, "grade": grade,
                    "correct_grade": "", "expected": "refuse",
                    "best_distance": self._best_distance(grade, topic),
                    "kept_passages": content["total_relevant"],
                })

        for probe in harness.load_probes("grade_boundary")["probes"]:
            grade, topic = probe["grade"], probe["topic"]
            content = retrieval.gather_topic_content(grade, topic)
            rows.append({
                "set": "grade_boundary", "family": "grade-boundary", "topic": topic, "grade": grade,
                "correct_grade": probe.get("correct_grade", ""), "expected": "refuse",
                "best_distance": self._best_distance(grade, topic),
                "kept_passages": content["total_relevant"],
            })

        self.stdout.write(f"Measured {len(rows)} probe/grade combinations "
                          f"({sum(1 for r in rows if r['expected'] == 'accept')} positive, "
                          f"{sum(1 for r in rows if r['expected'] == 'refuse')} negative).")
        return rows

    # --- scoring ----------------------------------------------------------------

    @staticmethod
    def _accepts(row, threshold):
        best = row["best_distance"]
        return best is not None and best <= threshold

    def _score(self, rows, threshold):
        tp = fp = tn = fn = 0
        for row in rows:
            accepted = self._accepts(row, threshold)
            row["layer1_accept"] = accepted
            row["correct"] = (accepted and row["expected"] == "accept") or \
                             (not accepted and row["expected"] == "refuse")
            if row["expected"] == "accept":
                tp += 1 if accepted else 0
                fn += 0 if accepted else 1
            else:
                fp += 1 if accepted else 0
                tn += 0 if accepted else 1
        return harness.confusion(tp, fp, tn, fn)

    def _report_headline(self, m, rows, threshold):
        self.stdout.write(self.style.HTTP_INFO("\nConfusion matrix (positive = accepted as in-syllabus)"))
        self.stdout.write(f"  TP {m['tp']:4d}   FN {m['fn']:4d}      (in-syllabus topics)")
        self.stdout.write(f"  FP {m['fp']:4d}   TN {m['tn']:4d}      (off-syllabus and grade-boundary topics)")
        self.stdout.write(
            f"\n  accuracy={m['accuracy']}  precision={m['precision']}  recall={m['recall']}  "
            f"specificity={m['specificity']}  F1={m['f1']}")

        misses = [r for r in rows if not r["correct"]]
        if misses:
            self.stdout.write(self.style.WARNING(f"\n  {len(misses)} misclassified probes (report these as "
                                                 f"failure analysis in Chapter 7):"))
            for row in misses[:15]:
                best = row["best_distance"]
                self.stdout.write(self.style.WARNING(
                    f"    G{row['grade']} '{row['topic']}' expected={row['expected']} "
                    f"best_distance={round(best, 4) if best is not None else 'none'}"))
            if len(misses) > 15:
                self.stdout.write(self.style.WARNING(f"    ... and {len(misses) - 15} more (see CSV)."))

    def _report_by_family(self, rows, threshold):
        families = {}
        for row in rows:
            fam = families.setdefault(row["family"], {"n": 0, "correct": 0, "distances": []})
            fam["n"] += 1
            fam["correct"] += 1 if row["correct"] else 0
            if row["best_distance"] is not None:
                fam["distances"].append(row["best_distance"])

        table_rows = []
        for name, data in sorted(families.items()):
            mean, sd = harness.mean_sd(data["distances"])
            table_rows.append({
                "family": name, "n": data["n"],
                "correct": data["correct"],
                "rate": round(data["correct"] / data["n"], 3) if data["n"] else 0,
                "mean_best_distance": mean, "sd": sd,
            })
        self.stdout.write(self.style.HTTP_INFO("\nBreakdown by probe family"))
        self.stdout.write(harness.table(table_rows,
                                        ["family", "n", "correct", "rate", "mean_best_distance", "sd"]))
        harness.write_csv("t1_gate_by_family", table_rows,
                          ["family", "n", "correct", "rate", "mean_best_distance", "sd"])

    # --- threshold sweep (free) --------------------------------------------------

    def _sweep(self, rows, lo, hi, step, current):
        self.stdout.write(self.style.HTTP_INFO(
            "\nThreshold sweep — recomputed offline over the recorded distances (no extra cost)"))
        sweep_rows, best = [], None
        threshold = lo
        while threshold <= hi + 1e-9:
            m = self._score(list(rows), threshold)
            entry = {"threshold": round(threshold, 3), **m,
                     "is_current": "<-- current" if abs(threshold - current) < 1e-9 else ""}
            sweep_rows.append(entry)
            if best is None or m["f1"] > best["f1"]:
                best = entry
            threshold += step

        self.stdout.write(harness.table(
            sweep_rows, ["threshold", "tp", "fp", "tn", "fn", "accuracy", "recall", "specificity", "f1", "is_current"]))

        # Re-score at the configured threshold so the CSV reflects live behaviour.
        self._score(rows, current)

        path = harness.write_csv("t1_gate_sweep", sweep_rows,
                                 ["threshold", "tp", "fp", "tn", "fn", "accuracy",
                                  "precision", "recall", "specificity", "f1", "is_current"])
        self.stdout.write(self.style.SUCCESS(
            f"\nBest F1 at threshold {best['threshold']} (F1={best['f1']}); "
            f"configured value is {current}."))
        if abs(best["threshold"] - current) > 1e-9:
            self.stdout.write(
                "If the optimum differs from the configured value, either retune the constant and re-run, or "
                "state in Chapter 7 why the configured value is preferred — e.g. the optimum trades "
                "specificity for recall, and for a children's tool a false acceptance is the costlier error.")
        self.stdout.write(self.style.SUCCESS(f"Sweep data: {path}"))

    # --- optional layer 2 (paid) -------------------------------------------------

    def _layer2(self, rows, limit):
        """Run the model adjudication layer on probes that PASSED layer 1.

        Layer 2 only ever sees topics layer 1 accepted, so this measures how many
        of layer 1's false positives the model catches — the value added by the
        second stage, which is the number worth reporting.
        """
        from core import llm, llm_config

        if llm_config.use_mock():
            self.stdout.write(self.style.WARNING(
                "\nUSE_MOCK_LLM is true — layer 2 skipped. Set USE_MOCK_LLM=false in backend/.env to run it."))
            return

        candidates = [r for r in rows if r["layer1_accept"]]
        if limit:
            candidates = candidates[:limit]
        self.stdout.write(self.style.HTTP_INFO(
            f"\nLayer 2 — model adjudication on {len(candidates)} layer-1 acceptances (paid calls)"))

        budget = harness.Budget("t1_layer2")
        model_id = llm_config.get_model()
        caught = 0

        for i, row in enumerate(candidates, start=1):
            content = retrieval.gather_topic_content(row["grade"], row["topic"])
            try:
                result = llm.generate_chapter(
                    row["topic"], row["grade"], difficulty=3,
                    passages=content["passages"], gate=True,
                    min_paragraphs=2, max_paragraphs=3, min_questions=0, max_questions=1)
                in_syllabus = bool(result.get("in_syllabus", True))
                row["layer2_in_syllabus"] = in_syllabus
                row["layer2_reason"] = (result.get("reason") or "")[:160]
                budget.record(model_id, {"prompt_tokens": 0, "completion_tokens": 0})
                if row["expected"] == "refuse" and not in_syllabus:
                    caught += 1
            except Exception as exc:
                row["layer2_in_syllabus"] = ""
                row["layer2_reason"] = f"ERROR {type(exc).__name__}"
                budget.record(model_id, {"prompt_tokens": 0, "completion_tokens": 0}, failed=True)
            if i % 5 == 0:
                self.stdout.write(f"  ... {i}/{len(candidates)}")

        leaks = [r for r in candidates if r["expected"] == "refuse"]
        self.stdout.write(
            f"\n  Layer-1 false positives passed to layer 2: {len(leaks)}\n"
            f"  Caught by layer 2: {caught}"
            + (f" ({round(100 * caught / len(leaks), 1)}%)" if leaks else ""))
        self.stdout.write(
            "  Report this as the two-stage gate result: layer 1 is deterministic and free, layer 2 recovers "
            "the residual. The combined figure is the one to quote as the system's boundary accuracy.")
        self.stdout.write(self.style.SUCCESS("\n" + budget.summary()))
