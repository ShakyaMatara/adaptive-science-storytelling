"""T4 run-3 analysis: significance, inter-judge agreement, generation-to-generation
variance against run 2, and the faithfulness / evidence-base relationship.

Reads only CSVs already written by eval_faithfulness. No API calls, no cost.
"""
import csv
import math
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402
django.setup()

from evaluation import harness  # noqa: E402

R = pathlib.Path(__file__).resolve().parents[1] / "results"


def load(name):
    with open(R / name, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def fnum(row, key, default=None):
    v = (row.get(key) or "").strip()
    if v == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default


run3 = load("t4_faithfulness_latest.csv")
run2 = load("t4_faithfulness_gemini_run1_latest.csv")   # gemini primary, no evidence kept

JUDGE = "google/gemini-3.7-flash"
JUDGE2 = "deepseek/deepseek-v4-flash-0731"

line = "=" * 78


def cond(rows, c):
    return [r for r in rows if r["condition"] == c and not r["judge_error"]]


# ---------------------------------------------------------------- 1. means + significance
print(line)
print("1. RUN 3 MEANS AND SIGNIFICANCE  (gemini primary, evidence persisted)")
print(line)

on = cond(run3, "rag_on")
off = cond(run3, "rag_off")
on_f = [fnum(r, "faithfulness") for r in on]
off_f = [fnum(r, "faithfulness") for r in off]
on_u = [fnum(r, "unsupported") for r in on]
off_u = [fnum(r, "unsupported") for r in off]
on_c = [fnum(r, "total_claims") for r in on]
off_c = [fnum(r, "total_claims") for r in off]

on_m, on_sd = harness.mean_sd(on_f)
off_m, off_sd = harness.mean_sd(off_f)
on_um, _ = harness.mean_sd(on_u)
off_um, _ = harness.mean_sd(off_u)
on_cm, _ = harness.mean_sd(on_c)
off_cm, _ = harness.mean_sd(off_c)

print(f"  rag_on   n={len(on):2d}  faithfulness {on_m:.3f} (sd {on_sd:.3f})  "
      f"claims {on_cm:.2f}  unsupported {on_um:.2f}")
print(f"  rag_off  n={len(off):2d}  faithfulness {off_m:.3f} (sd {off_sd:.3f})  "
      f"claims {off_cm:.2f}  unsupported {off_um:.2f}")

pooled = math.sqrt((on_sd ** 2 + off_sd ** 2) / 2) if (on_sd or off_sd) else 0.0
diff = round(on_m - off_m, 4)
d = round(diff / pooled, 4) if pooled else 0.0
u_f, z_f, p_f, note_f = harness.mann_whitney_u(on_f, off_f)
u_u, z_u, p_u, _ = harness.mann_whitney_u(off_u, on_u)

print(f"\n  difference in means      {diff:+.4f}")
print(f"  Cohen's d (pooled sd)    {d:+.4f}")
print(f"  Mann-Whitney U           {u_f}   z={z_f}   p(two-tailed)={p_f}")
print(f"  unsupported claims       U={u_u}  z={z_u}  p={p_u}  "
      f"({off_um:.2f} -> {on_um:.2f} per chapter)")

sig_row = {
    "judge": JUDGE, "run": "run3_evidence_persisted",
    "rag_on_n": len(on), "rag_on_mean": on_m, "rag_on_sd": on_sd,
    "rag_off_n": len(off), "rag_off_mean": off_m, "rag_off_sd": off_sd,
    "difference": diff, "cohens_d": d,
    "mann_whitney_u": u_f, "z": z_f, "p_two_tailed": p_f,
    "approximation_note": note_f,
}
harness.write_csv("t4_significance", [sig_row], list(sig_row))

failed = [r for r in run3 if r["judge_error"]]
print(f"\n  judgements failed: {len(failed)} of {len(run3)}")
for r in failed:
    print(f"      {r['condition']:8s} {r['topic'][:34]:34s} {r['judge_error'][:60]}")

incons = [r for r in run3 if r.get("claims_consistent") == "False" and not r["judge_error"]]
print(f"  total_claims != len(claim list): {len(incons)} of "
      f"{len([r for r in run3 if not r['judge_error']])}")
for r in incons:
    print(f"      {r['condition']:8s} {r['topic'][:30]:30s} "
          f"reported {r['total_claims']}, listed {r['claims_listed']}")

# ---------------------------------------------------------------- 2. generation variance
print()
print(line)
print("2. GENERATION-TO-GENERATION VARIANCE  (run 2 vs run 3)")
print(line)
print("  Same 12 topics, same primary judge, same index, same prompt. The ONLY thing")
print("  that differs is the sample drawn at temperature 0.7. Any movement here is")
print("  generation variance, not a correction to run 2.\n")

r2on, r2off = cond(run2, "rag_on"), cond(run2, "rag_off")
r2on_m, r2on_sd = harness.mean_sd([fnum(r, "faithfulness") for r in r2on])
r2off_m, r2off_sd = harness.mean_sd([fnum(r, "faithfulness") for r in r2off])
r2diff = round(r2on_m - r2off_m, 4)
r2pooled = math.sqrt((r2on_sd ** 2 + r2off_sd ** 2) / 2)
r2d = round(r2diff / r2pooled, 4) if r2pooled else 0.0
r2u, r2z, r2p, _ = harness.mann_whitney_u(
    [fnum(r, "faithfulness") for r in r2on],
    [fnum(r, "faithfulness") for r in r2off])

hdr = f"  {'':22s} {'run 2':>12s} {'run 3':>12s} {'shift':>10s}"
print(hdr)
print("  " + "-" * (len(hdr) - 2))
for label, a, b in (
    ("rag_on mean", r2on_m, on_m), ("rag_on sd", r2on_sd, on_sd),
    ("rag_off mean", r2off_m, off_m), ("rag_off sd", r2off_sd, off_sd),
    ("difference", r2diff, diff), ("Cohen's d", r2d, d),
    ("Mann-Whitney U", r2u, u_f), ("p (two-tailed)", r2p, p_f),
):
    print(f"  {label:22s} {a:12.4f} {b:12.4f} {b - a:+10.4f}")

# paired by topic+condition
key = lambda r: (r["topic"], r["condition"])
m2 = {key(r): r for r in run2 if not r["judge_error"]}
paired = []
for r in run3:
    if r["judge_error"] or key(r) not in m2:
        continue
    a, b = fnum(m2[key(r)], "faithfulness"), fnum(r, "faithfulness")
    paired.append({
        "topic": r["topic"], "grade": r["grade"], "condition": r["condition"],
        "total_relevant": r["total_relevant"],
        "run2_faithfulness": a, "run3_faithfulness": b,
        "delta": round(b - a, 4),
        "run2_claims": m2[key(r)]["total_claims"], "run3_claims": r["total_claims"],
    })
if paired:
    deltas = [p["delta"] for p in paired]
    dm, dsd = harness.mean_sd(deltas)
    absm, _ = harness.mean_sd([abs(x) for x in deltas])
    identical = sum(1 for x in deltas if x == 0)
    print(f"\n  Paired on topic+condition, n={len(paired)}")
    print(f"    mean signed change   {dm:+.4f} (sd {dsd:.4f})")
    print(f"    mean absolute change {absm:.4f}")
    print(f"    unchanged            {identical}/{len(paired)}")
    print(f"    largest movements:")
    for p in sorted(paired, key=lambda x: -abs(x["delta"]))[:5]:
        print(f"      {p['condition']:8s} {p['topic'][:32]:32s} "
              f"{p['run2_faithfulness']:.4f} -> {p['run3_faithfulness']:.4f} "
              f"({p['delta']:+.4f})")
    harness.write_csv("t4_generation_variance", paired,
                      ["topic", "grade", "condition", "total_relevant",
                       "run2_faithfulness", "run3_faithfulness", "delta",
                       "run2_claims", "run3_claims"])

# ---------------------------------------------------------------- 3. inter-judge
print()
print(line)
print("3. INTER-JUDGE AGREEMENT  (chapters scored by BOTH judges)")
print(line)
dual = [r for r in run3 if (r.get("faithfulness2") or "").strip() != "" and not r["judge_error"]]
if dual:
    j1 = [fnum(r, "faithfulness") for r in dual]
    j2 = [fnum(r, "faithfulness2") for r in dual]
    absdiff = [abs(a - b) for a, b in zip(j1, j2)]
    rho = harness.spearman(j1, j2)
    j1m, j1sd = harness.mean_sd(j1)
    j2m, j2sd = harness.mean_sd(j2)
    admean, _ = harness.mean_sd(absdiff)
    exact = sum(1 for x in absdiff if x == 0)
    within = sum(1 for x in absdiff if x <= 0.10 + 1e-9)
    print(f"  n = {len(dual)}   judge1 = {JUDGE}   judge2 = {JUDGE2}")
    print(f"  judge1 mean {j1m:.3f} (sd {j1sd:.3f})   judge2 mean {j2m:.3f} (sd {j2sd:.3f})")
    print(f"  Spearman rho {rho}   mean |difference| {admean:.4f}   "
          f"exact {exact}/{len(dual)}   within 0.10 {within}/{len(dual)}")
    print("\n  per chapter:")
    for r, a, b in sorted(zip(dual, j1, j2), key=lambda t: -abs(t[1] - t[2])):
        print(f"    {r['condition']:8s} {r['topic'][:30]:30s} "
              f"judge1 {a:.4f}  judge2 {b:.4f}  diff {abs(a - b):.4f}")
    harness.write_csv("t4_interjudge_agreement", [{
        "n": len(dual), "judge1": JUDGE, "judge2": JUDGE2,
        "judge1_mean": j1m, "judge1_sd": j1sd, "judge2_mean": j2m, "judge2_sd": j2sd,
        "mean_abs_difference": round(admean, 4), "spearman_rho": rho,
        "exact_agreement": exact, "within_0.10": within,
    }], ["n", "judge1", "judge2", "judge1_mean", "judge1_sd", "judge2_mean",
         "judge2_sd", "mean_abs_difference", "spearman_rho", "exact_agreement",
         "within_0.10"])
else:
    print("  no dual-judged chapters in this run")

# ---------------------------------------------------------------- 4. evidence base
print()
print(line)
print("4. FAITHFULNESS AGAINST THE SIZE OF THE EVIDENCE BASE")
print(line)
print(f"  {'topic':<32}{'G':>2} {'rel':>4} {'band':<9}{'psg':>4}{'chars':>7}"
      f"{'rag_on':>8}{'rag_off':>9}")
print("  " + "-" * 74)
by_topic = {}
for r in run3:
    if r["judge_error"]:
        continue
    e = by_topic.setdefault(r["topic"], {"grade": r["grade"],
                                         "rel": int(r["total_relevant"]),
                                         "band": r["richness"],
                                         "psg": r["passages_used"],
                                         "chars": r["evidence_chars"]})
    e[r["condition"]] = fnum(r, "faithfulness")
for topic, e in sorted(by_topic.items(), key=lambda kv: kv[1]["rel"]):
    onv = e.get("rag_on")
    offv = e.get("rag_off")
    print(f"  {topic[:32]:<32}{e['grade']:>2} {e['rel']:>4} {e['band']:<9}"
          f"{e['psg']:>4}{e['chars']:>7}"
          f"{('%.4f' % onv) if onv is not None else '     -':>8}"
          f"{('%.4f' % offv) if offv is not None else '     -':>9}")

for c in ("rag_on", "rag_off"):
    subset = cond(run3, c)
    if len(subset) >= 3:
        rel = [fnum(r, "total_relevant") for r in subset]
        chars = [fnum(r, "evidence_chars") for r in subset]
        faith = [fnum(r, "faithfulness") for r in subset]
        print(f"\n  {c} (n={len(subset)}): "
              f"rho(total_relevant, faithfulness) = {harness.spearman(rel, faith)}, "
              f"rho(evidence_chars, faithfulness) = {harness.spearman(chars, faith)}")

print("\n  by richness band:")
print(f"  {'band':<10}{'cond':<9}{'n':>3}{'mean rel':>10}{'mean chars':>12}"
      f"{'faithfulness':>14}{'sd':>7}")
print("  " + "-" * 65)
for band in ("thin", "moderate", "rich"):
    for c in ("rag_on", "rag_off"):
        subset = [r for r in cond(run3, c) if r["richness"] == band]
        if not subset:
            continue
        fm, fsd = harness.mean_sd([fnum(r, "faithfulness") for r in subset])
        relm, _ = harness.mean_sd([fnum(r, "total_relevant") for r in subset])
        chm, _ = harness.mean_sd([fnum(r, "evidence_chars") for r in subset])
        print(f"  {band:<10}{c:<9}{len(subset):>3}{relm:>10.2f}{chm:>12.0f}"
              f"{fm:>14.4f}{fsd:>7.3f}")

perfect = [r for r in cond(run3, "rag_on") if fnum(r, "faithfulness") == 1.0]
if perfect:
    pm, _ = harness.mean_sd([fnum(r, "total_relevant") for r in perfect])
    pc, _ = harness.mean_sd([fnum(r, "evidence_chars") for r in perfect])
    imperfect = [r for r in cond(run3, "rag_on") if fnum(r, "faithfulness") < 1.0]
    print(f"\n  rag_on chapters scoring exactly 1.000: {len(perfect)}/{len(cond(run3, 'rag_on'))}"
          f"  mean total_relevant {pm:.2f}, mean evidence {pc:.0f} chars")
    if imperfect:
        im, _ = harness.mean_sd([fnum(r, "total_relevant") for r in imperfect])
        ic, _ = harness.mean_sd([fnum(r, "evidence_chars") for r in imperfect])
        print(f"  rag_on chapters scoring below 1.000: {len(imperfect)}"
              f"  mean total_relevant {im:.2f}, mean evidence {ic:.0f} chars")

print()
print(line)
print("wrote: t4_significance_latest.csv, t4_generation_variance_latest.csv,")
print("       t4_interjudge_agreement_latest.csv")
print(line)
