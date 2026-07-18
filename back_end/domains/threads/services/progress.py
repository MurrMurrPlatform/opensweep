"""Derived thread progress (unified dev flow).

The reliability principle this project keeps re-learning: platform state must
be DERIVED from what the platform observes, never requested from agents.
Progress is computed at read time from the thread's own facts — questions
asked/answered, plan state, phase, PR opened, review verdicts, fix rounds —
all of which are recorded deterministically on the thread. Nothing here is
stored, so nothing here can drift.
"""

from __future__ import annotations

PHASE_LABELS = {
    "refining": "Planning",
    "implementing": "Implementing",
    "in_review": "In review",
    "done": "Done",
    "abandoned": "Abandoned",
}


def compute_progress(*, phase: str, plan_state: str, events: list[dict]) -> dict:
    """Compact, human-legible progress from platform-observed facts."""
    questions = [e for e in events if e.get("type") == "question"]
    answered = sum(1 for e in questions if e.get("status") == "answered")
    open_count = sum(1 for e in questions if e.get("status") == "open")
    fix_rounds = sum(1 for e in events if e.get("type") == "fix_started")
    verdicts = [e for e in events if e.get("type") == "review_verdict"]
    last_verdict = str(verdicts[-1].get("result") or "") if verdicts else ""
    pr_opened = any(e.get("type") == "pr_opened" for e in events)

    bits: list[str] = []
    if phase == "refining":
        if questions:
            bits.append(f"{answered}/{len(questions)} questions answered")
        if plan_state == "drafted":
            bits.append("plan drafted")
        elif plan_state == "approved":
            bits.append("plan approved")
        if not bits:
            bits.append("exploring")
    elif phase == "implementing":
        bits.append("plan approved" if plan_state == "approved" else "no plan gate")
        if open_count:
            bits.append(f"{open_count} question{'s' if open_count != 1 else ''} open")
        bits.append("PR open" if pr_opened else "no PR yet")
    elif phase == "in_review":
        if last_verdict:
            bits.append(f"last verdict: {last_verdict.replace('_', ' ')}")
        if fix_rounds:
            bits.append(f"fix round {fix_rounds}")
        if not bits:
            bits.append("awaiting first verdict")
    elif phase == "done":
        bits.append("merged")

    label = PHASE_LABELS.get(phase, phase)
    if bits:
        label = f"{label} — {', '.join(bits)}"
    return {
        "phase": phase,
        "label": label,
        "questions_total": len(questions),
        "questions_answered": answered,
        "questions_open": open_count,
        "plan_state": plan_state,
        "pr_opened": pr_opened,
        "fix_rounds": fix_rounds,
        "last_verdict": last_verdict,
    }
