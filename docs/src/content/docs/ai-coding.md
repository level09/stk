---
title: "Working with Agents"
description: "How coding agents find the truth in an stk project, and how it stays true"
---

stk is built to be operated by coding agents. Every fact an agent needs has exactly one home, and every surface an agent reads points at it instead of copying it. Copies drift; pointers do not.

## Three layers

**1. The running code answers questions about the code.** Routes, auth guards, models, commands, and environment state are read from the live app, never from prose:

```bash
uv run stk inspect context --json    # Routes with auth and source, models with columns
uv run stk inspect commands --json   # Every command and option
uv run stk doctor --json             # Checkout state, each problem with its fix
uv run stk new invoice               # The canonical CRUD module, as code
```

**2. These docs explain everything else**, and they ship inside the repo at `docs/src/content/docs/`. An agent reads the version that matches the code it is editing, straight from disk. The same files build this site, `/llms.txt`, and a Markdown copy of every page (`/frontend.md`), so a human, a browser agent, and a coding agent all read one source.

**3. `AGENTS.md` is the index.** It is short on purpose: what stk is, the rules that fail silently, and a table mapping each task to its docs page. It is always in the agent's context, so the agent knows which page to open without having to remember to look. `CLAUDE.md` is the same file, for agents that read that name.

Skills hold procedures, not facts. Each `SKILL.md` in `.claude/skills/` (mirrored at `.agents/skills/`) is a step-by-step workflow an agent loads when the task matches, and links to the docs for the why:

- `stk-blueprint`: scaffold a feature module, customize it, and prove it in a browser.
- `stk-api`: add CRUD endpoints to an existing model.
- `stk-migrate`: generate, review, and round-trip an Alembic migration.
- `stk-deploy`: take an app live on a fresh VPS with HTTPS, systemd, and a hardened OS.

## The gate keeps it honest

Documentation that nothing checks is a guess with a date on it. `stk verify` fails when:

- a docs page, skill, `AGENTS.md`, `README.md`, or `SECURITY.md` names a `stk` command or flag that does not exist, or a `SECURITY_*`/`STK_*` setting the code never reads
- one of them points at a repo file that does not exist
- the [CLI reference](/cli) differs from the live command tree
- `stk/settings.py` reads an environment variable [Configuration](/configuration) does not list
- a Vue `${ }` interpolation in a template contains `{`, which blanks the page
- `AGENTS.md` does not index every docs page, or grows past 8KB (skills past 4KB): detail belongs in a docs page

Every failure names the fix. Change behavior and its docs page in the same commit, and the gate tells you which one you forgot.

## Several agents in one repository

Give each agent its own git worktree and let one owner merge; agents sharing a working tree sweep each other's staged files into their commits. A worktree lacks ignored files, so link the main `.env` into it. Rebase a finished branch onto current `master` and run the gate on the combined result before merging.

## Verify, don't guess

```bash
uv run stk verify --watch    # instant feedback while editing
uv run stk smoke --json      # real browser: status codes, console errors, contrast
```

See [The Build Loop](/build-loop) for the whole cycle, including test-only browser login for agents.

## Example prompts

```bash
claude

> "Add a Post module with title and content"
> "Add a JSON API to list and edit posts"
> "Add the posts page to the sidebar for admins only"
```

## Customizing for your project

An app gets the same structure from `stk init`: its own `CLAUDE.md` (with `AGENTS.md` linked to it) carrying stk's rules and pointing at these docs, and the stk skills in `.claude/skills/`. Both belong to the app: add project rules to its `CLAUDE.md` and a skill for each repeatable workflow. `stk verify` checks an app's code, templates, and migrations; the docs drift checks guard stk's own repository.

## Lessons

When a failure the docs did not warn about costs an agent time, the `stk-lessons` skill has it log one line in `.stk/lessons.md` and carry on. Ask an agent to triage the file now and then: it drops what is covered or happened once, confirms the rest in code, and proposes each one at the strongest home that holds, in this order: a code default that makes the mistake impossible, a `stk verify` check, a `stk doctor` hint, a docs line, a skill step. Nothing changes until you approve the diff, and the size budgets keep `CLAUDE.md` and skills from growing into a pile of rules. Lessons about stk itself come out in generic terms you can send upstream.
