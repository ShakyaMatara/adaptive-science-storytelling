"""Sensitivity of the T4 run-3 result to the one chapter that came from the
application's canned fallback path rather than from grounded generation.

Detection is deterministic and needs no judgement: in `rag_on` the application
attaches `sources` from the supplied passages, so `sources_attached == 0` in a
rag_on row means generate_chapter fell through both parse attempts and returned
the canned chapter at core/llm.py:414. That row scores the fallback path, not the
grounding path.

Both figures are reported. Neither replaces the other.
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
rows = list(csv.DictReader(open(R / "t4_faithfulness_latest.csv", encoding="utf-8")))

f = lambda r, k: float(r[k])
on = [r for r in rows if r["condition"] == "rag_on" and not r["judge_error"]]
off = [r for r in rows if r["condition"] == "rag_off" and not r["judge_error"]]
fallback = [r for r in on if r["sources_attached"] == "0"]
on_clean = [r for r in on if r["sources_attached"] != "0"]

print("Fallback detection in rag_on (sources_attached == 0):")
for r in fallback:
    print(f"  row_id {r['row_id']:>2}  {r['topic']:<32} faithfulness={r['faithfulness']} "
          f"claims={r['total_claims']} words={r['words']} citations={r['citations_valid']}")
print(f"  {len(fallback)} of {len(on)} rag_on generations "
      f"({100.0 * len(fallback) / len(on):.1f}%)\n")

out = []
for label, subset in (("as measured (all rag_on)", on),
                      ("excluding fallback row", on_clean)):
    fv = [f(r, "faithfulness") for r in subset]
    ov = [f(r, "faithfulness") for r in off]
    m, sd = harness.mean_sd(fv)
    om, osd = harness.mean_sd(ov)
    pooled = math.sqrt((sd ** 2 + osd ** 2) / 2)
    diff = round(m - om, 4)
    d = round(diff / pooled, 4) if pooled else 0.0
    u, z, p, note = harness.mann_whitney_u(fv, ov)
    un, _ = harness.mean_sd([f(r, "unsupported") for r in subset])
    oun, _ = harness.mean_sd([f(r, "unsupported") for r in off])
    print(f"{label}")
    print(f"  rag_on  n={len(subset):2d}  mean {m:.3f} (sd {sd:.3f})  unsupported {un:.2f}")
    print(f"  rag_off n={len(off):2d}  mean {om:.3f} (sd {osd:.3f})  unsupported {oun:.2f}")
    print(f"  difference {diff:+.4f}   Cohen's d {d:+.4f}   U={u}  z={z}  p={p}")
    print(f"  ({note})\n")
    out.append({
        "basis": label, "rag_on_n": len(subset), "rag_on_mean": m, "rag_on_sd": sd,
        "rag_off_n": len(off), "rag_off_mean": om, "rag_off_sd": osd,
        "difference": diff, "cohens_d": d, "mann_whitney_u": u, "z": z,
        "p_two_tailed": p, "mean_unsupported_on": un, "mean_unsupported_off": oun,
        "approximation_note": note,
    })

harness.write_csv("t4_fallback_sensitivity", out, list(out[0]))
print("wrote t4_fallback_sensitivity_latest.csv")

# Fallback incidence across all three runs, from data already persisted.
print("\nFallback incidence across runs (rag_on rows with sources_attached == 0):")
tot_on = tot_fb = 0
for label, fn in (("run 1  deepseek primary", "t4_faithfulness_deepseek_primary_latest.csv"),
                  ("run 2  gemini primary  ", "t4_faithfulness_gemini_run1_latest.csv"),
                  ("run 3  gemini primary  ", "t4_faithfulness_latest.csv")):
    rr = list(csv.DictReader(open(R / fn, encoding="utf-8")))
    o = [x for x in rr if x["condition"] == "rag_on"]
    fb = [x for x in o if x["sources_attached"] == "0"]
    tot_on += len(o)
    tot_fb += len(fb)
    print(f"  {label}: {len(fb)}/{len(o)}")
print(f"  pooled: {tot_fb}/{tot_on} = {100.0 * tot_fb / tot_on:.1f}% of live grounded "
      f"generations returned the canned fallback")
