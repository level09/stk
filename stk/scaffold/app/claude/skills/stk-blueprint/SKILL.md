---
name: stk-blueprint
description: |
  Scaffold a new extension in an stk app: blueprint, model, page, sidebar entry, and Alembic migration. Use when creating a new feature module, adding a new section to the app, or scaffolding a blueprint.
argument-hint: "[blueprint-name]"
---

# Scaffold stk Blueprint

Create a complete extension for `$ARGUMENTS` in the app package (run from the app's directory).

## Workflow

The scaffolder generates the full module structure. Run it first, then customize domain fields and logic.

```bash
uv run stk new <name>
```

`<name>` must be lowercase snake_case (e.g. `blog_post`, `invoice_line`). Reserved names (`user`, `role`, `portal`, `public`, `session`, `admin`, etc.) are rejected with a clear error.

The command generates, inside the app package (`myapp/`):
- `<name>/__init__.py` with `init_app(app)`: registers the blueprint and appends the sidebar entry to `app.navigation`
- `<name>/models.py`, `<name>/views.py`, `<name>/templates/<name>/index.html`
- Adds `<name>` to `extensions` in the app module (import + list entry)
- Generates AND applies the migration in the app's lineage, then prints the page URL

It never edits a stk file. Then:
1. Customize `<name>/models.py` -- add/rename fields to fit your domain; point at core tables by foreign key (`ForeignKey("user.id")`)
2. If you changed the model after scaffolding: `uv run stk db revision -m "update <name>"` and review, then `uv run stk db upgrade`
   (only needed for post-scaffold model edits; the initial migration is already applied. With `--no-migrate`, the first revision is manual)
3. Verify: `uv run stk verify && uv run stk smoke`

## Conventions

The generated files already follow every stk convention. When you change them, the rules
are in `CLAUDE.md` and the details in https://docs.stk.dev/models/, https://docs.stk.dev/api/, and
https://docs.stk.dev/frontend/. Read the page before editing that layer.

## Before you report done

Each line is a mistake an agent made while building a real app on stk.

- Lint and format only the files you changed (`uv run ruff format path/a.py path/b.py`), never a whole package another person owns.
- Tests: give test-only blueprints names an app cannot already use.
- Migrations: check each command's exit code, never behind a pipe to `tail`. Never delete a revision file before `stk db downgrade <target>` has succeeded.
- Tables inside Vue's in-DOM templates: never put `<tbody>`/`<tr>` inside `<v-table>` or another custom element; the browser parser moves the rows out before Vue mounts and they never render. Use `v-data-table`, a native `<table>`, or flex rows.
- Verify UI in a browser: `uv run stk smoke`, then look at a screenshot of the page with real rows. A 200 and green tests do not prove columns, labels or buttons render.
