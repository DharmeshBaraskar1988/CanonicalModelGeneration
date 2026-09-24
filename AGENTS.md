# Canonical Model Generator - Working Agreement

## Project memory

Before planning or changing code, read these files in order:

1. `docs/STATUS.md`
2. `docs/NEXT_STEPS.md`
3. `docs/IMPLEMENTATION_PLAN.md`
4. `docs/DECISIONS.md` when an architectural decision is involved

Treat these files as the durable project memory. Do not rely only on chat history.

## Work-cycle hook

For every material implementation task:

1. Identify the current milestone and task IDs from `docs/IMPLEMENTATION_PLAN.md`.
2. Confirm that the requested work matches `docs/NEXT_STEPS.md`. If it does not, explain the deviation and update the plan when appropriate.
3. Implement and verify the smallest complete vertical slice.
4. Before finishing, update:
   - `docs/STATUS.md` with completed work, verification evidence, blockers, and the date.
   - `docs/NEXT_STEPS.md` so the first unchecked item is the recommended next action.
   - `docs/IMPLEMENTATION_PLAN.md` task checkboxes and milestone status.
   - `docs/DECISIONS.md` only when a durable architectural or product decision was made.
5. Never mark a task complete without verification evidence. If verification was not run, record that explicitly.

Documentation-only discussion does not require a status update unless it changes scope, sequencing, or a recorded decision.

## Scope guardrails

- Phase 1 is deterministic discovery only.
- Python and LangGraph orchestrate the workflow.
- Roslyn and the OpenAPI parser perform deterministic extraction.
- Do not add LLM classification, semantic alignment, canonical generation, persistence, or a review UI before the discovery MVP is accepted.
- Start with one region and one Quote API vertical slice.
- Preserve source lineage and conflicting evidence; do not silently discard conflicts.
- Keep generated identifiers and artifact output deterministic.

## Definition of done

A task is complete only when its acceptance criteria are met, relevant tests pass, generated output is inspected when applicable, and the tracking documents reflect the result.
