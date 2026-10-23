---
title: "Frontend"
description: "Vue 3 and Vuetify with no build step"
---

Pages are Vue 3 (Options API) plus Vuetify, loaded from static files with no build step. Each page script uses `mixins: [layoutMixin]` for the drawer, navigation, WebSocket, and notifications, sets `delimiters: config.delimiters` so Vue uses `${}` instead of Jinja's `{{}}`, and calls `registerStkComponents(app)` before mounting. Icons are Tabler (`ti ti-pencil`), not Material Design Icons. Sidebar entries live in `stk/static/js/navigation.js`; add `role: 'admin'` to restrict one.

Pass server data with `<script type="application/json" id="...">{{ data|tojson|safe }}</script>` inside `{% block js %}`. Vue strips `<script>` tags inside the `#app` mount element, so the same tag in `{% block content %}` comes back as null.

Vue template expressions cannot see page globals. Expose shared helpers with `app.config.globalProperties.labels = labels` before mount. The production Vue build fails such lookups silently, so check the rendered page rather than relying on `stk smoke`.

Pinned versions and the full component reference live in `.stk/context/frontend.md`.
