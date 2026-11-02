# AGENTS.md

Rules for every coding agent on this repo (Claude Code, Cursor, Copilot, Codex…) and for the humans driving them. Four part-time people, every change through a pull request. Keep it working, keep it readable, leak nothing.

## Project

**Idea:** Storm Shield, a community flood warning dashboard, demonstrated on a replay of the 26 August 2026 Bhote Koshi flood in Nepal (ADR 0004), whose Community Readings keep flowing over a local Mesh when the internet goes down (glossary: `CONTEXT.md`). Spec: `docs/specs/`.

## Stack

- Node service: Python 3.12+, FastAPI, managed with uv (`node/`)
- Dashboard: React + Vite + TypeScript, managed with pnpm (`dashboard/`), built to `dashboard/dist` and served by every Node
- Tests: pytest (Node API seam), Vitest (dashboard seam)
- Hosting for the demo: laptops and Raspberry Pis on the local Wi-Fi, no cloud

## Commands

Run these before calling any issue done. An agent must not claim "done" without running them.

| Task | Command |
|---|---|
| Install | `cd node && uv sync` and `cd dashboard && pnpm install` |
| Build dashboard | `cd dashboard && pnpm build` |
| Run a Node | `cd node && uv run storm-shield-node` (serves the built dashboard; `NODE_ROLE=hub` for the Hub, default `sensor`; `NODE_REGION=<folder under regions/>` picks the Hub's Region, and its Cache Pack is downloaded from the Release `cache-pack-<region>-v<N>` unless `CACHE_PACK_URL` says otherwise) |
| Try the app with no setup | `scripts/sandbox.sh` from anywhere (a Hub and four registered simulated Sensors in one process, then the browser; `--port`, `--pack`; it uses the Region's pack from `node/build/<region>/` or `.demo/pack/<region>/`, else downloads it from the Release once, and says `scripts/build-cache-pack.sh <region>` when neither works; it builds the dashboard on the first run, so it needs `pnpm`) |
| Sandbox app (Mac/Windows downloads) | built by the "Sandbox app" workflow (`.github/workflows/sandbox-app.yml`), not by `scripts/check.sh`: a pull request touching the packaging builds and smoke-checks both; dispatch it with a number to publish the Release `sandbox-app-v<N>`. Try the smoke check on your own machine: `uv run --project node --with "pyinstaller>=6,<7" python scripts/sandbox_app_build.py`, then `uv run --project node python scripts/sandbox_app_smoke.py dist-sandbox-app/<zip>` (Mac or Windows only) |
| Keep the Pi's Hub on your checkout | `scripts/run-live.sh` (a Hub by default; rebuilds whenever `HEAD` moves, e.g. after `git pull`, and swaps the Node only when the build worked) |
| Build a Region's Cache Pack | `scripts/build-cache-pack.sh nepal` (reads `regions/<name>/region.json`; needs the internet and `uv`; writes `node/build/<name>/cache-pack.zip`; notes in `scripts/cache-pack/README.md`) |
| Dashboard dev server | `cd dashboard && pnpm dev` (proxies `/api` to port 8000) |
| Typecheck | `cd node && uv run mypy src tests` and `cd dashboard && pnpm typecheck` |
| Lint + format | `cd node && uv run ruff check . && uv run ruff format --check .` and `cd dashboard && pnpm lint` (`pnpm format` to fix) |
| Tests | `cd node && uv run pytest` and `cd dashboard && pnpm test` |
| Real-Reticulum tests (not in CI) | `cd node && uv run pytest -m mesh_integration`, or the "Mesh integration" workflow on GitHub |
| **All of the above** | `scripts/check.sh` (`node` or `dashboard` for one side; works without uv/pnpm and on Node 20, and lists anything it could not run) |
| Start an issue | `/implement <N>` (assigns you, worktree, branch `<N>-<slug>`, draft PR) |
| Setup problems | `scripts/doctor.sh` (missing tools, hooks off, behind `main`, a Node left running) |
| Stop stray Nodes | `scripts/stop-nodes.sh` (frees the ports the Node tests need) |

## No Pis or sensors

Agents and their drivers currently have **no Raspberry Pis or sensors**; phones are available. Any check that says "unplug the internet" or "over the mesh" is rehearsed on one laptop: two or more Node processes with `NODE_MESH_INTERFACE=loopback`, each with its own `NODE_PORT`, `NODE_LOOPBACK_SLOT` and `NODE_DATA_DIR` (a group that does not start at slot 0 also sets `NODE_LOOPBACK_FIRST_SLOT` to its lowest slot, or it joins every Node below it), and "no internet" simulated by stopping whatever serves the Cache Pack. A phone on the same Tailscale network can open the dashboard from the laptop's Tailscale address, which covers "renders on a phone". Never report a Pi or sensor check as passed; say it was rehearsed locally and what is still unproven on real devices. The recipe is in `docs/agents/lessons.md`.

## Workflow

Idea → spec → issues → build → review → pull request → merge. Plan and order of work: `docs/roadmap.md`.

1. **Grill** the idea until it's sharp (`grilling` skill, or `/grill-with-docs` to also update `CONTEXT.md` and ADRs as you go). Opus.
2. **Spec** it: `to-spec` writes `docs/specs/<feature>.md`. Opus.
3. **Slice** it: `to-tickets` files GitHub issues — thin vertical slices, each one demoable, with blockers and sub-issues. Opus.
4. **Build** one issue per session: `/implement <N>`. Sonnet.
5. **Review** before merge: `code-review` against `main`.
6. **Merge** through the pull request once CI is green and the branch is up to date with `main` (squash). No human approval needed.

Tracker rules: `docs/agents/issue-tracker.md`. Assign yourself and open a draft PR before you write code; that is the claim everyone can see. Every new issue gets a type and an area label; the area says whose queue it is in (dashboard → Fazorath; Node rules, routes and data builds → refloow-0; hardware and Mesh → amitathik7; workflow, tests and the rest → leonardorofaDV). `docs/tickets/` is the frozen hackathon tracker: read it, never edit it.

Other playbooks: `prototype` (throwaway UI/logic experiments), `diagnosing-bugs` (anything broken or slow), `domain-modeling` (keeps `CONTEXT.md`, the shared glossary), `resolving-merge-conflicts`, `handoff` (context running low), `wait-what` (agent lost you).

**Not using Claude Code?** Every playbook is plain markdown at `.claude/skills/<name>/SKILL.md`. Tell your agent "follow `.claude/skills/implement/SKILL.md` for issue 42".

## Code

The repo is public and open source; strangers read it. Write for a teammate seeing the file for the first time at 4 am.

- **Deep modules.** Small interface, real work behind it. `saveTrip(trip)` hides the three API calls; callers never see them. No pass-through wrappers, no one-line "service" classes.
- **Names say what it is.** No `data`, `info`, `handle`, `utils`, `helpers`, `manager`. Use the words in `CONTEXT.md`.
- **No speculative code.** Build what the issue asks. No config options, plugin points or abstractions for needs nobody has.
- **No dead code.** Delete commented-out blocks, unused exports, `console.log` debugging and placeholder TODOs before merge.
- **Comments explain why, never what.** If code needs a "what" comment, rename things instead.
- **One feature, one place.** Code that changes together lives together (feature folders over layer folders).
- **Match the file you're in.** Same naming, same patterns, same formatting as the surrounding code.
- **Errors are visible.** No empty `catch`. Fail loudly in dev; show the user something sane in the demo.

## Secrets — nothing leaks

- Secrets live only in `.env` (gitignored). Every key you add goes into `.env.example` with a blank value and a one-line comment.
- **Never** put a secret in frontend code. Anything shipped to the browser is public. Proxy paid/secret APIs through the backend.
- Never paste keys into chat logs, specs, tickets, commit messages or screenshots.
- The pre-commit hook (`.githooks/pre-commit`) blocks staged `.env` files and things shaped like keys. If it fires, remove the secret — don't bypass it with `--no-verify`. If a key ever reaches GitHub, rotate it immediately; deleting the commit is not enough.

## Git

- Branch per issue: `<N>-<slug>` from an up-to-date `origin/main`, in its own worktree. Never two issues in one checkout.
- Small commits, imperative subject: `add trip search endpoint`.
- Nothing is pushed to `main`: open a pull request (`Closes #N`), and it merges when CI is green and the branch is up to date with `main`. `main` must always be demoable.
- **Pull before you start and before you push.** `git fetch origin main && git merge origin/main`, then rerun `scripts/check.sh` if that brought code in. The `pre-push` hook refuses a push to `main` and a push from a branch behind `origin/main`; `scripts/doctor.sh` runs at Claude Code session start and after every `git pull` and says how far behind you are.
- Never force-push, `reset --hard`, or delete someone else's branch (Claude Code blocks these via a hook).
- No AI attribution in commits or PRs (no `Co-Authored-By: Claude`, no "Generated with" footers). Commits are authored by whoever is driving; the `commit-msg` hook strips any trailer an agent adds.

## Saving limits

- One issue per session. Start a fresh session for the next issue instead of continuing a long one.
- When context runs low, run `handoff` and start fresh from the file it writes.
- Point agents at exact files and issues; don't ask them to "look around the codebase".
- Big searches go to a subagent so the main session keeps only the answer.
