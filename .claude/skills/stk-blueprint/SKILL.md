---
name: stk-blueprint
description: |
  Scaffold a new stk blueprint with models, views, templates, and Alembic migration. Use when creating a new feature module, adding a new section to the app, or scaffolding a blueprint.
argument-hint: "[blueprint-name]"
---

# Scaffold stk Blueprint

Create a complete blueprint for `$ARGUMENTS` in the stk framework.

## Workflow

The scaffolder generates the full module structure. Run it first, then customize domain fields and logic.

```bash
uv run stk new <name>
```

`<name>` must be lowercase snake_case (e.g. `blog_post`, `invoice_line`). Reserved names (`user`, `role`, `portal`, `public`, `session`, `admin`, etc.) are rejected with a clear error.

The command generates:
- `stk/<name>/__init__.py`, `models.py`, `views.py`
- `stk/templates/cms/<name>.html`
- Patches `stk/app.py` (import + `register_blueprint`)
- Patches `stk/static/js/navigation.js` (nav entry)
- Generates AND applies the Alembic migration, then prints the page URL

Then:
1. Customize `stk/<name>/models.py` -- add/rename fields to fit your domain
2. If you changed the model after scaffolding: `uv run stk db revision -m "update <name>"` and review, then `uv run stk db upgrade`
   (only needed for post-scaffold model edits; the initial migration is already applied. With `--no-migrate`, the first revision is manual)
3. Verify: `uv run stk verify && uv run stk smoke`

## Conventions

The generated files already follow every stk convention. When you change them, the rules
are in `CLAUDE.md` and the details in `docs/src/content/docs/models.md`, `docs/src/content/docs/api.md`, and
`docs/src/content/docs/frontend.md`. Read the page before editing that layer.

## Before you report done

Each line is a mistake an agent made while building a real app on stk.

- Lint and format only the files you changed (`uv run ruff format path/a.py path/b.py`), never a whole package another person owns.
- Tests: give test-only blueprints names an app cannot already use.
- Migrations: check each command's exit code, never behind a pipe to `tail`. Never delete a revision file before `stk db downgrade <target>` has succeeded.
- Tables inside Vue's in-DOM templates: never put `<tbody>`/`<tr>` inside `<v-table>` or another custom element; the browser parser moves the rows out before Vue mounts and they never render. Use `v-data-table`, a native `<table>`, or flex rows.
- Verify UI in a browser: `uv run stk smoke`, then look at a screenshot of the page with real rows. A 200 and green tests do not prove columns, labels or buttons render.
