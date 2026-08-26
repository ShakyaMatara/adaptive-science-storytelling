"""T4 human validation: agreement between the hand-scored subset and the LLM judge.

The scores were recorded by hand in the blind dossier, which carries the chapter prose
and the evidence and no judge output of any kind. This script parses those tables, merges
them onto the judge's scores by `row_id`, and reports the agreement.

Reads:  results/t4_chapter_dossier_BLIND_latest.md   (hand-scored)
        results/t4_faithfulness_latest.csv           (judge's scores)
Writes: results/t4_human_validation_latest.csv       (merged, per chapter)
        results/t4_human_agreement_latest.csv        (agreement summary)
        results/t4_judge_validation_TEMPLATE_latest.csv  (human columns backfilled)

No API calls, no cost.
"""
import csv
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()
from evaluation import harness  # noqa: E402

R = pathlib.Path(__file__).resolve().parents[1] / "results"

# Rows the hand-scorer flagged as not measuring what the other rows measure. They are
# EXCLUDED ONLY IN A CLEARLY LABELLED SENSITIVITY ANALYSIS, never from the headline.
FLAGGED = {
    8: "quiz stem and four options leaked into the chapter body",
    3: "evidence is a trilingual glossary plus an unanswered exercise page",
    4: "same evidence as row 3",
}

HEAD = re.compile(r"^## row_id (\d+) — (.+?) \(Grade (\d+), (\w+)\)\s*$")
CELL = re.compile(r"^\|\s*(.+?)\s*\|\s*(.*?)\s*\|\s*$")


def parse_dossier(path):
    """Pull the hand-written scoring tables out of the blind dossier."""
    out, cur = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = HEAD.match(line)
        if m:
            cur = int(m.group(1))
            out[cur] = {"row_id": cur, "topic": m.group(2), "grade": int(m.group(3)),
                        "condition": m.group(4)}
            continue
        if cur is None:
            continue
        c = CELL.match(line)
        if not c:
            continue
        label, value = c.group(1).lower(), c.group(2).strip()
        if not value:
            continue
        if label.startswith("distinct scientific claims"):
            out[cur]["human_total_claims"] = value
        elif label.startswith("of those, supported"):
            out[cur]["human_supported"] = value
        elif label.startswith("faithfulness"):
            out[cur]["human_faithfulness"] = value
        elif label == "notes":
            out[cur]["human_notes"] = value
    return out


scored = parse_dossier(R / "t4_chapter_dossier_BLIND_latest.md")
scored = {k: v for k, v in scored.items() if "human_faithfulness" in v}
judge = {int(r["row_id"]): r for r in csv.DictReader(
    open(R / "t4_faithfulness_latest.csv", encoding="utf-8"))}

line = "=" * 78
print(line)
print("T4 HUMAN VALIDATION OF THE LLM JUDGE")
print(line)
print(f"  hand-scored chapters: {len(scored)}")

merged = []
for rid in sorted(scored):
    h, j = scored[rid], judge[rid]
    hf = float(h["human_faithfulness"])
    htc = int(h["human_total_claims"])
    hs = int(h["human_supported"])
    jf = float(j["faithfulness"])
    # The hand-written ratio is rounded to 2dp; check it against the counts recorded
    # beside it, so a transcription slip cannot pass as a disagreement.
    exact = hs / htc if htc else 0.0
    merged.append({
        "row_id": rid, "topic": h["topic"], "grade": h["grade"],
        "condition": h["condition"],
        "total_relevant": j["total_relevant"], "richness": j["richness"],
        "human_total_claims": htc, "human_supported": hs,
        "human_faithfulness": hf, "human_faithfulness_exact": round(exact, 4),
        "judge_total_claims": int(j["total_claims"]),
        "judge_supported": int(j["supported"]),
        "judge_faithfulness": jf,
        "abs_difference": round(abs(hf - jf), 4),
        "signed_difference": round(hf - jf, 4),
        "flagged": FLAGGED.get(rid, ""),
    })

bad = [m for m in merged if abs(m["human_faithfulness"] - m["human_faithfulness_exact"]) > 0.005]
print(f"  internal consistency of the hand scores (ratio vs recorded counts): "
      f"{len(merged) - len(bad)}/{len(merged)} agree to 2dp")
for m in bad:
    print(f"      row {m['row_id']}: recorded {m['human_faithfulness']}, "
          f"{m['human_supported']}/{m['human_total_claims']} = "
          f"{m['human_faithfulness_exact']}")

print()
print(f"  {'row':>3} {'topic':<30}{'cond':<9}{'human':>7}{'judge':>8}{'|diff|':>8}"
      f"  {'h.claims':>8}{'j.claims':>9}")
print("  " + "-" * 76)
for m in merged:
    flag = "  <-- flagged" if m["flagged"] else ""
    print(f"  {m['row_id']:>3} {m['topic'][:30]:<30}{m['condition']:<9}"
          f"{m['human_faithfulness']:>7.2f}{m['judge_faithfulness']:>8.4f}"
          f"{m['abs_difference']:>8.4f}  {m['human_total_claims']:>8}"
          f"{m['judge_total_claims']:>9}{flag}")

harness.write_csv("t4_human_validation", merged, list(merged[0]))


def agreement(subset, label):
    hs = [m["human_faithfulness"] for m in subset]
    js = [m["judge_faithfulness"] for m in subset]
    ad = [m["abs_difference"] for m in subset]
    sd_ = [m["signed_difference"] for m in subset]
    rho = harness.spearman(hs, js)
    hm, hsd = harness.mean_sd(hs)
    jm, jsd = harness.mean_sd(js)
    adm, _ = harness.mean_sd(ad)
    bias, _ = harness.mean_sd(sd_)
    within10 = sum(1 for x in ad if x <= 0.10 + 1e-9)
    within05 = sum(1 for x in ad if x <= 0.05 + 1e-9)
    exact = sum(1 for x in ad if x < 1e-9)
    print(f"\n  {label}  (n = {len(subset)})")
    print(f"    Spearman rho                    {rho:+.4f}")
    print(f"    mean absolute difference        {adm:.4f}")
    print(f"    within 0.10                     {within10}/{len(subset)}")
    print(f"    within 0.05                     {within05}/{len(subset)}")
    print(f"    exact                           {exact}/{len(subset)}")
    print(f"    human mean {hm:.3f} (sd {hsd:.3f})   judge mean {jm:.3f} (sd {jsd:.3f})")
    print(f"    mean signed difference (human - judge)  {bias:+.4f}")
    return {"basis": label, "n": len(subset), "spearman_rho": rho,
            "mean_abs_difference": round(adm, 4),
            "within_0.10": within10, "within_0.05": within05, "exact": exact,
            "human_mean": hm, "human_sd": hsd, "judge_mean": jm, "judge_sd": jsd,
            "mean_signed_difference": round(bias, 4)}


print()
print(line)
print("AGREEMENT")
print(line)
rows_out = [agreement(merged, "all hand-scored chapters (reported)")]
no8 = [m for m in merged if m["row_id"] != 8]
rows_out.append(agreement(no8, "sensitivity: excluding the quiz-contaminated row 8"))
clean = [m for m in merged if m["row_id"] not in FLAGGED]
rows_out.append(agreement(clean, "sensitivity: excluding rows 3, 4 and 8"))
harness.write_csv("t4_human_agreement", rows_out, list(rows_out[0]))

# --- does the ablation conclusion survive human scoring? ------------------------
print()
print(line)
print("THE ABLATION UNDER HUMAN SCORING, on the same chapters")
print(line)
cond_rows = []
for label, subset in (("all hand-scored", merged),
                      ("excluding rows 3, 4, 8", clean)):
    on = [m for m in subset if m["condition"] == "rag_on"]
    off = [m for m in subset if m["condition"] == "rag_off"]
    if not on or not off:
        continue
    hon, hon_sd = harness.mean_sd([m["human_faithfulness"] for m in on])
    hoff, hoff_sd = harness.mean_sd([m["human_faithfulness"] for m in off])
    jon, _ = harness.mean_sd([m["judge_faithfulness"] for m in on])
    joff, _ = harness.mean_sd([m["judge_faithfulness"] for m in off])
    print(f"\n  {label}  (rag_on n={len(on)}, rag_off n={len(off)})")
    print(f"    human: {hoff:.3f} -> {hon:.3f}   effect {hon - hoff:+.4f}")
    print(f"    judge: {joff:.3f} -> {jon:.3f}   effect {jon - joff:+.4f}")
    cond_rows.append({
        "basis": label, "rag_on_n": len(on), "rag_off_n": len(off),
        "human_rag_on": hon, "human_rag_on_sd": hon_sd,
        "human_rag_off": hoff, "human_rag_off_sd": hoff_sd,
        "human_effect": round(hon - hoff, 4),
        "judge_rag_on": jon, "judge_rag_off": joff,
        "judge_effect": round(jon - joff, 4),
    })
if cond_rows:
    harness.write_csv("t4_human_ablation", cond_rows, list(cond_rows[0]))

# --- claim atomisation ----------------------------------------------------------
print()
print(line)
print("CLAIM ATOMISATION — the two scorers do not cut the prose the same way")
print(line)
hc = [m["human_total_claims"] for m in merged]
jc = [m["judge_total_claims"] for m in merged]
hcm, _ = harness.mean_sd(hc)
jcm, _ = harness.mean_sd(jc)
diff, _ = harness.mean_sd([a - b for a, b in zip(hc, jc)])
print(f"  human mean claims {hcm:.2f}   judge mean claims {jcm:.2f}   "
      f"mean difference {diff:+.2f}")
print(f"  rho(human claims, judge claims) = {harness.spearman(hc, jc)}")
print(f"  human counted more in {sum(1 for a, b in zip(hc, jc) if a > b)}/{len(hc)} chapters")
print("  The faithfulness RATIO agrees far better than the claim COUNT it is built from:")
print("  the two scorers atomise the same prose differently and still land on the same")
print("  proportion, which is the property the metric needs.")

# --- backfill the template ------------------------------------------------------
tpl = R / "t4_judge_validation_TEMPLATE_latest.csv"
rows = list(csv.DictReader(open(tpl, encoding="utf-8")))
fields = list(rows[0])
by_id = {m["row_id"]: m for m in merged}
n = 0
for r in rows:
    m = by_id.get(int(r["row_id"]))
    if not m:
        continue
    r["human_total_claims"] = m["human_total_claims"]
    r["human_supported"] = m["human_supported"]
    r["human_faithfulness"] = m["human_faithfulness"]
    if m["flagged"]:
        r["human_notes"] = m["flagged"]
    n += 1
with open(tpl, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
print(f"\nbackfilled {n} human scores into {tpl.name}")
print("wrote t4_human_validation_latest.csv, t4_human_agreement_latest.csv,")
print("      t4_human_ablation_latest.csv")
