# Architecture

STK is an async Quart framework for owned SaaS applications. The core runtime is Quart, async SQLAlchemy, Alembic migrations, quart-security auth, native WebSockets, and Vue 3 plus Vuetify without a JavaScript build step.

Agents should treat the running app and CLI inspection output as canonical. Prefer `quart inspect routes --json` over guessing routes from files.

Important boundaries:
- Request DB sessions live on `g.db_session`.
- CLI DB sessions use `stk.extensions.async_session_factory`.
- Models inherit from `stk.extensions.Base`.
- Blueprint routes are async.
- Frontend code uses Vue Options API with `${}` delimiters.
