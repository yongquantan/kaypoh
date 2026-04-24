# Workflow: Implement and Verify

Use this workflow for any task that touches a frozen spec (`specs/sse-contract.md`,
`specs/grabmaps-client.md`, `specs/audit-agent.md`) or spans both backend and frontend.

## Steps

1. **Orient.** Read `AGENTS.md`, then the specific spec your change belongs to.
   If the change requires a spec edit, do it FIRST, in the same commit as the
   implementation.

2. **Implement depth-first.** One small, testable slice at a time. Don't batch.

3. **Verify locally.**
   - Backend change: `pytest backend/tests` (add a test if one doesn't exist),
     plus one live curl against the affected endpoint.
   - Frontend change: `npm run lint`, manual click-through with the backend
     running against `demo_bishan`.
   - Full-stack change: run an end-to-end audit and watch the browser Network
     tab + the backend log.

4. **Surface hidden API friction.** If a GrabMaps call misbehaves:
   - Open `docs/bug-hunter.md`.
   - Add an entry with: summary, severity, curl repro, observed, expected, workaround.
   - Implement the workaround, not a silent catch.

5. **Adversarial pass (optional).** For a decision that locks architecture,
   spawn `codex:codex-rescue` with a design critique prompt. See the thread
   that produced the adversarial review of this project's architecture for
   the pattern — narrow scope, 7 prompts, ≤700 words back.

6. **Close the loop.** Update `TODO.md` (check the box), update the spec's
   **Status** line if a Draft graduated to Frozen, and commit with a message
   pointing at the spec:

   ```
   feat(agent): implement verify_walk_time

   Refs specs/audit-agent.md §walk_time thresholds.
   ```

## When to skip this workflow

- Pure documentation edits to `docs/` that don't affect code.
- Fixture content tweaks.
- Formatting / lint-only changes.
