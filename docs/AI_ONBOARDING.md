# AI / Agent Onboarding — OrderHub CRM

> Read this **first** in any new AI session before touching code or
> docs. It is the durable contract between Sergii (the user), Cowork
> (the planning agent — usually Claude in Claude.ai with file +
> browser tools), and Claude Code (CC — the CLI coding agent).
> Sprint-specific state lives in `task.md` and `implementation_plan.md`,
> not here. **This file describes how we work, not what we are working
> on.**

## 1. Business context (one paragraph)

OrderHub CRM is a multi-channel order-management system for a
Ukrainian handcrafted leather-goods business. Orders flow in from
three sales channels — **Etsy** (CSV import), **Shopify** (API
sync), and **Manual entry** — into a unified pipeline with logistics
automation via **Nova Poshta** (UA national carrier). Real shops in
the system: KoraKlenu (manual, UA, ships via NP), Lamamarka Shopify
(US shipping), LeatherCraft UA (Etsy), Leather by Mykola (Etsy). The
operator (Sergii) is the single human user. Stack: Python 3.11 +
FastAPI backend, React 18 + TypeScript + Vite frontend, PostgreSQL
in Docker, Alembic migrations, JWT auth.

## 2. First message into a new chat

### 2.0 Pre-flight — filesystem access (do this BEFORE typing the template)

The AI in a new chat can't read any of the docs below unless the
session has filesystem access to this repo. Confirm both prerequisites
before pasting the template:

1. **Cowork mode** (not a regular Claude.ai chat — Cowork is the
   variant with file tools: `Read`, `Write`, `Edit`, `Bash`, etc.).
   Open it from the desktop app or claude.com sidebar.
2. **Mount this WSL repo as the workspace folder.** In Cowork's
   folder selector, pick
   `\\wsl.localhost\ubuntu\home\serhii\projects\OrderHub`.
3. **Verify.** The `<env>` block at the bottom of the system prompt
   should show `User selected a folder: yes` and the resolved path
   should match the repo. If not — re-select the folder.

If you skip these steps, the AI responds to the template with
"I don't see those files" and the bootstrap fails. **Do the
pre-flight first.**

### 2.1 First message template (copy-paste)

Once pre-flight is green, paste this. It loads the AI's mental
model from invariant + volatile docs in the right order.

```
Привіт! Я працюю над OrderHub CRM.

Перед тим як почати — переконайся, що у <env> видно
"User selected a folder: yes" і шлях
\\wsl.localhost\ubuntu\home\serhii\projects\OrderHub.
Якщо ні — скажи мені, я перепідключу папку.

Якщо доступ є — прочитай у цьому порядку:
  1. docs/AI_ONBOARDING.md   — workflow, tools, paths (this file)
  2. CLAUDE.md               — project rules, stack, conventions
  3. implementation_plan.md  — sections "Active Roadmap" +
                               "Explicitly deferred" +
                               "Open Architectural Questions"
  4. task.md                 — current sprint, if any
  5. docs/integrations/nova-poshta.md  — if anything touches NP

Then give me a one-paragraph summary of current state and ask
what's next. Don't start any work until I confirm.
```

The order matters: invariant rules first (§1-9 of this guide +
CLAUDE.md), volatile state second (`implementation_plan.md` +
`task.md`).

### 2.2 Fallback — when Cowork isn't available

If you're on a device or in a session without Cowork (e.g.,
regular Claude.ai chat on a phone, or another vendor's tool), the
AI has no filesystem access — you'll need to inject the docs
manually:

- **Quick path (for short questions):** paste the contents of
  `CLAUDE.md` + the relevant section of `implementation_plan.md`
  directly into chat. Sufficient for one-off "what's the rule
  for X" lookups.
- **Full bootstrap (for actual work):** copy-paste all five docs
  in the order listed in §2.1. Slow (5 paste operations) and
  the AI can't write back to the repo — but it works for
  read-only planning conversations.
- **Best alternative:** wait until you're back on a Cowork-capable
  session. The file-tool round-trip (read code, run tests, write
  back, verify) is what makes the workflow fast. Without it, you
  lose most of the value.

## 3. Three-actor model

| Actor | Role | Tools | Commits |
|---|---|---|---|
| **Sergii** (user) | States priorities, runs SQL on local DB, reviews plans, performs manual smoke when browser MCP gets stuck, commits docs and pushes | Local shell, NP cabinet UI | docs / `implementation_plan.md` |
| **Cowork** (this guide's audience) | Planning agent. Drafts task.md prompts (English, settled rules + Open Questions). Verifies sprints visually via browser MCP. Writes closure entries in `implementation_plan.md`. Does NOT edit production code. | `Read` / `Write` / `Edit` / `Grep` / `Glob` / `Bash` / `mcp__Claude_in_Chrome__*` / `TaskCreate` / `TaskUpdate` / `mcp__scheduled-tasks__*` / `WebSearch` | Never |
| **Claude Code (CC)** | Code execution. Runs on the CLI with Opus high-effort. Plan mode → edits → tests → commit. Never edits `task.md` / `implementation_plan.md` post-fix notes. | CC's own toolset (separate process — not Cowork's tools) | Source code only |

**Key invariant:** task.md and implementation_plan.md are written
by **Cowork + Sergii together**. CC reads them, never modifies
them. Source code is the inverse — CC owns it; Cowork only reads.

## 4. Tooling + path mapping

The repo lives in WSL on Sergii's Windows box. Cowork reaches the
filesystem through **two different paths** depending on the tool:

Sergii mounts the repo in Cowork's folder picker using this exact
UNC path (Cowork cannot request it programmatically — the folder
picker will not accept a UNC path from `request_cowork_directory`):

```
\\wsl.localhost\ubuntu\home\serhii\projects\OrderHub
```

| Tool | Works over the WSL mount? |
|---|---|
| `Read`, `Write`, `Edit`, `Grep` | **Yes** |
| `Glob` | Unreliable — times out on broad patterns over UNC. Prefer `Grep` with a narrow `path`. |
| `Bash` (`mcp__workspace__bash`) | **No.** Returns `UNC paths are not supported`. |

**Correction (2026-07-21):** an earlier version of this section
claimed a file edited at the UNC path was also reachable by `Bash`
at a `/sessions/<id>/mnt/` path. **That is false.** The Linux
sandbox cannot mount UNC at all, so Cowork can read and write the
repo but **cannot run anything in it** — no `pytest`, no `alembic`,
no `npm`, no `git`. Those are run by Sergii in WSL, or by CC.
Do not spend time looking for a workaround; there isn't one.

Practical consequence: Cowork can never verify its own doc edits by
running the test suite, and cannot inspect git state. When Cowork
needs `git status` or a test result, it must ask.

**Browser MCP** (`mcp__Claude_in_Chrome__*`) automates the
frontend at `http://localhost:3000` (Vite dev server) backed by
`http://localhost:8000` (uvicorn). Used for smoke tests after each
sprint. **Always call `tabs_context_mcp` first** in a fresh
session to see existing tabs; pass `createIfEmpty: true` if none
exist yet. Other browser tools fail until a tab is registered.

**Scheduled tasks** (`mcp__scheduled-tasks__*`) — Cowork can set
reminders for Sergii (e.g., "tomorrow 10:00, continue with X").
Used between work sessions.

### 4.1 Where the environments live

Three distinct places — do not confuse them:

| Environment | Where | Who touches it |
|---|---|---|
| **Dev** | Sergii's WSL, `/home/serhii/projects/OrderHub`. Vite on `:3000`, uvicorn on `:8000`, local Postgres. There is **no separate dev server** — "dev" is this laptop. | CC edits, Sergii runs, Cowork reads |
| **Remote** | `github.com/cropsp/OrderHub` (**private**). Branches are local until Sergii pushes — a committed sprint is *not* automatically on GitHub. | Sergii pushes |
| **Prod** | Home server `prorder@192.168.31.71` (`ssh orderhub`), Docker Compose, public at `https://orderhub.orderapp.uk` via Cloudflare Tunnel. | Sergii approves; **CC executes** (`ssh orderhub` from the dev WSL — merge, push, server pull, rebuild, migrations, prod SQL checks). Sergii does not drive deploys by hand. If the auto-mode classifier pauses an ssh step mid-deploy, that is the §9 approval quirk — re-confirm and continue. (Clarified 2026-08-07 after a planning agent read "Sergii deploys" as "Sergii types the commands".) |

**Canonical prod reference is `CLAUDE.md` § "Server Deployment" plus
`SERVER_DEPLOY_PLAN.md` §1–§10, and `BACKUP_PLAN.md` for backups and
restore** — deliberately not duplicated here, so there is one place to
keep correct. This table exists only so a new agent
knows the three environments are distinct and which document to open.

A sprint is on prod only after: commit → push → merge to `main` →
deploy. A closure entry that says "not merged, not deployed" means the
code exists **only in Sergii's working copy.**

## 5. Documentation hierarchy

| File | Stability | Read on every session start? | Content |
|---|---|---|---|
| `CLAUDE.md` | Invariant | Yes | Project rules, stack, conventions, gotchas |
| `docs/AI_ONBOARDING.md` (this file) | Invariant | Yes | Workflow, tooling, path mapping |
| `implementation_plan.md` | Slow-evolving (one closure entry per sprint) | Yes — sections **Active Roadmap** + **Explicitly deferred** + **Open Architectural Questions** | Sprint history + parked backlog + design questions |
| `task.md` | Volatile (rewritten every sprint) — **git-ignored, local only** | Yes if file exists | Current sprint spec for CC |
| `docs/integrations/nova-poshta.md` | Slow-evolving | Only if sprint touches NP | NP API contract, gotchas, credentials, playbook |
| Per-sprint reading suggestions | — | Sprint context | Find sprint ID in implementation_plan.md to read sprint history |

When in doubt about the current sprint, search
`implementation_plan.md` for sprint IDs (`PKG-`, `NP-FIX-`, `BUG-`,
etc.) — each has a closure entry with commit hash, tasks, post-fix
notes, and smoke evidence.

### 5.1 Two rules added 2026-07-21 (learned the hard way)

**`task.md` is git-ignored and disappears at the next sprint.** Until
2026-07-21 it was *tracked but never re-committed*, so `HEAD` held a spec
frozen at the S005 era while ADDR-VAL-1/2, USERS-LIST-500, USER-ACCESS-1
and USER-ACCESS-2 were each written in place and overwritten by the next
sprint. That is the worst of both worlds: misleading archaeology in git
plus a permanent `M task.md` in `git status`. It is now explicitly
untracked.

**Consequence — the closure entry is the only durable record.** A closure
entry in `implementation_plan.md` must therefore carry the *reasoning*,
not just the outcome: rejected alternatives, accepted trade-offs, and what
remains unverified. If it only says what was built, the answer to "why
capabilities and not roles?" exists nowhere three months later.

**`CLAUDE.md` describes the state of `main`, never work in flight.** A
sprint's rules go into CLAUDE.md when it is **merged**, not when the code
is written. On 2026-07-21 CLAUDE.md described USER-ACCESS-2 in the past
tense while its 32 files were still uncommitted on a feature branch; a
planning agent read that as shipped, wrote "USER-ACCESS-2 is DONE, merged
+ deployed" into the next sprint's task.md, and the next sprint's commit
collided with the uncommitted work. If a sprint is not on `main`, its
status belongs in `implementation_plan.md` with an explicit
"not merged, not deployed" line — not in CLAUDE.md.

## 6. Sprint workflow — happy path

Seven steps from idea to merged commits:

```
1. Sergii  states priority / bug / feature.
2. Cowork  writes task.md with:
              • Behaviour rules (settled — do not relitigate)
              • Scope (in / out)
              • Open questions for the planner
              • Verification (pytest + manual smoke steps)
              • Workflow (plan mode first, commit message,
                "do not touch task.md / implementation_plan.md")
3. Sergii  hands task.md to CC: "Read task.md, plan mode,
            wait for my approval."
4. CC      enters plan mode and answers Open Questions with
            cited evidence (file:line refs, grep results, curl
            probes, etc.). Sergii reviews with Cowork's help.
5. CC      gets approval (ExitPlanMode + auto-mode), edits +
            tests + commits.
6. Cowork  runs manual smoke via browser MCP. Documents
            results.
7. Cowork  writes closure entry in implementation_plan.md.
            Sergii commits docs (.gitignore / docs / plan /
            other config) and pushes.
```

Commit message conventions (consistent across history):

- CC code: `feat(<area>): ...`, `fix(<area>): ...`,
  `refactor(<area>): ...`
- Cowork closure docs: `docs(<sprint-id>): close sprint with ...`

## 7. When the happy path doesn't fit

Three deviation patterns observed in practice — useful to recognise:

- **Wrong hypothesis revision** (e.g., NP-FIX-3a Rev 1 → Rev 2).
  task.md's hypothesis turns out wrong during CC's plan or smoke.
  Cowork rewrites task.md with the corrected hypothesis; CC
  rolls back its edits via `git checkout HEAD -- <files>` and
  starts the new plan. Re-iteration is expected, not failure.
- **User-side manual config alongside CC** (e.g., PKG-1b
  KoraKlenu setup, NP-FIX-3 dev shop). Some work cannot be
  scripted — Sergii configures via the UI or runs SQL while CC
  works in parallel. Cowork coordinates the order in task.md.
- **Smoke surfaces a related bug** (e.g., PKG-2 smoke surfaced
  NP-FIX-4 root cause). Don't reopen the current sprint — file
  the new bug as a fresh ID in **Explicitly deferred** with a
  short repro note, finish current sprint, then either pick up
  the new bug next or park it.

## 8. task.md writing pattern (template)

Every task.md follows this skeleton. Settled answers go into
**Behaviour rules**; uncertainties go into **Open Questions** for
the planner to resolve.

```markdown
## <SPRINT-ID> — <one-line title>

### Goal
<2-4 sentences. What we are fixing/building and why.>

### Behaviour rules (settled — do not relitigate)
1. <Rule with file:line ref where possible.>
2. <Etc.>

### Scope
- In scope: <files / endpoints / models touched>
- Out of scope (do NOT touch): <list>

### Open questions for the planner
1. <Question CC must answer with cited evidence in the plan.>

### Verification
- Backend: `python -m pytest tests/ -v` — expect <N> passing
- Frontend: `npx tsc -p tsconfig.app.json --noEmit && npm run lint` —
  no NEW errors vs the TYPECHECK-1 baseline (see CLAUDE.md § Test &
  Verify; bare `npx tsc --noEmit` is a no-op that checks 0 files —
  never cite it as evidence)
- Manual smoke (Cowork via browser MCP / Sergii): <steps>

### Workflow
- Use plan mode first. Wait for my approval before editing.
- After approval: edits + tests + commit.
- Commit: `feat(<area>): <short>` or similar.
- Do NOT update implementation_plan.md or task.md post-fix
  notes — the planning agent owns those.
```

The "Behaviour rules" + "Open questions" split is the load-bearing
distinction. Settled decisions are settled; CC plans against them.
Open questions force CC to demonstrate understanding with evidence
before editing.

## 9. Gotchas & operational tips

Patterns from real failures — phrased as "what to do when you see
X". If a quirk goes away in a future tool/model version, ignore the
note; it isn't gospel.

- **Auto-mode classifier mid-flow approval block.** Pattern
  observed since 2026-05: after `ExitPlanMode` is approved and
  auto-mode is selected, CC sometimes pauses again before tests,
  commit, or migration apply, citing the original "wait for my
  approval" instruction from task.md. The original instruction
  applies to the plan→edit transition only. Re-confirm via the CC
  menu ("Yes, continue") or a brief chat reply — work resumes.
  Not a real safety gate; transparency quirk.
- **Browser MCP timeout on confirmation dialogs.** Observed twice
  on Delete TTN. Symptom: `left_click` on the Delete button
  returns no error but subsequent screenshots / network reads
  time out. Workaround: Sergii clicks the in-browser confirmation
  manually; Cowork resumes after.
- **Backend logs are in `backend/logs/server.log`, not docker
  stdout.** `docker compose logs backend` returns only what
  `uvicorn` wrote to stdout — RotatingFileHandler writes the real
  log file. Always grep the file when debugging
  `[SHIPPING]`, `nova_poshta`, etc.
- **NP API errors come as `list[str]` or `dict[str, str]`.**
  Always check shape before joining. See NP-UX-4 in
  implementation_plan.md for the recurrent symptom.
- **UNC path globbing.** `Glob` with `path` set to the UNC root
  is more reliable using `**/<pattern>` than `<dir>/<pattern>`
  (the latter sometimes returns empty even when files exist).
  Prefer `**/foo.md`. Workaround verified 2026-05.
- **Do not add `Co-Authored-By: Claude` trailer to CC's commits.**
  Anthropic policy blocks impersonation; the auto-mode classifier
  blocks the commit if it sees that trailer. CC commits without
  the trailer. Sergii's docs commits are his own — no trailer
  needed there either.
- **`task.md` and `start-dev.sh` are intentionally not committed
  between sprints.** task.md is rewritten every sprint;
  `start-dev.sh` is a local-only startup script. Sergii skips
  them at `git add`; Cowork does not stage them.
- **Migration round-trip is part of verification, not optional.**
  `alembic upgrade head && alembic downgrade -1 && alembic
  upgrade head` — all three must complete cleanly before any
  migration ships. Downgrade-incompatible migrations should call
  it out in the module docstring (e.g., PKG-1b's shop_id drop
  warns about unrecoverable shop ownership).

## 10. Operational commands cheat-sheet

```bash
# Backend
cd backend && source venv/bin/activate
python -m pytest tests/ -v
alembic upgrade head
alembic downgrade -1
alembic revision --autogenerate -m "description"

# Frontend
cd frontend
npx tsc -p tsconfig.app.json --noEmit   # the REAL typecheck; bare `npx tsc --noEmit` is a no-op (solution tsconfig, 0 files)
npm run lint
npm run dev          # dev server on :3000 (vite.config.ts:16 — NOT Vite's default 5173)

# Database — admin access
docker compose exec -T postgres psql -U crm -d crm_db -c "<SQL>"
docker compose exec -T postgres psql -U crm -d crm_db <<'SQL'
<multi-line>
SQL

# Logs
grep -E "SHIPPING|nova_poshta|ERROR" backend/logs/server.log | tail -30

# Startup (Sergii's local wrapper — not in repo)
./start-dev.sh
```

## 11. When stuck — troubleshooting decision tree

If Cowork hits an unexpected state, work through this list before
asking Sergii:

1. **Tool returned empty / error.** Re-check the path mapping
   (§4) — UNC vs sandbox. `Glob` empty? Try `**/<pattern>`.
2. **`git status` shows no changes after editing a file.** The
   edit may already be committed — check `git log --oneline -5`
   and `Read` the file to confirm content. Don't re-edit.
3. **Browser MCP times out.** Try `get_page_text` (lighter than
   `screenshot`); if still stuck, ask Sergii to do the click
   manually.
4. **CC pauses asking for approval.** Read the prompt — if it's
   the same task that was already approved via `ExitPlanMode +
   auto-mode`, tell CC to continue (gotcha §9). If it's a new
   decision (e.g., migration apply with data loss), surface it
   to Sergii.
5. **Backend test failing after migration.** Run `alembic upgrade
   head` once explicitly — sometimes CC writes the migration but
   forgets to apply it on the dev DB.
6. **NP API error not in the gotchas table.** Read
   `docs/integrations/nova-poshta.md` §3, then grep
   `backend/logs/server.log` for the raw payload. Most NP errors
   are parameter-name or parameter-shape issues.
7. **Lost — no clear next step.** Ask Sergii. Don't speculate
   into code edits.

---

## Closing notes

This file is invariant. The list of sprints, the active sprint,
the latest commit — all of that lives in `implementation_plan.md`
and `task.md`. When this guide ages (tools rename, MCP behaviour
changes, workflow shifts), update it in a small docs-only commit
rather than letting outdated guidance accumulate.
