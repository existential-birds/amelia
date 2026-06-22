# 01 — Orchestration Playbook

This is *how* the prior session shipped 7 clean PRs in parallel. Reuse it verbatim. You are
the **orchestrator**: you do not write production code yourself. You fan out isolated subagents,
each owning one issue, and shepherd their PRs. Keep your own context lean — push work and state
into subagents and files.

## The core mechanic: one worktree subagent per issue

Launch implementation agents with the **Agent tool**, `subagent_type: "general-purpose"`,
`isolation: "worktree"`. The worktree gives each agent its own checkout so parallel agents
never collide. Each agent: writes failing tests first, implements, verifies, commits, pushes,
opens its own PR, and returns a ≤150-word summary.

**Launch independent agents in a single message** (multiple Agent tool calls in one turn) so
they run concurrently.

### Concurrency limit — learned the hard way
The prior session launched **7 heavy agents at once** (including one 43-minute monster for the
sandbox worker) and **5 of them died on transient `API Error: 529 Overloaded`** mid-work.
- Keep concurrent heavy agents to **~3–4 at a time**, not 7+.
- If an agent dies on 529, it is **server-side and transient** — just relaunch that issue.
- **You cannot `SendMessage`-resume a dead agent in this (Remote Control) environment.** So a
  relaunch is a *fresh* agent with no memory of the dead one's partial work. Before relaunching,
  **check whether the dead agent got far enough to push** (see "Recovering from a dead agent").

## The subagent prompt template

Every implementation-agent prompt followed this shape. Fill the `«...»` slots from the issue.

```
Implement GitHub issue #«N» in the amelia repo (Python, uv, TDD). You are in an isolated git
worktree — work on a new branch and open a PR.

ISSUE #«N» — «title».
PROBLEM: «1–3 sentences. Paste the issue's problem statement.»
LOCATIONS: «file:line references from the issue — these matter; agents waste time without them.
            Add "(line numbers approximate; locate the actual code)" since lines drift.»

REQUIRED CHANGES:
1. «concrete change»
2. «concrete change»

ACCEPTANCE CRITERIA:
- «observable outcome 1»
- «observable outcome 2»
- Test: «what to assert — see "Test discipline" below. Demand the OBSERVABLE consequence and an
   edge-case SHAPE, not just that a function was called.»

DISCIPLINE: TDD — write the failing test FIRST, then implement. Assert observable consequences,
not dispatch. Read each file before editing; re-read before re-editing. There is NO such thing
as a pre-existing failure — if any test fails in your session, fix it (no "unrelated" /
"environmental" / "out of scope" excuses).

VERIFY (run, and report the ACTUAL output — do not claim success with errors outstanding):
- uv run ruff check --fix amelia tests
- uv run mypy amelia
- uv run pytest tests/unit/   (plus the specific tests for «this area»)
State exactly which commands you ran and their pass/fail counts.

OPEN PR:
- Branch: «perf|feat|refactor»/«N»-«slug»
- Commit ALL your changes. Use the commit/PR trailers your own environment specifies (the
  Co-Authored-By line and Claude-Session URL from your Bash tool instructions — do NOT copy
  another session's IDs).
- If `git push` pre-push hook fails on `pnpm build` because the fresh worktree has no
  dashboard deps, run `cd dashboard && pnpm install` then retry. The gate must pass
  legitimately — never use --no-verify.
- gh pr create --title "«type(scope): summary (#N)»" --body "«problem, change, verification,
  Closes #N»". The PR body must end with the 🤖 Generated-with-Claude-Code trailer + your
  session URL (as your environment specifies).

Return ≤150 words: what changed, exact verification results (pass/fail counts), the PR URL.
```

### Why each piece matters
- **file:line LOCATIONS** — the single biggest quality lever. Agents with precise locations
  went straight to work; without them they flailed.
- **"observable consequence, not dispatch"** — enforces the project's test rule (CLAUDE.md):
  assert the state the user would observe (the row written, the client reused, the coroutine
  that advanced), never "the method was called."
- **edge-case SHAPE** — bugs hide in structural variation. Demand N=many, bare-repo,
  detached-HEAD, mid-cut spans, etc. — whatever shape would break the naive implementation.
- **"NO pre-existing failure"** — this project (CLAUDE.md + the user's standing rule) treats
  *every* failing test in your session as yours to fix. Agents must not surface "unrelated"
  failures; they fix them.

## Project verification facts

- Backend lint/type/test:
  `uv run ruff check --fix amelia tests` · `uv run mypy amelia` · `uv run pytest` (or `tests/unit/`).
- Dashboard (from `dashboard/`): `pnpm build` · `pnpm test:run` · `pnpm lint:fix` · `pnpm type-check`.
- **Pre-push hook runs `ruff check`, `mypy`, `pytest`, and `pnpm build` — all must pass.** A
  successful `git push` therefore *proves* the gate passed. This is why a pushed branch == verified.
- Tests use `pytest-asyncio` with `asyncio_mode = "auto"`. Integration tests
  (`tests/integration/`) use real components — mock only at the external boundary (HTTP to LLM
  APIs, the Daytona SDK). Never mock internal classes.
- Fresh worktrees lack `dashboard/node_modules`; the agent must `pnpm install` there before the
  pre-push `pnpm build` can pass.

## Verifying results after agents return

1. **Confirm each PR exists and is green:**
   ```bash
   gh pr list --state open --json number,title,headRefName --jq 'sort_by(.number)|.[]|"#\(.number) \(.headRefName)  \(.title)"'
   ```
2. **Trust GitHub, not the local checkout.** Worktree-agent branches may NOT propagate cleanly
   into the primary checkout's branch namespace — `git rev-parse <branch>` in the main checkout
   can show `main`'s SHA while the **remote/PR has the real commit**. Always verify with
   `gh pr diff <PR> --name-only` and `gh pr view <PR> --json commits`. The prior session hit
   exactly this and nearly mis-reported a complete PR as empty.
3. **Check file overlaps → merge order.** When two PRs touch the same file, note it so whoever
   merges second rebases:
   ```bash
   for br in «branch1» «branch2»; do echo "--- $br ---"; gh pr diff «PR» --name-only; done
   ```
   (Prior cluster overlaps were `sandbox/driver.py` between #640/#641 and `drivers/api/deepagents.py`
   between #642/#645 — different regions, trivially resolvable.)

## Recovering from a dead agent (529 or any mid-run death)

The Agent tool result for a dead worktree agent still reports its `worktreePath` and
`worktreeBranch`. Before relaunching:

```bash
git worktree list                                  # find the orphan worktree + its branch
git log -1 <branch>                                # did it commit?
git ls-remote origin <intended-branch-name>        # did it push? (remote ref present = pushed = gate passed)
gh pr list --state open                            # did it already open a PR?
```

- **If it pushed but never opened a PR** (remote branch exists, no PR): it's essentially done —
  just open the PR yourself: `gh pr create --head <branch> --title ... --body ...`. (Prior
  session did exactly this for #645/PR #651.)
- **If it never committed** (branch == main, no remote): genuinely incomplete. **Prune the
  orphan and relaunch fresh:**
  ```bash
  git worktree remove --force .claude/worktrees/agent-<id>
  git branch -D <branch>
  ```
- Worktrees with uncommitted changes are NOT auto-cleaned — you must `--force` remove them.

## Cleanup at the end

After PRs are open, leave the per-PR worktrees (they hold the branch until merge). Remove any
scratch files you or subagents created in the repo root (the prior session had to delete stray
`.research-*.md` / `.*-arch-map.md` dotfiles left by exploration agents — "no ghosts").

## Do-not list
- Don't write production code yourself — orchestrate.
- Don't launch 7+ heavy agents at once (529 storms).
- Don't copy another session's commit/PR trailer IDs — use your own.
- Don't trust a local branch SHA over the GitHub PR.
- Don't merge PRs unless the user asks — they merge.
