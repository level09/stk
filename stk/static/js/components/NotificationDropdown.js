/**
 * NotificationDropdown Component
 * The signed-in user's notification bell: loads from /api/notifications, takes
 * live ones through receive(), and marks them read on the server.
 */

const NotificationDropdown = {
  name: 'NotificationDropdown',

  template: `
    <v-menu offset="14" :close-on-content-click="false" max-width="380" transition="fade-transition">
      <template v-slot:activator="{ props }">
        <v-btn v-bind="props" icon variant="text" size="small" title="Notifications">
          <v-badge
            :model-value="unread > 0"
            :content="unread"
            color="error"
            offset-x="-2"
            offset-y="-2"
          >
            <i class="ti ti-bell" style="font-size: 22px;"></i>
          </v-badge>
        </v-btn>
      </template>

      <v-card width="380">
        <v-card-title class="d-flex align-center py-3 px-4">
          <span class="text-body-large font-weight-medium">Notifications</span>
          <v-chip v-if="unread > 0" size="x-small" color="primary" class="ml-2">
            {{ unread }} New
          </v-chip>
          <v-spacer></v-spacer>
          <v-btn
            v-if="unread > 0"
            icon
            variant="text"
            size="x-small"
            @click="markAllRead"
            title="Mark all as read"
          >
            <i class="ti ti-mail-opened" style="font-size: 18px;"></i>
          </v-btn>
        </v-card-title>

        <v-divider></v-divider>

        <v-list class="notification-list py-0">
          <template v-for="(n, index) in items" :key="n.id">
            <v-list-item class="notification-item py-3" @click="open(n)">
              <v-list-item-title class="text-body-medium mb-1" :class="{ 'font-weight-bold': !n.read_at }">
                {{ n.title }}
              </v-list-item-title>
              <v-list-item-subtitle v-if="n.body" class="text-body-small">
                {{ n.body }}
              </v-list-item-subtitle>
              <v-list-item-subtitle class="text-body-small mt-1" style="opacity: 0.6;">
                {{ new Date(n.created_at).toLocaleString() }}
              </v-list-item-subtitle>
              <template v-slot:append>
                <v-badge v-if="!n.read_at" dot color="primary" inline></v-badge>
              </template>
            </v-list-item>
            <v-divider v-if="index < items.length - 1"></v-divider>
          </template>

          <v-list-item v-if="!items.length" class="text-center py-8">
            <div class="d-flex flex-column align-center">
              <i class="ti ti-bell-off mb-2" style="font-size: 48px; opacity: 0.3;"></i>
              <v-list-item-title class="text-body-medium text-medium-emphasis">
                No notifications
              </v-list-item-title>
            </div>
          </v-list-item>
        </v-list>

        <template v-if="items.length < total">
          <v-divider></v-divider>
          <v-card-actions class="pa-3">
            <v-btn block variant="text" color="primary" @click="load(page + 1)">Load more</v-btn>
          </v-card-actions>
        </template>
      </v-card>
    </v-menu>
  `,

  data() {
    return { items: [], total: 0, unread: 0, page: 1 };
  },

  mounted() {
    this.load(1);
  },

  methods: {
    async load(page) {
      const [list, unread] = await Promise.all([
        axios.get('/api/notifications', { params: { page } }),
        axios.get('/api/notifications/unread'),
      ]);
      const seen = new Set(this.items.map(n => n.id));
      this.items = page === 1 ? list.data.items : [...this.items, ...list.data.items.filter(n => !seen.has(n.id))];
      this.total = list.data.total;
      this.unread = unread.data.count;
      this.page = page;
    },

    receive(n) {
      this.items.unshift(n);
      this.total += 1;
      this.unread += 1;
    },

    async open(n) {
      if (!n.read_at) {
        await axios.post(`/api/notifications/${n.id}/read`, {});
        n.read_at = new Date().toISOString();
        this.unread -= 1;
      }
      if (n.link) window.location.href = n.link;
    },

    async markAllRead() {
      await axios.post('/api/notifications/read', {});
      const now = new Date().toISOString();
      this.items.forEach(n => { n.read_at = n.read_at || now; });
      this.unread = 0;
    }
  }
};
