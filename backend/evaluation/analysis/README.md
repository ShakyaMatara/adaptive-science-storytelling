# Offline analysis scripts

Post-processing over CSVs the `eval_*` management commands have already written. These
make **no API calls and cost nothing** — they are separated from the commands because
they compare runs against each other, which a single run cannot do from inside itself.

Run them from `backend/` with the project's virtualenv:

```
python evaluation/analysis/t4_analysis.py
python evaluation/analysis/t4_fallback_sensitivity.py
```

| Script | Reads | Writes |
|---|---|---|
| `t4_analysis.py` | `t4_faithfulness_latest.csv`, `t4_faithfulness_gemini_run1_latest.csv` | `t4_significance_latest.csv`, `t4_generation_variance_latest.csv`, `t4_interjudge_agreement_latest.csv` |
| `t4_fallback_sensitivity.py` | all three runs' per-chapter CSVs | `t4_fallback_sensitivity_latest.csv` |

`t4_analysis.py` also prints the faithfulness-against-evidence-base tables reported in
section 6 of `RESULTS_SUMMARY.md`.
