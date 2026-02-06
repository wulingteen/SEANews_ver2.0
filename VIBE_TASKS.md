# Vibe Coding Persistent Backlog

Last Updated: 2026-02-06

## Rules
- Treat each task as a small deliverable.
- One completed task equals one commit.
- Before each task commit, update this file and `vibe_tasks.json`.
- Commit message format: `task(<TASK_ID>): <short summary>`.

## Task Board

| ID | Status | Task | Estimate | Depends On | Done Commit |
|---|---|---|---|---|---|
| VC-01 | DONE | Auth baseline refactor (remove forced relogin/clear-on-login behavior) | 4-6h | - | task(VC-01) |
| VC-02 | DONE | Google OAuth login integration (frontend + backend token verify) | 6-10h | VC-01 | task(VC-02) |
| VC-03 | DONE | Multi-user data isolation (news/tags/history by user_id) | 8-14h | VC-02 | task(VC-03) |
| VC-04 | TODO | P0 UX fixes (no stacking, recent-by-default, max_results) | 6-10h | VC-01 | - |
| VC-05 | TODO | Release hardening (env setup, callback config, smoke checklist) | 3-6h | VC-02, VC-03, VC-04 | - |

## Task Definition

### VC-01 Auth baseline refactor
- Goal: keep session across refresh, stop automatic wipe on login.
- Acceptance:
  - Existing token is reused if valid.
  - Login no longer clears all records automatically.
  - Manual "new case" still works as explicit reset.

### VC-02 Google OAuth integration
- Goal: support Google sign-in and map to internal session.
- Acceptance:
  - Frontend shows Google login flow.
  - Backend verifies Google ID token and returns app session token.
  - Invalid token path is handled gracefully.

### VC-03 Multi-user data isolation
- Goal: persist records per user.
- Acceptance:
  - News records and tags are scoped by user ID.
  - APIs read/write only current user data.
  - Legacy rows are still readable or migrated.

### VC-04 P0 UX fixes
- Goal: remove high-friction pain points in search flow.
- Acceptance:
  - New search can replace old result set (default on).
  - Default search window uses recent period.
  - User can set result cap (`max_results`).

### VC-05 Release hardening
- Goal: make rollout repeatable and low-risk.
- Acceptance:
  - `.env` keys documented and validated.
  - Google OAuth callback and origin settings documented.
  - Smoke checklist can be run in under 10 minutes.
