# Minimal

Built on [stk](https://github.com/level09/stk) 17.0.0. The app composes stk
from `minimal/app.py` and never edits stk's files.

```bash
uv run stk db upgrade     # stk's migrations, then the app's
uv run stk install        # admin user
uv run stk run            # http://localhost:5000
uv run stk new <module>   # an extension: blueprint, model, page, migration
uv run stk verify && uv run stk smoke
```

Upgrade stk by bumping the tag in `[tool.uv.sources]` and the range in
`dependencies`, then `uv sync`, `uv run stk db upgrade`, `uv run stk verify`,
`uv run stk smoke`, and read the release note.
