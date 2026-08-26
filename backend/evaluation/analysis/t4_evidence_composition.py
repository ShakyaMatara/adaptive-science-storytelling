"""How much of the index is assessment and glossary material rather than exposition?

Hand-scoring T4 surfaced two chapters whose retrieved "evidence" was not expository
prose at all: a trilingual Technical Terms glossary and an unanswered exercise page. A
chapter grounded on those has almost nothing it can be faithful TO, so the faithfulness
score for that topic is measuring something different from the other topics'.

This quantifies the exposure. It is a corpus measurement, not a judgement: chunks are
classified by markers that only appear in the books' assessment and glossary furniture.

Reads the Chroma index directly. No API calls, no cost.
"""
import os
import pathlib
import re
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()
from core import retrieval  # noqa: E402
from evaluation import harness  # noqa: E402

R = pathlib.Path(__file__).resolve().parents[1] / "results"

# Markers of the books' own assessment / reference furniture. Deliberately narrow:
# each is a heading or stem the textbooks use, not a word that occurs in prose.
GLOSSARY = re.compile(r"Technical Terms", re.I)
EXERCISE = re.compile(
    r"Answer the following|Exercise\b|Assignment\s+\d|"
    r"Study the table and answer|Fill in the blank|"
    r"Select the correct|Write down the answer", re.I)
QUESTION_STEM = re.compile(
    r"(?:^|\s)(?:[IVX]{1,4}|\d{1,2})[.)]\s+(?:What|Which|Why|How|Name|State|"
    r"Write|Give|Explain|Describe|Mention|List|Find)\b")


# A sentence counts as EXPOSITORY when it is a declarative statement long enough to
# assert something: at least 8 words, not a question, not a bare numbered stem, and not
# a glossary line (which are dash-separated term triples, not sentences).
_SENT = re.compile(r"[.!?]\s+|\n")
_GLOSS_LINE = re.compile(r"\s-\s")


def expository_share(text):
    """Fraction of a chunk's sentences that actually state something.

    Near 0 means the chunk is furniture - a glossary, a list of question stems, a table
    - and a chapter grounded on it has almost nothing it can be faithful TO.
    """
    parts = [s.strip() for s in _SENT.split(text or "") if s and s.strip()]
    if not parts:
        return 0.0
    good = 0
    for s in parts:
        words = s.split()
        if len(words) < 8:
            continue
        if s.rstrip().endswith("?") or "?" in s:
            continue
        if QUESTION_STEM.search(" " + s):
            continue
        # Glossary runs are term - sinhala - tamil triples separated by hyphens.
        if len(_GLOSS_LINE.findall(s)) >= 2:
            continue
        good += 1
    return round(good / len(parts), 4)


def classify(text):
    kinds = []
    if GLOSSARY.search(text):
        kinds.append("glossary")
    if EXERCISE.search(text):
        kinds.append("exercise")
    if len(QUESTION_STEM.findall(text)) >= 2:
        kinds.append("question_run")
    return kinds


col = retrieval.get_collection()
data = col.get(include=["documents", "metadatas"])
docs, metas = data["documents"], data["metadatas"]
print(f"index: {len(docs)} chunks\n")

line = "=" * 78
rows, per_grade = [], {}
counts = Counter()
for text, meta in zip(docs, metas):
    kinds = classify(text or "")
    grade = meta.get("grade")
    g = per_grade.setdefault(grade, {"n": 0, "glossary": 0, "exercise": 0,
                                     "question_run": 0, "any": 0})
    g["n"] += 1
    for k in kinds:
        counts[k] += 1
        g[k] += 1
    if kinds:
        counts["any"] += 1
        g["any"] += 1

print(line)
print("ASSESSMENT AND GLOSSARY MATERIAL IN THE INDEX")
print(line)
print(f"  {'kind':<16}{'chunks':>8}{'share':>9}")
print("  " + "-" * 32)
for k in ("glossary", "exercise", "question_run", "any"):
    print(f"  {k:<16}{counts[k]:>8}{100.0 * counts[k] / len(docs):>8.1f}%")

print(f"\n  {'grade':<8}{'chunks':>8}{'glossary':>10}{'exercise':>10}"
      f"{'q-runs':>9}{'any':>8}{'share':>9}")
print("  " + "-" * 62)
for grade in sorted(per_grade, key=lambda x: (x is None, x)):
    g = per_grade[grade]
    rows.append({"grade": grade, "chunks": g["n"], "glossary": g["glossary"],
                 "exercise": g["exercise"], "question_run": g["question_run"],
                 "any_assessment": g["any"],
                 "share": round(g["any"] / g["n"], 4) if g["n"] else 0.0})
    print(f"  {str(grade):<8}{g['n']:>8}{g['glossary']:>10}{g['exercise']:>10}"
          f"{g['question_run']:>9}{g['any']:>8}{100.0 * g['any'] / g['n']:>8.1f}%")
rows.append({"grade": "all", "chunks": len(docs), "glossary": counts["glossary"],
             "exercise": counts["exercise"], "question_run": counts["question_run"],
             "any_assessment": counts["any"],
             "share": round(counts["any"] / len(docs), 4)})
harness.write_csv("index_assessment_content", rows,
                  ["grade", "chunks", "glossary", "exercise", "question_run",
                   "any_assessment", "share"])

# --- exposure of the T4 topics --------------------------------------------------
print()
print(line)
print("EXPOSURE OF THE TWELVE T4 TOPICS")
print(line)
print("  What share of the passages actually supplied to the generator were")
print("  assessment or glossary material rather than exposition?\n")
probes = harness.load_probes("in_syllabus")["probes"]
seen = {(p["topic"], p["grade"]) for p in probes}
import csv as _csv  # noqa: E402

t4 = list(_csv.DictReader(open(R / "t4_faithfulness_latest.csv", encoding="utf-8")))
topics = []
for r in t4:
    key = (r["topic"], int(r["grade"]))
    if r["condition"] != "rag_on" or key in [t[0] for t in topics]:
        continue
    topics.append((key, r))

print(f"  {'topic':<32}{'G':>2}{'rel':>5}{'psg':>5}{'assessment psg':>16}"
      f"{'contains':>8}{'expository':>10}{'faith':>8}")
print("  " + "-" * 86)
out = []
for (topic, grade), r in topics:
    content = retrieval.gather_topic_content(grade, topic)
    passages = content["passages"][:4]
    flagged = [p for p in passages if classify(p.get("text") or "")]
    share = len(flagged) / len(passages) if passages else 0.0
    chars = sum(len(p.get("text") or "") for p in passages)
    fchars = sum(len(p.get("text") or "") for p in flagged)
    dens = [expository_share(p.get("text") or "") for p in passages]
    mean_dens = round(sum(dens) / len(dens), 4) if dens else 0.0
    out.append({"topic": topic, "grade": grade,
                "total_relevant": content["total_relevant"],
                "passages_used": len(passages),
                "assessment_passages": len(flagged),
                "assessment_share": round(share, 4),
                "assessment_char_share": round(fchars / chars, 4) if chars else 0.0,
                "expository_share": mean_dens,
                "min_expository_share": round(min(dens), 4) if dens else 0.0,
                "faithfulness_rag_on": r["faithfulness"]})
    print(f"  {topic[:32]:<32}{grade:>2}{content['total_relevant']:>5}"
          f"{len(passages):>5}{len(flagged):>9}{100.0 * share:>9.0f}%"
          f"{100.0 * mean_dens:>11.0f}%{float(r['faithfulness']):>8.3f}")
harness.write_csv("t4_evidence_composition", out, list(out[0]))

full = [o for o in out if o["assessment_share"] >= 0.999]
if full:
    print(f"\n  {len(full)} topic(s) where EVERY supplied passage is assessment or")
    print("  glossary material:")
    for o in full:
        print(f"      G{o['grade']} {o['topic']}  "
              f"total_relevant={o['total_relevant']}  "
              f"faithfulness={o['faithfulness_rag_on']}")

f_share = [o["assessment_share"] for o in out]
f_faith = [float(o["faithfulness_rag_on"]) for o in out]
print(f"\n  rho(assessment share, rag_on faithfulness) = "
      f"{harness.spearman(f_share, f_faith)}  (n={len(out)})")
print("\nwrote index_assessment_content_latest.csv, t4_evidence_composition_latest.csv")

dens_all = [o["expository_share"] for o in out]
print(f"  rho(expository share, rag_on faithfulness) = "
      f"{harness.spearman(dens_all, f_faith)}  (n={len(out)})")
print()
print("  CONTAINS vs IS. The `contains` flag cannot separate a chunk of exposition that")
print("  ends in an Activity box from a chunk that is nothing but a glossary. Expository")
print("  share can: it is the fraction of a passage's sentences that actually state")
print("  something. The two thin topics are both flagged at 100% `contains` and score")
print("  1.000 and 0.333 respectively - the density measure is what tells them apart.")
