"""Generate the Chapter 7 figures from the result CSVs.

    pip install matplotlib
    python manage.py eval_charts

Reads the `*_latest.csv` files written by the eval commands and produces 300 dpi
PNGs in evaluation/results/figures/, sized for a 1.5-spaced A4 report. Missing
inputs are skipped with a note rather than raising, so the command can be run at
any point during the experiment programme.

Figures produced:
  fig_t1_sweep.png        gate accuracy vs threshold, with the configured value marked
  fig_t1_distances.png    distribution of best retrieval distance by probe family
  fig_t2_sweep.png        attack catch rate vs legitimate false-block rate
  fig_t2_by_class.png     layer-1 catch rate per perturbation class
  fig_t3_scatter.png      textbook coverage vs planned chapters (the CDIS result)
  fig_t3_richness.png     mean chapters and questions by richness band
  fig_t5_difficulty.png   FKGL by configured difficulty, with the 6-9 target band
  fig_t6_models.png       first-attempt JSON validity and latency by model
  fig_t4_ablation.png     faithfulness with and without retrieval grounding
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand

from evaluation import harness

FIG_DIR = harness.RESULTS_DIR / "figures"


class Command(BaseCommand):
    help = "Generate Chapter 7 figures from the evaluation result CSVs."

    def handle(self, *args, **options):
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            self.stdout.write(self.style.ERROR("matplotlib is required: pip install matplotlib"))
            return

        FIG_DIR.mkdir(parents=True, exist_ok=True)
        plt.rcParams.update({
            "figure.dpi": 300, "savefig.dpi": 300, "font.size": 9,
            "axes.grid": True, "grid.alpha": 0.3, "axes.spines.top": False,
            "axes.spines.right": False,
        })

        made = []
        for builder in (self._t1_sweep, self._t1_distances, self._t2_sweep, self._t2_by_class,
                        self._t3_scatter, self._t3_richness, self._t5_difficulty,
                        self._t6_models, self._t4_ablation):
            try:
                name = builder(plt)
                if name:
                    made.append(name)
            except FileNotFoundError as exc:
                self.stdout.write(self.style.WARNING(f"  skipped: {exc}"))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  failed {builder.__name__}: {exc}"))

        if made:
            self.stdout.write(self.style.SUCCESS(f"\n{len(made)} figures written to {FIG_DIR}"))
            for name in made:
                self.stdout.write(f"  {name}")
            self.stdout.write(
                "\nEvery figure needs a caption in the thesis stating what it illustrates — the APIIT "
                "guidance is explicit about this and it is a cheap mark to lose.")
        else:
            self.stdout.write(self.style.WARNING("\nNo figures produced — run the eval commands first."))

    # --- helpers -------------------------------------------------------------

    @staticmethod
    def _read(name):
        path = harness.RESULTS_DIR / f"{name}_latest.csv"
        if not path.exists():
            raise FileNotFoundError(f"{path.name} not found — run the matching eval command first.")
        with open(path, "r", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    @staticmethod
    def _f(row, key, default=0.0):
        try:
            return float(row.get(key) or default)
        except (TypeError, ValueError):
            return default

    def _save(self, plt, fig, name):
        fig.tight_layout()
        fig.savefig(FIG_DIR / name, bbox_inches="tight")
        plt.close(fig)
        return name

    # matplotlib 3.9 deprecated boxplot(labels=...) and 3.11 removed it in favour of
    # tick_labels. This harness runs on 3.11, so the newer spelling is used.

    # --- T1 -------------------------------------------------------------------

    def _t1_sweep(self, plt):
        rows = self._read("t1_gate_sweep_verbatim")
        x = [self._f(r, "threshold") for r in rows]
        fig, ax = plt.subplots(figsize=(6, 3.4))
        ax.plot(x, [self._f(r, "recall") for r in rows], marker="o", ms=3,
                label="Recall (in-syllabus accepted)")
        ax.plot(x, [self._f(r, "specificity") for r in rows], marker="s", ms=3,
                label="Specificity (off-syllabus refused)")
        ax.plot(x, [self._f(r, "f1") for r in rows], marker="^", ms=3, label="F1")
        para = self._read("t1_gate_sweep_paraphrased")
        if para:
            ax.plot([self._f(r, "threshold") for r in para],
                    [self._f(r, "recall") for r in para], marker="o", ms=3, ls=":",
                    color="tab:blue", alpha=0.8, label="Recall (learner phrasing)")
        current = next((self._f(r, "threshold") for r in rows if r.get("is_current")), None)
        if current is not None:
            ax.axvline(current, color="crimson", ls="--", lw=1,
                       label=f"Configured = {current}")
        ax.set_xlabel("GATE_MAX_DISTANCE threshold")
        ax.set_ylabel("Score")
        ax.set_ylim(0, 1.05)
        ax.set_title("Syllabus gate across thresholds: contents-page vs learner phrasing")
        ax.legend(fontsize=7, loc="lower center", ncol=2)
        return self._save(plt, fig, "fig_t1_sweep.png")

    def _t1_distances(self, plt):
        rows = self._read("t1_gate_verbatim")
        families, data = [], []
        for row in rows:
            fam = row.get("family") or "other"
            if fam not in families:
                families.append(fam)
        for fam in families:
            data.append([self._f(r, "best_distance") for r in rows
                         if (r.get("family") or "other") == fam and r.get("best_distance")])
        families = [f for f, d in zip(families, data) if d]
        data = [d for d in data if d]
        fig, ax = plt.subplots(figsize=(6.5, 3.4))
        ax.boxplot(data, tick_labels=families, showfliers=True)
        try:
            from core import retrieval
            ax.axhline(retrieval.GATE_MAX_DISTANCE, color="crimson", ls="--", lw=1,
                       label=f"GATE_MAX_DISTANCE = {retrieval.GATE_MAX_DISTANCE}")
            ax.legend(fontsize=7)
        except Exception:
            pass
        ax.set_ylabel("Best retrieval distance (lower = closer)")
        ax.set_title("Separation between in-syllabus and off-syllabus topics")
        plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
        return self._save(plt, fig, "fig_t1_distances.png")

    # --- T2 -------------------------------------------------------------------

    def _t2_sweep(self, plt):
        rows = self._read("t2_anticheat_sweep")
        x = [self._f(r, "threshold") for r in rows]
        fig, ax = plt.subplots(figsize=(6, 3.4))
        ax.plot(x, [self._f(r, "attack_catch_rate") for r in rows], marker="o", ms=3,
                label="Attacks blocked")
        ax.plot(x, [self._f(r, "legit_false_block_rate") for r in rows], marker="s", ms=3,
                color="darkorange", label="Legitimate questions wrongly blocked")
        current = next((self._f(r, "threshold") for r in rows if r.get("is_current")), None)
        if current is not None:
            ax.axvline(current, color="crimson", ls="--", lw=1, label=f"Configured = {current}")
        ax.set_xlabel("SIMILARITY_THRESHOLD")
        ax.set_ylabel("Rate")
        ax.set_ylim(-0.02, 1.05)
        ax.set_title("Assessment-integrity gate: protection against pedagogical cost")
        ax.legend(fontsize=7)
        return self._save(plt, fig, "fig_t2_sweep.png")

    def _t2_by_class(self, plt):
        rows = self._read("t2_anticheat_by_class")
        labels = [r["class"] for r in rows]
        values = [self._f(r, "block_rate") for r in rows]
        colours = ["steelblue" if r.get("desired") == "block" else "darkorange" for r in rows]
        fig, ax = plt.subplots(figsize=(6, 3.2))
        ax.bar(labels, values, color=colours)
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("Proportion blocked by layer 1")
        ax.set_title("Deterministic gate performance by perturbation class")
        for i, v in enumerate(values):
            ax.text(i, v + 0.02, f"{v:.2f}", ha="center", fontsize=7)
        ax.text(0.99, 0.02, "blue = should block   orange = should allow",
                transform=ax.transAxes, ha="right", fontsize=7, style="italic")
        plt.setp(ax.get_xticklabels(), rotation=15, ha="right")
        return self._save(plt, fig, "fig_t2_by_class.png")

    # --- T3 -------------------------------------------------------------------

    def _t3_scatter(self, plt):
        rows = self._read("t3_planner")
        manual = [r for r in rows if r.get("gt_pages")]
        use_manual = len(manual) >= 3
        source = manual if use_manual else rows
        x_key = "gt_pages" if use_manual else "distinct_pages"
        x_label = ("Textbook pages covering the topic (manual count)" if use_manual
                   else "Distinct textbook pages retrieved")
        xs = [self._f(r, x_key) for r in source]
        ys = [self._f(r, "chapters") for r in source]
        qs = [self._f(r, "max_questions") for r in source]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.2, 3.2))
        ax1.scatter(xs, ys, s=26, alpha=0.75, color="steelblue")
        ax1.set_xlabel(x_label, fontsize=8)
        ax1.set_ylabel("Chapters planned")
        ax1.set_title(f"Coverage vs chapters (rho = {harness.spearman(xs, ys)})", fontsize=9)

        ax2.scatter(xs, qs, s=26, alpha=0.75, color="seagreen")
        ax2.set_xlabel(x_label, fontsize=8)
        ax2.set_ylabel("Questions planned")
        ax2.set_title(f"Coverage vs questions (rho = {harness.spearman(xs, qs)})", fontsize=9)

        fig.suptitle("Content-Derived Instructional Scaling tracks curricular coverage", fontsize=10)
        return self._save(plt, fig, "fig_t3_scatter.png")

    def _t3_richness(self, plt):
        rows = self._read("t3_planner_by_richness")
        labels = [r["richness"] for r in rows]
        chapters = [self._f(r, "mean_chapters") for r in rows]
        questions = [self._f(r, "mean_questions") for r in rows]
        ch_sd = [self._f(r, "sd_chapters") for r in rows]
        q_sd = [self._f(r, "sd_questions") for r in rows]
        width, positions = 0.38, range(len(labels))
        fig, ax = plt.subplots(figsize=(5.4, 3.2))
        ax.bar([p - width / 2 for p in positions], chapters, width, yerr=ch_sd,
               capsize=3, label="Mean chapters", color="steelblue")
        ax.bar([p + width / 2 for p in positions], questions, width, yerr=q_sd,
               capsize=3, label="Mean questions", color="seagreen")
        ax.set_xticks(list(positions))
        ax.set_xticklabels(labels)
        ax.set_ylabel("Count")
        ax.set_title("Planned instructional volume by measured richness band")
        ax.legend(fontsize=7)
        return self._save(plt, fig, "fig_t3_richness.png")

    # --- T5 -------------------------------------------------------------------

    def _t5_difficulty(self, plt):
        rows = self._read("t5_difficulty_summary")
        detail = self._read("t5_difficulty")
        levels = [int(self._f(r, "difficulty")) for r in rows]
        means = [self._f(r, "mean_fkgl") for r in rows]
        sds = [self._f(r, "sd_fkgl") for r in rows]

        fig, ax = plt.subplots(figsize=(6, 3.4))
        ax.axhspan(6, 9, color="seagreen", alpha=0.12,
                   label="Target band for ages 11-14 (FKGL 6-9)")
        by_level = [[self._f(r, "fkgl") for r in detail
                     if int(self._f(r, "difficulty")) == lvl] for lvl in levels]
        for lvl, values in zip(levels, by_level):
            ax.scatter([lvl] * len(values), values, s=12, alpha=0.35, color="grey")
        ax.errorbar(levels, means, yerr=sds, marker="o", ms=5, lw=1.6,
                    capsize=4, color="steelblue", label="Mean FKGL +/- SD")
        rho = harness.spearman([self._f(r, "difficulty") for r in detail],
                               [self._f(r, "fkgl") for r in detail])
        ax.set_xticks(levels)
        ax.set_xlabel("Configured difficulty level")
        ax.set_ylabel("Flesch-Kincaid Grade Level")
        ax.set_title(f"Measured linguistic complexity by difficulty setting (rho = {rho})")
        ax.legend(fontsize=7)
        return self._save(plt, fig, "fig_t5_difficulty.png")

    # --- T6 -------------------------------------------------------------------

    def _t6_models(self, plt):
        rows = self._read("t6_models_summary")
        labels = [r["model"].split("/")[-1][:24] for r in rows]
        json_rate = [self._f(r, "json_rate") for r in rows]
        latency = [self._f(r, "median_latency_s") for r in rows]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.6, 3.2))
        ax1.barh(labels, json_rate, color="steelblue")
        ax1.set_xlim(0, 1.05)
        ax1.set_xlabel("First-attempt strict-JSON validity")
        ax1.set_title("Schema compliance", fontsize=9)
        for i, v in enumerate(json_rate):
            ax1.text(v + 0.02, i, f"{v:.0%}", va="center", fontsize=7)

        ax2.barh(labels, latency, color="indianred")
        ax2.set_xlabel("Median latency per chapter (s)")
        ax2.set_title("Responsiveness", fontsize=9)
        try:
            ax2.axvline(15, color="black", ls="--", lw=1)
            ax2.text(15.3, -0.4, "NFR-05 budget", fontsize=6.5, rotation=90, va="bottom")
        except Exception:
            pass
        fig.suptitle("Candidate model comparison on the criteria that determine fitness", fontsize=10)
        return self._save(plt, fig, "fig_t6_models.png")

    # --- T4 -------------------------------------------------------------------

    def _t4_ablation(self, plt):
        rows = self._read("t4_faithfulness_summary")
        labels = ["Retrieval enabled" if r["condition"] == "rag_on" else "Retrieval disabled"
                  for r in rows]
        faith = [self._f(r, "mean_faithfulness") for r in rows]
        sds = [self._f(r, "sd") for r in rows]
        unsupported = [self._f(r, "mean_unsupported") for r in rows]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.2, 3.2))
        ax1.bar(labels, faith, yerr=sds, capsize=4,
                color=["seagreen", "indianred"][:len(labels)])
        ax1.set_ylim(0, 1.05)
        ax1.set_ylabel("Mean faithfulness")
        ax1.set_title("Claims supported by the textbook", fontsize=9)
        for i, v in enumerate(faith):
            ax1.text(i, v + 0.02, f"{v:.2f}", ha="center", fontsize=7)

        ax2.bar(labels, unsupported, color=["seagreen", "indianred"][:len(labels)])
        ax2.set_ylabel("Mean unsupported claims per chapter")
        ax2.set_title("Potential misconceptions introduced", fontsize=9)
        for i, v in enumerate(unsupported):
            ax2.text(i, v + 0.05, f"{v:.1f}", ha="center", fontsize=7)

        fig.suptitle("Groundedness ablation: the effect of the retrieval layer", fontsize=10)
        plt.setp(ax1.get_xticklabels(), fontsize=8)
        plt.setp(ax2.get_xticklabels(), fontsize=8)
        return self._save(plt, fig, "fig_t4_ablation.png")
