---
title: "AI-Assisted Development"
description: "Build faster with AI coding assistants"
sidebar:
  label: "AI Coding"
---

## Overview

stk is built to be operated by coding agents. The repository ships four layers of agent context, from broad to specific:

| Path | What it holds |
|---|---|
| `CLAUDE.md` | Commands, architecture, auth policy, frontend conventions, gotchas |
| `AGENTS.md` | A symlink to `CLAUDE.md`, for agents that read that name |
| `.stk/context/` | Focused references: architecture, commands, verification, frontend, security, deployment |
| `.claude/skills/` | Task skills, mirrored at `.agents/skills/` |

Because `AGENTS.md` points at `CLAUDE.md`, there is one file to maintain. Claude Code reads `CLAUDE.md` and loads the skills automatically; other agents that read `AGENTS.md` get the same content.

## Skills

Each skill is a `SKILL.md` an agent loads when the task matches:

- `stk-dev`: background conventions for models, views, templates, queries, auth, and the Vue frontend, so the agent writes async Quart instead of Flask patterns.
- `stk-blueprint`: scaffold a feature module with models, views, templates, and a migration.
- `stk-api`: async CRUD endpoints for an existing model.
- `stk-migrate`: generate and review an Alembic migration.
- `stk-deploy`: take an app live on a fresh VPS with HTTPS, systemd, and a hardened OS.

## Verify, Don't Guess

The instructions steer agents to the CLI over reading files, because the running app is the canonical source:

```bash
uv run stk inspect context --json   # Routes and models in one contract
uv run stk doctor                   # Environment state, each line with its fix
uv run stk verify --json            # Lint, sanity, and migration checks
uv run stk smoke --json             # Real-browser behavioral check
```

See [The Build Loop](/build-loop) for how these fit together.

## Example Prompts

```bash
claude

> "Add a Post module with title and content"
> "Add a JSON API to list and edit posts"
> "Add the posts page to the sidebar for admins only"
```

## Customizing for Your Project

Add project-specific patterns to `CLAUDE.md`, or a new skill under `.claude/skills/` for a repeatable task:

```markdown
## Order Processing
1. Create order via POST /api/orders
2. Process payment via Stripe
3. Update status to 'paid'
```

Agents pick up the change on their next session.
