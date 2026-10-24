# Lessons: gotchas that are still true

Loaded into every agent session, so it holds only what applies across the repo. Area lessons live beside their code and load only when a session works there: `node/AGENTS.md` (Node service and the Mesh), `dashboard/AGENTS.md`, `scripts/AGENTS.md` (data builds) and `pi/AGENTS.md` (Pi and networking). Add a line when something breaks, surprises you or takes more than one try, in the file for its area; delete a line once your change makes it untrue. The full hackathon log, with the story behind each line, is `docs/agents/lessons-archive.md` (search it, don't load it).

## Working in the repo

- **One `pytest` at a time, and no stray Nodes.** A Node left running (yours, another worktree's, a demo) holds test ports and serves old code. `scripts/stop-nodes.sh` clears them, but check `ss -ltnp` first: it would kill a teammate's or your other session's Node. On Windows it cannot find them; use `Get-NetTCPConnection` and `Stop-Process`.
- **Rerun before chasing a flake.** Known ones: `evacuationFlow.test.tsx` and other dashboard flow tests in full parallel `vitest` runs (`--maxWorkers=2` helps); the `mesh_integration` Reticulum tests when ports are busy. A second failure is real.
- **Check exit codes, never pipe through `tail`.** `check.sh | tail` hid a failing pytest and the push went through; vitest can pass every test and still exit 1 with "Errors" from an uncaught exception.
- **A baseline "without my change" is the parent of your merge**, not a commit that already holds it.
- **Two branches green alone can clash once merged** (0060 and 0012 did). Rerun the Commands after every merge of `main`.
- **Worktree sessions refuse compound shell commands** (`cd x && ...`, `env VAR=... cmd &`, heredocs mixed with `cd`). Run plain commands, or write a script to the scratchpad and run that.
- **`pkill -f <pattern>` inside a compound command can kill its own shell**, and over SSH the remote shell; use `pkill -f "[s]torm-shield-node"`.
- **Don't name two files apart only by case** (`joinCard.ts` and `JoinCard.tsx`): they collide on macOS.
- **After editing a file by script, read `git diff --stat`**: a splice of `App.css` once duplicated 1,300 lines and every check stayed green.
- **Windows checkouts have CRLF**: `layoutCss.test.ts` fails on them, and Python text-mode writes add CRLF (open with `newline=""`). Identity-file tests assert mode 600, which Windows cannot report; those two failing alone is expected there.
- **The secret scan matches `sk-` plus 20 characters** not inside a word. Rename what trips it; never `--no-verify`.
- **Some cloud agent sessions cannot reach PyPI or npm** (`uv sync` and `pnpm install` fail on the proxy, and the local caches are partial), so nothing in `scripts/check.sh` runs there. Say so, keep the PR a draft and let CI run the checks; hand-wrap any line you lengthen, since `ruff format` cannot run either.
- **No `uv`:** another checkout's `node/.venv` works with `PYTHONPATH=src` (`check.sh` does it). **No `pnpm`:** `npx --yes pnpm@10`. Vitest needs Node 22 (its jsdom worker dies on 20). On Windows install `uv` from PowerShell; plain `venv` on Python 3.14 fails on `cryptography`.
- **Run `mypy src tests` from `node/`**, or it stops on a duplicate `__main__`. mypy strict follows `scripts/` imports from the tests, so a script a test imports must be fully typed.
- **Don't run `ruff format` on `scripts/*.py`**: they are not formatted by it. Write new lines at 100 columns by hand.
- **Don't edit `node/uv.lock` by hand.**
- **Prettier reformats new test files**: `pnpm format` before `pnpm lint`.
- **Area lessons load only when a session reads a file in that folder** (`node/`, `dashboard/`, `scripts/`, `pi/`). Before building in an area you have not opened a file in yet, read its `AGENTS.md`.

## Rehearsing without devices

- **Rehearsing without devices:** Hub on slot 0 and Sensors on later slots with `NODE_MESH_INTERFACE=loopback`, their own ports and data dirs; serve a pack with `python3 -m http.server`; "no internet" is stopping that server. Open `http://localhost:<port>` for Hub-only pages (`/api/join` needs loopback). This proves the software path only; say so.
