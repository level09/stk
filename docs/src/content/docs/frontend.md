---
title: "Frontend"
description: "Vue 3 and Vuetify with no build step: page shape, conventions, and the components stk uses"
---

Pages are Jinja templates that mount a Vue 3 app (Options API) with Vuetify. Vue, Vuetify, Axios, and Tabler Icons are vendored into `stk/static/`, so there is no npm, bundler, or build step. Versions are pinned in `stk/static/VERSIONS.txt`; to bump one, edit `vendor.sh`, run `./vendor.sh`, then `uv run stk smoke`.

The fastest way to see the whole pattern is `uv run stk new <module>`: the generated `<module>/templates/<module>/index.html` in your app is a working CRUD page that follows every rule below.

## Page shape

```html
{% extends "layout.html" %}
{% block css %}{% endblock %}        <!-- optional extra CSS -->
{% block content %}
  <!-- Vuetify components -->
{% endblock %}
{% block js %}
<script type="application/json" id="roles-data">{{ roles|tojson|safe }}</script>
<script>
const {createApp, toRaw} = Vue;
const {createVuetify} = Vuetify;
const vuetify = createVuetify(config.vuetifyConfig);  // stk/static/js/config.js

window.app = createApp({
  mixins: [layoutMixin],          // drawer, nav, WebSocket
  delimiters: config.delimiters,  // ['${', '}'], so Jinja keeps {{ }}
  data() {
    return {
      roles: JSON.parse(document.querySelector('#roles-data').textContent),
    };
  },
  methods: {},
});

registerStkComponents(app);       // stk/static/js/components/index.js
app.use(vuetify).mount("#app");
</script>
{% endblock %}
```

The layout shell (app bar, navigation drawer, `v-main`) lives in `layout.html`. Page templates fill `{% block content %}` and never redefine it.

## Rules that fail silently

- **Delimiters are `${expr}`**, never `{{expr}}`, which Jinja renders first. The delimiter ends at the first `}`, so an object literal inside it (`${ (x || {}).y }`) breaks the render function and the page stays blank. Move it into a method; `stk verify` fails on `{` inside `${ }`.
- **Reference static JS and CSS with `url_for('static', filename=...)`.** It adds a content hash (`?v=...`) that the app and the shipped proxies cache forever. A literal `/static/...` path revalidates on every load, which is correct but slower. ES modules can import each other by plain path (`import "./chart.js"`): the layout's import map, `{{ import_map() }}`, maps every `.js` and `.mjs` file in the app's, extensions' and stk's static folders to its versioned URL, so nested imports are fresh after a deploy too. A layout that does not extend `stk/layout.html` calls `{{ import_map() }}` in its `<head>`, before any module script.
- **User text rendered by Jinja inside `#app` runs as code.** Vue compiles the rendered page, and Jinja's escaping leaves `${ }` intact, so a user named `${...}` executes script. Pass user text as data and show it with `${ }`, or put `v-pre` on the element that renders it.
- **Server data goes in `{% block js %}`.** Vue strips `<script>` tags inside the `#app` mount element, so the same JSON tag in `{% block content %}` reads back as null and the page crashes. A 200 response does not catch this; `stk smoke` does.
- **Template expressions cannot see page globals.** A `const labels = {...}` in the page script is undefined inside `${...}` and directives. Expose shared helpers with `app.config.globalProperties.labels = labels` before mount. The production Vue build fails such lookups silently (the cell renders nothing, columns shift), so look at the rendered table.
- **Vuetify 4 type classes are MD3.** The old MD2 classes apply no styling and log nothing:

  | Do not use (v3) | Use (v4) |
  |---|---|
  | `text-h2` | `text-display-large` |
  | `text-h4` | `text-headline-large` |
  | `text-h5` | `text-headline-small` |
  | `text-h6` | `text-title-large` |
  | `text-subtitle-1` | `text-title-medium` |
  | `text-subtitle-2` | `text-title-small` |
  | `text-body-1` | `text-body-large` |
  | `text-body-2` | `text-body-medium` |
  | `text-caption` | `text-body-small` |
  | `text-overline` | `text-label-small` |

  The font overrides in `stk/static/css/app.css` select on the MD3 names, so a stray MD2 class also loses the typeface.
- **No `<tbody>`/`<tr>` inside `<v-table>`** or another custom element. The browser parser moves the rows out before Vue mounts. Use `v-data-table`, a native `<table>`, or flex rows.
- **Never ship the Vue development build.** Vue 3.5's production build loops forever on state mutated inside a computed, where the dev build only warns. That is why `filterNavByRole` in `stk/static/js/components/index.js` must stay pure.

## Talking to the server

Mutations wrap the payload in `{item: {...}}`; the view reads `json_data.get("item", {})`. Axios already sends the CSRF token from the layout.

```javascript
axios.post('/api/thing/', {item: this.eitem})                  // create
axios.post(`/api/thing/${this.eitem.id}`, {item: this.eitem})  // update (POST, not PUT)
axios.delete(`/api/thing/${item.id}`)                          // delete
axios.get(`/api/things?page=${this.options.page}&per_page=${this.options.itemsPerPage}`)
```

Logout is POST-only: call `logout()` from `layoutMixin`. See [JSON APIs](/api) for the server side.

## Navigation

The sidebar is data. stk's layout renders its own entries (Dashboard, the account pages, user administration) with the app's pages under Dashboard. An extension adds its page in `init_app`:

```python
def init_app(app):
    app.register_blueprint(bp_report)
    app.navigation.append(
        {
            "title": "Reports",
            "icon": "ti ti-chart-bar",
            "to": "/reports/",
            "role": "admin",
        }
    )
```

Entries appear in extension order. A group takes `children` instead of `to`, a section title is `{"heading": "..."}`. `role` is a single string, not an array. Optional link fields: `target`, `badge`, `badgeClass`. Hiding an entry is cosmetic; the view itself must check the role. To replace the whole sidebar, override `layout.html`, extend `stk/layout.html`, and fill `{% block navigation %}` with your own `stkNavigation` array. To show only the app's entries, without stk's Dashboard, Account and Administration sections, use `app_navigation()`, which returns `app.navigation`:

```html
{% block navigation %}
<script>const stkNavigation = {{ app_navigation() | tojson }};</script>
{% endblock %}
```

## Overriding templates and static files

Templates and static files resolve app first, then each extension's, then stk's, so a file at the same path in `myapp/templates/` or `myapp/static/` replaces stk's. The original stays reachable as `stk/<name>`:

```html
{# myapp/templates/layout.html #}
{% extends "stk/layout.html" %}
{% block title %}{{ config.APP_NAME }}{% endblock %}
```

`layout.html` has the blocks `title`, `css`, `head_js`, `body_class`, `content`, `navigation`, and `js`. Override a block rather than copying the layout: a copy stops receiving stk's fixes. `url_for('static', ...)` versions the file that will actually be served.

## layoutMixin

Defined in `stk/templates/layout.html`. Every page gets:

- **data:** `drawer`, `isNavCollapsed`, `isMobile`, `navItems`, `wsConnected`
- **computed:** `filteredNavItems` (nav filtered by the user's roles)
- **methods:** `logout()`, `toggleNavCollapse()` (persisted in localStorage)
- **mounted:** restores nav state and, for signed-in users, connects the `/ws` WebSocket with backoff. Messages of `{type: 'notification'}` go to the bell; override `_onWsMessage(msg)` for your own types. See [Background Work](/background-work).

## Icons

Tabler Icons (`ti ti-*`), self-hosted. Never Material Design Icons.

```html
<i class="ti ti-pencil" style="font-size: 20px;"></i>
<v-btn icon="ti ti-x" variant="text" size="small"></v-btn>
<v-icon class="mr-2">ti ti-pencil</v-icon>
```

Vuetify's internal icons map to Tabler through `config.vuetifyConfig.icons.aliases`.

## Components

Global defaults from `config.vuetifyConfig.defaults`, so pages rarely repeat them:

| Component | Defaults |
|---|---|
| `VTextField`, `VSelect`, `VTextarea`, `VCombobox` | `variant="outlined"` |
| `VBtn` | `variant="elevated"`, `size="small"`, `rounded="0"` |
| `VCard` | `elevation="0"`, `rounded="0"` |
| `VChip` | `size="small"`, `rounded="sm"` |
| `VDialog` | `rounded="0"` |
| `VMenu` | `offset="10"` |
| `VToolbar` | `elevation="0"` |
| `VDataTableServer` | `items-per-page="25"`, options `[25, 50, 100]` |

### Server-paginated table

```html
<v-data-table-server
  :items="items" :items-length="itemsLength" :headers="headers"
  :page="options.page" :items-per-page="options.itemsPerPage"
  @update:options="refresh" hover
>
  <template v-slot:top>
    <v-toolbar color="transparent">
      <v-btn class="ml-auto" color="primary" @click="createItem">
        <template v-slot:prepend><i class="ti ti-plus"></i></template>
        Add
      </v-btn>
    </v-toolbar>
  </template>
  <template v-slot:item.actions="{ item }">
    <v-icon class="mr-2" @click="editItem(item)">ti ti-pencil</v-icon>
    <v-icon @click="deleteItem(item)">ti ti-trash</v-icon>
  </template>
</v-data-table-server>
```

```javascript
headers: [
  {title: 'ID', value: 'id'},
  {title: 'Name', value: 'name'},
  {title: 'Actions', value: 'actions', sortable: false},
],

refresh(options) {
  if (options) {
    this.options = {...this.options, page: options.page, itemsPerPage: options.itemsPerPage};
  }
  axios.get(`/api/things?page=${this.options.page}&per_page=${this.options.itemsPerPage}`)
    .then(res => { this.items = res.data.items; this.itemsLength = res.data.total; })
    .catch(() => this.showSnack('Failed to load'));
},
```

### Edit dialog

Put `v-if` on the inner card so the form remounts each time it opens, and copy the row with `toRaw(item)` before editing.

```html
<v-dialog v-model="edialog" width="660">
  <v-card v-if="edialog">
    <v-toolbar>
      <v-toolbar-title>Editor</v-toolbar-title>
      <template v-slot:append>
        <v-btn @click="edialog=false" icon="ti ti-x" variant="text"></v-btn>
      </template>
    </v-toolbar>
    <v-card-text>
      <v-text-field label="Name" v-model="eitem.name"></v-text-field>
      <v-select label="Roles" :items="roles" item-title="name" v-model="eitem.roles"
                multiple chips clearable return-object></v-select>
      <v-switch color="primary" label="Active" v-model="eitem.active"></v-switch>
    </v-card-text>
    <v-card-actions>
      <v-spacer></v-spacer>
      <v-btn @click="edialog=false" variant="text">Cancel</v-btn>
      <v-btn color="primary" @click="saveItem">Save</v-btn>
    </v-card-actions>
  </v-card>
</v-dialog>
```

### Snackbar

```html
<v-snackbar v-model="snackBar" rounded="pill" elevation="25">
  ${snackMessage}
  <template v-slot:actions>
    <v-btn @click="snackBar=false" icon="ti ti-x" size="small" variant="text"></v-btn>
  </template>
</v-snackbar>
```

### stk components

Registered by `registerStkComponents(app)`:

| Tag | Purpose |
|---|---|
| `<vertical-nav-link>`, `<vertical-nav-group>`, `<vertical-nav-section-title>` | Sidebar entries |
| `<transition-expand>` | Animated height for nav groups |
| `<notification-dropdown>` | The signed-in user's bell: unread badge, list, mark read. Loads `/api/notifications` itself and takes live ones from the socket |
| `<theme-switcher>` | Light/dark toggle, persisted in localStorage |

Create notifications on the server with `notify()`; see [Background Work](/background-work#notifications).
