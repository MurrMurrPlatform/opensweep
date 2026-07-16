"""Analysis domain — the cohesive, interactive deep-scan report.

A deep-scan Run authors exactly one Analysis (keyed by source_run_uid): a
first-class container for the verdict (health grade + per-dimension
scorecard), the narrative report sections, auditable lists (coverage,
strengths, validation baseline), and interactive unresolved questions the
user can answer. Findings are NOT stored here — they join at read time via
Finding.source_run_uid == Analysis.source_run_uid.
"""
