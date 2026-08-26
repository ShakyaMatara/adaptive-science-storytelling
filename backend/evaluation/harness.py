"""Shared utilities for the ASCALS evaluation harness.

This package is NOT part of the running application. It exists to produce the
quantitative evidence reported in Chapter 7 (Testing) of the thesis: every table
and figure in that chapter is generated from a CSV written by one of the
`eval_*` management commands, so the results are reproducible end-to-end.

Design notes
------------
* Retrieval is expensive in wall-clock time but free in money; model calls are
  the opposite. Wherever possible the commands retrieve ONCE, record the raw
  measurement (e.g. the best embedding distance), and then sweep decision
  thresholds offline over the recorded values. A full threshold sweep therefore
  costs nothing extra.
* Every command writes a timestamped CSV into evaluation/results/ and also
  updates a `<name>_latest.csv` copy, so charts and the thesis always point at a
  stable filename while the timestamped history is preserved as an audit trail.
* Nothing here mutates application data. The commands read the Chroma index and
  call the provider; they do not create Learner, Session or Chapter rows.
"""

import csv
import json
import math
import os
import re
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# --- Paths ---------------------------------------------------------------------

EVAL_DIR = Path(__file__).resolve().parent
PROBES_DIR = EVAL_DIR / "probes"
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def load_probes(name):
    """Load a probe set by filename stem, e.g. load_probes('in_syllabus')."""
    path = PROBES_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Probe set not found: {path}\n"
            f"Run `python manage.py eval_probes` first, or create the file by hand."
        )
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_csv(name, rows, fieldnames=None):
    """Write rows to a timestamped CSV plus a stable `<name>_latest.csv`.

    Returns the timestamped path. Empty `rows` is allowed (writes headers only)
    so a failed run still leaves an auditable artefact.
    """
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stamped = RESULTS_DIR / f"{name}_{stamp}.csv"
    latest = RESULTS_DIR / f"{name}_latest.csv"
    for path in (stamped, latest):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in fieldnames})
    return stamped


def write_json(name, payload):
    """Write a nested record to a timestamped JSON plus a stable `<name>_latest.json`.

    The CSV writer above is the right container for a table of metrics, and the
    wrong one for the material those metrics were computed from: a judge's verdict
    is a LIST of per-claim decisions, and flattening it into a cell destroys exactly
    the structure an audit needs. Commands that produce evidence as well as numbers
    write the numbers with write_csv and the evidence with this.
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stamped = RESULTS_DIR / f"{name}_{stamp}.json"
    latest = RESULTS_DIR / f"{name}_latest.json"
    for path in (stamped, latest):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
    return stamped


def write_text(name, text, suffix=".md"):
    """Write a human-readable artefact alongside the machine-readable ones."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stamped = RESULTS_DIR / f"{name}_{stamp}{suffix}"
    latest = RESULTS_DIR / f"{name}_latest{suffix}"
    for path in (stamped, latest):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return stamped


# --- Corpus text quality -------------------------------------------------------
# FINDING-4: the trilingual glossaries use legacy non-Unicode fonts and are recovered
# as unrelated Latin characters, then indexed as though they were English. The defect
# is documented rather than repaired (see results/corpus_defects.md), so experiments
# that could be affected by it report a clean-corpus counterfactual alongside the
# real figure.
#
# Detection targets non-ASCII LETTERS specifically. English prose contains none,
# whereas the legacy-font output is dense with them; counting non-ASCII characters
# generally would sweep in the bullet and ellipsis glyphs the books use deliberately.

_MICRO_SIGN = "µ"


def _is_scientific_letter(ch):
    """Greek and Letterlike Symbols are notation - mu for micro, the ohm sign."""
    code = ord(ch)
    return 0x0370 <= code <= 0x03FF or 0x2100 <= code <= 0x214F


def is_mojibake_char(ch):
    if ord(ch) <= 127 or ch == _MICRO_SIGN or _is_scientific_letter(ch):
        return False
    if 0xE000 <= ord(ch) <= 0xF8FF:      # Private Use Area is a different defect
        return False
    return unicodedata.category(ch).startswith("L")


def has_mojibake(text):
    """True when any whitespace token carries legacy-font corruption."""
    return any(any(is_mojibake_char(c) for c in token) for token in (text or "").split())


def clean_passages(passages):
    """The passages that are free of legacy-font corruption."""
    return [p for p in passages if not has_mojibake(p.get("text") or "")]


# --- Provenance and printed pages ----------------------------------------------
# Part of the corpus was recovered from page images rather than read from a text
# layer (see results/g9p1_coverage_gap.md). Every experiment reports how much of its
# result rests on that recovered text, so a reader can discount it if they choose.

def provenance(passages):
    """Return (recovered, total, share) for a list of retrieved passages."""
    total = len(passages)
    recovered = sum(1 for p in passages if p.get("source_type") == "ocr_vision")
    return recovered, total, (recovered / total if total else 0.0)


def min_agreement(passages):
    """Lowest A/B extraction agreement among the recovered passages, or "" if none."""
    scores = []
    for p in passages:
        raw = p.get("ocr_agreement")
        try:
            if raw not in (None, ""):
                scores.append(float(raw))
        except (TypeError, ValueError):
            continue
    return min(scores) if scores else ""


def printed_pages(passages):
    """Printed page numbers of the passages, as integers, ignoring unnumbered ones."""
    out = []
    for p in passages:
        raw = p.get("page_label_start")
        if raw not in (None, ""):
            try:
                out.append(int(raw))
            except (TypeError, ValueError):
                continue
    return out


def printed_span(passages):
    """Printed pages a topic occupies, summed per book.

    A grade's material is split across two physical volumes whose page numbering
    each restart at 1, so a single max-minus-min across the grade would be
    meaningless. The span is therefore computed within each source file and summed.
    """
    by_file = {}
    for p in passages:
        raw = p.get("page_label_start")
        if raw in (None, ""):
            continue
        try:
            page = int(raw)
        except (TypeError, ValueError):
            continue
        by_file.setdefault(p.get("source_file") or "?", []).append(page)
    return sum(max(v) - min(v) + 1 for v in by_file.values() if v)


# --- Classification statistics -------------------------------------------------

def confusion(tp, fp, tn, fn):
    """Return the standard classification metrics from a 2x2 confusion matrix.

    Positive class = "the system accepted the topic as in-syllabus" (or "the gate
    fired"), depending on the command. Each command documents its own polarity.
    """
    total = tp + fp + tn + fn
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    accuracy = (tp + tn) / total if total else 0.0
    return {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "specificity": round(specificity, 4),
        "f1": round(f1, 4),
    }


def _rank(values):
    """Fractional ranks (ties averaged) — needed for a correct Spearman's rho."""
    indexed = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and values[indexed[j + 1]] == values[indexed[i]]:
            j += 1
        average = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k]] = average
        i = j + 1
    return ranks


def spearman(xs, ys):
    """Spearman's rank correlation coefficient, implemented without SciPy.

    Handles ties correctly by using fractional ranks and then computing Pearson's
    r over the ranks (the simplified 6*d^2 formula is only valid without ties).
    Returns 0.0 for degenerate input.
    """
    if len(xs) != len(ys) or len(xs) < 3:
        return 0.0
    rx, ry = _rank(xs), _rank(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    den = math.sqrt(sum((rx[i] - mx) ** 2 for i in range(n)) *
                    sum((ry[i] - my) ** 2 for i in range(n)))
    return round(num / den, 4) if den else 0.0


def mann_whitney_u(a, b):
    """Mann-Whitney U with a normal approximation, implemented without SciPy.

    Returns (u, z, p_two_tailed, note). The test is non-parametric and makes no
    normality assumption, which suits small samples of bounded scores. The p-value
    uses the normal approximation WITH tie correction and a continuity correction;
    below roughly n=8 per group that approximation is rough, and the returned note
    says so rather than letting a precise-looking p stand unqualified.
    """
    n1, n2 = len(a), len(b)
    if n1 == 0 or n2 == 0:
        return 0.0, 0.0, 1.0, "empty group"
    combined = sorted(a + b)
    ranks = _rank(combined)
    lookup = {}
    for value, rank in zip(combined, ranks):
        lookup.setdefault(value, []).append(rank)
    used = {}
    def rank_of(v):
        i = used.get(v, 0)
        used[v] = i + 1
        return lookup[v][i]
    r1 = sum(rank_of(v) for v in sorted(a))
    u1 = r1 - n1 * (n1 + 1) / 2.0
    u2 = n1 * n2 - u1
    u = min(u1, u2)

    mean_u = n1 * n2 / 2.0
    tie_groups = {}
    for v in combined:
        tie_groups[v] = tie_groups.get(v, 0) + 1
    n = n1 + n2
    tie_term = sum(t ** 3 - t for t in tie_groups.values())
    var_u = (n1 * n2 / 12.0) * ((n + 1) - tie_term / float(n * (n - 1))) if n > 1 else 0.0
    if var_u <= 0:
        return round(u, 2), 0.0, 1.0, "zero variance"
    z = max(0.0, abs(u - mean_u) - 0.5) / math.sqrt(var_u)
    p = 2.0 * (1.0 - _norm_cdf(z))
    note = ("normal approximation is rough below n=8 per group"
            if min(n1, n2) < 8 else "normal approximation")
    return round(u, 2), round(z, 4), round(min(1.0, max(0.0, p)), 5), note


def _norm_cdf(z):
    """Standard normal CDF via the error function."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def mean_sd(values):
    """Sample mean and standard deviation (n-1 denominator)."""
    values = [v for v in values if v is not None]
    if not values:
        return 0.0, 0.0
    n = len(values)
    m = sum(values) / n
    if n < 2:
        return round(m, 3), 0.0
    var = sum((v - m) ** 2 for v in values) / (n - 1)
    return round(m, 3), round(math.sqrt(var), 3)


# --- Readability ---------------------------------------------------------------
# Implemented inline so the harness has no hard third-party dependency. If you
# want an independent cross-check, `pip install textstat` and compare — the
# syllable heuristic below is the standard vowel-group approximation and lands
# within roughly +/-0.3 grade levels of textstat on prose of this kind.

_VOWELS = "aeiouy"


def count_syllables(word):
    """Approximate syllable count for one English word."""
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 0
    if len(word) <= 3:
        return 1
    count, prev_vowel = 0, False
    for ch in word:
        is_vowel = ch in _VOWELS
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if word.endswith("e") and not word.endswith(("le", "ee")):
        count -= 1
    if word.endswith("le") and len(word) > 2 and word[-3] not in _VOWELS:
        count += 1
    return max(1, count)


def readability(text):
    """Flesch Reading Ease, Flesch-Kincaid Grade Level and supporting counts.

    Returns a dict with fre, fkgl, words, sentences, syllables, words_per_sentence
    and type_token_ratio (lexical diversity). Empty or single-word input returns
    zeros rather than raising, so a failed generation does not break a batch.
    """
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    words = re.findall(r"[A-Za-z']+", text)
    if not words or not sentences:
        return {"fre": 0.0, "fkgl": 0.0, "words": 0, "sentences": 0,
                "syllables": 0, "words_per_sentence": 0.0, "type_token_ratio": 0.0}
    syllables = sum(count_syllables(w) for w in words)
    wps = len(words) / len(sentences)
    spw = syllables / len(words)
    fre = 206.835 - 1.015 * wps - 84.6 * spw
    fkgl = 0.39 * wps + 11.8 * spw - 15.59
    ttr = len({w.lower() for w in words}) / len(words)
    return {
        "fre": round(fre, 2),
        "fkgl": round(fkgl, 2),
        "words": len(words),
        "sentences": len(sentences),
        "syllables": syllables,
        "words_per_sentence": round(wps, 2),
        "type_token_ratio": round(ttr, 4),
    }


# --- Provider access with usage accounting -------------------------------------
# The application's llm._call_llm() returns text only and hides its internal
# retry. For evaluation we need the raw first attempt, the token usage and the
# latency, so the harness makes its own call using the same configuration.

@contextmanager
def use_model(model_id):
    """Temporarily point llm_config at a different model.

    llm_config reads os.environ at call time, so setting MODEL here is enough to
    redirect every downstream call — no application code changes needed. The
    previous value is always restored, including on exception.
    """
    previous = os.environ.get("MODEL")
    if model_id:
        os.environ["MODEL"] = model_id
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("MODEL", None)
        else:
            os.environ["MODEL"] = previous


def raw_call(messages, max_tokens=1200, temperature=0.7, model=None):
    """One chat-completion call returning (text, usage_dict, latency_seconds).

    Mirrors llm._call_llm but exposes usage and latency and performs NO retry, so
    first-attempt schema compliance can be measured honestly. Raises RuntimeError
    with a readable message on provider failure.
    """
    from openai import OpenAI
    from core import llm_config

    client = OpenAI(
        base_url=llm_config.get_base_url(),
        api_key=llm_config.get_api_key(),
        timeout=180,
        default_headers={
            "HTTP-Referer": "http://localhost:5173",
            "X-Title": "ASCALS Evaluation Harness",
        },
    )
    model_id = model or llm_config.get_model()
    started = time.time()
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc
    latency = time.time() - started

    usage = getattr(response, "usage", None)
    usage_dict = {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
    }
    text = (response.choices[0].message.content or "") if response.choices else ""
    return text, usage_dict, round(latency, 3)


def strip_to_json(text):
    """Best-effort extraction of a JSON object from a model reply.

    Mirrors the application's tolerance for fenced code blocks and stray prose so
    that first-attempt validity is measured on the same basis the app uses.
    """
    if not text:
        return ""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    return cleaned[start:end + 1] if start != -1 and end > start else cleaned


def parse_json(text):
    """Return (parsed_or_None, error_message)."""
    try:
        return json.loads(strip_to_json(text)), ""
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


# --- Cost accounting -----------------------------------------------------------
# Prices change; these are placeholders. Put YOUR provider's current per-million
# token rates here before reporting a cost column, and say in the thesis that
# costs are indicative and were computed from the rates in force on the run date.

PRICES_PER_MTOK = {
    # "model-id": (prompt_usd_per_million, completion_usd_per_million)
    # Read from the RAW openrouter.ai/api/v1/models JSON on 2026-08-25 (419 models).
    # Prices change; state in the
    # thesis that costs are indicative and were computed from the rates in force on the
    # run date, and re-read them before quoting a figure.
    "openai/gpt-5.4-mini":             (0.75,   4.50),   # the configured model
    "openai/gpt-5.6-luna":             (0.20,   1.20),
    "deepseek/deepseek-v4-flash-0731": (0.0616, 0.1232),
    "google/gemini-3.7-flash":         (0.375,  1.875),
    "qwen/qwen3.8-27b":                (0.425,  2.55),
}


def estimate_cost(model_id, usage):
    """Approximate USD cost for one call; 0.0 when the model has no price entry."""
    rates = PRICES_PER_MTOK.get(model_id)
    if not rates:
        return 0.0
    prompt_rate, completion_rate = rates
    cost = (usage.get("prompt_tokens", 0) / 1_000_000) * prompt_rate
    cost += (usage.get("completion_tokens", 0) / 1_000_000) * completion_rate
    return round(cost, 6)


class Budget:
    """Running tally of calls, tokens and estimated spend for one command.

    Print the summary at the end of every command so that the cost of reproducing
    each experiment is documented in the thesis rather than guessed at.
    """

    def __init__(self, label):
        self.label = label
        self.calls = 0
        self.failures = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cost = 0.0

    def record(self, model_id, usage, failed=False):
        self.calls += 1
        if failed:
            self.failures += 1
        self.prompt_tokens += usage.get("prompt_tokens", 0)
        self.completion_tokens += usage.get("completion_tokens", 0)
        self.cost += estimate_cost(model_id, usage)

    def summary(self):
        total = self.prompt_tokens + self.completion_tokens
        line = (f"[{self.label}] calls={self.calls} failures={self.failures} "
                f"prompt_tokens={self.prompt_tokens} completion_tokens={self.completion_tokens} "
                f"total_tokens={total}")
        if self.cost:
            line += f" estimated_cost_usd={self.cost:.4f}"
        else:
            line += " estimated_cost_usd=n/a (populate PRICES_PER_MTOK)"
        return line


# --- Console helpers -----------------------------------------------------------

def table(rows, headers):
    """Render a simple fixed-width table for terminal output."""
    if not rows:
        return "(no rows)"
    widths = [len(h) for h in headers]
    body = []
    for row in rows:
        cells = [str(row.get(h, "")) for h in headers]
        widths = [max(w, len(c)) for w, c in zip(widths, cells)]
        body.append(cells)
    sep = "  ".join("-" * w for w in widths)
    out = ["  ".join(h.ljust(w) for h, w in zip(headers, widths)), sep]
    out += ["  ".join(c.ljust(w) for c, w in zip(cells, widths)) for cells in body]
    return "\n".join(out)
