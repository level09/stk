# stk Frontend Reference

Canonical lookup for Vuetify/Vue component surface actually used in this codebase.
Every prop and pattern below is sourced from stk/templates/ or stk/static/js/ — not from memory.

## Pinned Versions

- **Vue**: 3.3.4 (`stk/static/js/vue.min.js`)
- **Vuetify**: 3.7.8 (`stk/static/js/vuetify.min.js`)
- **Axios**: shipped as `stk/static/js/axios.min.js`
- **Tabler Icons**: loaded via CDN `@tabler/icons-webfont@latest`

## Boilerplate: App Init

Every page script follows this exact shape:

```html
{% block js %}
<script>
const {createApp, toRaw} = Vue;
const {createVuetify} = Vuetify;
const vuetify = createVuetify(config.vuetifyConfig);  // config in static/js/config.js

window.app = createApp({
  mixins: [layoutMixin],          // defined in layout.html <script>
  delimiters: config.delimiters,  // ['${', '}'] — avoids Jinja {{ conflict
  data() { return { ... }; },
  methods: { ... }
});

registerStkComponents(app);       // static/js/components/index.js
app.use(vuetify).mount("#app");
</script>
{% endblock %}
```

## Delimiters

Vue delimiter config: `['${', '}']`. In templates use `${expr}`, never `{{expr}}`.

```html
${item.name}
${JSON.stringify(currentData, null, 2)}
```

## Server Data via script tag

Pass Jinja data to Vue without XSS risk:

```html
<!-- In template body -->
<script type="application/json" id="roles-data">
{{ roles|tojson|safe }}
</script>

<!-- In Vue data() -->
roles: JSON.parse(document.querySelector('#roles-data').textContent)
```

## Axios Mutation Convention

Frontend always wraps mutation payloads in `{item: {...}}`. Backend extracts with `json_data.get("item", {})`.

```javascript
// create
axios.post('/api/thing/', {item: this.eitem})
// update
axios.post(`/api/thing/${this.eitem.id}`, {item: this.eitem})
// delete
axios.delete(`/api/thing/${item.id}`)
// list (GET with query params)
axios.get(`/api/things?page=${this.options.page}&per_page=${this.options.itemsPerPage}`)
```

## layoutMixin Contract

Defined inline in `stk/templates/layout.html`. Provides:

**data:**
- `drawer: true` — nav drawer open state
- `isNavCollapsed: false` — rail mode toggle
- `isMobile: window.innerWidth < 960`
- `navItems: stkNavigation` — from `static/js/navigation.js`
- `notifications: []` — array of notification objects
- `wsConnected: false` — WebSocket connection state
- `_ws: null`, `_wsRetry: 1000` — internal WS state

**computed:**
- `filteredNavItems` — navItems filtered by `userRoles` (server-injected const)

**methods:**
- `resolveNavComponent(item)` — returns component name for nav item
- `toggleNavCollapse()` — persists to localStorage key `stk-nav-collapsed`
- `handleResize()` — updates isMobile on window resize
- `handleNotificationClick(notification)` — follows `notification.to` if set
- `markNotificationRead(id)` — sets `notification.isSeen = true`
- `markAllNotificationsRead()` — sets all isSeen true
- `removeNotification(id)` — splices from notifications array
- `_connectWs()` — connects to `/ws`, exponential backoff on close
- `_onWsMessage(msg)` — handles `{type: 'notification'}` messages via `unshift`

**mounted:** restores nav state, adds resize listener, connects WS (authenticated only).

## Icons

Always Tabler Icons. Never MDI. Two usage forms:

```html
<!-- Inline HTML (preferred for sized icons) -->
<i class="ti ti-pencil" style="font-size: 20px;"></i>

<!-- Vuetify icon prop (on v-btn, v-icon) -->
<v-btn icon="ti ti-x" variant="text" size="small"></v-btn>
<v-icon small class="mr-2">ti ti-pencil</v-icon>
```

Vuetify aliases map to Tabler names via `config.vuetifyConfig.icons.aliases` (e.g. `close` -> `x`, `delete` -> `x`). The defaultSet is `tabler`.

## Vuetify Component Reference

### Global Defaults (from config.vuetifyConfig.defaults)

| Component | Default props |
|---|---|
| VTextField | `variant="outlined"` |
| VSelect | `variant="outlined"` |
| VTextarea | `variant="outlined"` |
| VCombobox | `variant="outlined"` |
| VChip | `size="small"`, `rounded="sm"` |
| VCard | `elevation="0"`, `rounded="0"` |
| VMenu | `offset="10"` |
| VBtn | `variant="elevated"`, `size="small"`, `rounded="0"` |
| VDialog | `rounded="0"` |
| VToolbar | `elevation="0"` |
| VDataTableServer | `items-per-page="25"`, `items-per-page-options="[25, 50, 100]"` |

---

### v-data-table-server

Server-paginated table. Fires `@update:options` when page/sort changes — pass handler as `refresh`.

```html
<v-data-table-server
  :items="items"
  :items-length="itemsLength"
  :headers="headers"
  :page="options.page"
  :items-per-page="options.itemsPerPage"
  @update:options="refresh"
  hover
>
  <!-- Toolbar slot for action buttons -->
  <template v-slot:top>
    <v-toolbar dense elevation="0" color="transparent" class="mb-4">
      <v-btn class="ml-auto" @click="createItem" size="small" color="primary" variant="elevated">
        <template v-slot:prepend><i class="ti ti-plus"></i></template>
        Add Item
      </v-btn>
    </v-toolbar>
  </template>

  <!-- Custom cell -->
  <template v-slot:item.roles="{ item }">
    <v-chip v-for="role in item.roles" :key="role.id" color="primary" class="mr-2">
      ${role.name}
    </v-chip>
  </template>

  <!-- Actions cell -->
  <template v-slot:item.actions="{ item }">
    <v-icon small class="mr-2" @click="editItem(item)">ti ti-pencil</v-icon>
    <v-icon small @click="deleteItem(item)">ti ti-trash</v-icon>
  </template>
</v-data-table-server>
```

Headers shape:
```javascript
headers: [
  {title: 'ID', value: 'id'},
  {title: 'Name', value: 'name'},
  {title: 'Roles', value: 'roles', sortable: false},
  {title: 'Actions', value: 'actions', sortable: false}
]
```

Refresh handler (from `@update:options`):
```javascript
refresh(options) {
  if (options) {
    this.options = {...this.options, page: options.page, itemsPerPage: options.itemsPerPage};
  }
  axios.get(`/api/things?page=${this.options.page}&per_page=${this.options.itemsPerPage}`)
    .then(res => {
      this.items = res.data.items;
      this.itemsLength = res.data.total;
      if (res.data.perPage) this.options.itemsPerPage = res.data.perPage;
    })
    .catch(err => this.showSnack('Failed to load'));
}
```

Props used: `:items`, `:items-length`, `:headers`, `:page`, `:items-per-page`, `hover`
Events used: `@update:options`, `@click:row`
Slots used: `v-slot:top`, `v-slot:item.{field}`, `v-slot:item.actions`

---

### v-dialog

Toggle with `v-model`. Always add `v-if="dialogBool"` on inner `v-card` to force re-mount.

```html
<v-dialog v-model="edialog" width="660">
  <v-card v-if="edialog">
    <v-toolbar>
      <v-toolbar-title>Editor</v-toolbar-title>
      <template v-slot:append>
        <v-btn @click="edialog=false" size="small" icon="ti ti-x" variant="text"></v-btn>
      </template>
    </v-toolbar>
    <v-card-text>
      <v-text-field label="Name" v-model="eitem.name"></v-text-field>
      <v-textarea label="Description" v-model="eitem.description" rows="3"></v-textarea>
      <v-select label="Roles" :items="roles" item-title="name" v-model="eitem.roles"
                multiple chips clearable return-object></v-select>
      <v-switch color="primary" label="Active" v-model="eitem.active"></v-switch>
    </v-card-text>
    <v-card-actions>
      <v-spacer></v-spacer>
      <v-btn @click="edialog=false" variant="text">Cancel</v-btn>
      <v-btn color="primary" @click="saveItem" variant="elevated">Save</v-btn>
    </v-card-actions>
  </v-card>
</v-dialog>
```

Props used: `v-model`, `width`

---

### v-snackbar

```html
<v-snackbar size="small" class="d-flex" v-model="snackBar" rounded="pill" elevation="25">
  ${snackMessage}
  <template v-slot:actions>
    <v-btn @click="snackBar=false" icon="ti ti-x" class="ml-auto" size="small" variant="text"></v-btn>
  </template>
</v-snackbar>
```

Helper method (every page):
```javascript
showSnack(message) {
  this.snackMessage = message;
  this.snackBar = true;
}
```

Props used: `v-model`, `size`, `rounded`, `elevation`
Slots used: `v-slot:actions`

---

### v-btn

```html
<!-- icon button -->
<v-btn icon="ti ti-x" size="small" variant="text" @click="..."></v-btn>

<!-- text button with prepend icon -->
<v-btn variant="text" href="/change">
  <template v-slot:prepend><i class="ti ti-key"></i></template>
  Change Password
</v-btn>

<!-- action button -->
<v-btn color="primary" variant="elevated" size="small" @click="saveItem">Save</v-btn>
```

Props used: `icon`, `size`, `variant`, `color`, `href`, `v-bind="props"` (from menu activator)
Slots used: `v-slot:prepend`, `v-slot:append`

---

### v-text-field / v-textarea / v-select

Default variant is `outlined` (set globally). No need to specify unless overriding.

```html
<v-text-field label="Name" v-model="eitem.name"></v-text-field>
<v-text-field type="email" v-model="eitem.email" label="Email" required></v-text-field>
<v-text-field type="password" v-model="eitem.password"
  :rules="[v => !!v && v.length >= 12 || 'Min 12 characters']"></v-text-field>
<v-text-field label="Search" v-model="q" hide-details single-line>
  <template v-slot:prepend-inner><i class="ti ti-search mr-2"></i></template>
</v-text-field>
<v-textarea label="Description" v-model="eitem.description" rows="3"></v-textarea>
<v-select label="Roles" :items="roles" item-title="name" v-model="eitem.roles"
          multiple chips clearable return-object></v-select>
```

v-select props: `:items`, `item-title`, `v-model`, `multiple`, `chips`, `clearable`, `return-object`

---

### v-switch

```html
<v-switch color="primary" label="Active" v-model="eitem.active"></v-switch>
```

---

### v-card

Flat by default (elevation 0, rounded 0 from global defaults).

```html
<v-card class="ma-2 mt-12 w-100 h-100">
  <v-toolbar>
    <v-toolbar-title>Title</v-toolbar-title>
    <v-spacer></v-spacer>
  </v-toolbar>
  <v-card-text>...</v-card-text>
  <v-card-actions>
    <v-spacer></v-spacer>
    <v-btn color="primary" variant="elevated">Save</v-btn>
  </v-card-actions>
</v-card>
```

---

### v-menu (user menu pattern)

```html
<v-menu :close-on-content-click="false" location="bottom end" transition="fade-transition">
  <template v-slot:activator="{ props }">
    <v-btn v-bind="props" icon variant="text" size="small">
      <v-avatar color="primary" size="32">...</v-avatar>
    </v-btn>
  </template>
  <v-card min-width="280">...</v-card>
</v-menu>
```

Props used: `:close-on-content-click`, `location`, `transition`, `offset`
Slots used: `v-slot:activator="{ props }"` — bind `props` to activator via `v-bind="props"`

---

### v-list / v-list-item

```html
<v-list density="compact">
  <v-list-item href="/dashboard" title="..." subtitle="...">
    <template v-slot:prepend><i class="ti ti-layout-dashboard mr-3" style="font-size: 18px;"></i></template>
    <v-list-item-title>My Account</v-list-item-title>
    <v-list-item-subtitle>Subtitle text</v-list-item-subtitle>
  </v-list-item>
</v-list>
```

Props: `density` (`compact`, default), `href`, `title`, `subtitle`, `base-color`
Slots: `v-slot:prepend`, `v-slot:append`

---

### v-tooltip

```html
<v-tooltip :text="wsConnected ? 'Connected' : 'Reconnecting...'" location="bottom">
  <template v-slot:activator="{ props }">
    <div v-bind="props">...</div>
  </template>
</v-tooltip>
```

Props: `:text`, `location`

---

### v-app-bar / v-navigation-drawer / v-main (layout shell)

Defined in `layout.html`. Do not redefine in page templates — use `{% block content %}` only.

```html
<v-app id="app" v-cloak>
  <v-layout class="rounded rounded-md">
    <v-app-bar color="surface" density="comfortable" elevation="1">...</v-app-bar>
    <v-navigation-drawer v-model="drawer" :rail="isNavCollapsed" :rail-width="68" width="260">
      ...
    </v-navigation-drawer>
    <v-main class="d-flex align-center justify-center" style="min-height: 300px;">
      {% block content %}{% endblock %}
    </v-main>
  </v-layout>
</v-app>
```

---

### v-avatar / v-chip / v-badge / v-alert / v-divider / v-otp-input

```html
<v-avatar color="primary" size="32"><span>AB</span></v-avatar>
<v-avatar size="16" color="green"></v-avatar>  <!-- status dot -->

<v-chip color="primary" class="mr-2">${role.name}</v-chip>

<!-- v-badge (used in NotificationDropdown) -->
<v-badge :model-value="unreadCount > 0" :content="unreadCount" color="error" offset-x="-2" offset-y="-2">
  <i class="ti ti-bell"></i>
</v-badge>
<v-badge dot color="primary" inline></v-badge>

<v-alert>...</v-alert>  <!-- used in auth templates -->
<v-divider></v-divider>
<v-otp-input></v-otp-input>  <!-- used in 2FA templates -->
```

---

## Custom stk Components

Registered via `registerStkComponents(app)` (`static/js/components/index.js`):

| Tag | File | Purpose |
|---|---|---|
| `<transition-expand>` | TransitionExpand.js | Animated height expand for nav groups |
| `<vertical-nav-link>` | VerticalNavLink.js | Single nav link (`item.to`, `item.title`, `item.icon`) |
| `<vertical-nav-group>` | VerticalNavGroup.js | Collapsible group with `item.children` |
| `<vertical-nav-section-title>` | VerticalNavSectionTitle.js | Section heading (`item.heading`) |
| `<notification-dropdown>` | NotificationDropdown.js | Bell icon with notification list |
| `<theme-switcher>` | ThemeSwitcher.js | Light/dark toggle, persists to localStorage |

### notification-dropdown props/events

```html
<notification-dropdown
  :notifications="notifications"
  @click="handleNotificationClick"
  @mark-read="markNotificationRead"
  @mark-all-read="markAllNotificationsRead"
  @remove="removeNotification"
></notification-dropdown>
```

Notification object shape: `{id, title, subtitle, time, icon, img, color, isSeen, to}`

---

## Navigation Entry Shape (`static/js/navigation.js`)

```javascript
const stkNavigation = [
  { heading: 'Section Title' },                          // section divider
  { title: 'Dashboard', icon: 'ti ti-home', to: '/dashboard' },  // link (all users)
  { title: 'Admin Page', icon: 'ti ti-history', to: '/activities', role: 'admin' },  // role-gated
  {
    title: 'Group', icon: 'ti ti-users-group', role: 'admin',  // collapsible group
    children: [
      { title: 'Users', icon: 'ti ti-users', to: '/users' },
      { title: 'Roles', icon: 'ti ti-shield', to: '/roles' },
    ]
  }
];
```

`role` is a single string (not array). `filterNavByRole(navItems, userRoles)` filters by role.
`resolveNavComponent(item)` picks the right component based on `heading`/`children` presence.

Optional link fields: `target`, `badge`, `badgeClass`.

---

## Template Block Structure

```html
{% extends "layout.html" %}
{% block css %}{% endblock %}      <!-- optional extra CSS -->
{% block content %}               <!-- Vuetify components here -->
{% endblock %}
{% block js %}                    <!-- Vue app script here -->
{% endblock %}
```

`{% block sidebar %}{% endblock %}` and `{% block layout_classes %} align-center {% endblock %}`
are used in full-width pages (e.g. CMS) to suppress the sidebar.
