---
name: stk-migrate
description: |
  Generate and review an Alembic database migration for stk. Use when adding or changing models, creating migrations, or managing database schema changes.
argument-hint: "[description]"
---

# Generate Alembic Migration: $ARGUMENTS

## Current state

Current revision:
!`cd /Users/level09/projects/stk && uv run quart db current 2>&1 | tail -5`

Recent migrations:
!`ls -1 alembic/versions/*.py 2>/dev/null | grep -v __pycache__`

Models with tables:
!`grep -rn "__tablename__" stk/*/models.py 2>/dev/null`

## Steps

1. **Generate the migration:**
   ```bash
   uv run quart db revision -m "$ARGUMENTS"
   ```

2. **Review the generated file** in `alembic/versions/`. Check:
   - All expected table/column changes are present
   - Foreign keys reference correct tables
   - Indexes are created where needed
   - `downgrade()` correctly reverses `upgrade()`
   - No destructive changes that would lose data (if so, warn the user)

3. **For SQLite compatibility**, verify batch mode is used. The `env.py` enables `render_as_batch` automatically for SQLite, but if writing manual SQL, wrap ALTER TABLE operations in `with op.batch_alter_table()`.

4. **If the migration needs manual edits** (data migrations, complex constraints, multi-step operations):
   - Edit the generated file directly
   - Use `op.execute()` for raw SQL when needed
   - Add data migration steps between schema changes

5. **Test the migration:**
   ```bash
   uv run quart db upgrade    # apply
   uv run quart db downgrade -1  # rollback
   uv run quart db upgrade    # re-apply to confirm idempotency
   ```

6. **Run checks:**
   ```bash
   uv run python checks.py
   ```

## Common patterns

**Add a column:**
```python
op.add_column("users", sa.Column("bio", sa.Text(), nullable=True))
```

**Add an index:**
```python
op.create_index("ix_products_name", "products", ["name"])
```

**Data migration (backfill):**
```python
from alembic import op
from sqlalchemy import text

def upgrade():
    op.add_column("users", sa.Column("display_name", sa.String(255)))
    op.execute(text("UPDATE users SET display_name = name WHERE display_name IS NULL"))
```

**Rename with SQLite (batch mode):**
```python
with op.batch_alter_table("users") as batch_op:
    batch_op.alter_column("old_name", new_column_name="new_name")
```
