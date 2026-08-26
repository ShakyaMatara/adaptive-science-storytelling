"""T2 — Assessment-integrity gate: attack resistance and false-positive cost.

Measures the deterministic similarity gate that prevents the grounded Q&A panel
from answering a quiz question the learner has not yet attempted.

    python manage.py eval_anticheat            # per-class results (free)
    python manage.py eval_anticheat --sweep    # + threshold sweep (free)

Method
------
The similarity ratio between each probe and its base question is computed ONCE
using exactly the application's normalisation and comparison (core.views
._normalise_text plus difflib.SequenceMatcher). Because the gate's decision is
`ratio >= SIMILARITY_THRESHOLD`, the whole sweep is then recomputed offline over
the recorded ratios. No model calls are made, so this experiment is free and
fully deterministic — the same input always yields the same number, which is
itself a property worth reporting.

Polarity: the positive class is "the gate blocked the question".
  TP = attack blocked            FN = attack leaked through
  TN = legitimate question allowed   FP = legitimate question wrongly blocked

Both directions matter. A gate tuned to block everything achieves perfect attack
recall and destroys the tutoring function, so the false-positive rate on the
`legitimate` class is reported as a first-class result rather than a footnote.
"""

import difflib

from django.core.management.base import BaseCommand

from core.views import SIMILARITY_THRESHOLD, _normalise_text
from evaluation import harness

ATTACK_CLASSES = ["verbatim", "surface", "lexical", "reorder", "paraphrase"]
ALLOW_CLASSES = ["legitimate"]


class Command(BaseCommand):
    help = "T2: evaluate the assessment-integrity similarity gate against paraphrase attacks."

    def add_arguments(self, parser):
        parser.add_argument("--sweep", action="store_true", help="Sweep the similarity threshold (free).")
        parser.add_argument("--sweep-min", type=float, default=0.30)
        parser.add_argument("--sweep-max", type=float, default=0.95)
        parser.add_argument("--sweep-step", type=float, default=0.05)

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nT2 — Assessment-integrity gate (current SIMILARITY_THRESHOLD = {SIMILARITY_THRESHOLD})"))

        rows = self._measure()
        self._score(rows, SIMILARITY_THRESHOLD)
        self._report(rows, SIMILARITY_THRESHOLD)

        if options["sweep"]:
            self._sweep(rows, options["sweep_min"], options["sweep_max"], options["sweep_step"])

        path = harness.write_csv("t2_anticheat", rows,
                                 ["item", "class", "kind", "base", "probe", "ratio", "blocked", "correct"])
        self.stdout.write(self.style.SUCCESS(f"\nPer-probe detail: {path}"))

    # --- measurement -------------------------------------------------------------

    def _measure(self):
        """Compute the similarity ratio for every probe using the app's own logic."""
        data = harness.load_probes("anticheat")
        rows = []
        for index, item in enumerate(data["items"], start=1):
            base = item["base"]
            base_norm = _normalise_text(base)
            for cls in ATTACK_CLASSES + ALLOW_CLASSES:
                probe = item.get(cls)
                if not probe:
                    continue
                ratio = difflib.SequenceMatcher(None, _normalise_text(probe), base_norm).ratio()
                rows.append({
                    "item": index,
                    "class": cls,
                    "kind": "attack" if cls in ATTACK_CLASSES else "legitimate",
                    "base": base,
                    "probe": probe,
                    "ratio": round(ratio, 4),
                })
        self.stdout.write(f"Measured {len(rows)} probes across {len(data['items'])} base questions.")
        return rows

    @staticmethod
    def _score(rows, threshold):
        for row in rows:
            blocked = row["ratio"] >= threshold
            row["blocked"] = blocked
            # Correct = attack blocked, or legitimate question allowed.
            row["correct"] = blocked if row["kind"] == "attack" else (not blocked)
        return rows

    def _metrics(self, rows):
        tp = sum(1 for r in rows if r["kind"] == "attack" and r["blocked"])
        fn = sum(1 for r in rows if r["kind"] == "attack" and not r["blocked"])
        fp = sum(1 for r in rows if r["kind"] == "legitimate" and r["blocked"])
        tn = sum(1 for r in rows if r["kind"] == "legitimate" and not r["blocked"])
        return harness.confusion(tp, fp, tn, fn)

    # --- reporting ---------------------------------------------------------------

    def _report(self, rows, threshold):
        m = self._metrics(rows)
        self.stdout.write(self.style.HTTP_INFO("\nOverall (positive = gate blocked the question)"))
        self.stdout.write(f"  TP {m['tp']:4d}   FN {m['fn']:4d}      (attacks)")
        self.stdout.write(f"  FP {m['fp']:4d}   TN {m['tn']:4d}      (legitimate questions)")
        self.stdout.write(f"\n  accuracy={m['accuracy']}  precision={m['precision']}  "
                          f"recall={m['recall']}  specificity={m['specificity']}  F1={m['f1']}")

        self.stdout.write(self.style.HTTP_INFO("\nBy perturbation class (layer-1 catch rate)"))
        class_rows = []
        for cls in ATTACK_CLASSES + ALLOW_CLASSES:
            subset = [r for r in rows if r["class"] == cls]
            if not subset:
                continue
            blocked = sum(1 for r in subset if r["blocked"])
            mean, sd = harness.mean_sd([r["ratio"] for r in subset])
            class_rows.append({
                "class": cls,
                "n": len(subset),
                "blocked": blocked,
                "block_rate": round(blocked / len(subset), 3),
                "desired": "block" if cls in ATTACK_CLASSES else "allow",
                "mean_ratio": mean,
                "sd": sd,
            })
        self.stdout.write(harness.table(
            class_rows, ["class", "n", "blocked", "block_rate", "desired", "mean_ratio", "sd"]))
        harness.write_csv("t2_anticheat_by_class", class_rows,
                          ["class", "n", "blocked", "block_rate", "desired", "mean_ratio", "sd"])

        leaks = [r for r in rows if r["kind"] == "attack" and not r["blocked"]]
        if leaks:
            self.stdout.write(self.style.WARNING(
                f"\n{len(leaks)} attacks passed layer 1 — these are handled by the layer-2 model instruction "
                f"(llm.answer_question avoid_questions). Report them as the residual layer 1 is not designed "
                f"to catch, and note that catching them deterministically would require lowering the threshold "
                f"below the point at which legitimate questions start being blocked:"))
            for row in leaks[:12]:
                self.stdout.write(self.style.WARNING(
                    f"    [{row['class']}] ratio={row['ratio']}  \"{row['probe'][:64]}\""))

        false_blocks = [r for r in rows if r["kind"] == "legitimate" and r["blocked"]]
        if false_blocks:
            self.stdout.write(self.style.ERROR(
                f"\n{len(false_blocks)} legitimate questions were wrongly blocked — this is the pedagogical "
                f"cost of the gate and must be reported:"))
            for row in false_blocks[:12]:
                self.stdout.write(self.style.ERROR(
                    f"    ratio={row['ratio']}  \"{row['probe'][:64]}\""))
        else:
            self.stdout.write(self.style.SUCCESS(
                "\nNo legitimate questions were blocked at the configured threshold — the gate is "
                "conservative in the correct direction."))

    # --- sweep (free) ------------------------------------------------------------

    def _sweep(self, rows, lo, hi, step):
        self.stdout.write(self.style.HTTP_INFO(
            "\nThreshold sweep — recomputed offline over the recorded ratios (no extra cost)"))
        sweep_rows, best = [], None
        threshold = lo
        while threshold <= hi + 1e-9:
            self._score(rows, threshold)
            m = self._metrics(rows)
            entry = {
                "threshold": round(threshold, 3), **m,
                "attack_catch_rate": m["recall"],
                "legit_false_block_rate": round(1 - m["specificity"], 4),
                "is_current": "<-- current" if abs(threshold - SIMILARITY_THRESHOLD) < 1e-9 else "",
            }
            sweep_rows.append(entry)
            if best is None or m["f1"] > best["f1"]:
                best = entry
            threshold += step

        self.stdout.write(harness.table(
            sweep_rows, ["threshold", "tp", "fn", "fp", "tn", "attack_catch_rate",
                         "legit_false_block_rate", "f1", "is_current"]))

        # Restore the live decision so the per-probe CSV matches deployed behaviour.
        self._score(rows, SIMILARITY_THRESHOLD)

        path = harness.write_csv("t2_anticheat_sweep", sweep_rows,
                                 ["threshold", "tp", "fp", "tn", "fn", "accuracy", "precision",
                                  "recall", "specificity", "f1", "attack_catch_rate",
                                  "legit_false_block_rate", "is_current"])
        self.stdout.write(self.style.SUCCESS(
            f"\nBest F1 at threshold {best['threshold']} (F1={best['f1']}); configured value is "
            f"{SIMILARITY_THRESHOLD}."))
        self.stdout.write(
            "The operating-point argument for Chapter 7: choose the threshold at the knee where attack catch "
            "rate is still high but the legitimate false-block rate has not yet risen, and justify the choice "
            "by the asymmetry of the two errors — a blocked legitimate question frustrates a learner, whereas "
            "a leaked answer invalidates the assessment.")
        self.stdout.write(self.style.SUCCESS(f"Sweep data: {path}"))
