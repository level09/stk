# Plan: Steal Astro's wins for stk

Branch: `dev`. Goal: make stk fast-by-default (HTML-first, JS only where needed) and feel SPA-smooth, without adding a build step. Ordered cheapest-payoff first.

## Context (why)

Today every page (login, marketing index, dashboard) ships `vue.min.js` (474KB) + `vuetify.min.js` (459KB) ≈ **930KB blocking JS**, and the entire `layout.html` chrome is Vuetify hidden behind `[v-cloak]`. So first paint is blank until Vue mounts. That is the exact opposite of Astro's HTML-first / islands model. Each phase below moves stk toward "send HTML, hydrate only the interactive bits."

Scope rule (from CLAUDE.md): every changed line traces to one of these phases. No drive-by refactors.

---

## Phase 0 — Easy wins (no architecture change)

### 0.1 Drop the dead MDI webfont
`layout.html:13` and `login-layout.html` load `@mdi/font` from CDN, but icons are Tabler (`ti ti-*`). The MDI font is unused payload + a render-blocking CDN round-trip on every page.
- **Do:** remove the `materialdesignicons.min.css` `<link>` from `layout.html`, `login-layout.html`, `auth_layout.html` (any layout that has it). Also check `stk/static/mdi/` — if nothing references it, note it as removable (don't delete yet, confirm with a grep).
- **Verify:** `grep -rn "mdi-" stk/templates stk/static/js` returns nothing; icons still render; one fewer network request in devtools.

### 0.2 Cross-document View Transitions (the big perceived win)
Native browser API, ideal for a server-rendered MPA. Chrome 126+/Safari 18.2+ support it; Firefox ignores the rule and just snaps (graceful degradation), so it's safe today.
- **Do:** add to `app.css` (or a shared base CSS loaded on all layouts):
  ```css
  @view-transition { navigation: auto; }
  @media (prefers-reduced-motion: reduce) {
    @view-transition { navigation: none; }
  }
  ```
  Both source and destination pages need the rule, so put it in the global CSS, not per-page.
- **Optional polish:** name persistent elements (app bar logo, drawer) with `view-transition-name` so they morph instead of cross-fade. Defer until 0.1/0.2 land.
- **Verify:** navigate between two server-rendered pages in Chrome → cross-fade; in Firefox → instant snap, no errors. Confirm reduced-motion disables it.

### 0.3 Speculation Rules prefetch (instant nav)
Chrome-only today, pure progressive enhancement. Use **prefetch** (not prerender) to avoid prerender side effects (analytics double-counts, auth/session mutations, extra server load).
- **Do:** inject in base layout before `</body>`:
  ```html
  <script type="speculationrules">
  { "prefetch": [{ "where": { "href_matches": "/*" }, "eagerness": "moderate" }] }
  </script>
  ```
  `moderate` = prefetch on 200ms hover. Exclude mutating routes: add `"not": {"href_matches": "/logout"}` style rules for `/logout`, OAuth callbacks, anything GET-with-side-effects.
- **Verify:** hover a nav link in Chrome devtools → prefetch fires; `/logout` does NOT prefetch.

**Phase 0 exit:** ~1 fewer blocking request, SPA-feel navigation, instant clicks in Chrome. Zero architecture change. Commit per item.

---

## Phase 1 — Scope the 930KB (HTML-first for non-app pages)

Scout verdict: Vuetify 3 **cannot** be tree-shaken without a bundler — the UMD `vuetify.min.js` is all-or-nothing. So the only no-build win is **don't load it where it isn't needed.** Login, register, password reset, marketing index render a form or static content; they don't need 930KB.

### 1.1 Split the layouts by JS need
- `login-layout.html` / `auth_layout.html` / public marketing → plain semantic HTML + existing `app.css`/`layout.css`. **No Vue, no Vuetify.** Flash messages already render as plain HTML (`layout.html:155`), so this is mostly removing `<v-*>` wrappers and the core script block.
- `layout.html` (authenticated dashboard chrome) → keep Vue + Vuetify.
- **Main risk (from scout):** the navbar/login chrome now exists in two forms (plain HTML vs Vuetify) and can drift. **Mitigation:** single source of truth for nav links (`navigation.js` already exists / a Jinja macro); share `app.css` custom properties for colors/spacing so both look identical.
- **Verify:** `/login` first paint < 100ms, no `vue.min.js`/`vuetify.min.js` in network tab; dashboard unchanged.

### 1.2 Defer the heavy scripts on pages that keep them
- **Do:** add `defer` to the Vue/Vuetify `<script>` tags in `layout.html`. Safe (scout-confirmed). Doesn't fix the blank-paint alone but stops parser-blocking.
- **Verify:** scripts load deferred; no console errors from load order.

**Phase 1 exit:** the 80% of pages that are forms/content ship ~0 framework JS. Only the dashboard pays for Vuetify.

---

## Phase 2 — Islands (the real structural lever)

Goal: even on the dashboard, stop one giant app owning `<body>`. Server-render the chrome as HTML; mount small Vue apps onto declared interactive zones.

Scout verdict on *how*:
- **Recommended: multiple `createApp().mount('[data-island="x"]')` instances.** Officially supported by Vue 3, no new dependency, same Options API + Vuetify you already use. Share state across islands with a small `reactive()` object passed at init if needed.
- **Rejected: petite-vue** — unmaintained since Jan 2022, no Vue 3.2+ features, CSP issues. Do not use.
- **Watch: Alpine.js** — viable ~15KB option, but it can't render Vuetify components, so it'd mean reinventing UI chrome. Only revisit if multi-createApp hits a wall.

### 2.1 Island mounting harness
- **Do:** replace the single root `<v-app id="app">` mount with a small bootstrap that scans for `[data-island]` nodes and mounts the matching component app to each. Convert the always-present chrome (app bar shell, drawer container) to plain HTML/CSS; keep genuinely interactive widgets (NotificationDropdown, ThemeSwitcher, user menu, WebSocket status) as islands.
- The WebSocket/notification logic in `layoutMixin` (`layout.html:207`) moves into a small "shell" island rather than the whole-page mixin.
- **Verify:** dashboard renders chrome as HTML before JS; only interactive widgets hydrate; WebSocket connect + notifications still work; theme switch still works.

### 2.2 Migrate one real page as proof
- Pick the simplest dashboard/portal page, convert it to islands, measure JS executed + first paint vs current. Decide go/no-go for the rest from real numbers.

**Phase 2 exit:** stk is fast-by-default with opt-in interactivity — the Astro model, on Quart.

---

## Explicitly NOT doing
- **Dropping Vuetify entirely** — saves only 459KB; `vue.min.js` (474KB) dominates anyway; high migration cost, poor payoff.
- **Astro content collections** — maps to Pydantic + markdown, but only worth it if stk becomes a docs/content platform. Not a goal now.
- **Prerender (vs prefetch)** in speculation rules — side-effect risk not worth it yet.

## Sequencing
Phase 0 is independent and shippable now (1-2 commits each). Phase 1 depends on nothing but is a bigger diff. Phase 2 is the strategic bet — only start after 0+1 prove the direction and after a quick review checkpoint.

## Sources (dates accessed May 2026)
- View Transitions cross-doc support + `@view-transition`: [Chrome for Developers](https://developer.chrome.com/docs/web-platform/view-transitions/cross-document), [MDN](https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API), [CSS-Tricks gotchas](https://css-tricks.com/cross-document-view-transitions-part-1/) — Chrome 126+/Safari 18.2+, Firefox pending, degrades gracefully.
- Speculation Rules eagerness + syntax: [MDN](https://developer.mozilla.org/en-US/docs/Web/API/Speculation_Rules_API), [Chrome for Developers](https://developer.chrome.com/docs/web-platform/prerender-pages) — `moderate` = 200ms hover; prefetch safer than prerender.
- Islands without build / multi-createApp official support; petite-vue unmaintained since 2022: [vuejs.org guide], scout lane.
- Vuetify 3 no tree-shaking without bundler: [vuetifyjs.com], scout lane.
